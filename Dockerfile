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

# Install PostgreSQL MCP server (Node.js, official reference implementation)
# Works with plain PostgreSQL and Apache AGE (via SQL interface)
RUN npm install -g @modelcontextprotocol/server-postgres

# Download GitHub MCP server binary (Go binary, official from github.com/github/github-mcp-server)
# Detects host arch so the image builds correctly on both x86_64 and arm64/aarch64.
ENV GITHUB_MCP_VERSION=1.5.0
RUN ARCH="$(uname -m)" && \
    case "$ARCH" in \
      aarch64|arm64) GH_ARCH="arm64" ;; \
      *) GH_ARCH="x86_64" ;; \
    esac && \
    curl -fsSL \
      "https://github.com/github/github-mcp-server/releases/download/v${GITHUB_MCP_VERSION}/github-mcp-server_Linux_${GH_ARCH}.tar.gz" \
      | tar -xzf - -C /tmp/ \
    && mv /tmp/github-mcp-server /usr/local/bin/github-mcp-server \
    && chmod +x /usr/local/bin/github-mcp-server

# Install Playwright Chromium for crawl4ai browser-based crawling.
# --with-deps installs OS-level browser dependencies (libnss, fonts, etc.)
RUN playwright install chromium --with-deps

WORKDIR /workspace/jarvis

# Create startup scripts directory
RUN mkdir -p /etc/startup.d

# Entrypoint script that starts all services
RUN cat > /entrypoint.sh << 'ENTRYPOINT'
#!/bin/bash
set -e

echo "=========================================="
echo "Jarvis Development Environment Startup"
echo "=========================================="

# Load environment variables from .env if it exists
if [ -f /workspace/.env ]; then
    echo "[*] Loading environment from /workspace/.env"
    set -a; source /workspace/.env; set +a
fi

if [ -f /workspace/jarvis/.env ]; then
    echo "[*] Loading environment from /workspace/jarvis/.env"
    set -a; source /workspace/jarvis/.env; set +a
fi

# Add docker group to current user for docker socket access
if [ -S /var/run/docker.sock ]; then
    echo "[*] Docker socket found at /var/run/docker.sock"
    docker ps > /dev/null 2>&1 && echo "[✓] Docker socket accessible" || echo "[!] Docker socket may not be accessible (permissions issue)"
fi

# Start Tailscale if auth key is set
if [ -n "$TAILSCALE_AUTHKEY" ]; then
    echo "[*] Starting Tailscale daemon..."
    tailscaled --tun=userspace-networking &
    TAILSCALED_PID=$!
    sleep 2
    tailscale up --authkey="$TAILSCALE_AUTHKEY" --accept-dns=false 2>&1 | tee -a /tmp/tailscale.log &
    sleep 3
    if tailscale status > /dev/null 2>&1; then
        echo "[✓] Tailscale started successfully"
        TAILSCALE_IP=$(tailscale ip -4)
        echo "    Tailscale IP: $TAILSCALE_IP"
    else
        echo "[!] Tailscale startup issue; continuing anyway"
    fi
else
    echo "[*] TAILSCALE_AUTHKEY not set; skipping Tailscale"
fi

# Configure code-server
echo "[*] Configuring code-server..."
mkdir -p /root/.config/code-server

if [ -n "$GITHUB_TOKEN" ]; then
    echo "[✓] GitHub token detected; configuring token authentication"
    cat > /root/.config/code-server/config.yaml << EOF
bind-addr: 0.0.0.0:8443
auth: token
password: ${GITHUB_TOKEN}
cert: false
EOF
else
    _cs_pass="${CODE_SERVER_PASSWORD:-changeme}"
    echo "[*] GitHub token not set; using password auth (password: $CODE_SERVER_PASSWORD)"
    cat > /root/.config/code-server/config.yaml << EOF
bind-addr: 0.0.0.0:8443
auth: password
password: ${_cs_pass}
cert: false
EOF
fi

# Start code-server in background
echo "[*] Starting code-server on https://0.0.0.0:8443"
code-server --config /root/.config/code-server/config.yaml > /tmp/code-server.log 2>&1 &
CODE_SERVER_PID=$!
sleep 2
echo "[✓] code-server started (PID: $CODE_SERVER_PID)"

# Start FastAPI app
if [ -f /workspace/jarvis/app.py ]; then
    echo "[*] Starting FastAPI app on http://0.0.0.0:8000..."
    cd /workspace/jarvis
    uvicorn app:app --host 0.0.0.0 --port 8000 --log-level info > /tmp/fastapi.log 2>&1 &
    FASTAPI_PID=$!
    sleep 4
    if kill -0 "$FASTAPI_PID" 2>/dev/null; then
        echo "[✓] FastAPI started (PID: $FASTAPI_PID)"
    else
        echo "[!] FastAPI failed to start — check /tmp/fastapi.log:"
        tail -20 /tmp/fastapi.log
    fi
else
    echo "[!] WARNING: /workspace/jarvis/app.py not found — FastAPI not started"
fi

# Print service summary
echo ""
echo "=========================================="
echo "Services:"
echo "  code-server : https://0.0.0.0:8443"
echo "  FastAPI     : http://0.0.0.0:8000"
echo "  Docker      : Available for agent sandboxing"
echo "  Logs        : /tmp/fastapi.log, /tmp/code-server.log"
echo "=========================================="
echo ""

# Keep container alive
wait
ENTRYPOINT

RUN chmod +x /entrypoint.sh

EXPOSE 8443 8000

ENTRYPOINT ["/entrypoint.sh"]

