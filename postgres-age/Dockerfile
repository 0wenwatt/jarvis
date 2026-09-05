# PostgreSQL with Apache AGE and pgvector.
FROM apache/age:latest

ARG PG_MAJOR=18

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        ca-certificates \
        postgresql-server-dev-${PG_MAJOR}; \
    git clone --branch v0.8.1 --depth 1 \
        https://github.com/pgvector/pgvector.git /tmp/pgvector; \
    PG_CONFIG=/usr/lib/postgresql/${PG_MAJOR}/bin/pg_config; \
    test -x "$PG_CONFIG"; \
    make -C /tmp/pgvector PG_CONFIG="$PG_CONFIG"; \
    make -C /tmp/pgvector install PG_CONFIG="$PG_CONFIG"; \
    rm -rf /tmp/pgvector; \
    rm -rf /var/lib/apt/lists/*
