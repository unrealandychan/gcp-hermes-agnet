# Hermes Agent — Cost Estimation & LLM Provider Guide

> Prices sourced from official GCP and provider pricing pages.
> All figures in USD. Last updated: **May 2026**.

---

## Which LLM is this using?

By default every agent runs on **Gemini 2.0 Flash** via Vertex AI.
The platform supports hot-swapping to any model per agent via a single `.env` change — see [Multi-Provider Support](#multi-provider-support).

| Agent | Default Model | Role |
|---|---|---|
| Orchestrator | `gemini-2.5-flash` | Routes requests to sub-agents |
| AnalyticsAgent | `gemini-2.5-flash` | BigQuery / reporting |
| ITHelpdeskAgent | `gemini-2.5-flash` | IT incidents / runbooks |
| HRAgent | `gemini-2.5-flash` | HR policies / PTO |
| DeveloperAgent | `gemini-2.5-flash` | Code help / architecture |
| PlannerAgent (LoopAgent) | `gemini-2.5-flash` | Long-running task planning |
| ExecutorAgent (LoopAgent) | `gemini-2.5-flash` | Long-running task execution |
| **SkillExtractor** | **`gemini-2.5-flash-lite`** | Background skill extraction — cheapest model |

---

## LLM Pricing Reference (per 1M tokens)

### Google Gemini (Vertex AI — native)

| Model | Input | Output | Best for |
|---|---|---|---|
| `gemini-2.5-flash-lite` | $0.10 | $0.40 | Background tasks, high volume |
| `gemini-2.5-flash` | $0.15 | $0.60 | Default — best price/performance |
| `gemini-2.5-flash` | $0.30 | $2.50 | Better reasoning, more nuanced |
| `gemini-2.5-pro` | $1.25 | $10.00 | Complex multi-step reasoning |

### OpenAI (via LiteLLM)

| Model | Input | Output | Best for |
|---|---|---|---|
| `openai/gpt-4o-mini` | $0.15 | $0.60 | Drop-in Gemini Flash alternative |
| `openai/gpt-4o` | $2.50 | $10.00 | Complex tasks |

### Anthropic Claude (via LiteLLM — on Vertex AI)

| Model | Input | Output | Best for |
|---|---|---|---|
| `anthropic/claude-3-5-haiku-20241022` | $0.80 | $4.00 | Fast, cheap |
| `anthropic/claude-sonnet-4-5` | $3.00 | $15.00 | Strong reasoning |
| `anthropic/claude-opus-4` | $15.00 | $75.00 | Maximum capability |

> **Note:** Claude on Vertex AI uses the same per-token pricing as above.
> Prices billed in USD regardless of your currency.

---

## Monthly Cost Estimates

### PoC (50 testers · 10 messages/day)

**Traffic:** 50 users × 10 messages × 30 days = **15,000 messages/month**

**Token model per message (all Gemini 2.0 Flash):**
- 3 LLM calls per message (Orchestrator → Sub-agent → SkillExtractor)
- ~8,000 input tokens + ~800 output tokens total per message

| Service | Calculation | Cost/mo |
|---|---|---|
| Gemini 2.0 Flash — input | 15,000 × 8,000 tokens ÷ 1M × $0.15 | $18.00 |
| Gemini 2.0 Flash — output | 15,000 × 800 tokens ÷ 1M × $0.60 | $7.20 |
| **LLM Subtotal** | | **$25.20** |
| Cloud Run (0 min-instances, cold start OK) | 15,000 req × 15s × 2vCPU × $0.000024 | $10.80 |
| Cloud Run memory | 15,000 req × 15s × 2 GiB × $0.0000025 | $1.13 |
| Vertex AI RAG retrieval | 15,000 queries × ~$0.001 | $15.00 |
| BigQuery on-demand | ~1,000 queries × 2 GB × $6.25/TB | $12.50 |
| Vertex AI Agent Runtime | Hosting fee (1 engine) | $10–20 |
| GCS + Logging + Networking | Misc | $5 |
| **Total PoC (cold start)** | | **~$80–90/mo** |
| **Total PoC (1 min-instance, warm)** | Add ~$80/mo idle Cloud Run | **~$160–175/mo** |

---

### Small Production (500 users/day)

**Traffic:** 500 users × 5 messages × 30 days = **75,000 messages/month**

| Service | Cost/mo |
|---|---|
| Gemini 2.0 Flash LLM | ~$126 |
| Cloud Run (1–3 min-instances, auto-scale to 20) | ~$150–250 |
| Vertex AI RAG | ~$75 |
| BigQuery | ~$30 |
| Vertex AI Agent Runtime | ~$20–40 |
| GCS + misc | ~$15 |
| **Total** | **~$420–540/mo** |

---

### Enterprise (10,000 users/day)

**Traffic:** 10,000 users × 5 messages × 30 days = **1.5M messages/month**

| Service | Cost/mo |
|---|---|
| Gemini 2.0 Flash LLM | ~$2,520 |
| Cloud Run (3 min + auto-scale to 100) | ~$400–800 |
| Vertex AI RAG | ~$1,500 |
| BigQuery | ~$200 |
| Vertex AI Agent Runtime | ~$100–200 |
| GCS + Logging + Networking | ~$100 |
| **Total** | **~$4,800–5,300/mo** |

> At this scale, switch to **Provisioned Throughput** for Gemini to get ~20–30% savings.
> Provisioned Throughput: 1-year commit = $2,000/GSU/month.

---

## Cost Optimisation Strategies

### 1. Use `gemini-2.5-flash-lite` for lightweight agents

SkillExtractor already defaults to `gemini-2.5-flash-lite` — the cheapest Gemini model.
You can also apply it to the Orchestrator (routing only, no heavy reasoning needed):

```env
AGENT_MODEL_SKILL_EXTRACTOR=gemini-2.5-flash-lite
AGENT_MODEL_ORCHESTRATOR=gemini-2.5-flash-lite
```

**Savings:** Reduces SkillExtractor + Orchestrator cost by ~85% vs Gemini 2.0 Flash.

---

### 2. Mix models by workload complexity

Assign heavier models to agents that do complex reasoning, lighter ones to routing/extraction:

```env
# Routing & background — cheapest
AGENT_MODEL_ORCHESTRATOR=gemini-2.5-flash-lite
AGENT_MODEL_SKILL_EXTRACTOR=gemini-2.5-flash-lite

# Standard knowledge retrieval
AGENT_MODEL_HR=gemini-2.5-flash
AGENT_MODEL_IT_HELPDESK=gemini-2.5-flash

# Heavy reasoning
AGENT_MODEL_ANALYTICS=gemini-2.5-flash
AGENT_MODEL_DEVELOPER=gemini-2.5-flash

# Long-running autonomous tasks
AGENT_MODEL_TASK_PLANNER=gemini-2.5-flash
AGENT_MODEL_TASK_EXECUTOR=gemini-2.5-flash
```

---

### 3. Switch to OpenAI or Anthropic for specific agents

If your team already has negotiated pricing with OpenAI or Anthropic:

```env
# OpenAI GPT-4o-mini is price-competitive with Gemini 2.0 Flash
AGENT_MODEL_ORCHESTRATOR=openai/gpt-4o-mini
AGENT_MODEL_ANALYTICS=openai/gpt-4o
OPENAI_API_KEY=sk-...

# Claude Haiku for cost-sensitive tasks
AGENT_MODEL_HR=anthropic/claude-3-5-haiku-20241022
ANTHROPIC_API_KEY=sk-ant-...
```

---

### 4. Long-running tasks: LoopAgent cost awareness

Each LoopAgent iteration = 2 LLM calls (Planner + Executor):

| Scenario | Iterations | Est. tokens | Est. cost |
|---|---|---|---|
| Short task (5 steps) | 5–10 | ~60K tokens | ~$0.04 |
| Medium task (20 steps) | 20–30 | ~250K tokens | ~$0.19 |
| Long task (50 steps, max) | 50 | ~600K tokens | ~$0.45 |

> Tip: For tasks with predictable steps, use a smaller `max_iterations` limit to cap cost.

---

### 5. Provisioned Throughput (10K+ users)

At high volume, pay-as-you-go becomes expensive.
Switch to Vertex AI Provisioned Throughput:

| Commit | Price per GSU | Break-even vs PAYG |
|---|---|---|
| 1 week | $1,200/week | ~8M tokens/week |
| 1 month | $2,700/month | ~18M tokens/month |
| 1 year | $2,000/month | ~13M tokens/month |

---

## Multi-Provider Support

All agents use the `models/provider.py` factory. The factory:

- Returns a native Gemini string for `gemini-*` model IDs (zero overhead)
- Wraps non-Gemini models in `google.adk.models.LiteLlm` (LiteLLM bridge)

```python
# models/provider.py — usage
from models.provider import get_model

agent = LlmAgent(
    name="MyAgent",
    model=get_model(settings.agent_model_analytics),  # reads from .env
    ...
)
```

### Supported Providers

| Provider | Format | Required env var |
|---|---|---|
| Gemini (Vertex AI) | `gemini-2.5-flash` | GCP ADC / service account |
| OpenAI | `openai/gpt-4o` | `OPENAI_API_KEY` |
| Anthropic (direct) | `anthropic/claude-sonnet-4-5` | `ANTHROPIC_API_KEY` |
| Azure OpenAI | `azure/<deployment>` | `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION` |
| AWS Bedrock | `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0` | AWS credentials |
| Ollama (local) | `ollama/llama3` | Ollama running on localhost |
| Cohere | `cohere/command-r` | `COHERE_API_KEY` |
| Any LiteLLM provider | `<provider>/<model>` | Provider-specific key |

Full list: https://docs.litellm.ai/docs/providers

---

## GCP Infrastructure Pricing Reference

### Cloud Run (us-central1, request-based billing)

| Resource | Active rate | Idle rate (min-instance) | Free tier/mo |
|---|---|---|---|
| CPU | $0.000024/vCPU-sec | $0.0000025/vCPU-sec | 180K vCPU-sec |
| Memory | $0.0000025/GiB-sec | $0.0000025/GiB-sec | 360K GiB-sec |
| Requests | $0.40/1M requests | — | 2M requests |

### Vertex AI RAG / Embeddings

| Service | Rate |
|---|---|
| `text-embedding-004` online | $0.000025/1K chars |
| Gemini Embedding online | $0.00015/1M tokens |

### BigQuery

| Resource | Rate |
|---|---|
| On-demand queries | $6.25/TB scanned |
| Storage (active) | $0.02/GB/month |
| Free tier | First 1 TB queries + 10 GB storage free |

### GCS

| Resource | Rate |
|---|---|
| Storage (standard) | $0.026/GB/month |
| Class A ops (write) | $0.05/10K ops |
| Class B ops (read) | $0.004/10K ops |
