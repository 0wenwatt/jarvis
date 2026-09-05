# Quick Fill-In Guide: Gemini, Groq, Mistral + Your Existing Keys

You have **3 new API keys** to add. Here's exactly where to put them in your `.env` file.

---

## 📍 File Location

**Edit this file:**  
`C:\Users\Owen\jarvis-dev\.env`

**Use any editor:**
- Notepad
- VSCode
- Nano in terminal: `nano C:\Users\Owen\jarvis-dev\.env`

---

## 📝 What to Add

Open `.env` and find/update these sections:

### Section: LLM API Keys

```ini
# ==================================================
# 2. LLM API KEYS — MULTIPLE PROVIDERS
# ==================================================

# --- ANTHROPIC (you likely already have this) ---
ANTHROPIC_API_KEY=sk-ant-xxxxx

# --- OPENAI (optional, if you have it) ---
OPENAI_API_KEY=sk-xxxxx

# --- GOOGLE GEMINI (NEW — add your key here) ---
GEMINI_API_KEY=xxxxx

# --- GROQ (NEW — add your key here) ---
GROQ_API_KEY=gsk_xxxxx

# --- MISTRAL (NEW — add your key here) ---
MISTRAL_API_KEY=aI1xxxxx
```

---

## 🔑 Your 3 New Keys — Where to Get Them

### 1️⃣ GEMINI_API_KEY

**Get it:**
1. Go to: https://aistudio.google.com/app/apikeys
2. Click "Create API Key"
3. Choose "Create API key in new Google Cloud project" (or select existing)
4. Copy the key (looks like: `AIzaSyDxxxxxxxxx`)

**Fill in `.env`:**
```ini
GEMINI_API_KEY=AIzaSyDxxxxxxxxx
```

**Cost:** FREE! Up to 1M input tokens/day, 100K output tokens/day

---

### 2️⃣ GROQ_API_KEY

**Get it:**
1. Go to: https://console.groq.com/keys
2. Sign up (takes 1 minute)
3. Click "Create API Key"
4. Copy the key (looks like: `gsk_xxxxx`)

**Fill in `.env`:**
```ini
GROQ_API_KEY=gsk_xxxxx
```

**Cost:** Very cheap, ~$0.01 per million tokens

---

### 3️⃣ MISTRAL_API_KEY

**Get it:**
1. Go to: https://console.mistral.ai/api-keys/
2. Sign up (takes 1 minute)
3. Click "Create API Key"
4. Copy the key (looks like: `aI1xxxxx`)

**Fill in `.env`:**
```ini
MISTRAL_API_KEY=aI1xxxxx
```

**Cost:** Competitive, ~$0.14-2 per million tokens (depends on model)

---

## ✅ Complete `.env` Fill-In (Minimal)

Here's what your `.env` should look like with all three new keys + your existing setup:

```ini
# GitHub OAuth (fill in if you don't have it)
GITHUB_TOKEN=ghp_xxxxx

# Your existing LLM keys
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx

# NEW: Your three new keys
GEMINI_API_KEY=AIzaSyDxxxxxxxxx
GROQ_API_KEY=gsk_xxxxx
MISTRAL_API_KEY=aI1xxxxx

# Which model to use by default
AGENT_MODEL=anthropic:claude-sonnet-4-6

# Database
POSTGRES_HOST=postgres-age
POSTGRES_PORT=5432
POSTGRES_DB=your_database
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password

# Logfire (optional)
LOGFIRE_TOKEN=

# Tailscale (optional)
TAILSCALE_AUTHKEY=

# code-server (fallback password)
CODE_SERVER_PASSWORD=changeme
```

---

## 🚀 After Filling In

### Step 1: Restart Container

```bash
cd C:\Users\Owen\jarvis-dev
docker compose down jarvis-dev
docker compose up -d jarvis-dev
```

### Step 2: Access FastAPI

1. Open browser: `http://localhost:8000`
2. Start a new chat
3. Look for **Model selector dropdown** at the top or sidebar
4. You should see ALL these options:
   - anthropic:claude-sonnet-4-6
   - openai:gpt-4o
   - google:gemini-2.0-flash ← NEW
   - groq:llama-3.1-405b ← NEW
   - mistral:mistral-large-latest ← NEW

### Step 3: Test Each Model

Type a test message with each model to verify they all work:

1. **Select Gemini 2.0 Flash** → type "hello" → should get response
2. **Select Groq Llama** → type "hello" → should get response
3. **Select Mistral Large** → type "hello" → should get response

✅ If all three work, you're done!

---

## 📋 Model Selector in FastAPI UI

Once running, the web UI will let you pick any model:

```
┌─────────────────────────────────────┐
│ Model: [dropdown ▼]                 │
│  anthropic:claude-sonnet-4-6        │
│  anthropic:claude-opus-4-1          │
│  anthropic:claude-haiku-4-5         │
│  openai:gpt-4o                      │
│  google:gemini-2.0-flash     ← NEW  │
│  google:gemini-1.5-pro       ← NEW  │
│  groq:llama-3.1-405b         ← NEW  │
│  mistral:mistral-large       ← NEW  │
│  [+ more if configured]             │
└─────────────────────────────────────┘
```

Just click the dropdown and select any model you want to test.

---

## 🎯 My Recommendation for You

Since you have all 5 providers:

1. **Primary:** `anthropic:claude-sonnet-4-6` (most reliable)
2. **Backup Fast:** `groq:llama-3.1-405b` (super fast + cheap)
3. **Free Testing:** `google:gemini-2.0-flash` (free tier, great quality)

Set `AGENT_MODEL=anthropic:claude-sonnet-4-6` as default, but you can instantly switch to any of the others in the web UI dropdown.

---

## ❓ Quick FAQ

**Q: Do I need all 5 providers?**  
A: No. Fill in at least ONE. Multiple is nice for testing/fallback.

**Q: Which one should be my primary?**  
A: Stick with Anthropic Claude Sonnet 4-6. It's the most reliable for agent tasks.

**Q: Can I change the primary model?**  
A: Yes. Change `AGENT_MODEL` in `.env` and restart, OR select in the web UI dropdown.

**Q: What if I get a key error?**  
A: Double-check you copied the full key correctly (no extra spaces). Restart the container: `docker compose down && docker compose up -d jarvis-dev`

**Q: Which model is fastest?**  
A: Groq (llama-3.1-405b). Responses in <1 second.

**Q: Which is cheapest?**  
A: Gemini 2.0 Flash (FREE up to 1M tokens/day).

**Q: Which is best for complex code tasks?**  
A: Claude Sonnet 4-6 or OpenAI GPT-4o. Both excellent for reasoning.

---

## 🔗 Your Files

**Main config:** `C:\Users\Owen\jarvis-dev\.env` ← **EDIT THIS**  
**Template reference:** `C:\Users\Owen\jarvis-dev\.env.template`  
**Detailed guide:** `C:\Users\Owen\jarvis-dev\MODEL_SELECTION.md`

---

## ✨ Done!

Once you've:
1. ✅ Added your 3 new API keys to `.env`
2. ✅ Restarted the container
3. ✅ Tested models in the web UI

You can:
- Switch between 15+ models instantly in the UI
- Mix & match providers for testing
- Use fallback models if primary is down
- Pay only for what you use (Gemini free tier!)

🚀 That's it!
