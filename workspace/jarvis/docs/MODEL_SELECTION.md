# LLM Model Selection Guide — 5 Providers, 15+ Models

Your Jarvis environment supports **5 LLM providers** with **15+ models**. This guide explains each, how to configure them, and when to use which.

---

## 📊 Quick Comparison

| Provider | Model | Speed | Cost | Capability | Use Case |
|----------|-------|-------|------|-----------|----------|
| **Anthropic** | claude-sonnet-4-6 | Medium | $$$ | ⭐⭐⭐⭐⭐ | Best all-around, recommended primary |
| **Anthropic** | claude-opus-4-1 | Slow | $$$$ | ⭐⭐⭐⭐⭐ | Most capable, complex tasks |
| **Anthropic** | claude-haiku-4-5 | Fast | $ | ⭐⭐⭐ | Quick responses, simple tasks |
| **OpenAI** | gpt-4o | Medium | $$$ | ⭐⭐⭐⭐⭐ | Strong alternative, multimodal |
| **OpenAI** | gpt-4-turbo | Medium | $$ | ⭐⭐⭐⭐ | Balanced performance & cost |
| **OpenAI** | gpt-3.5-turbo | Fast | $ | ⭐⭐⭐ | Budget option |
| **Google Gemini** | gemini-2.0-flash | ⚡⚡⚡ | FREE | ⭐⭐⭐⭐ | Free tier, very fast, excellent |
| **Google Gemini** | gemini-1.5-pro | Medium | $ | ⭐⭐⭐⭐⭐ | Most capable Gemini |
| **Google Gemini** | gemini-1.5-flash | Fast | $ | ⭐⭐⭐ | Budget Gemini |
| **Groq** | llama-3.1-405b | ⚡⚡⚡ | $ | ⭐⭐⭐⭐ | Fastest open-source, excellent quality |
| **Groq** | mixtral-8x7b | ⚡⚡⚡ | $ | ⭐⭐⭐ | Fast, balanced |
| **Groq** | gemma-7b | ⚡⚡⚡ | $ | ⭐⭐ | Fast, lightweight |
| **Mistral** | mistral-large-latest | Medium | $$ | ⭐⭐⭐⭐⭐ | Capable European alternative |
| **Mistral** | mistral-medium-latest | Medium | $ | ⭐⭐⭐⭐ | Balanced Mistral |
| **Mistral** | mistral-small-latest | Fast | $ | ⭐⭐⭐ | Budget Mistral |

---

## 🔑 API Key Setup

### 1. Anthropic (Recommended Primary)

**Get API Key:**
1. Go to https://console.anthropic.com/keys
2. Click "Create Key"
3. Copy the key (starts with `sk-ant-`)

**In `.env`:**
```ini
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
AGENT_MODEL=anthropic:claude-sonnet-4-6
```

**Pricing:** https://www.anthropic.com/pricing  
**Recommended Model:** `claude-sonnet-4-6` (best balance of capability, speed, cost)

---

### 2. OpenAI (Strong Alternative)

**Get API Key:**
1. Go to https://platform.openai.com/account/api-keys
2. Click "Create new secret key"
3. Copy the key (starts with `sk-`)

**In `.env`:**
```ini
OPENAI_API_KEY=sk-xxxxxxxxxxxx
AGENT_MODEL=openai:gpt-4o
```

**Pricing:** https://openai.com/pricing  
**Recommended Model:** `gpt-4o` (latest, fast, capable)

---

### 3. Google Gemini (FREE!)

**Get API Key:**
1. Go to https://aistudio.google.com/app/apikeys
2. Click "Create API Key"
3. Copy the key (no prefix)

**In `.env`:**
```ini
GEMINI_API_KEY=xxxxxxxxxxxx
AGENT_MODEL=google:gemini-2.0-flash
```

**Pricing:** FREE for Gemini 1.5 (up to 1M input tokens/day)  
**Recommended Model:** `gemini-2.0-flash` (very fast, multimodal, excellent for free tier)

**⚠️ WARNING:** Some Gemini models have restricted features (no tool use on certain variants). If you encounter issues, fall back to `anthropic:claude-sonnet-4-6`.

---

### 4. Groq (VERY FAST & CHEAP)

**Get API Key:**
1. Go to https://console.groq.com/keys
2. Click "Create API Key"
3. Copy the key (starts with `gsk_`)

**In `.env`:**
```ini
GROQ_API_KEY=gsk_xxxxxxxxxxxx
AGENT_MODEL=groq:llama-3.1-405b
```

**Pricing:** https://groq.com/pricing/ (Extremely cheap, near free for heavy use)  
**Recommended Model:** `llama-3.1-405b` (fastest inference, excellent quality)

**Use Case:** When you need super fast responses and cost efficiency. Groq specializes in inference speed.

---

### 5. Mistral (EUROPEAN ALTERNATIVE)

**Get API Key:**
1. Go to https://console.mistral.ai/api-keys/
2. Click "Create API Key"
3. Copy the key (starts with `aI1`)

**In `.env`:**
```ini
MISTRAL_API_KEY=aI1xxxxxxxxxxxx
AGENT_MODEL=mistral:mistral-large-latest
```

**Pricing:** https://mistral.ai/technology/#pricing (Competitive)  
**Recommended Model:** `mistral-large-latest` (capable, European data residency)

**Use Case:** If you need EU data residency or prefer Mistral's model family.

---

## 🎯 Recommended Configurations

### Scenario 1: Best All-Around (Recommended)

```ini
ANTHROPIC_API_KEY=sk-ant-xxxxx
AGENT_MODEL=anthropic:claude-sonnet-4-6
```

**Why:** Claude Sonnet 4-6 is the best balance of capability, speed, and cost. Most reliable for complex agent tasks.

---

### Scenario 2: Free / Budget

```ini
GEMINI_API_KEY=xxxxx
AGENT_MODEL=google:gemini-2.0-flash
```

**Why:** Gemini 2.0 Flash is free (up to 1M tokens/day), very fast, and surprisingly capable. Great for development/testing.

---

### Scenario 3: Speed-Optimized

```ini
GROQ_API_KEY=gsk_xxxxx
AGENT_MODEL=groq:llama-3.1-405b
```

**Why:** Groq specializes in inference speed. Get responses 10x faster than traditional APIs. Cheap too.

---

### Scenario 4: Redundancy / Fallback

```ini
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx
GROQ_API_KEY=gsk_xxxxx

AGENT_MODEL=anthropic:claude-sonnet-4-6
```

**Why:** Configure multiple providers. If one is down, manually switch to another in the FastAPI UI.

---

### Scenario 5: Maximum Flexibility

```ini
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx
GEMINI_API_KEY=xxxxx
GROQ_API_KEY=gsk_xxxxx
MISTRAL_API_KEY=aI1xxxxx

AGENT_MODEL=anthropic:claude-sonnet-4-6
```

**Why:** All providers configured. Switch between any model in the FastAPI web UI to test/compare.

---

## 🚀 Switching Models at Runtime

### Via FastAPI Web UI

1. Start the app: `uvicorn app:app --reload --host 0.0.0.0 --port 8000`
2. Open `http://localhost:8000` in browser
3. In the chat interface, there's a **Model selector** dropdown
4. Choose any model whose API key is configured in `.env`
5. Start a new chat; it uses the selected model

### Via Python Code

```python
from pydantic_ai import Agent

# Use Anthropic
agent = Agent(model="anthropic:claude-sonnet-4-6", ...)

# Or switch to Groq
agent = Agent(model="groq:llama-3.1-405b", ...)

# Or Gemini
agent = Agent(model="google:gemini-2.0-flash", ...)
```

### Via Environment Variable (Entrypoint)

If you want to change the default model without editing `.env`:

```bash
# Override at runtime
export AGENT_MODEL=groq:llama-3.1-405b
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

---

## 📋 Model Details & Capabilities

### Anthropic Claude Family

| Model | Context | Input Cost | Output Cost | Speed | Best For |
|-------|---------|-----------|-------------|-------|----------|
| claude-sonnet-4-6 | 200K | $3/MTok | $15/MTok | ⭐⭐⭐ | **Recommended**: Best all-around |
| claude-opus-4-1 | 200K | $15/MTok | $75/MTok | ⭐⭐ | Complex reasoning, code generation |
| claude-haiku-4-5 | 200K | $0.80/MTok | $4/MTok | ⭐⭐⭐⭐ | Quick responses, high volume |

**Extended Thinking:** Only Claude supports this (expensive but very capable for complex reasoning)

---

### OpenAI GPT Family

| Model | Context | Input Cost | Output Cost | Speed | Best For |
|-------|---------|-----------|-------------|-------|----------|
| gpt-4o | 128K | $5/MTok | $15/MTok | ⭐⭐⭐ | Latest, multimodal capable |
| gpt-4-turbo | 128K | $10/MTok | $30/MTok | ⭐⭐⭐ | Legacy, still capable |
| gpt-3.5-turbo | 16K | $0.50/MTok | $1.50/MTok | ⭐⭐⭐⭐ | Budget, older but still works |

---

### Google Gemini Family

| Model | Context | Input Cost | Output Cost | Speed | Notes |
|-------|---------|-----------|-------------|-------|-------|
| gemini-2.0-flash | 1M | FREE* | FREE* | ⚡⚡⚡ | **NEW!** Very fast, multimodal |
| gemini-1.5-pro | 2M | $1.25/MTok | $5/MTok | ⭐⭐⭐ | Most capable, long context |
| gemini-1.5-flash | 1M | $0.075/MTok | $0.30/MTok | ⭐⭐⭐⭐ | Fast, budget |

*Free tier: 1M input + 100K output tokens per day

---

### Groq Inference Family

| Model | Context | Input Cost | Output Cost | Speed | Notes |
|-------|---------|-----------|-------------|-------|-------|
| llama-3.1-405b | 8K | $0.59/MTok | $0.79/MTok | ⚡⚡⚡ | **FASTEST**, best quality |
| mixtral-8x7b | 32K | $0.27/MTok | $0.27/MTok | ⚡⚡⚡ | Very fast, balanced |
| gemma-7b | 8K | $0.10/MTok | $0.10/MTok | ⚡⚡⚡ | Ultra-fast, lightweight |

**Key:** Groq specializes in INFERENCE SPEED. All are extremely fast.

---

### Mistral Model Family

| Model | Context | Input Cost | Output Cost | Speed | Notes |
|-------|---------|-----------|-------------|-------|-------|
| mistral-large | 32K | $2/MTok | $6/MTok | ⭐⭐⭐ | Most capable, EU alternative |
| mistral-medium | 32K | $0.81/MTok | $2.43/MTok | ⭐⭐⭐ | Balanced |
| mistral-small | 32K | $0.14/MTok | $0.42/MTok | ⭐⭐⭐⭐ | Budget |

---

## 💰 Cost Comparison (Monthly Estimate)

**Assumptions:** 100K requests/month, 500 input tokens, 200 output tokens per request

| Provider | Est. Cost | Notes |
|----------|-----------|-------|
| Anthropic (claude-sonnet) | ~$450-600 | Good balance, enterprise-grade |
| OpenAI (gpt-4o) | ~$600-700 | Latest, competitive |
| Google Gemini (gemini-2.0-flash) | ~$0 | **FREE tier covers this easily** |
| Groq (llama-3.1-405b) | ~$60-80 | **CHEAPEST**, fastest too |
| Mistral | ~$80-100 | European alternative |

**Recommendation for your setup:** Start with **Gemini 2.0 Flash** (free), then add **Groq** (cheap + fast) as a fallback.

---

## 📝 How to Fill in Your `.env`

### Step 1: Decide Your Strategy

**Option A: Simple (Recommended for starting)**
```
Provider: Anthropic (most reliable)
Backup: Gemini (free)
```

**Option B: Speed-Optimized**
```
Provider: Groq (fastest)
Backup: Anthropic
```

**Option C: Cost-Optimized**
```
Provider: Gemini (free!)
Backup: Groq
```

**Option D: Maximum Flexibility (What I recommend)**
```
All 5 providers configured
Can switch between models anytime
```

### Step 2: Get Your API Keys

For each provider you want to use:

1. **Anthropic:** https://console.anthropic.com/keys
2. **OpenAI:** https://platform.openai.com/account/api-keys
3. **Gemini:** https://aistudio.google.com/app/apikeys
4. **Groq:** https://console.groq.com/keys
5. **Mistral:** https://console.mistral.ai/api-keys/

### Step 3: Fill in `.env`

**File location:** `C:\Users\Owen\jarvis-dev\.env`

**Minimal setup (Anthropic only):**
```ini
GITHUB_TOKEN=ghp_xxxxx
ANTHROPIC_API_KEY=sk-ant-xxxxx
AGENT_MODEL=anthropic:claude-sonnet-4-6

POSTGRES_HOST=postgres-age
POSTGRES_PORT=5432
POSTGRES_DB=your_database
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
```

**Recommended setup (All 5 providers):**
```ini
GITHUB_TOKEN=ghp_xxxxx

ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx
GEMINI_API_KEY=xxxxx
GROQ_API_KEY=gsk_xxxxx
MISTRAL_API_KEY=aI1xxxxx

AGENT_MODEL=anthropic:claude-sonnet-4-6

POSTGRES_HOST=postgres-age
POSTGRES_PORT=5432
POSTGRES_DB=your_database
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
```

### Step 4: Start Container & Test

```bash
cd C:\Users\Owen\jarvis-dev
docker compose up -d jarvis-dev

# Verify all keys work
docker exec jarvis-dev python3 << 'EOF'
import os
from anthropic import Anthropic as AnthropicClient
from groq import Groq as GroqClient
from mistralai import Mistral as MistralClient
from google.generativeai import configure as configure_gemini
import openai

try:
    if os.getenv('ANTHROPIC_API_KEY'):
        print("✓ Anthropic key loaded")
except:
    print("✗ Anthropic key issue")

try:
    if os.getenv('GROQ_API_KEY'):
        print("✓ Groq key loaded")
except:
    print("✗ Groq key issue")

try:
    if os.getenv('GEMINI_API_KEY'):
        print("✓ Gemini key loaded")
except:
    print("✗ Gemini key issue")

try:
    if os.getenv('MISTRAL_API_KEY'):
        print("✓ Mistral key loaded")
except:
    print("✗ Mistral key issue")

try:
    if os.getenv('OPENAI_API_KEY'):
        print("✓ OpenAI key loaded")
except:
    print("✗ OpenAI key issue")
EOF
```

### Step 5: Switch Models in FastAPI UI

1. Open `http://localhost:8000`
2. Start a new chat
3. Click the **Model selector** dropdown
4. Choose any model (all configured ones appear)
5. Type a message; it uses the selected model

---

## 🔧 Advanced: Using Different Models for Different Tasks

### Example: Use Groq for fast iteration, Claude for final output

```python
from pydantic_ai import Agent, RunContext

# Fast testing with Groq
agent_fast = Agent(model="groq:llama-3.1-405b")
result_fast = agent_fast.run_sync("Generate quick code outline")

# Then refine with Claude
agent_final = Agent(model="anthropic:claude-sonnet-4-6")
result_final = agent_final.run_sync(f"Expand on this: {result_fast.data}")
```

### Example: Automatic fallback if primary fails

```python
from pydantic_ai import Agent

fallback_models = [
    "anthropic:claude-sonnet-4-6",
    "groq:llama-3.1-405b",
    "openai:gpt-4o"
]

for model in fallback_models:
    try:
        agent = Agent(model=model)
        result = agent.run_sync("Your task")
        break
    except Exception as e:
        print(f"Model {model} failed: {e}")
        continue
```

---

## 📚 Links & Pricing

- **Anthropic:** https://www.anthropic.com/pricing
- **OpenAI:** https://openai.com/pricing
- **Google Gemini:** https://ai.google.dev/pricing
- **Groq:** https://groq.com/pricing/
- **Mistral:** https://mistral.ai/technology/#pricing

---

## ❓ FAQ

**Q: Which model should I pick?**  
A: Start with `anthropic:claude-sonnet-4-6`. It's the most reliable all-around. Then add others as backups.

**Q: Can I use multiple models in one conversation?**  
A: No, each conversation uses one model. But you can switch models between conversations in the web UI.

**Q: What if a provider is down?**  
A: Configure multiple providers. Switch to a backup in the web UI. Agent code doesn't need to change.

**Q: Is Gemini really free?**  
A: Yes! Free tier gives 1M input + 100K output tokens/day. Perfect for development.

**Q: Groq vs Claude for agent tasks?**  
A: Claude is more reliable for complex reasoning. Groq is faster. For production agents, I recommend Claude primary + Groq backup.

**Q: Can I add more providers later?**  
A: Yes. Add the API key to `.env`, restart container, select in web UI. No code changes needed.

---

## 🎯 TL;DR - What to Do Right Now

1. **Get API keys:**
   - Anthropic: https://console.anthropic.com/keys
   - Groq: https://console.groq.com/keys
   - Gemini: https://aistudio.google.com/app/apikeys
   - Mistral: https://console.mistral.ai/api-keys/
   - OpenAI: https://platform.openai.com/account/api-keys

2. **Fill in `C:\Users\Owen\jarvis-dev\.env`:**
   ```ini
   ANTHROPIC_API_KEY=sk-ant-xxxxx
   GROQ_API_KEY=gsk_xxxxx
   GEMINI_API_KEY=xxxxx
   MISTRAL_API_KEY=aI1xxxxx
   OPENAI_API_KEY=sk-xxxxx
   AGENT_MODEL=anthropic:claude-sonnet-4-6
   [+ all other required fields from .env.template]
   ```

3. **Start container:**
   ```bash
   docker compose up -d jarvis-dev
   ```

4. **Access FastAPI:**
   ```
   http://localhost:8000
   ```

5. **Switch models in web UI dropdown & test**

Done! 🚀
