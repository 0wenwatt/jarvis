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

# -------------------------------------------------------
# GitHub CLI authentication
# -------------------------------------------------------
if [ -n "$GITHUB_TOKEN" ]; then
    echo "[*] Configuring GitHub CLI (gh) and git credentials..."
    echo "$GITHUB_TOKEN" | gh auth login --with-token 2>/dev/null \
        && echo "[✓] gh auth: logged in" \
        || echo "[!] gh auth: login failed (token may be invalid)"
    git config --global credential.helper store
    echo "https://x-access-token:${GITHUB_TOKEN}@github.com" > /root/.git-credentials
    git config --global user.name "Jarvis Agent"
    git config --global user.email "jarvis@local"
    echo "[✓] git credentials configured"
else
    echo "[*] GITHUB_TOKEN not set; skipping GitHub auth"
fi

# -------------------------------------------------------
# Docker socket access check
# -------------------------------------------------------
if [ -S /var/run/docker.sock ]; then
    echo "[*] Docker socket found at /var/run/docker.sock"
    docker ps > /dev/null 2>&1 && echo "[✓] Docker socket accessible" || echo "[!] Docker socket may not be accessible (permissions issue)"
fi

# -------------------------------------------------------
# Tailscale
# -------------------------------------------------------
mkdir -p /var/lib/tailscale
_TS_SOCK=/var/run/tailscale/tailscaled.sock
mkdir -p "$(dirname "$_TS_SOCK")"

# Prefer a real tun interface (needed for the phone to reach 8443/8000
# directly on the Tailscale IP); fall back to userspace mode if /dev/net/tun
# isn't available (e.g. missing --cap-add=NET_ADMIN / --device=/dev/net/tun).
if [ -c /dev/net/tun ]; then
    _TS_TUN_ARGS=""
else
    echo "[!] /dev/net/tun not available; falling back to userspace-networking (inbound access from your phone will NOT work)"
    _TS_TUN_ARGS="--tun=userspace-networking"
fi

if ! pgrep -x tailscaled > /dev/null 2>&1; then
    echo "[*] Starting Tailscale daemon..."
    tailscaled --state=/var/lib/tailscale/tailscaled.state --socket="$_TS_SOCK" $_TS_TUN_ARGS > /tmp/tailscaled.log 2>&1 &
    # Wait for the daemon socket instead of a fixed sleep
    for i in $(seq 1 10); do
        [ -S "$_TS_SOCK" ] && break
        sleep 1
    done
else
    echo "[*] tailscaled already running; reusing it"
fi

_TS_READY=0
if tailscale status > /dev/null 2>&1; then
    # Already logged in from persisted state — nothing else to do
    _TS_READY=1
    echo "[*] Tailscale already authenticated; reusing existing node identity"
elif [ -n "$TAILSCALE_AUTHKEY" ]; then
    echo "[*] Authenticating with Tailscale..."
    tailscale up --authkey="$TAILSCALE_AUTHKEY" --hostname=jarvis-dev --accept-dns=false > /tmp/tailscale.log 2>&1
    for i in $(seq 1 10); do
        if tailscale status > /dev/null 2>&1; then
            _TS_READY=1
            break
        fi
        sleep 1
    done
else
    echo "[*] TAILSCALE_AUTHKEY not set and no existing session; skipping Tailscale"
fi

if [ "$_TS_READY" = "1" ]; then
    echo "[✓] Tailscale is up"
    TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo 'unavailable')
    echo "    Tailscale IP: $TAILSCALE_IP  (open http://$TAILSCALE_IP:8000 or :8443 from your phone)"
elif [ -n "$TAILSCALE_AUTHKEY" ]; then
    echo "[!] Tailscale did not come up — check /tmp/tailscale.log and /tmp/tailscaled.log"
    tail -20 /tmp/tailscaled.log 2>/dev/null
    tail -20 /tmp/tailscale.log 2>/dev/null
fi

# -------------------------------------------------------
# Authsome credential gateway
# -------------------------------------------------------
if [ -n "$AUTHSOME_BASE_URL" ]; then
    echo "[*] Waiting for authsome daemon at $AUTHSOME_BASE_URL..."
    _authsome_ready=0
    for i in $(seq 1 20); do
        if python3 -c "import urllib.request; urllib.request.urlopen('$AUTHSOME_BASE_URL/health')" > /dev/null 2>&1; then
            _authsome_ready=1
            break
        fi
        sleep 3
    done

    if [ "$_authsome_ready" = "1" ]; then
        echo "[✓] Authsome daemon is healthy"
        echo "[*] Authsome ready — run 'authsome onboard' from the terminal to complete first-time setup"
    else
        echo "[!] Authsome daemon did not become healthy in time — continuing without it"
    fi
fi

# -------------------------------------------------------
# code-server (VS Code in browser)
# -------------------------------------------------------
echo "[*] Configuring code-server..."
mkdir -p /root/.config/code-server

if [ -n "$GITHUB_TOKEN" ]; then
    echo "[✓] GitHub token detected; using it as code-server password"
    cat > /root/.config/code-server/config.yaml << EOF
bind-addr: 0.0.0.0:8443
auth: password
password: ${GITHUB_TOKEN}
cert: false
EOF
else
    _cs_pass="${CODE_SERVER_PASSWORD:-changeme}"
    echo "[*] Using password auth for code-server"
    cat > /root/.config/code-server/config.yaml << EOF
bind-addr: 0.0.0.0:8443
auth: password
password: ${_cs_pass}
cert: false
EOF
fi

echo "[*] Starting code-server on http://0.0.0.0:8443"
code-server --config /root/.config/code-server/config.yaml > /tmp/code-server.log 2>&1 &
CODE_SERVER_PID=$!
sleep 2
if kill -0 "$CODE_SERVER_PID" 2>/dev/null; then
    echo "[✓] code-server started (PID: $CODE_SERVER_PID)"
else
    echo "[!] code-server failed to start — check /tmp/code-server.log:"
    tail -10 /tmp/code-server.log
fi

# -------------------------------------------------------
# FastAPI web GUI
# -------------------------------------------------------
if [ -f /workspace/jarvis/app.py ]; then
    echo "[*] Starting FastAPI app on http://0.0.0.0:8000..."
    # Ensure required directories exist (volume mounts may not create empty dirs)
    mkdir -p /workspace/jarvis/static /workspace/jarvis/workspaces
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

# -------------------------------------------------------
# Startup summary
# -------------------------------------------------------
echo ""
echo "=========================================="
echo "  JARVIS READY"
echo "=========================================="
echo "  code-server  : http://localhost:8443"
echo "  FastAPI GUI  : http://localhost:8000"
echo "  Authsome UI  : http://localhost:7998"
echo "  PostgreSQL   : localhost:5432  (db: jarvis)"
echo ""
echo "  FIRST-RUN: open a terminal and run:"
echo "    authsome onboard --base-url http://authsome:7998"
echo "  then visit http://localhost:7998 to claim your vault."
echo "=========================================="
echo ""

# Keep container alive
wait
