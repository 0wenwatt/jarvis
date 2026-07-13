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
    export $(cat /workspace/.env | grep -v '^#' | grep -v '^$' | xargs)
fi

if [ -f /workspace/jarvis/.env ]; then
    echo "[*] Loading environment from /workspace/jarvis/.env"
    export $(cat /workspace/jarvis/.env | grep -v '^#' | grep -v '^$' | xargs)
fi

# Add docker group to current user for docker socket access
if [ -S /var/run/docker.sock ]; then
    echo "[*] Docker socket found at /var/run/docker.sock"
    # This is handled by the host; verify access
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

# Configure code-server with GitHub token
echo "[*] Configuring code-server..."
mkdir -p /root/.config/code-server

if [ -n "$GITHUB_TOKEN" ]; then
    echo "[✓] GitHub token detected; configuring token authentication"
    cat > /root/.config/code-server/config.yaml << 'EOF'
bind-addr: 0.0.0.0:8443
auth: token
password: ${GITHUB_TOKEN}
cert: false
EOF
else
    echo "[*] GitHub token not set; using password auth (fallback)"
    cat > /root/.config/code-server/config.yaml << 'EOF'
bind-addr: 0.0.0.0:8443
auth: password
password: ${CODE_SERVER_PASSWORD:-changeme}
cert: false
EOF
fi

# Start code-server in background
echo "[*] Starting code-server on https://0.0.0.0:8443"
code-server --config /root/.config/code-server/config.yaml > /tmp/code-server.log 2>&1 &
CODE_SERVER_PID=$!
sleep 2
echo "[✓] code-server started (PID: $CODE_SERVER_PID)"

# Verify FastAPI app exists
if [ ! -f /workspace/jarvis/app.py ]; then
    echo "[!] WARNING: /workspace/jarvis/app.py not found!"
    echo "    The FastAPI full_app needs to be placed in /workspace/jarvis/"
    echo "    It will NOT start automatically."
else
    echo "[✓] Found /workspace/jarvis/app.py"
fi

# Keep container alive
echo "[*] Startup complete. Services running:"
echo "    code-server:  https://0.0.0.0:8443 (VSCode)"
echo "    FastAPI app:  http://0.0.0.0:8000 (after manual start in terminal)"
echo "    CLI access:   ssh into container or use VSCode terminal"
echo "    Docker:       Available for agent sandboxing"
echo ""
echo "To start FastAPI app, run in terminal:"
echo "    cd /workspace/jarvis && uvicorn app:app --reload --host 0.0.0.0 --port 8000"
echo ""

# Wait for signals
wait
ENTRYPOINT

RUN chmod +x /entrypoint.sh

EXPOSE 8443 8000

ENTRYPOINT ["/entrypoint.sh"]
