# Jarvis Deep Agent Development Environment — Setup Information

**Container Name:** jarvis-dev  
**Network:** jarvis-net (shared with postgres-age container)  
**Created:** 2025-10-22

---

## 🚀 Quick Start

### 1. **Access VSCode from Browser**
- URL: `https://localhost:8443`
- Authentication: GitHub token (from `GITHUB_TOKEN` env var)
- Workspace: `/workspace/jarvis/`

### 2. **Access FastAPI Web GUI (Agent Chat)**
- URL: `http://localhost:8000`
- Start manually in VSCode terminal:
  ```bash
  cd /workspace/jarvis
  uvicorn app:app --reload --host 0.0.0.0 --port 8000
  ```

### 3. **CLI Agent Access**
- SSH or VSCode terminal:
  ```bash
  cd /workspace/jarvis
  # Option 1: Run FastAPI directly (see above)
  # Option 2: Import agent modules in Python REPL
  python3 -c "from pydantic_deep import create_deep_agent; print('Agent imports work!')"
  ```

### 4. **SSH into Container**
```bash
docker exec -it jarvis-dev bash
# Or from Windows host with Tailscale enabled
ssh -l root <tailscale-ip>
```

---

## 📝 Environment Setup

### Required Environment Variables

Create or update `/workspace/jarvis/.env` (or `/workspace/.env`):

```ini
# GitHub OAuth (required for code-server + Tailscale)
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# LLM APIs (at least one required)
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx

# PostgreSQL + Apache AGE (auto-connects via jarvis-net)
POSTGRES_HOST=postgres-age
POSTGRES_PORT=5432
POSTGRES_DB=your_database
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password

# Logfire Observability (optional but recommended)
LOGFIRE_TOKEN=your_logfire_token
LOGFIRE_PROJECT=0wenwatt/jarvis-graph-agent
LOGFIRE_BASE_URL=https://logfire-us.pydantic.dev

# Tailscale (optional, for Tailscale remote access)
TAILSCALE_AUTHKEY=tskey-xxxxx

# code-server Fallback (if GitHub token auth fails)
CODE_SERVER_PASSWORD=fallback_password
```

---

## 🔧 Services Running

| Service | Port | Access | Status |
|---------|------|--------|--------|
| **code-server (VSCode)** | 8443 | `https://localhost:8443` | Auto-start |
| **FastAPI App** | 8000 | `http://localhost:8000` | Manual start in terminal |
| **Tailscale** | — | Daemon | If `TAILSCALE_AUTHKEY` set |
| **Docker (for agent)** | `/var/run/docker.sock` | Socket mount | Available |
| **PostgreSQL** | 5432 | Via `jarvis-net` | On postgres-age container |

---

## 🤖 Agent Framework: Pydantic Deep Agents

**Version:** 0.3.35+  
**Location:** `/workspace/jarvis/app.py` (FastAPI full example)

### Features Enabled

✅ Docker sandbox execution (agent spawns isolated containers for code execution)  
✅ Skills system (production-postgres, production-docker, data-analysis, code-review)  
✅ Multi-agent subagents (joke-generator, code-reviewer, planner, general-purpose)  
✅ Persistent memory across sessions  
✅ Plan mode for structured planning  
✅ File operations (read, write, edit, glob, grep)  
✅ Shell execution with human-in-the-loop approval  
✅ Web search and fetching  
✅ Browser automation (Playwright)  
✅ MCP (Model Context Protocol) support  
✅ Logfire tracing for all runs  
✅ Checkpointing (save/rewind/fork conversations)  

### Full Example Web UI Features

- FastAPI backend with WebSocket streaming
- Real-time chat interface
- File upload support
- Skill management & discovery
- Multi-user session management (each user gets isolated Docker container)
- Human-in-the-loop approval for shell commands
- Real-time tool call visualization
- TODO list tracking
- GitHub integration (mock tools)
- Data analysis workflow
- Code review & testing workflows
- Timeline/checkpoint navigation

---

## 📚 Skills Installed

### production-postgres (`/workspace/jarvis/skills/production-postgres/`)
Guides agent on:
- Zero-downtime database migrations
- Connection pooling best practices
- Safe schema evolution (expand-contract pattern)
- Query optimization & EXPLAIN ANALYZE
- Index strategies (B-tree, BRIN, GIN, partial)
- Backup & recovery patterns
- Monitoring queries (pg_stat_statements, locks, cache hit ratio)

### production-docker (`/workspace/jarvis/skills/production-docker/`)
Guides agent on:
- Multi-stage Docker builds
- Non-root user execution
- Distroless and minimal base images
- BuildKit secrets handling
- Layer optimization & caching strategies
- Health checks (HTTP, shell, exec)
- Security scanning with Trivy
- docker-compose production patterns
- Runtime hardening (read-only fs, capability dropping)
- .dockerignore best practices

### Built-in Skills
- **data-analysis** — CSV, pandas, matplotlib, data workflows
- **code-review** — Python code quality, security, best practices
- **test-generator** — Generate unit & integration tests
- **quick-reference** — Commands, shortcuts, tips

---

## 🗄️ PostgreSQL + Apache AGE Connection

### Connection Details

- **Host:** `postgres-age` (DNS via `jarvis-net`)
- **Port:** 5432
- **Database:** `${POSTGRES_DB}`
- **User:** `${POSTGRES_USER}`
- **Password:** `${POSTGRES_PASSWORD}`

### Test Connection

```bash
# From inside container
psql -h postgres-age -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT version();"

# Test AGE extension
psql -h postgres-age -U $POSTGRES_USER -d $POSTGRES_DB << 'EOF'
LOAD 'age';
SELECT * FROM ag_catalog.ag_graph;
EOF
```

### From Python

```python
import psycopg
import asyncpg

# Sync: psycopg3
conn = psycopg.connect("host=postgres-age user=$POSTGRES_USER password=$POSTGRES_PASSWORD dbname=$POSTGRES_DB")
cur = conn.cursor()
cur.execute("SELECT version();")
print(cur.fetchone())

# Async: asyncpg
async def test():
    pool = await asyncpg.create_pool('postgresql://user:pass@postgres-age/dbname')
    async with pool.acquire() as conn:
        result = await conn.fetch('SELECT version();')
        print(result)
```

### From Agent

The agent can execute SQL via:
1. `execute` tool (shell commands like `psql`)
2. Python scripts with psycopg/asyncpg imports
3. Subagents delegated for specific DB tasks

---

## 🐳 Docker-in-Docker Setup

### Configuration

**Mount:** `/var/run/docker.sock` (host → container)  
**Access:** Docker CLI + Python docker SDK  
**Purpose:** Agent spawns isolated containers for code execution, sandboxing, testing

### Verify Docker Access

```bash
# Inside container
docker ps
docker images
docker run --rm alpine echo "Hello from Docker"

# Verify Docker socket
ls -la /var/run/docker.sock
```

### Agent Usage

Pydantic-deep's `DockerSandbox` (via `SessionManager`):
1. Creates isolated per-session containers
2. Mounts workspace volumes
3. Executes arbitrary code safely
4. Cleans up after execution

**Example:**
```python
from pydantic_ai_backends import SessionManager, RuntimeConfig

session_manager = SessionManager(
    default_runtime=RuntimeConfig(name="python-datascience"),  # Pre-installed: pandas, numpy, matplotlib
    default_idle_timeout=3600,
    workspace_root="/workspace/jarvis/workspaces"
)

sandbox = await session_manager.get_or_create("user-123")
result = sandbox.execute("python -c 'import pandas; print(pandas.__version__)'")
```

---

## 📊 Observability: Logfire

### Configuration

**Base URL:** https://logfire-us.pydantic.dev (US instance)  
**Project:** 0wenwatt/jarvis-graph-agent  
**MCP Server:** https://logfire-us.pydantic.dev/mcp  
**Docs:** https://pydantic.dev/docs/logfire/

### Setup Steps

1. **Generate Logfire Token:**
   - Go to https://logfire-us.pydantic.dev
   - Sign in with credentials
   - Project: 0wenwatt/jarvis-graph-agent (create if needed)
   - Generate write token

2. **Set Environment Variables:**
   ```
   LOGFIRE_TOKEN=your_token_here
   LOGFIRE_PROJECT=0wenwatt/jarvis-graph-agent
   LOGFIRE_BASE_URL=https://logfire-us.pydantic.dev
   ```

3. **Verify app.py Configuration:**
   ```python
   import logfire
   logfire.configure(
       advanced=logfire.AdvancedOptions(base_url="https://logfire-us.pydantic.dev")
   )
   ```

4. **View Traces:**
   - Agent runs, tool calls, WebSocket events appear in Logfire Live view
   - Search by service name, span type, attributes
   - Trace distributed interactions across services

### What Gets Traced

- Agent initialization & configuration
- Each user message + response
- Tool execution (name, args, results, timing)
- Subagent delegation & interactions
- WebSocket streaming events
- Error/exception events with stack traces
- Skill loading & discovery
- Model response generation
- LLM token usage
- Checkpoint save/rewind operations

---

## 🎮 Keyboard Shortcuts & Common Commands

### In VSCode Integrated Terminal

```bash
# Navigate
cd /workspace/jarvis

# View logs
tail -f /tmp/code-server.log
tail -f /tmp/tailscale.log

# Check services
tailscale status
docker ps

# Verify Postgres
psql -h postgres-age -U $POSTGRES_USER -d $POSTGRES_DB -c "\dt"

# View environment
printenv | grep -E "(POSTGRES|GITHUB|ANTHROPIC|LOGFIRE|TAILSCALE)"

# Start FastAPI app (main command!)
uvicorn app:app --reload --host 0.0.0.0 --port 8000

# Test agent imports
python3 -c "from pydantic_deep import create_deep_agent; print('✓ Imports OK')"

# List skills
ls -la /workspace/jarvis/skills/

# Check Docker-in-Docker
docker run --rm alpine echo "✓ Docker works"
```

---

## 🔒 Security & Best Practices

### Secrets Management
- ✅ All secrets in `.env` (not in git)
- ✅ GitHub token for auth (no hardcoded passwords)
- ✅ Logfire write token in env, not in code
- ⚠️  **NEVER commit `.env` to git**

### Network Isolation
- ✅ Services use `jarvis-net` bridge (internal)
- ✅ Postgres only accessible from jarvis-dev + postgres-age
- ✅ code-server requires GitHub token auth
- ✅ FastAPI can be protected with API key middleware

### Resource Limits
- ✅ Hard memory: 2GB
- ✅ CPU: 2 cores
- ✅ Prevents runaway processes from crashing host

### Docker Security
- ✅ Docker socket mounted for agent sandboxing
- ⚠️  **Intentional:** Agent needs to spawn containers
- ✅ Per-session isolated workspaces

---

## 🐛 Troubleshooting

### Can't Connect to Postgres

```bash
# Check DNS
getent hosts postgres-age

# Test connectivity
psql -h postgres-age -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT 1;"

# Verify network
docker network inspect jarvis-net
docker inspect postgres-age | grep -A 10 Networks
docker inspect jarvis-dev | grep -A 10 Networks
```

### Can't Access code-server from Browser

```bash
# Check if running
ps aux | grep code-server

# View logs
cat /tmp/code-server.log

# Restart
pkill -f code-server
code-server --config /root/.config/code-server/config.yaml &
```

### Docker Commands Fail in Agent

```bash
# Verify socket
ls -la /var/run/docker.sock
docker ps

# Test permission
docker run --rm alpine whoami
```

**Fix:** Ensure docker-compose mounts `/var/run/docker.sock`

### Agent Can't Find Skills

```bash
# List skills
ls -la /workspace/jarvis/skills/

# Find SKILL.md
find /workspace/jarvis -name "SKILL.md"

# Verify full example skills
ls -la /workspace/jarvis/skills/production-postgres/SKILL.md
ls -la /workspace/jarvis/skills/production-docker/SKILL.md
```

### Tailscale Not Connecting

```bash
# Check status
tailscale status

# View logs
cat /tmp/tailscale.log

# Manual auth
tailscale up --authkey=$TAILSCALE_AUTHKEY
```

**Fix:** Regenerate auth key at https://login.tailscale.com/admin/settings/keys

---

## 📁 Directory Structure

```
/workspace/
├── jarvis/
│   ├── app.py                       # FastAPI full_app (start manually)
│   ├── requirements.txt             # Python dependencies
│   ├── SETUP_INFO.md               # This file
│   ├── audit_middleware.py         # Audit + permission capabilities
│   │
│   ├── skills/
│   │   ├── production-postgres/SKILL.md
│   │   ├── production-docker/SKILL.md
│   │   ├── data-analysis/SKILL.md
│   │   ├── code-review/SKILL.md
│   │   └── test-generator/SKILL.md
│   │
│   ├── static/                     # Frontend UI
│   │   ├── index.html
│   │   ├── styles.css
│   │   └── app.js
│   │
│   ├── workspaces/                 # Per-session isolated workspaces
│   │   └── {session_id}/
│   │       ├── workspace/          # Agent file operations
│   │       └── MEMORY.md           # Per-session persistent memory
│   │
│   └── workspace/                  # Workspace for file operations
│       └── (agent-generated files)

└── .env                            # Root env file (checked if /workspace/jarvis/.env not found)
```

---

## ✅ Next Steps

1. **Fill in `.env` file:**
   ```bash
   # Copy template
   cp /workspace/jarvis/.env.template /workspace/jarvis/.env
   
   # Edit with your values
   nano /workspace/jarvis/.env
   ```

2. **Start the container:**
   ```bash
   # From host
   docker compose -f docker-compose.yml up -d jarvis-dev
   
   # Or from existing container
   docker ps  # Verify it's running
   ```

3. **Access code-server:**
   - Browser: https://localhost:8443
   - Authenticate with GitHub token
   - Terminal appears at bottom

4. **Start FastAPI app (in terminal):**
   ```bash
   cd /workspace/jarvis
   uvicorn app:app --reload --host 0.0.0.0 --port 8000
   ```

5. **Access FastAPI UI:**
   - Browser: http://localhost:8000
   - Start chatting with the agent!

6. **Test database:**
   ```bash
   psql -h postgres-age -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT version();"
   ```

7. **View Logfire traces:**
   - Go to https://logfire-us.pydantic.dev
   - Navigate to 0wenwatt/jarvis-graph-agent
   - Watch traces appear in Live view

---

## 📖 Documentation & Links

- **Pydantic Deep Agents:** https://github.com/vstorm-co/pydantic-deepagents
- **Full Example:** https://github.com/vstorm-co/pydantic-deepagents/tree/main/examples/full_app
- **Production Skills:** https://github.com/vstorm-co/production-stack-skills
- **code-server:** https://coder.com/docs/code-server/latest
- **Tailscale:** https://tailscale.com/docs/
- **Logfire:** https://pydantic.dev/docs/logfire/
- **FastAPI:** https://fastapi.tiangolo.com/
- **Docker:** https://docs.docker.com/

---

**Status:** ✅ Ready for development  
**Last Updated:** 2025-10-22  
**Container:** jarvis-dev  
**Network:** jarvis-net
