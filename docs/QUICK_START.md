# Jarvis Dev Environment — Quick Reference

## 🚀 Start

```bash
# 1. Fill .env
nano C:\Users\Owen\jarvis-dev\.env
# Minimum: GITHUB_TOKEN, ANTHROPIC_API_KEY, POSTGRES_* vars

# 2. Start container
cd C:\Users\Owen\jarvis-dev
docker compose up -d jarvis-dev

# 3. Access code-server
# Browser: https://localhost:8443

# 4. Start FastAPI (in code-server terminal)
cd /workspace/jarvis
uvicorn app:app --reload --host 0.0.0.0 --port 8000

# 5. Access agent UI
# Browser: http://localhost:8000
```

---

## 🔌 Ports

- **8443** → code-server (VSCode)
- **8000** → FastAPI (Agent UI)
- **5432** → Postgres (via jarvis-net)

---

## 📁 Files

| File | Purpose |
|------|---------|
| `.env` | **Fill this** with your credentials |
| `.env.template` | Configuration template |
| `docker-compose.yml` | Container orchestration |
| `Dockerfile` | Container image definition |
| `requirements.txt` | Python dependencies |
| `DEPLOYMENT_SUMMARY.md` | Full setup summary (this folder) |
| `workspace/jarvis/SETUP_INFO.md` | Detailed setup docs (in container) |
| `workspace/jarvis/app.py` | FastAPI agent application |

---

## 🔑 Required .env Fields

```ini
GITHUB_TOKEN=ghp_xxxxx              # For code-server auth
ANTHROPIC_API_KEY=sk-ant-xxxxx      # For LLM
POSTGRES_HOST=postgres-age          # Don't change
POSTGRES_PORT=5432                  # Don't change
POSTGRES_DB=your_database           # Fill in
POSTGRES_USER=your_user             # Fill in
POSTGRES_PASSWORD=your_password     # Fill in
```

---

## ✅ Verify Working

```bash
# Check container
docker ps | grep jarvis-dev

# Check Postgres
docker exec jarvis-dev psql -h postgres-age -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT 1;"

# Check Docker-in-Docker
docker exec jarvis-dev docker ps

# Check Python
docker exec jarvis-dev python3 -c "from pydantic_deep import create_deep_agent; print('✓')"

# Access in browser
# code-server: https://localhost:8443
# FastAPI: http://localhost:8000 (after manual start)
```

---

## 🛠️ Common Commands

```bash
# SSH into container
docker exec -it jarvis-dev bash

# View code-server logs
docker exec jarvis-dev tail -f /tmp/code-server.log

# View Tailscale logs
docker exec jarvis-dev tail -f /tmp/tailscale.log

# Restart code-server
docker exec jarvis-dev pkill -f code-server

# List skills
docker exec jarvis-dev ls -la /workspace/jarvis/skills/*/SKILL.md

# Stop container
docker compose -f docker-compose.yml down jarvis-dev

# Remove container
docker rm jarvis-dev

# View resources
docker stats jarvis-dev
```

---

## 🐛 Issues

| Issue | Fix |
|-------|-----|
| Can't access https://localhost:8443 | Wait 10s after `docker compose up`, restart code-server: `docker exec jarvis-dev pkill -f code-server` |
| Postgres connection error | Verify: `docker network inspect jarvis-net` |
| FastAPI won't start | Check: `docker exec jarvis-dev python3 -c "from app import app; print('OK')"` |
| Docker commands fail in agent | Verify: `docker exec jarvis-dev docker ps` |
| Memory/CPU issues | Check limits: `docker inspect jarvis-dev \| grep -A 5 Memory` |

---

## 📚 Documentation

- **In host:** `C:\Users\Owen\jarvis-dev\DEPLOYMENT_SUMMARY.md` (this guide)
- **In container:** `/workspace/jarvis/SETUP_INFO.md` (detailed setup)
- **Pydantic Deep:** https://github.com/vstorm-co/pydantic-deepagents
- **Full Example:** https://github.com/vstorm-co/pydantic-deepagents/tree/main/examples/full_app
- **Skills:** https://github.com/vstorm-co/production-stack-skills

---

## 💡 Tips

1. **code-server:** SSH tunnel for remote access: `ssh -L 8443:localhost:8443 user@host`
2. **FastAPI:** Use `--reload` to auto-restart on code changes
3. **Agent:** Upload files via web UI; agent accesses via `/uploads/` path
4. **Docker:** Agent spawns isolated containers for safe code execution
5. **Postgres:** Both containers on `jarvis-net` can DNS resolve each other

---

**Status:** ✅ Ready  
**Container Image:** `jarvis-dev:latest` (2.65 GB)  
**Network:** `jarvis-net`  
**Created:** 2025-10-22
