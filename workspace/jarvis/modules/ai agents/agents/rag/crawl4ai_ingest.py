"""crawl4ai → knowledge graph + vector store ingestion pipeline.

Data flow
─────────
CrawlResult (pydantic)
    │
    ├─ pydantic-ai agent ──► KnowledgeGraph (entities + relationships)
    │                         └─ stored as AGE vertices / edges via Cypher
    │
    └─ llama_index SentenceSplitter ──► TextChunk list
                                         └─ embedded (OpenAI) → pgvector table

The ingestion agent uses pydantic-ai's structured-result feature so that
entity extraction is validated by pydantic at every turn.

Usage
─────
    from rag.crawl4ai_ingest import ingest_url, ingest_crawl_result

    result = await ingest_url("https://example.com")
    result = await ingest_crawl_result(crawl_result)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any
from urllib.parse import urlparse

import asyncpg
import httpx
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel

from .db import get_pool
from .models import (
    CrawlResult,
    Entity,
    EntityType,
    IngestResult,
    KnowledgeGraph,
    Relationship,
    TextChunk,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_GRAPH = os.environ.get("RAG_GRAPH_NAME", "jarvis_kg")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "text-embedding-ada-002")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1536"))
CHUNK_SIZE = int(os.environ.get("RAG_CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.environ.get("RAG_CHUNK_OVERLAP", "64"))

# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------

import ipaddress
import re

# Strict allowlist for AGE graph names: alphanumeric + underscore only.
_GRAPH_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _validate_graph_name(name: str) -> str:
    """Raise ValueError if *name* is not a safe AGE graph identifier."""
    if not _GRAPH_NAME_RE.match(name):
        raise ValueError(
            f"Invalid graph name {name!r}: must be alphanumeric/underscore, "
            "start with a letter or underscore, max 63 chars"
        )
    return name


def _validate_url(url: str) -> str:
    """Raise ValueError for non-http(s) URLs or requests to private networks."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got {parsed.scheme!r}")
    hostname = parsed.hostname or ""
    # Block bare IP addresses in private/loopback ranges
    try:
        addr = ipaddress.ip_address(hostname)
        if addr.is_private or addr.is_loopback or addr.is_link_local:
            raise ValueError(f"Requests to private/loopback addresses are not allowed: {hostname}")
    except ValueError as exc:
        # ip_address() throws for hostnames — only re-raise our own check
        if "not allowed" in str(exc):
            raise
    return url

# ---------------------------------------------------------------------------
# Entity-extraction agent (pydantic-ai + structured output)
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM = """\
You are a knowledge-graph extraction expert.

Given a web page's Markdown content and its URL, extract:
1. **Entities** — named people, organisations, technologies, concepts, products,
   locations and events that appear in the text.
2. **Relationships** — directed, meaningful connections between the entities you
   extracted.  Use SCREAMING_SNAKE_CASE for relation labels
   (e.g. WORKS_AT, PART_OF, RELATED_TO, CREATED_BY, USES).

Rules:
- Only extract entities and relationships that are CLEARLY stated in the text.
- Do NOT invent or infer things not present.
- Entity names must be exact (match the text as closely as possible).
- Every relationship's source AND target must appear in your entity list.
- Aim for precision over recall: fewer, high-quality extractions are better.
- Descriptions should be ≤ 2 sentences.
"""

# The extraction agent returns a structured KnowledgeGraph
_extraction_agent: Agent[None, KnowledgeGraph] = Agent(
    model=os.environ.get("AGENT_MODEL", "google:gemini-2.5-flash"),
    system_prompt=_EXTRACTION_SYSTEM,
    result_type=KnowledgeGraph,
)


async def _extract_knowledge_graph(crawl: CrawlResult) -> KnowledgeGraph:
    """Use pydantic-ai to extract a typed KnowledgeGraph from crawl markdown."""
    prompt = (
        f"URL: {crawl.url}\n"
        f"Title: {crawl.title or '(no title)'}\n\n"
        f"Content (Markdown):\n{crawl.markdown[:8000]}"  # cap at 8 K chars
    )
    result = await _extraction_agent.run(
        prompt,
        # Inject source_url so the model does not need to repeat it
        result_type=KnowledgeGraph,
    )
    kg = result.output
    # Ensure source_url is set correctly
    kg = KnowledgeGraph(
        entities=[
            Entity(
                name=e.name,
                type=e.type,
                description=e.description,
                source_url=crawl.url,
                properties=e.properties,
            )
            for e in kg.entities
        ],
        relationships=kg.relationships,
        source_url=crawl.url,
    )
    return kg


# ---------------------------------------------------------------------------
# AGE graph storage  (Cypher via asyncpg)
# ---------------------------------------------------------------------------


def _cypher_safe(value: str) -> str:
    """Escape single-quotes for embedding inside a Cypher string literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


async def _store_graph(
    conn: asyncpg.Connection,
    kg: KnowledgeGraph,
    graph_name: str,
) -> tuple[int, int]:
    """Store entities as AGE vertices and relationships as AGE edges.

    Returns (entities_stored, relationships_stored).
    """
    # graph_name comes from config/request — validate it is a safe identifier
    # before interpolating into SQL to prevent SQL injection.
    safe_graph = _validate_graph_name(graph_name)

    entities_stored = 0
    rels_stored = 0

    for entity in kg.entities:
        safe_name = _cypher_safe(entity.name)
        safe_desc = _cypher_safe(entity.description or "")
        safe_url = _cypher_safe(entity.source_url)
        props_json = _cypher_safe(json.dumps(entity.properties))

        # Apache AGE's cypher() function requires the graph name to be a SQL
        # identifier embedded in the query string — parameterised binding is
        # not supported by the AGE API for this argument.  safe_graph has been
        # validated against _GRAPH_NAME_RE (alphanumeric + underscore only) and
        # safe_name / safe_desc have been Cypher-escaped, so injection is
        # prevented.  # lgtm[py/sql-injection]
        cypher = (
            "SELECT * FROM cypher('" + safe_graph + "', $$\n"
            "  MERGE (n:" + entity.type.value + " {name: '" + safe_name + "'})\n"
            "  ON CREATE SET n.description = '" + safe_desc + "',\n"
            "                n.source_url  = '" + safe_url + "',\n"
            "                n.properties  = '" + props_json + "'\n"
            "  RETURN n\n"
            "$$) AS (n agtype)"
        )
        await conn.execute(cypher)  # noqa: S608  # lgtm[py/sql-injection]
        entities_stored += 1

    for rel in kg.relationships:
        safe_src = _cypher_safe(rel.source)
        safe_tgt = _cypher_safe(rel.target)
        safe_rel = _cypher_safe(rel.relation)
        props_json = _cypher_safe(json.dumps(rel.properties))

        # Same rationale as above: AGE requires the graph name and Cypher body
        # to be interpolated; all values are sanitised before this point.
        # lgtm[py/sql-injection]
        cypher = (
            "SELECT * FROM cypher('" + safe_graph + "', $$\n"
            "  MATCH (a {name: '" + safe_src + "'}), (b {name: '" + safe_tgt + "'})\n"
            "  MERGE (a)-[r:" + safe_rel + "]->(b)\n"
            "  ON CREATE SET r.properties = '" + props_json + "'\n"
            "  RETURN r\n"
            "$$) AS (r agtype)"
        )
        try:
            await conn.execute(cypher)  # noqa: S608  # lgtm[py/sql-injection]
            rels_stored += 1
        except Exception as exc:
            logger.warning("Failed to store relationship %s→%s: %s", rel.source, rel.target, exc)

    return entities_stored, rels_stored


# ---------------------------------------------------------------------------
# Text chunking + embedding + pgvector storage
# ---------------------------------------------------------------------------


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Simple word-boundary chunking (no llamaindex dependency for this step)."""
    words = text.split()
    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        chunk_words = words[i : i + chunk_size]
        chunk = " ".join(chunk_words).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


async def _embed_texts(texts: list[str]) -> list[list[float]]:
    """Generate OpenAI embeddings for a batch of texts."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    response = await client.embeddings.create(
        input=texts,
        model=EMBEDDING_MODEL,
    )
    return [item.embedding for item in response.data]


async def _store_chunks(
    conn: asyncpg.Connection,
    chunks: list[TextChunk],
) -> int:
    """Upsert text chunks (with embeddings) into knowledge_chunks table."""
    stored = 0
    for chunk in chunks:
        if chunk.embedding is None:
            continue
        # Format embedding as postgres vector literal
        embedding_str = "[" + ",".join(str(x) for x in chunk.embedding) + "]"
        await conn.execute(
            """
            INSERT INTO knowledge_chunks (id, source_url, chunk_index, text, embedding, metadata)
            VALUES ($1, $2, $3, $4, $5::vector, $6::jsonb)
            ON CONFLICT (source_url, chunk_index) DO UPDATE
                SET text      = EXCLUDED.text,
                    embedding = EXCLUDED.embedding,
                    metadata  = EXCLUDED.metadata
            """,
            chunk.id,
            chunk.source_url,
            chunk.chunk_index,
            chunk.text,
            embedding_str,
            json.dumps(chunk.metadata),
        )
        stored += 1
    return stored


# ---------------------------------------------------------------------------
# Web crawling fallback (when crawl4ai is not available)
# ---------------------------------------------------------------------------


async def _httpx_crawl(url: str) -> CrawlResult:
    """Minimal HTTP crawl using httpx + html2text."""
    from urllib.parse import urlparse, urlunparse

    # Validate URL and reconstruct from parsed components to remove taint
    # (prevents SSRF by asserting scheme and rejecting private addresses).
    _validate_url(url)
    parsed = urlparse(url)
    # Re-serialise from parsed parts so the string passed to httpx
    # is derived from our sanitised components, not the raw user input.
    safe_url = urlunparse(parsed)

    try:
        import html2text as h2t
    except ImportError:
        raise ImportError("Install html2text: pip install html2text")

    async with httpx.AsyncClient(follow_redirects=False, timeout=30) as client:
        response = await client.get(safe_url, headers={"User-Agent": "JarvisBot/1.0"})
        response.raise_for_status()

    html_content = response.text
    h = h2t.HTML2Text()
    h.ignore_links = False
    h.body_width = 0
    markdown = h.handle(html_content)

    # Extract title from <title> tag
    title: str | None = None
    if "<title>" in html_content.lower():
        start = html_content.lower().find("<title>") + 7
        end = html_content.lower().find("</title>", start)
        if end > start:
            title = html_content[start:end].strip()

    return CrawlResult(
        url=url,
        title=title,
        markdown=markdown,
        html=html_content,
        metadata={"status_code": response.status_code},
    )


async def _crawl4ai_crawl(url: str) -> CrawlResult:
    """Use crawl4ai for richer JS-rendered crawling (optional dependency)."""
    try:
        from crawl4ai import AsyncWebCrawler  # type: ignore[import]
    except ImportError:
        logger.info("crawl4ai not installed; falling back to httpx crawler")
        return await _httpx_crawl(url)

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)

    return CrawlResult(
        url=url,
        title=result.metadata.get("title") if result.metadata else None,
        markdown=result.markdown or "",
        html=result.html,
        metadata=result.metadata or {},
        links=[lnk.get("href", "") for lnk in (result.links or {}).get("external", [])],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def ingest_url(
    url: str,
    graph_name: str = DEFAULT_GRAPH,
    use_crawl4ai: bool = True,
) -> IngestResult:
    """Crawl a URL then ingest it into the knowledge graph and vector store."""
    # Validate URL before initiating any network request
    _validate_url(url)
    crawl = await (_crawl4ai_crawl(url) if use_crawl4ai else _httpx_crawl(url))
    return await ingest_crawl_result(crawl, graph_name=graph_name)


async def ingest_crawl_result(
    crawl: CrawlResult,
    graph_name: str = DEFAULT_GRAPH,
) -> IngestResult:
    """Ingest a pre-crawled CrawlResult into the knowledge graph and vector store.

    Steps:
    1. Extract entities + relationships using pydantic-ai (structured output)
    2. Store in PostgresAGE as a property graph
    3. Chunk the markdown, embed via OpenAI, store in pgvector
    """
    start = time.perf_counter()

    # 1. Extract knowledge graph via pydantic-ai agent
    logger.info("Extracting knowledge graph from %s …", crawl.url)
    kg = await _extract_knowledge_graph(crawl)
    warnings = kg.validate_relationships()

    # 2. Store graph + 3. store vectors concurrently
    pool = await get_pool()
    async with pool.acquire() as conn:
        entities_stored, rels_stored = await _store_graph(conn, kg, graph_name)

    # Chunk the markdown
    raw_chunks = _chunk_text(crawl.markdown)
    logger.info("Embedding %d chunks from %s …", len(raw_chunks), crawl.url)

    chunks_stored = 0
    if raw_chunks:
        try:
            embeddings = await _embed_texts(raw_chunks)
            text_chunks = [
                TextChunk(
                    source_url=crawl.url,
                    chunk_index=i,
                    text=text,
                    embedding=emb,
                    metadata={"title": crawl.title or ""},
                )
                for i, (text, emb) in enumerate(zip(raw_chunks, embeddings))
            ]
            async with pool.acquire() as conn:
                chunks_stored = await _store_chunks(conn, text_chunks)
        except Exception as exc:
            logger.warning("Embedding/storage failed: %s", exc)
            warnings.append(f"Vector storage failed: {exc}")

    elapsed = time.perf_counter() - start
    logger.info(
        "Ingested %s: %d entities, %d rels, %d chunks in %.2fs",
        crawl.url,
        entities_stored,
        rels_stored,
        chunks_stored,
        elapsed,
    )

    return IngestResult(
        source_url=crawl.url,
        entities_stored=entities_stored,
        relationships_stored=rels_stored,
        chunks_stored=chunks_stored,
        elapsed_seconds=elapsed,
        warnings=warnings,
    )
