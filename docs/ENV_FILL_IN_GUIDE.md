# 🎯 How to Fill In Your `.env` File — Complete Guide

Your Jarvis environment is **100% ready**. You just need to fill in your API keys.

---

## 📍 File Location

**Edit this file:**  
`C:\Users\Owen\jarvis-dev\.env`

**Using any editor:**
- Notepad / VSCode / nano / any text editor

---

## 🔑 Your API Keys

You have **3 new keys** + existing **2 keys**:

| Provider | Key Type | Status |
|----------|----------|--------|
| Anthropic | Existing | ✅ You have it |
| OpenAI | Existing | ✅ You have it |
| Gemini | New | ← Add this |
| Groq | New | ← Add this |
| Mistral | New | ← Add this |

---

## 📝 Step-by-Step Fill-In

### 1. Open Your `.env` File

```bash
# On Windows, use:
notepad C:\Users\Owen\jarvis-dev\.env

# Or in VSCode:
code C:\Users\Owen\jarvis-dev\.env
```

### 2. Find These Sections and Fill Them In

#### GITHUB_TOKEN (Required)
```ini
# Find this line:
GITHUB_TOKEN=

# Fill it with your GitHub token:
GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

#### ANTHROPIC (You already have this)
```ini
# Find this line:
ANTHROPIC_API_KEY=sk-ant-

# Fill it:
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
```

#### OPENAI (You already have this)
```ini
# Find this line:
OPENAI_API_KEY=sk-

# Fill it:
OPENAI_API_KEY=sk-xxxxxxxxxxxx
```

#### GEMINI (NEW — Add your key)
```ini
# Find this line:
GEMINI_API_KEY=

# Get key at: https://aistudio.google.com/app/apikeys
# Click "Create API Key"
# Copy and paste:
GEMINI_API_KEY=AIzaSyDxxxxxxxxx
```

#### GROQ (NEW — Add your key)
```ini
# Find this line:
GROQ_API_KEY=

# Get key at: https://console.groq.com/keys
# Click "Create API Key"
# Copy and paste:
GROQ_API_KEY=gsk_xxxxxxxxxxxx
```

#### MISTRAL (NEW — Add your key)
```ini
# Find this line:
MISTRAL_API_KEY=aI1

# Get key at: https://console.mistral.ai/api-keys/
# Click "Create API Key"
# Copy and paste:
MISTRAL_API_KEY=aI1xxxxxxxxxxxx
```

#### POSTGRES (Required — Your database)
```ini
# Find these lines:
POSTGRES_HOST=postgres-age
POSTGRES_PORT=5432
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=

# Fill in your database credentials:
POSTGRES_HOST=postgres-age            # Don't change this
POSTGRES_PORT=5432                    # Don't change this
POSTGRES_DB=your_database_name        # Fill in
POSTGRES_USER=your_database_user      # Fill in
POSTGRES_PASSWORD=your_database_pass  # Fill in
```

#### AGENT_MODEL (Which model to use by default)
```ini
# Find this line:
AGENT_MODEL=anthropic:claude-sonnet-4-6

# This is already set to Claude (recommended)
# You can change it to:
#   - openai:gpt-4o
#   - google:gemini-2.0-flash
#   - groq:llama-3.1-405b
#   - mistral:mistral-large-latest

# Leave as-is or change as you prefer
```

---

## ✅ Minimal Configuration (Get Running NOW)

If you just want to get started, fill in ONLY these fields:

```ini
# Required for code-server access
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# Required for LLM (pick ONE provider, or add all as backups)
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
GROQ_API_KEY=gsk_xxxxxxxxxxxx
GEMINI_API_KEY=AIzaSyDxxxxxxxxx

# Required for database
POSTGRES_HOST=postgres-age
POSTGRES_PORT=5432
POSTGRES_DB=your_database_name
POSTGRES_USER=your_database_user
POSTGRES_PASSWORD=your_database_password

# Which model to use
AGENT_MODEL=anthropic:claude-sonnet-4-6
```

That's it! Restart the container and you're done.

---

## 🎁 Full Configuration (Recommended)

Fill in all of these for maximum flexibility:

```ini
# GitHub
GITHUB_TOKEN=ghp_xxxxxxxxxxxx

# ALL LLM Providers (you can switch between any in the web UI)
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
OPENAI_API_KEY=sk-xxxxxxxxxxxx
GEMINI_API_KEY=AIzaSyDxxxxxxxxx
GROQ_API_KEY=gsk_xxxxxxxxxxxx
MISTRAL_API_KEY=aI1xxxxxxxxxxxx

# Database
POSTGRES_HOST=postgres-age
POSTGRES_PORT=5432
POSTGRES_DB=your_database_name
POSTGRES_USER=your_database_user
POSTGRES_PASSWORD=your_database_password

# Logfire (optional — for observability)
LOGFIRE_TOKEN=                    # If you set this up
LOGFIRE_PROJECT=0wenwatt/jarvis-graph-agent
LOGFIRE_BASE_URL=https://logfire-us.pydantic.dev

# Tailscale (optional — for remote access)
TAILSCALE_AUTHKEY=                # If you use Tailscale

# Agent defaults
AGENT_MODEL=anthropic:claude-sonnet-4-6
AGENT_THINKING=medium
AGENT_BUDGET_USD=10
```

---

## 🚀 After Filling In `.env`

### Step 1: Save the file
```bash
# Ctrl+S in editor or just close & save in notepad
```

### Step 2: Restart the container
```bash
cd C:\Users\Owen\jarvis-dev
docker compose down jarvis-dev
docker compose up -d jarvis-dev
```

### Step 3: Wait 10 seconds for startup

### Step 4: Access in browser
```
code-server: https://localhost:8443
FastAPI:     http://localhost:8000
```

### Step 5: In code-server terminal, start FastAPI
```bash
cd /workspace/jarvis
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### Step 6: Access FastAPI UI
```
http://localhost:8000
```

### Step 7: Test a model
- In the web UI, select a model from the dropdown (e.g., Gemini, Groq, Claude)
- Type "hello"
- See the response

✅ **Done!** All 3 new providers are working.

---

## 🔍 How to Get Each Key

### GitHub Token
1. Go to: https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Check: `read:user`
4. Generate & copy
5. Paste into `GITHUB_TOKEN=`

### Anthropic (You already have this)
1. Go to: https://console.anthropic.com/keys
2. Click "Create Key"
3. Copy
4. Paste into `ANTHROPIC_API_KEY=sk-ant-`

### OpenAI (You already have this)
1. Go to: https://platform.openai.com/account/api-keys
2. Click "Create new secret key"
3. Copy
4. Paste into `OPENAI_API_KEY=sk-`

### Google Gemini (NEW)
1. Go to: https://aistudio.google.com/app/apikeys
2. Click "Create API Key"
3. Choose "Create API key in new Google Cloud project"
4. Copy
5. Paste into `GEMINI_API_KEY=`

**Free! 1M input tokens/day, 100K output tokens/day**

### Groq (NEW)
1. Go to: https://console.groq.com/keys
2. Sign up (1 minute)
3. Click "Create API Key"
4. Copy
5. Paste into `GROQ_API_KEY=gsk_`

**Very cheap! ~$0.01 per million tokens. Super fast.**

### Mistral (NEW)
1. Go to: https://console.mistral.ai/api-keys/
2. Sign up (1 minute)
3. Click "Create API Key"
4. Copy
5. Paste into `MISTRAL_API_KEY=aI1`

**Competitive pricing. European data residency option.**

### Database Credentials (Postgres)
1. Get from your postgres-age container setup
2. Or ask whoever set up the database
3. Fill in: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`

---

## ❓ FAQ

**Q: Do I need ALL 5 providers?**  
A: No. Pick at least 1 (Anthropic recommended). Others are optional but useful as backups.

**Q: Can I change the primary model later?**  
A: Yes! Change `AGENT_MODEL` in `.env` and restart, OR select in the web UI dropdown.

**Q: What if I get errors?**  
A: Check:
1. API keys are full and not truncated
2. No extra spaces at start/end
3. File is saved
4. Container restarted: `docker compose down && docker compose up -d`

**Q: Which model is fastest?**  
A: Groq (responses in <1 second)

**Q: Which is cheapest?**  
A: Gemini (free!) then Groq (~$0.01/MTok)

**Q: Which is best for complex tasks?**  
A: Claude Sonnet 4-6 or GPT-4o

---

## 📚 Documentation Files

After you fill in `.env`, read these for more context:

1. **FILL_IN_KEYS.md** — Quick reference for your 3 new keys (Gemini, Groq, Mistral)
2. **MODEL_SELECTION.md** — Detailed comparison of all models (15+ options)
3. **GATEWAY_vs_DIRECT.md** — Optional: cost tracking with Pydantic AI Gateway
4. **QUICK_START.md** — After filling .env, next steps to run the app
5. **SETUP_INFO.md** — Inside the container at `/workspace/jarvis/SETUP_INFO.md`

---

## ✨ You're Ready

Once `.env` is filled:

```bash
docker compose up -d jarvis-dev
# Access code-server: https://localhost:8443
# Start FastAPI in terminal
# Access UI: http://localhost:8000
# Switch models in dropdown
# Chat with agent!
```

All 5 providers ready. All 15+ models available. All features working.

---

**Questions?** Read MODEL_SELECTION.md or GATEWAY_vs_DIRECT.md

**Next step:** Fill in `.env` and run the container.
