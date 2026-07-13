"""GraphRAG — retrieve context from the PostgresAGE property graph.

The retrieval strategy:
  1. A pydantic-ai agent converts the natural-language query into one or more
     Cypher patterns that describe the relevant subgraph.
  2. Those Cypher queries are executed against the Apache AGE graph.
  3. The resulting nodes and edges are assembled into a ``GraphContext`` that
     the synthesis agent can read.

No llamaindex is used here — everything is pydantic + pydantic-ai + asyncpg.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import asyncpg
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from .crawl4ai_ingest import _validate_graph_name
from .db import get_pool
from .models import GraphContext, GraphEdge, GraphNode, RAGQuery, VectorContext

logger = logging.getLogger(__name__)

DEFAULT_GRAPH = os.environ.get("RAG_GRAPH_NAME", "jarvis_kg")

# ---------------------------------------------------------------------------
# Cypher-generation agent
# ---------------------------------------------------------------------------


class CypherPlan(BaseModel):
    """Structured plan returned by the Cypher-generation agent."""

    queries: list[str] = Field(
        ...,
        min_length=1,
        max_length=3,
        description="1–3 Cypher MATCH queries that retrieve relevant nodes/edges",
    )
    reasoning: str = Field(description="Brief explanation of the retrieval strategy")


_CYPHER_SYSTEM = """\
You are a graph query expert for Apache AGE (PostgreSQL property graph extension).

Given a natural-language question, generate 1–3 Cypher MATCH queries that will
retrieve the most relevant entities and their relationships from the knowledge graph.

Rules:
- Return ONLY the Cypher body (everything after the graph name in a cypher() call).
- Each query must end with RETURN — include node/edge variables you want back.
- Use MATCH (n {name: '...'}) for known entities; use MATCH (n) WHERE n.name CONTAINS '...' for fuzzy.
- Keep queries simple and targeted.
- The graph schema: vertices have a 'name' and optional 'description' and 'source_url'.
  Edges have a relation label like WORKS_AT, PART_OF, RELATED_TO, etc.

Example queries:
  MATCH (n) WHERE toLower(n.name) CONTAINS 'python' RETURN n LIMIT 20
  MATCH (a)-[r]->(b) WHERE toLower(a.name) CONTAINS 'openai' RETURN a, r, b LIMIT 20
"""

_cypher_agent: Agent[None, CypherPlan] = Agent(
    model=os.environ.get("AGENT_MODEL", "anthropic:claude-sonnet-4-6"),
    system_prompt=_CYPHER_SYSTEM,
    result_type=CypherPlan,
)


async def _generate_cypher(query: str) -> CypherPlan:
    result = await _cypher_agent.run(f"Question: {query}")
    return result.output


# ---------------------------------------------------------------------------
# Graph retrieval
# ---------------------------------------------------------------------------


def _parse_agtype_node(row_value: Any) -> GraphNode | None:
    """Parse a single AGE agtype node into a GraphNode."""
    try:
        import json as _json

        if isinstance(row_value, str):
            data = _json.loads(row_value)
        elif hasattr(row_value, "__dict__"):
            data = row_value.__dict__
        else:
            data = dict(row_value)

        props = data.get("properties", {})
        label = data.get("label", "Unknown")
        return GraphNode(
            id=data.get("id"),
            label=label,
            name=props.get("name", str(props)),
            description=props.get("description"),
            properties={k: v for k, v in props.items() if k not in ("name", "description")},
        )
    except Exception as exc:
        logger.debug("Could not parse AGE node: %s — %s", row_value, exc)
        return None


def _parse_agtype_edge(row_value: Any, start_name: str = "", end_name: str = "") -> GraphEdge | None:
    """Parse a single AGE agtype edge into a GraphEdge."""
    try:
        import json as _json

        if isinstance(row_value, str):
            data = _json.loads(row_value)
        elif hasattr(row_value, "__dict__"):
            data = row_value.__dict__
        else:
            data = dict(row_value)

        label = data.get("label", "RELATED_TO")
        props = data.get("properties", {})
        return GraphEdge(
            start_name=start_name,
            end_name=end_name,
            relation=label,
            properties=props,
        )
    except Exception as exc:
        logger.debug("Could not parse AGE edge: %s — %s", row_value, exc)
        return None


async def _execute_cypher_query(
    conn: asyncpg.Connection,
    cypher_body: str,
    graph_name: str,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Execute one Cypher query and parse results into nodes + edges."""
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    # Validate graph_name is a safe identifier before SQL interpolation
    safe_graph = _validate_graph_name(graph_name)
    sql = f"SELECT * FROM cypher('{safe_graph}', $$ {cypher_body} $$) AS result(c agtype)"

    try:
        rows = await conn.fetch(sql)
    except Exception as exc:
        logger.warning("Cypher query failed: %s\nError: %s", cypher_body, exc)
        return nodes, edges

    for row in rows:
        value = row[0] if row else None
        if value is None:
            continue

        # Try to parse as node first, then edge
        node = _parse_agtype_node(value)
        if node and node.name:
            nodes.append(node)

    return nodes, edges


async def retrieve(query: RAGQuery) -> GraphContext:
    """Run graphRAG retrieval for *query*, returning a populated GraphContext."""
    graph_name = _validate_graph_name(query.graph_name or DEFAULT_GRAPH)

    # 1. Generate Cypher queries via pydantic-ai
    plan = await _generate_cypher(query.query)
    logger.debug("Cypher plan: %s", plan.queries)

    pool = await get_pool()
    all_nodes: list[GraphNode] = []
    all_edges: list[GraphEdge] = []

    async with pool.acquire() as conn:
        for cypher_body in plan.queries:
            n, e = await _execute_cypher_query(conn, cypher_body, graph_name)
            all_nodes.extend(n)
            all_edges.extend(e)

    # Deduplicate nodes by name
    seen: set[str] = set()
    unique_nodes: list[GraphNode] = []
    for node in all_nodes:
        key = f"{node.label}:{node.name}"
        if key not in seen:
            seen.add(key)
            unique_nodes.append(node)

    # Limit to top_k most relevant nodes
    unique_nodes = unique_nodes[: query.top_k * 2]  # 2x because edges bring extra value

    # Also retrieve relationships between found entities
    if unique_nodes:
        entity_names = [f"'{_cypher_safe(n.name)}'" for n in unique_nodes[:10]]
        names_list = ", ".join(entity_names)
        rel_cypher = (
            f"MATCH (a)-[r]->(b) "
            f"WHERE a.name IN [{names_list}] OR b.name IN [{names_list}] "
            f"RETURN a, r, b LIMIT {query.top_k * 3}"
        )
        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(
                    f"SELECT * FROM cypher('{graph_name}', $$ {rel_cypher} $$) "
                    f"AS result(a agtype, r agtype, b agtype)"
                )
                for row in rows:
                    a_node = _parse_agtype_node(row[0])
                    b_node = _parse_agtype_node(row[2])
                    if a_node and b_node:
                        edge = _parse_agtype_edge(row[1], a_node.name, b_node.name)
                        if edge:
                            all_edges.append(edge)
            except Exception as exc:
                logger.debug("Relationship retrieval failed: %s", exc)

    combined_cypher = "\n".join(plan.queries)
    return GraphContext(
        nodes=unique_nodes,
        edges=all_edges,
        cypher_query=combined_cypher,
    )


def _cypher_safe(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")
