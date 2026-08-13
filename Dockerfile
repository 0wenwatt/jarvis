FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH="/usr/local/bin:/root/.local/bin:$PATH"

# System packages: build, dev, Docker, SSH, utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    wget \
    ca-certificates \
    openssh-client \
    pkg-config \
    python3 \
    python3-pip \
    python3-dev \
    python3-venv \
    libpq-dev \
    postgresql-client \
    docker.io \
    docker-compose \
    vim \
    nano \
    jq \
    tar \
    gzip \
    unzip \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Node.js 20 (LTS) — needed for @modelcontextprotocol/server-postgres MCP
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI (gh) — for git credential helper and GitHub operations
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# uv — fast Python package/tool manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:/root/.local/bin:$PATH"

# Create workspace and set permissions
RUN mkdir -p /workspace /workspace/jarvis /workspace/jarvis/workspaces /workspace/jarvis/skills

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install code-server
RUN curl -fsSL https://code-server.dev/install.sh | sh

# Install Tailscale
RUN curl -fsSL https://tailscale.com/install.sh | sh

# Install Python dependencies from requirements.txt
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Install authsome credential gateway CLI
# authsome requires Python 3.13+; uv handles the Python version automatically
RUN uv tool install --python 3.13 authsome && \
    ln -sf /root/.local/bin/authsome /usr/local/bin/authsome

# Install PostgreSQL MCP server (Node.js, official reference implementation)
# Works with plain PostgreSQL and Apache AGE (via SQL interface)
RUN npm install -g @modelcontextprotocol/server-postgres

# Download GitHub MCP server binary (Go binary, official from github.com/github/github-mcp-server)
ENV GITHUB_MCP_VERSION=1.5.0
RUN curl -fsSL \
    "https://github.com/github/github-mcp-server/releases/download/v${GITHUB_MCP_VERSION}/github-mcp-server_Linux_x86_64.tar.gz" \
    | tar -xzf - -C /tmp/ \
    && mv /tmp/github-mcp-server /usr/local/bin/github-mcp-server \
    && chmod +x /usr/local/bin/github-mcp-server

WORKDIR /workspace/jarvis

# Create startup scripts directory
RUN mkdir -p /etc/startup.d

# Copy entrypoint script (kept as a separate file to avoid CRLF issues on Windows)
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8443 8000

ENTRYPOINT ["/entrypoint.sh"]

