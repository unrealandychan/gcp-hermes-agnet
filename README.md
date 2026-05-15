# Hermes — Enterprise Agent Platform on GCP

A production-grade, self-learning multi-agent system built on Google's Agent Development Kit (ADK) and Vertex AI Agent Runtime.

> **Target scale:** 10 000 concurrent users · Up to 1-hour autonomous tasks · Multi-platform (Web, Telegram, Slack, Teams)

---

## Google Enterprise Agent Platform Features

This PoC implements all key capabilities from the [Google Cloud Enterprise Agent Platform](https://cloud.google.com/gemini-enterprise-agent-platform):

| Feature | Implementation | Status |
|---|---|---|
| **Grounded Google Search** | All 5 agents have `google_search` built-in | ✅ |
| **Code Execution Sandbox** | `DeveloperAgent` — `BuiltInCodeExecutionTool` (Vertex AI managed sandbox) | ✅ |
| **Model Armor** | `tools/model_armor.py` — every `/chat` prompt screened for injection, PII, toxicity | ✅ |
| **MCP (Model Context Protocol)** | `tools/mcp_connector.py` — filesystem (stdio) + remote SSE servers | ✅ |
| **Agent Observability (Cloud Trace)** | `gateway/observability.py` — OpenTelemetry + Cloud Trace span per request | ✅ |

---

## What's New

See [RELEASE_NOTES.md](./RELEASE_NOTES.md) for the full changelog.

**Latest additions:**
- 📋 `AGENTS.md` — onboarding guide for AI assistants and human contributors
- 🧩 `agents.yaml` — add new agents without touching Python
- 📚 `skills/` — write skills as Markdown files, no code required
- 🧠 Memory split: user profile (who) vs. skills (what), with context budget guard
- ✅ 90 tests, all passing

---

## Customising Agents

### Add a new agent (no Python required)

Edit `agents.yaml` and append your agent:

```yaml
agents:
  - name: FinanceAgent
    description: "Financial reporting, P&L queries, budget forecasting"
    model: ${AGENT_MODEL_FINANCE:-gemini-2.0-flash}
    tools: [bigquery, search]
```

Valid tool names: `bigquery`, `search`, `storage`, `rag_knowledge`, `code_sandbox`, `mcp_filesystem`, `mcp_sse`.

### Add a custom skill (no Python required)

Copy `skills/TEMPLATE.md` to `skills/your-skill-name.md`, fill in the YAML frontmatter and steps.
Skills are loaded into the RAG corpus automatically on gateway startup.

### For custom agent logic

See `AGENTS.md` for step-by-step instructions on adding Python builders.

---

## Architecture

```
                   ┌──────────────────────────────────────┐
  Clients          │  Web Chat (Next.js)                   │
                   │  Telegram Bot  /webhooks/telegram      │
                   │  Slack Bot     /webhooks/slack          │
                   │  Teams Bot     /webhooks/teams          │
                   └──────────────┬───────────────────────┘
                                  │ HTTPS / SSE
                   ┌──────────────▼───────────────────────┐
  API Gateway      │  FastAPI + Cloud Run                  │
  (gateway/)       │  • Google OAuth2 JWT validation       │
                   │  • Rate limiting (slowapi)            │
                   │  • Model Armor prompt screening       │
                   │  • Cloud Trace spans (OpenTelemetry)  │
                   │  • SSE streaming  POST /chat          │
                   │  • Long tasks     POST /tasks         │
                   └──────────────┬───────────────────────┘
                                  │ VertexAiSessionService
                   ┌──────────────▼───────────────────────┐
  Agent Runtime    │  Reasoning Engine (Vertex AI)         │
  (agents/)        │                                       │
                   │  Orchestrator (LlmAgent + Search)     │
                   │  ├── AnalyticsAgent  → BQ, RAG, Search│
                   │  ├── ITHelpdeskAgent → RAG, GCS, Search│
                   │  ├── HRAgent         → RAG, Search    │
                   │  ├── DeveloperAgent  → RAG, Search,   │
                   │  │                     Code Sandbox   │
                   │  └── TaskAgent (LoopAgent, ≤1 h)      │
                   └──────────────┬───────────────────────┘
                                  │
                   ┌──────────────▼───────────────────────┐
  Self-Learning    │  SkillExtractor  (LlmAgent)           │
  (memory/)        │  Skill Store     (Vertex AI RAG)      │
                   │  Memory Bank     (VertexAiMemoryBank) │
                   └──────────────────────────────────────┘
```

---

## LLM Providers & Models

All agents use **Gemini 2.0 Flash** by default (native Vertex AI, no extra config).
You can change the model for any agent independently via `.env` — no code changes needed.

### Supported providers

| Provider | Model format | Example |
|---|---|---|
| **Gemini (Vertex AI)** — default | `gemini-<version>` | `gemini-2.0-flash` |
| **OpenAI** | `openai/<model>` | `openai/gpt-4o` |
| **Anthropic Claude** | `anthropic/<model>` | `anthropic/claude-sonnet-4-5` |
| **Azure OpenAI** | `azure/<deployment>` | `azure/my-gpt4o` |
| **AWS Bedrock** | `bedrock/<model>` | `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0` |
| **Ollama (local)** | `ollama/<model>` | `ollama/llama3` |
| Any [LiteLLM provider](https://docs.litellm.ai/docs/providers) | `<provider>/<model>` | — |

### Switch model per agent in `.env`

```bash
# Use OpenAI GPT-4o for the analytics agent
AGENT_MODEL_ANALYTICS=openai/gpt-4o
OPENAI_API_KEY=sk-...

# Use Claude Sonnet for developer agent
AGENT_MODEL_DEVELOPER=anthropic/claude-sonnet-4-5
ANTHROPIC_API_KEY=sk-ant-...

# Keep everything else on Gemini
AGENT_MODEL_ORCHESTRATOR=gemini-2.0-flash
AGENT_MODEL_SKILL_EXTRACTOR=gemini-2.5-flash-lite  # already the cheapest default
```

> See [docs/cost-estimation.md](docs/cost-estimation.md) for a full breakdown of model pricing and cost optimisation presets.

---

## Cost Estimation (PoC → Production)

See **[docs/cost-estimation.md](docs/cost-estimation.md)** for detailed tables.

**Quick summary:**

| Scale | Users/day | Est. monthly cost |
|---|---|---|
| PoC (cold start OK) | 50 users, 10 msg/day | **~$80–90** |
| PoC (always-warm) | 50 users, 10 msg/day | **~$160–175** |
| Small production | 500 users, 5 msg/day | **~$420–540** |
| Enterprise | 10,000 users, 5 msg/day | **~$4,800–5,300** |

**Cost tips:**
- `AGENT_MODEL_SKILL_EXTRACTOR=gemini-2.5-flash-lite` is already set by default — saves ~85% on background extraction.
- Set `AGENT_MODEL_ORCHESTRATOR=gemini-2.5-flash-lite` for routing-only workloads.
- Use `min-instances=0` for a PoC to eliminate idle Cloud Run charges.

---

## Quick Start

**Prerequisites:** `gcloud` CLI authenticated as project owner. Python 3.11+.

```bash
git clone https://github.com/unrealandychan/gcp-hermes-agnet.git
cd gcp-hermes-agnet
python setup_wizard.py
```

The wizard asks **3 questions**, then handles everything automatically:

- ✅ Pre-flight checks (gcloud auth, Python/Node version)
- ⚙️ Enables 13 GCP APIs, creates bucket + service account + Firestore
- 🗄️ Creates Vertex AI RAG corpora, writes resource names into `.env`
- 🚀 Deploys agent to Vertex AI Reasoning Engine
- 🐳 Optionally deploys gateway to Cloud Run
- 🌱 Optionally seeds demo data (BigQuery tables + knowledge docs)

It is **idempotent** — safe to re-run at any time if something fails mid-way.

---

### After setup — start locally

```bash
source .env
uvicorn gateway.main:app --reload --port 8080
```

Test it works:

```bash
curl -X POST http://localhost:8080/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello! What can you help me with?"}'
```

---

### Web UI (optional)

```bash
cd ui
cp .env.local.example .env.local
# Edit .env.local: set NEXT_PUBLIC_GATEWAY_URL=http://localhost:8080
npm install && npm run dev
```

Open [http://localhost:3000](http://localhost:3000), sign in with Google, and start chatting.

---

### Step 8 — Deploy gateway to Cloud Run

```bash
PROJECT_ID=$(gcloud config get-value project)

# Build and push image
docker build -f Dockerfile.gateway -t gcr.io/$PROJECT_ID/hermes-gateway .
docker push gcr.io/$PROJECT_ID/hermes-gateway

# Deploy
gcloud run deploy hermes-gateway \
  --image gcr.io/$PROJECT_ID/hermes-gateway \
  --region us-central1 \
  --cpu 4 --memory 4Gi \
  --min-instances 3 --max-instances 100 \
  --concurrency 40 --timeout 3600 \
  --service-account hermes-agent-sa@$PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars GCP_PROJECT_ID=$PROJECT_ID,GCP_LOCATION=us-central1 \
  --set-secrets GOOGLE_CLIENT_ID=hermes-google-client-id:latest
```

Note the deployed service URL — you will need it for connector webhooks below.

---

## Platform Connectors

### Telegram

**1. Create a bot via @BotFather**

```
/newbot → follow prompts → copy the Bot Token
```

**2. Set credentials in `.env`**

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
TELEGRAM_WEBHOOK_SECRET=pick-any-random-string   # used to verify incoming requests
```

**3. Register the webhook** (after Cloud Run deploy)

```bash
GATEWAY_URL=https://your-gateway-url.run.app
BOT_TOKEN=123456789:ABCdef...
SECRET=pick-any-random-string

curl "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook" \
  --data-urlencode "url=${GATEWAY_URL}/webhooks/telegram" \
  --data-urlencode "secret_token=${SECRET}"

# Verify registration
curl "https://api.telegram.org/bot${BOT_TOKEN}/getWebhookInfo"
```

**4. Test end-to-end**

Open your bot in Telegram and send any message — Hermes replies within a few seconds.

**Test with a mock request (local):**

```bash
curl -X POST http://localhost:8080/webhooks/telegram \
  -H "X-Telegram-Bot-Api-Secret-Token: ${SECRET}" \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "chat": {"id": 999},
      "from": {"id": "12345"},
      "text": "What is our Q1 revenue?"
    }
  }'
# Hermes sends the reply to chat_id 999 via the Telegram API
```

---

### Slack

**1. Create a Slack App**

- Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App** → **From scratch**.
- **OAuth & Permissions** → Bot Token Scopes: `chat:write`, `im:history`, `app_mentions:read`.
- Install to your workspace → copy the **Bot User OAuth Token** (`xoxb-...`).
- **Basic Information** → copy the **Signing Secret**.

**2. Set credentials in `.env`**

```bash
SLACK_BOT_TOKEN=xoxb-...
SLACK_SIGNING_SECRET=abc123...
```

**3. Enable Event Subscriptions**

- **Event Subscriptions** → toggle **On**.
- Request URL: `https://your-gateway-url.run.app/webhooks/slack`
  - Slack sends a `url_verification` challenge — the gateway handles it automatically.
- Subscribe to Bot Events: `message.im`, `app_mention`.
- Save changes and reinstall the app if prompted.

**4. Test end-to-end**

DM the bot or mention `@Hermes` in a channel.

**Test with a mock request (local):**

```bash
# Helper to compute Slack HMAC signature
TIMESTAMP=$(date +%s)
BODY='{"type":"event_callback","event":{"type":"message","user":"U04AB12XY","channel":"D01234567","text":"Show me open IT incidents"}}'
SIG_BASE="v0:${TIMESTAMP}:${BODY}"
SIGNATURE="v0=$(echo -n "$SIG_BASE" | openssl dgst -sha256 -hmac "$SLACK_SIGNING_SECRET" | awk '{print $2}')"

curl -X POST http://localhost:8080/webhooks/slack \
  -H "Content-Type: application/json" \
  -H "X-Slack-Request-Timestamp: ${TIMESTAMP}" \
  -H "X-Slack-Signature: ${SIGNATURE}" \
  -d "$BODY"
```

---

### Microsoft Teams

**1. Register an Azure Bot**

- Azure Portal → **Create a resource** → search **Azure Bot**.
- Choose **Single Tenant** (for internal org) or **Multi Tenant**.
- **Configuration** → Messaging endpoint: `https://your-gateway-url.run.app/webhooks/teams`.
- **Configuration → Manage** → **Certificates & secrets** → new client secret.
- Note the **Application (client) ID** and the **Secret value**.

**2. Set credentials in `.env`**

```bash
TEAMS_APP_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
TEAMS_APP_PASSWORD=your-client-secret
```

**3. Add Teams channel**

- In your Azure Bot → **Channels** → add **Microsoft Teams** channel.
- In [Teams Developer Portal](https://dev.teams.microsoft.com), create an app manifest
  pointing to your bot, then install it to your org.

**4. Test end-to-end**

Message the bot in Teams — Hermes replies via the Bot Framework REST API.

**Smoke test without JWT (local dev only):**

```bash
# Temporarily comment out `await _verify_teams_token(...)` in connectors/teams.py
curl -X POST http://localhost:8080/webhooks/teams \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer MOCK" \
  -d '{
    "type": "message",
    "text": "Summarise the HR leave policy",
    "from": {"id": "29:1ABC"},
    "serviceUrl": "https://smba.trafficmanager.net/apis/",
    "conversation": {"id": "a:1XYZ"},
    "id": "activity-id-001"
  }'
```

> Re-enable JWT verification before deploying to production.

---

## Long-Running Tasks (ReAct Loop)

For tasks that require many steps — multi-table analysis, automated report generation, bulk operations — use the **task API** instead of `/chat`.

`TaskAgent` is an ADK `LoopAgent` running a **plan → execute → observe** loop for up to 50 iterations (~1 hour max).

### Submit a task

```bash
TOKEN=$(gcloud auth print-identity-token)
GATEWAY=https://your-gateway-url.run.app

curl -X POST "$GATEWAY/tasks" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Analyse all BigQuery tables in dataset `sales` and write a markdown revenue-trend report for 2024–2025. Save it to GCS at reports/revenue-2024-2025.md",
    "context": {
      "dataset": "sales",
      "project": "hermes-agent-prod"
    }
  }'
```

Response:

```json
{
  "task_id": "a1b2c3d4-...",
  "status": "pending",
  "created_at": "2026-05-15T10:00:00Z"
}
```

### Poll for status

```bash
curl "$GATEWAY/tasks/a1b2c3d4-..." \
  -H "Authorization: Bearer $TOKEN"
```

While running:

```json
{
  "status": "running",
  "progress": [
    "Step 1: Listed 12 tables in dataset sales.",
    "Step 2: Queried sales.orders — $48M revenue in 2024."
  ],
  "result": null
}
```

When done:

```json
{
  "status": "done",
  "result": "# Revenue Trends 2024–2025\n\n...",
  "completed_at": "2026-05-15T10:22:10Z"
}
```

### Other task endpoints

```bash
# List all your tasks
curl "$GATEWAY/tasks" -H "Authorization: Bearer $TOKEN"

# Cancel a running task
curl -X DELETE "$GATEWAY/tasks/a1b2c3d4-..." -H "Authorization: Bearer $TOKEN"
```

Task results are persisted to `gs://hermes-agent-artifacts/tasks/<task_id>.json` and survive Cloud Run restarts.

---

## Self-Learning

After every agent interaction:
1. `skill_learning_callback` runs automatically (ADK `after_agent_callback`).
2. `SkillExtractor` LlmAgent analyses the interaction.
3. If a reusable procedure is identified, it is saved to `hermes-skills-corpus` (RAG).
4. On the next relevant turn, `PreloadMemoryTool` injects matching skills into the agent's context.
5. Skills are versioned — newer learnings supersede old ones; old versions are archived with `is_current=False`.

---

## Project Structure

```
hermes-gcp/
├── agents/
│   ├── orchestrator.py    # Root LlmAgent — routes to sub-agents
│   ├── analytics.py
│   ├── it_helpdesk.py
│   ├── hr.py
│   ├── developer.py
│   └── task_agent.py      # LoopAgent — long-running ReAct tasks (≤1 h)
├── models/
│   ├── __init__.py
│   └── provider.py        # LLM provider factory (Gemini, OpenAI, Claude, Azure, Ollama…)
├── connectors/
│   ├── runner.py          # Shared non-streaming agent runner
│   ├── telegram.py        # POST /webhooks/telegram
│   ├── slack.py           # POST /webhooks/slack
│   └── teams.py           # POST /webhooks/teams
├── gateway/
│   ├── main.py            # FastAPI — /chat, /tasks, /sessions, /memories
│   ├── auth.py            # Google OAuth2 JWT validation + TTL cache
│   └── tasks.py           # Long-running task registry + GCS persistence
├── tools/
│   ├── bigquery_tool.py
│   ├── storage_tool.py
│   ├── search_tool.py
│   ├── model_armor.py      # Model Armor prompt/response screening
│   └── mcp_connector.py    # MCP toolset factory (filesystem + SSE)
├── memory/
│   ├── skill_models.py
│   ├── skill_extractor.py
│   ├── skill_store.py
│   └── skill_learning.py
├── tests/
│   ├── conftest.py
│   ├── tools/
│   │   ├── test_model_armor.py
│   │   └── test_mcp_connector.py
│   ├── gateway/
│   │   ├── test_observability.py
│   │   └── test_main_chat.py
│   └── agents/
│       └── test_agent_builds.py
├── docs/
│   └── cost-estimation.md # LLM pricing + monthly cost estimates
├── ui/                    # Next.js 14 Web Chat UI
│   └── src/
│       ├── app/
│       ├── components/
│       ├── lib/api.ts     # SSE streaming client
│       └── types/
├── scripts/
│   ├── deploy.py          # Deploy to Vertex AI Agent Runtime
│   └── setup_rag.py       # Create RAG corpora
├── infra/
│   ├── setup.sh           # GCP bootstrap
│   └── clouddeploy.yaml   # Cloud Run config
├── Dockerfile.gateway
├── requirements.txt
└── .env.example
```

---

## API Reference

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/chat` | Bearer | SSE streaming chat |
| `GET` | `/sessions/{user_id}` | Bearer | List active sessions |
| `DELETE` | `/memories/{user_id}` | Bearer | Clear long-term memory |
| `POST` | `/tasks` | Bearer | Submit long-running task |
| `GET` | `/tasks` | Bearer | List your tasks |
| `GET` | `/tasks/{task_id}` | Bearer | Poll task status + result |
| `DELETE` | `/tasks/{task_id}` | Bearer | Cancel a task |
| `POST` | `/webhooks/telegram` | Secret header | Telegram Bot webhook |
| `POST` | `/webhooks/slack` | HMAC-SHA256 | Slack Events API webhook |
| `POST` | `/webhooks/teams` | Bearer JWT | Teams Bot Framework webhook |

Interactive docs: `GET /docs` (Swagger UI).

---

## Testing

Tests run fully offline — no GCP credentials or network calls required. All external services (Model Armor, ADK, Cloud Trace) are mocked.

### Install test dependencies

```bash
pip install pytest pytest-asyncio pytest-mock httpx
```

### Run all tests

```bash
pytest
```

### Run a single module

```bash
pytest tests/tools/test_model_armor.py -v
pytest tests/gateway/test_observability.py -v
pytest tests/gateway/test_main_chat.py -v
pytest tests/agents/test_agent_builds.py -v
```

### Test coverage by module

| Module | Test file | Coverage areas |
|---|---|---|
| `tools/model_armor.py` | `tests/tools/test_model_armor.py` | `_parse`, `screen_prompt`, `screen_response`, timeout/404/disabled |
| `tools/mcp_connector.py` | `tests/tools/test_mcp_connector.py` | filesystem toolset, SSE toolset, `get_configured_mcp_tools`, auth header, ImportError fallback |
| `gateway/observability.py` | `tests/gateway/test_observability.py` | `_NoopTracer`, `_NoopSpan`, `get_tracer`, `setup_tracing` (with/without packages), `instrument_fastapi`, `agent_span` |
| `gateway/main.py` `/chat` | `tests/gateway/test_main_chat.py` | Model Armor block → 400, allowed prompt → 200, no runner → 503, session auth |
| `agents/` | `tests/agents/test_agent_builds.py` | All 5 agent builder functions — correct name, tools list, sub-agents |

---

## Scaling

Configured for 10 000 concurrent users:

| Parameter | Value | Reason |
|---|---|---|
| `max-instances` | 100 | 100 × 40 = 4 000 simultaneous SSE streams |
| `concurrency` | 40 | Limits memory pressure from long-lived connections |
| `min-instances` | 3 | Eliminates cold starts |
| `cpu` | 4 | Handles concurrent async I/O |
| `timeout` | 3600 s | Supports 1-hour long-running tasks |

- Auth token cache: `TTLCache(maxsize=50_000, ttl=300)` — avoids re-validating the same JWT on every request.
- GCP client singletons: `@lru_cache` on BigQuery and GCS clients — one instance per process.
- Rate limit: 20 chat requests/min per IP via `slowapi`, 5 task submissions/min.

