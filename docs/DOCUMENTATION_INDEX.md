# 📚 Jarvis Development Environment — Documentation Index

Your complete Jarvis setup is ready. Here's what goes where and what to read.

---

## 🎯 START HERE

**New to this? Read these in order:**

1. **ENV_FILL_IN_GUIDE.md** ← **READ THIS FIRST**
   - Step-by-step how to fill in your `.env` file
   - Where to get your 3 new API keys (Gemini, Groq, Mistral)
   - Takes 10 minutes

2. **QUICK_START.md** 
   - After you fill `.env`, run these commands
   - Access code-server & FastAPI UI
   - How to test each model

3. **SETUP_INFO.md** (inside container at `/workspace/jarvis/SETUP_INFO.md`)
   - Complete technical reference
   - All services, skills, troubleshooting
   - Read if something breaks

---

## 📖 Reference Guides

### API & Model Information

**MODEL_SELECTION.md**
- Detailed comparison of all 15+ models
- Speed, cost, capability matrix
- When to use each provider
- How to switch models at runtime

**FILL_IN_KEYS.md**
- Quick reference for your 3 new API keys
- Copy/paste instructions
- Verification commands

**GATEWAY_vs_DIRECT.md** ⭐ **Important**
- **Explains Pydantic AI Gateway** (what you asked about)
- Direct API keys vs Gateway (which to use)
- Hybrid approach (use both)
- Cost tracking & observability
- Routing groups & failover

### Container & Deployment

**DEPLOYMENT_SUMMARY.md**
- Complete setup summary
- What was built (2.65 GB image)
- Services, ports, volumes
- Resource limits
- Verification checklist

**docker-compose.yml**
- Container orchestration config
- Port mappings (8443, 8000)
- Volume mounts
- Resource limits (2GB RAM, 2 CPU)
- Network setup

**Dockerfile**
- Base image: Ubuntu 22.04
- System packages installed
- Python packages (850+ MB)
- Startup scripts
- Entrypoint configuration

---

## 📁 Configuration Files

### `.env` Files

**`.env`** ← **FILL THIS IN**
- Your API keys go here
- Database credentials
- Model selection
- Logfire token (optional)
- Tailscale key (optional)

**`.env.template`**
- Comprehensive template with 200+ lines
- Every field documented
- Examples & defaults
- Reference for all available options

**`.gitignore`** (implied)
- **Never commit `.env` to git**
- Secrets are in `.env`, not in code

### Other Config

**requirements.txt**
- Python dependencies (50+ packages)
- Including all LLM provider SDKs:
  - anthropic
  - openai
  - google-generativeai
  - groq
  - mistralai
- FastAPI, logfire, pydantic-deep, etc.

**docker-compose.yml**
- All services defined
- Postgres, jarvis-dev on jarvis-net
- Port mappings & volumes
- Resource limits

---

## 📋 Quick Reference

### File Locations (On Your Windows PC)

```
C:\Users\Owen\jarvis-dev\
├── ENV_FILL_IN_GUIDE.md      ← Start here
├── QUICK_START.md             ← Then here
├── MODEL_SELECTION.md         ← Reference
├── FILL_IN_KEYS.md            ← Your 3 new keys
├── GATEWAY_vs_DIRECT.md       ← ⭐ Important
├── DEPLOYMENT_SUMMARY.md      ← Full reference
│
├── .env                       ← Fill this in!
├── .env.template              ← Reference copy
├── requirements.txt           ← Python packages
├── Dockerfile                 ← Container image
├── docker-compose.yml         ← Orchestration
│
├── workspace/
│   └── jarvis/
│       ├── SETUP_INFO.md      ← Inside container
│       ├── app.py             ← FastAPI main app
│       ├── github_tools.py
│       ├── audit_middleware.py
│       ├── skills/
│       │   ├── production-postgres/
│       │   ├── production-docker/
│       │   └── [other skills]
│       ├── static/             ← Web UI
│       └── workspaces/         ← Per-session data
│
└── code-server-config/        ← VSCode settings

```

### Services & Ports

| Service | Port | URL | Purpose |
|---------|------|-----|---------|
| code-server | 8443 | https://localhost:8443 | VSCode editor |
| FastAPI | 8000 | http://localhost:8000 | Agent chat UI |
| Postgres | 5432 | Via jarvis-net | Database |
| Docker | /var/run/docker.sock | Socket mount | Agent sandboxing |

### Key Directories in Container

| Path | Purpose |
|------|---------|
| `/workspace/jarvis/` | Agent code & workspace |
| `/workspace/jarvis/skills/` | Skills (postgres, docker, etc.) |
| `/workspace/jarvis/static/` | Web UI (HTML/CSS/JS) |
| `/workspace/jarvis/workspaces/` | Per-session data |
| `/tmp/code-server.log` | code-server logs |
| `/tmp/tailscale.log` | Tailscale logs |

---

## 🔑 Your API Keys Checklist

- [ ] GitHub Token — https://github.com/settings/tokens
- [ ] Anthropic (existing) — https://console.anthropic.com/keys
- [ ] OpenAI (existing) — https://platform.openai.com/account/api-keys
- [ ] Gemini (NEW) — https://aistudio.google.com/app/apikeys
- [ ] Groq (NEW) — https://console.groq.com/keys
- [ ] Mistral (NEW) — https://console.mistral.ai/api-keys/
- [ ] Postgres credentials — From your database setup
- [ ] Optional: Logfire token — https://logfire.pydantic.dev/ (for cost tracking)
- [ ] Optional: Tailscale auth key — https://login.tailscale.com/admin/settings/keys

---

## 🚀 Execution Path (What to Do)

### Phase 1: Setup (10 minutes)
1. Read **ENV_FILL_IN_GUIDE.md**
2. Get your 3 new API keys (Gemini, Groq, Mistral)
3. Fill in `.env` file with all credentials
4. Save the file

### Phase 2: Run (2 minutes)
1. Open terminal
2. Run: `docker compose down jarvis-dev && docker compose up -d jarvis-dev`
3. Wait 10 seconds for startup

### Phase 3: Access (1 minute)
1. code-server: https://localhost:8443
2. FastAPI: http://localhost:8000 (after manual start in terminal)

### Phase 4: Test (5 minutes)
1. Start FastAPI app in code-server terminal
2. Access FastAPI UI
3. Select different models from dropdown
4. Chat with each provider

### Phase 5: Learn (Optional)
1. Read **MODEL_SELECTION.md** for details on each model
2. Read **GATEWAY_vs_DIRECT.md** to learn about advanced cost tracking
3. Read **SETUP_INFO.md** for complete technical reference

---

## ❓ Common Questions

**Q: Where do I fill in my API keys?**  
A: `C:\Users\Owen\jarvis-dev\.env` — see ENV_FILL_IN_GUIDE.md

**Q: What do I do after filling `.env`?**  
A: Restart container + access code-server — see QUICK_START.md

**Q: Which model should I use?**  
A: Claude Sonnet 4-6 (recommended). Details in MODEL_SELECTION.md

**Q: How do I switch models?**  
A: In FastAPI web UI dropdown or change AGENT_MODEL in `.env`

**Q: What's Pydantic AI Gateway?**  
A: Single unified API key + cost tracking. Read GATEWAY_vs_DIRECT.md

**Q: How many models can I use?**  
A: 15+ models across 5 providers (if all keys configured)

**Q: Which is fastest?**  
A: Groq (llama-3.1-405b) — responses in <1 second

**Q: Which is cheapest?**  
A: Gemini (FREE!) or Groq (~$0.01/MTok)

**Q: Can I use multiple providers simultaneously?**  
A: Yes. Configure all keys, switch via dropdown per query

**Q: What if a provider is down?**  
A: Use another provider (all configured as fallbacks)

---

## 🛠️ Troubleshooting Quick Links

**Can't access code-server?**
→ Restart: `docker exec jarvis-dev pkill -f code-server`

**FastAPI won't start?**
→ Check: `docker exec jarvis-dev python3 -c "from app import app; print('OK')"`

**Postgres connection fails?**
→ Verify: `docker network inspect jarvis-net`

**Model returns errors?**
→ Check: API key is full, no spaces, container restarted

**Memory/CPU issues?**
→ Check limits: `docker inspect jarvis-dev | grep -A 5 Memory`

**More issues?**
→ Read SETUP_INFO.md (comprehensive troubleshooting section)

---

## 📚 Documentation by Topic

### Getting Started
- ENV_FILL_IN_GUIDE.md
- QUICK_START.md

### API Keys & Models
- FILL_IN_KEYS.md
- MODEL_SELECTION.md

### Advanced
- GATEWAY_vs_DIRECT.md
- DEPLOYMENT_SUMMARY.md

### Reference
- SETUP_INFO.md (in container)
- Dockerfile
- docker-compose.yml
- requirements.txt

### Troubleshooting
- SETUP_INFO.md (Troubleshooting section)
- DEPLOYMENT_SUMMARY.md (Verification checklist)

---

## ✅ Verification

After filling `.env` and starting container:

```bash
# 1. Container running
docker ps | grep jarvis-dev

# 2. code-server accessible
https://localhost:8443

# 3. Database connected
docker exec jarvis-dev psql -h postgres-age -U $POSTGRES_USER -d $POSTGRES_DB -c "SELECT 1;"

# 4. Models working
docker exec jarvis-dev python3 -c "from pydantic_ai import Agent; print('✓')"

# 5. Skills loaded
docker exec jarvis-dev ls /workspace/jarvis/skills/*/SKILL.md

# 6. FastAPI ready
docker exec jarvis-dev python3 -c "from app import app; print('✓ FastAPI')"
```

---

## 🎯 Next Steps (Right Now)

1. **Read:** ENV_FILL_IN_GUIDE.md (10 min)
2. **Get:** Your 3 new API keys (10 min)
3. **Fill:** `.env` file (5 min)
4. **Run:** `docker compose up -d jarvis-dev` (2 min)
5. **Access:** https://localhost:8443 (code-server)
6. **Test:** FastAPI UI at http://localhost:8000

**Total time:** ~30 minutes to full working system

---

## 🔗 External Links

- **Pydantic AI Gateway:** https://pydantic.dev/docs/ai/overview/gateway/
- **Pydantic AI Docs:** https://docs.pydantic.dev/latest/api/pydantic_ai/
- **Pydantic Deep Agents:** https://github.com/vstorm-co/pydantic-deepagents
- **Production Skills:** https://github.com/vstorm-co/production-stack-skills
- **code-server Docs:** https://coder.com/docs/code-server/latest
- **Logfire:** https://logfire.pydantic.dev/
- **Tailscale:** https://tailscale.com/docs/

---

**Status:** ✅ Everything is built and ready.  
**Next action:** Read ENV_FILL_IN_GUIDE.md and fill in `.env`

Questions? Each document has a troubleshooting section or FAQ.
