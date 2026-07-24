# Pydantic AI Gateway vs Direct API Keys — Which Should You Use?

**IMPORTANT:** There are TWO ways to configure LLM providers in your Jarvis environment:

1. **Direct API Keys** (What you currently have) — Use your own API keys directly
2. **Pydantic AI Gateway** (Recommended for production) — Single unified gateway key, built on Logfire

This guide explains both approaches and helps you decide.

---

## 📊 Comparison: Direct vs Gateway

| Feature | Direct API Keys | Pydantic AI Gateway |
|---------|-----------------|-------------------|
| **Setup Complexity** | Simple | Requires Logfire account |
| **API Key Management** | Multiple keys (5 different ones) | Single Gateway key |
| **Cost Tracking** | Manual, fragmented | Built-in, unified, real-time |
| **Spending Limits** | None (except provider limits) | Yes, set by project/user/key |
| **Failover** | Manual switching | Automatic via routing groups |
| **Observability** | None (unless added separately) | Built-in via Logfire |
| **Provider Support** | All 5 (Anthropic, OpenAI, Gemini, Groq, Mistral) | 4 (OpenAI, Anthropic, Google, Groq, AWS Bedrock) |
| **Zero Latency Translation** | Direct (native format) | Direct (native format) |
| **Best For** | Development, testing, single-user | Production, multi-user, cost control |

---

## 🎯 What Pydantic AI Gateway Controls

The **Pydantic AI Gateway** is the **unified control plane** that sits between your agent and all LLM providers:

```
┌─────────────────┐
│  Jarvis Agent   │
└────────┬────────┘
         │ (PYDANTIC_AI_GATEWAY_API_KEY)
         ↓
┌─────────────────────────────────────────┐
│   Pydantic AI Gateway (Logfire)        │
├─────────────────────────────────────────┤
│ ✓ Cost tracking & limits                │
│ ✓ Automatic failover & routing          │
│ ✓ Real-time observability (OpenTelemetry) │
│ ✓ API key management (single key!)      │
│ ✓ Multi-provider orchestration          │
└─┬──┬──┬──┬──┐
  │  │  │  │  │
  ↓  ↓  ↓  ↓  ↓
 OpenAI Anthropic Google Groq AWS Bedrock
 (GPT-4) (Claude) (Gemini) (Llama) (Nova)
```

### Gateway Features

✅ **Multi-provider with single key** — One `PYDANTIC_AI_GATEWAY_API_KEY` accesses all configured providers  
✅ **BYOK or managed** — Use your own API keys OR pay through Pydantic  
✅ **Routing groups** — Define failover chains (e.g., Claude → Groq → OpenAI)  
✅ **Spend limits** — Set budgets per project/user/key (daily/weekly/monthly)  
✅ **Real-time cost insights** — See exactly what you're spending on each model  
✅ **Automatic retry/failover** — If Claude is down, seamlessly fallback to Groq  
✅ **Enterprise SSO** — For teams (inherited from Logfire)  

---

## 🚀 Option 1: Continue with Direct API Keys (Current Setup)

This is what you're using now. No changes needed.

**In `.env`:**
```ini
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx
GEMINI_API_KEY=xxxxx
GROQ_API_KEY=gsk_xxxxx
MISTRAL_API_KEY=aI1xxxxx

AGENT_MODEL=anthropic:claude-sonnet-4-6
```

**Model selector uses:**
- `anthropic:claude-sonnet-4-6`
- `openai:gpt-4o`
- `google:gemini-2.0-flash`
- `groq:llama-3.1-405b`
- `mistral:mistral-large-latest`

**Pros:**
- Simple setup
- No additional registration
- Immediate access to all providers
- Good for development

**Cons:**
- Multiple API keys to manage
- No automatic failover
- No built-in cost tracking
- Manual observability setup

---

## 🎛️ Option 2: Use Pydantic AI Gateway (Recommended for Production)

This approach gives you a single unified interface with automatic failover and cost tracking.

### Step 1: Create Logfire Account & Gateway Key

1. Go to: https://logfire.pydantic.dev/
2. Sign up (link to your existing Google/GitHub or email)
3. Choose region (US or EU)
4. Go to **Organization Settings → Gateway**
5. Click **"Create API Key"**
6. Copy the key (looks like: `pylf_v...`)

### Step 2: Set Up Routing Groups (Optional but Powerful)

In Logfire Gateway settings:

1. Go to **Routing Groups**
2. Create a group called `my-routing`:
   - **Provider 1:** Anthropic (Priority: 1, Weight: 1)
   - **Provider 2:** Groq (Priority: 2, Weight: 1) — fallback
   - **Provider 3:** OpenAI (Priority: 3, Weight: 1) — final fallback

Now if Claude is rate-limited, agent automatically tries Groq, then OpenAI.

### Step 3: Connect Your Existing API Keys (BYOK)

In Logfire Gateway settings:

1. Go to **Providers**
2. For each provider (Anthropic, OpenAI, Gemini, Groq), select "Bring Your Own Key"
3. Paste your API keys:
   - Anthropic: `sk-ant-xxxxx`
   - OpenAI: `sk-xxxxx`
   - Google: `xxxxx`
   - Groq: `gsk_xxxxx`

Now the Gateway manages all your keys. You only use `PYDANTIC_AI_GATEWAY_API_KEY` in code.

### Step 4: Update `.env`

Replace direct API keys with Gateway key:

```ini
# OLD: REMOVE THESE
# ANTHROPIC_API_KEY=sk-ant-xxxxx
# OPENAI_API_KEY=sk-xxxxx
# GEMINI_API_KEY=xxxxx
# GROQ_API_KEY=gsk_xxxxx
# MISTRAL_API_KEY=aI1xxxxx

# NEW: Single Gateway key
PYDANTIC_AI_GATEWAY_API_KEY=pylf_v...

# Model selector now uses gateway/ prefix
AGENT_MODEL=gateway/anthropic:claude-sonnet-4-6
```

### Step 5: Update `app.py` (FastAPI)

Your FastAPI full_app needs to use the gateway format:

```python
from pydantic_ai import Agent
import os

# OLD (direct API keys)
# agent = Agent('anthropic:claude-sonnet-4-6')

# NEW (via Gateway)
gateway_key = os.getenv('PYDANTIC_AI_GATEWAY_API_KEY')
if gateway_key:
    # Use Gateway routing
    agent = Agent('gateway/anthropic:claude-sonnet-4-6')
else:
    # Fallback to direct API key
    agent = Agent('anthropic:claude-sonnet-4-6')
```

### Step 6: Restart Container

```bash
cd C:\Users\Owen\jarvis-dev
docker compose down jarvis-dev
docker compose up -d jarvis-dev
```

### Step 7: Test in FastAPI UI

Models now show as:
- `gateway/anthropic:claude-sonnet-4-6`
- `gateway/openai:gpt-4o`
- `gateway/google-cloud:gemini-2-0-flash`
- `gateway/groq:llama-3.1-405b`

**Pros:**
- Single API key (gateway manages everything)
- Automatic failover via routing groups
- Real-time cost tracking
- Spending limits
- Enterprise-grade observability
- Can switch providers without code changes

**Cons:**
- Requires Logfire account
- Slightly more setup
- Some newer providers not yet supported (Mistral, local Ollama)

---

## 🔀 Hybrid Approach (Recommended for Your Setup)

Use **both** approaches:

```ini
# Primary: Gateway (for production features)
PYDANTIC_AI_GATEWAY_API_KEY=pylf_v...

# Secondary: Direct keys (for unsupported providers like Mistral/Ollama)
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx
GEMINI_API_KEY=xxxxx
GROQ_API_KEY=gsk_xxxxx
MISTRAL_API_KEY=aI1xxxxx
```

In `app.py`:

```python
from pydantic_ai import Agent
import os

gateway_key = os.getenv('PYDANTIC_AI_GATEWAY_API_KEY')

if gateway_key:
    # Try Gateway first (supported providers)
    model = 'gateway/anthropic:claude-sonnet-4-6'
else:
    # Fallback to direct keys (all providers)
    model = 'anthropic:claude-sonnet-4-6'

agent = Agent(model)
```

This gives you:
- ✅ Gateway benefits when available
- ✅ Fallback to direct keys for full provider coverage
- ✅ Best of both worlds

---

## 📋 Gateway-Supported Models

**Not all models are in Gateway yet.** Current support:

| Provider | Models | Via Gateway |
|----------|--------|-------------|
| OpenAI | gpt-5, gpt-4o, gpt-4-turbo, gpt-3.5 | ✅ Yes |
| Anthropic | claude-sonnet-4-6, claude-opus, claude-haiku | ✅ Yes |
| Google | gemini-2-0-flash, gemini-1.5-pro, gemini-1.5-flash | ✅ Yes |
| Groq | llama-3.1-405b, mixtral-8x7b, gemma-7b | ✅ Yes |
| AWS Bedrock | nova, llama-3.1, etc. | ✅ Yes |
| Mistral | mistral-large, mistral-medium, mistral-small | ❌ Not yet |
| Local Ollama | Any local model | ❌ Not in Gateway |

For unsupported providers (Mistral, Ollama), use direct API keys.

---

## 🎯 Recommendation for Your Setup

**Use the Hybrid Approach:**

1. **Keep direct API keys** for development flexibility
2. **Add Gateway key** for production observability
3. **Fallback logic** in `app.py` to try Gateway first, then direct keys
4. **This gives you:**
   - Single key management for supported providers (Gateway)
   - Full provider coverage (direct keys)
   - Automatic failover (Gateway routing groups)
   - Cost tracking (Logfire)
   - Zero code changes required

---

## 🔧 How to Set Up Pydantic AI Gateway (Step-by-Step)

### For Development (What to do now)

1. Go to: https://logfire.pydantic.dev/
2. Sign up (takes 2 minutes)
3. Create organization + project
4. Go to **Settings → Gateway → Create API Key**
5. Copy key
6. Add to `.env`:
   ```ini
   PYDANTIC_AI_GATEWAY_API_KEY=pylf_v...
   ```
7. In FastAPI app.py, use `gateway/anthropic:claude-sonnet-4-6` model string
8. Done! Now you have observability + cost tracking

### For Production (After initial testing)

1. Create routing groups in Gateway
2. Set spending limits
3. Monitor costs in real-time in Logfire
4. Adjust routing if certain providers are slow

---

## 📊 Cost Tracking Example

Once you're using Gateway, Logfire shows:

```
╔══════════════════════════════════════╗
║  Cost Breakdown (Last 30 Days)      ║
╠══════════════════════════════════════╣
║ Anthropic (Claude)     $127.45       ║
║ OpenAI (GPT-4)          $89.23       ║
║ Groq (Llama)             $2.15       ║
║ Google (Gemini)          $0.00       ║
╠══════════════════════════════════════╣
║ TOTAL:                 $219.03       ║
╚══════════════════════════════════════╝
```

You can set alerts and hard limits for each.

---

## ✅ Your Current Setup (No Changes Needed)

Your current setup with direct API keys works fine:

```ini
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx
GEMINI_API_KEY=xxxxx
GROQ_API_KEY=gsk_xxxxx
MISTRAL_API_KEY=aI1xxxxx

AGENT_MODEL=anthropic:claude-sonnet-4-6
```

**Models available:**
- `anthropic:claude-sonnet-4-6` ✅
- `openai:gpt-4o` ✅
- `google:gemini-2.0-flash` ✅
- `groq:llama-3.1-405b` ✅
- `mistral:mistral-large-latest` ✅

To add Gateway later (for cost tracking), just create a Logfire account and add the key.

---

## 🔗 Links

- **Pydantic AI Gateway Docs:** https://pydantic.dev/docs/ai/overview/gateway/
- **Pydantic Logfire:** https://logfire.pydantic.dev/
- **Create Logfire Account:** https://logfire.pydantic.dev/
- **Gateway Pricing:** https://pydantic.dev/logfire (includes Gateway)
- **Pydantic AI Docs:** https://docs.pydantic.dev/latest/api/pydantic_ai/

---

## 💡 TL;DR

**Right now:** Your direct API keys work perfectly. Use them.

**Later (when you want cost tracking):** Sign up for Logfire, get a Gateway key, add it to `.env`. No code changes needed — just switch model strings to `gateway/...` format.

**Best practice:** Have both. Use Gateway for production features, direct keys as fallback.
