-- ============================================================
-- Jarvis knowledge-graph database initialisation
-- Runs once when the postgres-age container is first created.
-- ============================================================

-- Apache AGE graph extension (property graph / Cypher)
CREATE EXTENSION IF NOT EXISTS age;

-- pgvector extension (vector similarity search)
CREATE EXTENSION IF NOT EXISTS vector;

-- Load AGE shared library into this session so we can call create_graph()
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- ── Knowledge graph ──────────────────────────────────────────
-- Create the default graph; ignore the error if it already exists.
DO $$
BEGIN
    PERFORM create_graph('jarvis_kg');
EXCEPTION
    WHEN SQLSTATE 'XX000' THEN
        -- Graph already exists – safe to continue
        NULL;
END;
$$;

-- ── Vector store ─────────────────────────────────────────────
-- Stores text chunks + their OpenAI embeddings (ada-002 = 1536 dims).
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_url  TEXT        NOT NULL,
    chunk_index INTEGER     NOT NULL,
    text        TEXT        NOT NULL,
    embedding   vector(1536),
    metadata    JSONB       NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_url, chunk_index)
);

-- IVFFlat index for approximate nearest-neighbour cosine search.
-- lists=100 is a reasonable default; raise to 200+ for >1 M rows.
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_embedding
    ON knowledge_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_url
    ON knowledge_chunks (source_url);

CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_metadata
    ON knowledge_chunks
    USING gin (metadata);
