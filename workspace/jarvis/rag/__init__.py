"""RAG module for Jarvis — GraphRAG, VectorRAG and Mixed RAG.

Public surface
──────────────
    from rag import (
        # Ingestion
        ingest_url,
        ingest_crawl_result,
        # Retrieval
        query_graph,
        query_vector,
        query_mixed,
        # DB lifecycle
        initialise_db,
        close_db,
        # Pydantic models
        CrawlResult,
        Entity,
        Relationship,
        KnowledgeGraph,
        TextChunk,
        RAGQuery,
        RAGResult,
        RAGMode,
        # Capabilities
        GraphRAGCapability,
        VectorRAGCapability,
        MixedRAGCapability,
    )
"""

from __future__ import annotations

from .capabilities import GraphRAGCapability, MixedRAGCapability, VectorRAGCapability
from .crawl4ai_ingest import ingest_crawl_result, ingest_url
from .db import close as close_db
from .db import initialise as initialise_db
from .mixed_rag import query_graph, query_mixed, query_vector
from .models import (
    CrawlResult,
    Entity,
    EntityType,
    GraphContext,
    GraphEdge,
    GraphNode,
    IngestResult,
    KnowledgeGraph,
    RAGMode,
    RAGQuery,
    RAGResult,
    Relationship,
    TextChunk,
    VectorChunkResult,
    VectorContext,
)
from .setup_db import setup as setup_db

__all__ = [
    # Ingestion
    "ingest_url",
    "ingest_crawl_result",
    # Retrieval
    "query_graph",
    "query_vector",
    "query_mixed",
    # DB lifecycle
    "initialise_db",
    "close_db",
    "setup_db",
    # Models
    "CrawlResult",
    "Entity",
    "EntityType",
    "Relationship",
    "KnowledgeGraph",
    "TextChunk",
    "RAGQuery",
    "RAGResult",
    "RAGMode",
    "GraphContext",
    "GraphNode",
    "GraphEdge",
    "VectorContext",
    "VectorChunkResult",
    "IngestResult",
    # Capabilities
    "GraphRAGCapability",
    "VectorRAGCapability",
    "MixedRAGCapability",
]
