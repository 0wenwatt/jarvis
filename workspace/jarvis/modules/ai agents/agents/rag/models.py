"""Pydantic models for the Jarvis RAG system.

All data flowing through the GraphRAG, VectorRAG and mixed-RAG pipelines is
typed here.  The models cover:

  - crawl4ai output (CrawlResult)
  - knowledge-graph building blocks (Entity, Relationship, KnowledgeGraph)
  - vector-store building block (TextChunk)
  - query/result envelopes for every RAG mode (RAGQuery, RAGResult, RAGMode)
  - intermediate retrieval types (GraphContext, VectorContext)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Annotated, Any

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class RAGMode(str, Enum):
    """Which retrieval strategy to use."""

    GRAPH = "graph"
    VECTOR = "vector"
    MIXED = "mixed"


class EntityType(str, Enum):
    """Broad category for a knowledge-graph vertex."""

    PERSON = "Person"
    ORGANIZATION = "Organization"
    TECHNOLOGY = "Technology"
    CONCEPT = "Concept"
    PRODUCT = "Product"
    LOCATION = "Location"
    EVENT = "Event"
    DOCUMENT = "Document"
    OTHER = "Other"


# ---------------------------------------------------------------------------
# Crawl4AI  ─ input to the ingestion pipeline
# ---------------------------------------------------------------------------


class CrawlResult(BaseModel):
    """Matches crawl4ai's output JSON envelope.

    When crawl4ai is used as the crawler the response dict can be passed
    straight to ``CrawlResult(**result_dict)``.  When using the httpx fallback
    the same model is produced manually.
    """

    url: str
    title: str | None = None
    markdown: str = Field(..., min_length=1, description="Main page content as Markdown")
    html: str | None = Field(default=None, description="Raw HTML (optional; not stored)")
    metadata: dict[str, Any] = Field(default_factory=dict)
    links: list[str] = Field(default_factory=list)
    crawled_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("url")
    @classmethod
    def _normalise_url(cls, v: str) -> str:
        return v.strip()

    @field_validator("markdown")
    @classmethod
    def _strip_markdown(cls, v: str) -> str:
        return v.strip()


# ---------------------------------------------------------------------------
# Knowledge-graph building blocks
# ---------------------------------------------------------------------------


class Entity(BaseModel):
    """A vertex in the knowledge graph extracted from a web page."""

    name: str = Field(..., min_length=1, description="Canonical display name")
    type: EntityType = EntityType.OTHER
    description: str | None = None
    source_url: str
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip()


class Relationship(BaseModel):
    """A directed edge in the knowledge graph."""

    source: str = Field(..., description="Source entity name")
    target: str = Field(..., description="Target entity name")
    relation: str = Field(
        ...,
        description="SCREAMING_SNAKE_CASE relation label, e.g. WORKS_AT, PART_OF",
    )
    properties: dict[str, Any] = Field(default_factory=dict)

    @field_validator("relation")
    @classmethod
    def _normalise_relation(cls, v: str) -> str:
        return v.upper().replace(" ", "_").strip()

    @model_validator(mode="after")
    def _source_ne_target(self) -> "Relationship":
        if self.source == self.target:
            raise ValueError("source and target must differ")
        return self


class KnowledgeGraph(BaseModel):
    """Extracted entities and relationships from a single crawl result."""

    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    source_url: str
    extracted_at: datetime = Field(default_factory=datetime.utcnow)

    @property
    def entity_names(self) -> set[str]:
        return {e.name for e in self.entities}

    def validate_relationships(self) -> list[str]:
        """Return a list of warnings for dangling relationships."""
        names = self.entity_names
        warnings: list[str] = []
        for rel in self.relationships:
            if rel.source not in names:
                warnings.append(f"Relationship source '{rel.source}' not in entity list")
            if rel.target not in names:
                warnings.append(f"Relationship target '{rel.target}' not in entity list")
        return warnings


# ---------------------------------------------------------------------------
# Vector-store building blocks
# ---------------------------------------------------------------------------


class TextChunk(BaseModel):
    """One chunk of text from a crawl result, ready for embedding."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_url: str
    chunk_index: int
    text: str = Field(..., min_length=1)
    embedding: list[float] | None = Field(
        default=None,
        description="Dense vector produced by the embedding model",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        return v.strip()


# ---------------------------------------------------------------------------
# RAG query / result envelopes
# ---------------------------------------------------------------------------


class RAGQuery(BaseModel):
    """Input to any RAG retrieval function."""

    query: str = Field(..., min_length=1)
    mode: RAGMode = RAGMode.MIXED
    top_k: int = Field(default=5, ge=1, le=50)
    graph_name: str = "jarvis_kg"


class GraphNode(BaseModel):
    """A vertex returned from an AGE graph traversal."""

    id: int | None = None
    label: str
    name: str
    description: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    """An edge returned from an AGE graph traversal."""

    start_name: str
    end_name: str
    relation: str
    properties: dict[str, Any] = Field(default_factory=dict)


class GraphContext(BaseModel):
    """Subgraph context assembled for graphRAG synthesis."""

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    cypher_query: str | None = None

    def to_text(self) -> str:
        """Render the subgraph as a human-readable context string."""
        lines: list[str] = []

        if self.nodes:
            lines.append("## Relevant Entities")
            for n in self.nodes:
                desc = f" — {n.description}" if n.description else ""
                lines.append(f"- [{n.label}] **{n.name}**{desc}")

        if self.edges:
            lines.append("\n## Relationships")
            for e in self.edges:
                lines.append(f"- {e.start_name} —[{e.relation}]→ {e.end_name}")

        return "\n".join(lines) if lines else "(no graph context found)"


class VectorChunkResult(BaseModel):
    """A single vector-store retrieval hit."""

    chunk_id: str
    source_url: str
    text: str
    score: float = Field(description="Cosine similarity (0–1, higher = more relevant)")
    metadata: dict[str, Any] = Field(default_factory=dict)


class VectorContext(BaseModel):
    """Vector retrieval results assembled for vectorRAG synthesis."""

    chunks: list[VectorChunkResult] = Field(default_factory=list)

    def to_text(self) -> str:
        if not self.chunks:
            return "(no vector context found)"
        parts = []
        for i, c in enumerate(self.chunks, 1):
            parts.append(
                f"### Chunk {i} (score={c.score:.3f}, source={c.source_url})\n{c.text}"
            )
        return "\n\n".join(parts)


class RAGResult(BaseModel):
    """Output of a RAG query across any mode."""

    query: str
    mode: RAGMode
    graph_context: GraphContext | None = None
    vector_context: VectorContext | None = None
    answer: str = Field(description="Synthesised answer from the LLM")
    sources: list[str] = Field(default_factory=list, description="Source URLs referenced")

    @property
    def combined_context(self) -> str:
        """Merge graph and vector context into one string for the LLM."""
        parts: list[str] = []
        if self.graph_context:
            parts.append("# Graph Context\n" + self.graph_context.to_text())
        if self.vector_context:
            parts.append("# Vector Context\n" + self.vector_context.to_text())
        return "\n\n".join(parts) if parts else "(no context)"


# ---------------------------------------------------------------------------
# Ingestion result
# ---------------------------------------------------------------------------


class IngestResult(BaseModel):
    """Summary returned after ingesting one CrawlResult."""

    source_url: str
    entities_stored: int
    relationships_stored: int
    chunks_stored: int
    elapsed_seconds: float
    warnings: list[str] = Field(default_factory=list)
