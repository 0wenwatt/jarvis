# PostgreSQL with Apache AGE (graph) + pgvector (vector similarity search)
# 
# Extends the official apache/age image by compiling and installing pgvector.
# This gives us:
#   - Apache AGE: Cypher-based property graph queries (graphRAG)
#   - pgvector:   Vector similarity search (vectorRAG)
#   Both in one Postgres instance — enabling mixed graph+vector RAG.

FROM apache/age:latest

# Postgres major version shipped with apache/age:latest
ARG PG_MAJOR=18

# Build pgvector from source (https://github.com/pgvector/pgvector)
RUN set -ex \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        git \
        ca-certificates \
        "postgresql-server-dev-${PG_MAJOR}" \
    && git clone --branch v0.8.0 --depth 1 \
        https://github.com/pgvector/pgvector.git /tmp/pgvector \
    && cd /tmp/pgvector \
    && make PG_CONFIG="/usr/lib/postgresql/${PG_MAJOR}/bin/pg_config" \
    && make install PG_CONFIG="/usr/lib/postgresql/${PG_MAJOR}/bin/pg_config" \
    && rm -rf /tmp/pgvector \
    && apt-get purge -y --auto-remove \
        build-essential \
        git \
        "postgresql-server-dev-${PG_MAJOR}" \
    && rm -rf /var/lib/apt/lists/*
