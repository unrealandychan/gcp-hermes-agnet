# Hermes Agent — Architecture

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Component Architecture](#2-component-architecture)
3. [Data Flow](#3-data-flow)
4. [Memory Architecture](#4-memory-architecture)
5. [Governance Flow](#5-governance-flow)
6. [Self-Learning Loop](#6-self-learning-loop)
7. [Deployment Topology](#7-deployment-topology)

---

## 1. System Overview

**Hermes** is an enterprise-grade, multi-agent AI assistant platform built on Google Cloud. It exposes a single conversational API that routes requests to a fleet of specialised sub-agents — covering analytics, IT helpdesk, HR, and software development — while maintaining per-user episodic memory, enforcing content governance policies, and continuously learning procedural skills from interactions.

### Core capabilities

- **Multi-turn conversation** with persistent session state via Vertex AI Session Service
- **Specialist routing** — an Orchestrator LlmAgent delegates to domain agents based on intent
- **Two-tier memory** — episodic (per-user facts) + procedural (shared skill RAG corpus)
- **Content governance** — Model Armor + PolicyEngine screen every prompt and response
- **Self-learning** — completed interactions are analysed; reusable skills are extracted and stored back into the RAG corpus
- **Multi-channel** — Telegram, Slack, and Microsoft Teams connectors all funnel into the same backend
- **Long-running tasks** — a dedicated TaskAgent (LoopAgent) handles work that spans many steps

---

## 2. Component Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                                 │
│   Browser / Mobile App    Telegram Bot    Slack App    Teams Bot    │
└────────────┬──────────────────┬───────────────┬──────────┬─────────┘
             │  REST + SSE      │  Webhook      │  Webhook │  Webhook
             ▼                  ▼               ▼          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     GATEWAY  (Cloud Run)                            │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │  FastAPI    │  │  Auth        │  │  Connectors              │  │
│  │  Application│  │  Google      │  │  /webhooks/telegram      │  │
│  │             │  │  OAuth2 JWT  │  │  /webhooks/slack  (HMAC) │  │
│  │  slowapi    │  │  OIDC verify │  │  /webhooks/teams  (JWT)  │  │
│  │  rate limit │  └──────────────┘  └──────────────────────────┘  │
│  │  20 req/min │                                                    │
│  └──────┬──────┘  ┌──────────────┐  ┌──────────────────────────┐  │
│         │         │ Model Armor  │  │  PolicyEngine            │  │
│         │─────────│  screening   │  │  prompt intercept        │  │
│         │         └──────────────┘  │  response intercept      │  │
│         │                           └──────────────────────────┘  │
│         │         ┌──────────────────────────────────────────────┐ │
│         │         │  Cloud Trace  (span per request)             │ │
│         │         └──────────────────────────────────────────────┘ │
│         │  SSE streaming (/chat)                                    │
└─────────┼───────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  AGENT RUNTIME  (Vertex AI Reasoning Engine)        │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                  ADK Runner                                   │  │
│  │           VertexAiSessionService  (session state)            │  │
│  └────────────────────────┬─────────────────────────────────────┘  │
│                           │                                         │
│              ┌────────────▼────────────┐                           │
│              │   Orchestrator Agent    │  (LlmAgent)               │
│              │   intent routing        │                           │
│              └──┬──────┬──────┬────┬──┘                           │
│                 │      │      │    │                                │
│        ┌────────▼─┐ ┌──▼───┐ │ ┌──▼──────────┐                   │
│        │Analytics │ │  IT  │ │ │  Developer  │                   │
│        │  Agent   │ │Help- │ │ │   Agent     │                   │
│        │BQ+RAG+   │ │desk  │ │ │RAG+Search+  │                   │
│        │Search    │ │Agent │ │ │CodeSandbox  │                   │
│        └──────────┘ │RAG+  │ │ └─────────────┘                   │
│                     │GCS+  │ │                                     │
│                     │Search│ └──▼──────────┐                      │
│                     └──────┘  │  HR Agent  │                      │
│                               │RAG+Search  │                      │
│                               └────────────┘                      │
│                                                                     │
│        ┌─────────────────────────────────────┐                    │
│        │  TaskAgent  (LoopAgent)              │                    │
│        │  max 50 iterations                   │                    │
│        │  async background execution          │                    │
│        └─────────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA & MEMORY LAYER                          │
│                                                                     │
│  ┌─────────────────────┐   ┌──────────────────────┐               │
│  │ AgentEngine MemoryBank  │   │  RAG Corpus           │               │
│  │ (episodic memory)   │   │  (procedural skills)  │               │
│  │  per-user facts     │   │  shared knowledge     │               │
│  └─────────────────────┘   └──────────────────────┘               │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐   │
│  │  Firestore   │  │  BigQuery    │  │  Cloud Storage (GCS)  │   │
│  │  user        │  │  analytics   │  │  task results         │   │
│  │  profiles    │  │  + quality   │  │  knowledge docs       │   │
│  └──────────────┘  └──────────────┘  └───────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Secret Manager  (API keys, tokens, credentials)             │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.1 Gateway Layer (Cloud Run)

| Component | Responsibility |
|-----------|---------------|
| **FastAPI Application** | HTTP routing, SSE streaming, request/response lifecycle |
| **Google OAuth2 JWT Auth** | Validates `Authorization: Bearer <Google ID Token>` on every request |
| **slowapi Rate Limiter** | 20 req/min per IP for `/chat`; 5 req/min per IP for `/tasks` |
| **Model Armor** | Pre-screens user prompts for harmful content before forwarding to the agent |
| **PolicyEngine** | Dual intercept: validates prompt (pre-agent) and response (post-agent) against enterprise policies |
| **Cloud Trace** | Creates a trace span per request; sub-spans for auth, policy, agent, memory |
| **Connectors** | Normalises inbound Telegram webhooks, Slack events, and Teams activities into the internal `ChatRequest` format |

### 2.2 Agent Runtime (Vertex AI Reasoning Engine)

| Component | Responsibility |
|-----------|---------------|
| **ADK Runner** | Orchestrates agent invocation, tool execution, and response aggregation |
| **VertexAiSessionService** | Persists multi-turn session state on Vertex AI infrastructure |
| **Orchestrator (LlmAgent)** | Classifies user intent and delegates to the appropriate specialist agent |
| **AnalyticsAgent** | Answers data questions via BigQuery queries, RAG retrieval, and web search |
| **ITHelpdeskAgent** | Resolves IT issues using RAG over knowledge articles, GCS documents, and search |
| **HRAgent** | Handles HR queries using RAG over policy documents and search |
| **DeveloperAgent** | Assists with code via RAG, search, and a sandboxed code execution environment |
| **TaskAgent (LoopAgent)** | Executes long-running, multi-step tasks asynchronously; capped at 50 loop iterations |

### 2.3 Data & Memory Layer

| Store | Purpose |
|-------|---------|
| **AgentEngine MemoryBank** | Episodic per-user memory — facts, preferences, and interaction history |
| **RAG Corpus** | Procedural skill store — reusable, agent-agnostic knowledge chunks |
| **Firestore** | User profiles and metadata |
| **BigQuery** | Analytics events and LLM response quality logs |
| **GCS** | Task output artefacts and source knowledge documents |
| **Secret Manager** | Runtime secrets (API keys, webhook tokens, service account credentials) |

---

## 3. Data Flow

### 3.1 Chat Request Lifecycle

```
Client
  │
  │  POST /chat  { message, session_id }
  │  Authorization: Bearer <Google ID Token>
  ▼
┌──────────────────────────────────────────────────────────┐
│  GATEWAY                                                 │
│                                                          │
│  1. JWT verification (Google OAuth2 public keys)         │
│  2. Rate limit check (slowapi, per-IP bucket)            │
│  3. Cloud Trace span open                                │
│  4. Model Armor prompt screening  ──► 400 if blocked     │
│  5. PolicyEngine.check_prompt()   ──► 400 if blocked     │
│                                                          │
│  6. Forward to Reasoning Engine via ADK Runner           │
└──────────────────┬───────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────┐
│  AGENT RUNTIME                                           │
│                                                          │
│  7.  VertexAiSessionService.get_or_create(session_id)    │
│  8.  Fetch episodic memories  (AgentEngine MemoryBank)       │
│  9.  Cross-corpus RAG retrieval  (async parallel)        │
│       ├── RAG Corpus (skills)                            │
│       └── Domain corpus (agent-specific)                 │
│  10. Orchestrator selects specialist agent               │
│  11. Specialist agent executes tools / sub-agents        │
│  12. Response assembled                                  │
└──────────────────┬───────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────┐
│  GATEWAY (response path)                                 │
│                                                          │
│  13. PolicyEngine.check_response()  ──► 400 if blocked  │
│  14. Emit SSE ChatEvent{ type:"text", content, sid }     │
│      ...stream tokens...                                 │
│  15. Emit SSE ChatEvent{ type:"done", session_id }       │
│  16. Cloud Trace span close                              │
│  17. Log quality event → BigQuery                        │
└──────────────────────────────────────────────────────────┘
                   │
                   ▼  SSE stream
                Client
```

### 3.2 Webhook Connector Flow

```
Telegram / Slack / Teams
        │
        │  POST /webhooks/{platform}
        ▼
┌───────────────────────────────────────┐
│  Connector Handler                    │
│  1. Verify platform signature/token   │
│     Telegram: X-Telegram-Bot-Api-     │
│               Secret-Token header     │
│     Slack:    HMAC X-Slack-Signature  │
│     Teams:    Bot Framework JWT       │
│  2. Parse platform-native payload     │
│  3. Normalise → internal ChatRequest  │
│  4. Inject synthetic user identity    │
└──────────────────┬────────────────────┘
                   │  (same pipeline as POST /chat)
                   ▼
           Agent Runtime ...
                   │
                   ▼
           Response dispatched back
           via platform API (async)
```

---

## 4. Memory Architecture

Hermes uses a **two-tier memory model** that separates *what the user has told us* from *how to do things well*.

```
┌──────────────────────────────────────────────────────────────┐
│                    TWO-TIER MEMORY                           │
│                                                              │
│  Tier 1: Episodic Memory (per-user)                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  AgentEngine MemoryBank                                  │    │
│  │  • User facts ("prefers Python", "team = Platform")  │    │
│  │  • Interaction history summaries                     │    │
│  │  • User preferences and constraints                  │    │
│  │  • Scoped strictly to one user_id                    │    │
│  │  • Queried at session start; enriches system prompt  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Tier 2: Procedural Memory (shared / skill-level)            │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  RAG Corpus (Vertex AI Search & Retrieval)           │    │
│  │  • Reusable skill descriptions ("how to query BQ")   │    │
│  │  • Extracted from successful interactions            │    │
│  │  • Domain corpora per agent (analytics, IT, HR, dev) │    │
│  │  • Retrieved async in parallel across corpora        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  Supporting Stores                                           │
│  ┌──────────────────┐   ┌────────────────────────────────┐  │
│  │ Firestore        │   │ Cross-Corpus Retrieval         │  │
│  │ user profiles    │   │ async parallel fan-out across  │  │
│  │ metadata, prefs  │   │ all relevant RAG corpora;      │  │
│  └──────────────────┘   │ results merged + re-ranked     │  │
│                         └────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### Memory lifecycle per request

1. **Session start** — `AgentEngine MemoryBank` is queried with the incoming message; top-*k* user facts are injected into the system prompt.
2. **RAG retrieval** — Cross-corpus retrieval fans out asynchronously across the RAG Corpus and any domain-specific corpora; results are merged and re-ranked before being passed to the agent as context.
3. **Post-session** — On conversation completion the Self-Learning Loop (§6) may update both tiers.

---

## 5. Governance Flow

The PolicyEngine provides a **dual intercept** — once before the agent sees the message, and once before the response reaches the client.

```
User Message
     │
     ▼
┌────────────────────────────────────────┐
│  PRE-AGENT INTERCEPT                   │
│                                        │
│  Step 1: Model Armor screening         │
│   • Checks for PII, toxicity,          │
│     prompt injection attempts          │
│   • Hard block → HTTP 400              │
│                                        │
│  Step 2: PolicyEngine.check_prompt()   │
│   • Enterprise content policies        │
│   • Topic restrictions per user role   │
│   • Data classification rules          │
│   • Soft warn / hard block → HTTP 400  │
└──────────────────┬─────────────────────┘
                   │ (passes)
                   ▼
           Agent Runtime
                   │
                   ▼
┌────────────────────────────────────────┐
│  POST-AGENT INTERCEPT                  │
│                                        │
│  Step 3: PolicyEngine.check_response() │
│   • Redact sensitive data patterns     │
│   • Validate output classification     │
│   • Enforce citation requirements      │
│   • Block disallowed content           │
│   • Block → HTTP 400, else pass        │
└──────────────────┬─────────────────────┘
                   │ (passes)
                   ▼
           SSE stream → Client
```

All governance decisions are logged to BigQuery for audit.

---

## 6. Self-Learning Loop

After each completed interaction, Hermes analyses the exchange and optionally extracts a reusable skill, persisting it to the RAG Corpus so all agents benefit from learned knowledge.

```
Completed Interaction
        │
        ▼
┌───────────────────────────────────────────────┐
│  Skill Extractor (async, post-response)        │
│                                               │
│  1. Score interaction quality                 │
│     (user feedback + implicit signals)        │
│  2. Check if interaction contains a           │
│     reusable, generalisable procedure         │
│  3. If yes:                                   │
│     a. Summarise as a skill document          │
│        { title, description, steps, tags }    │
│     b. Embed skill document                   │
│     c. Upsert into RAG Corpus                 │
│  4. Update user memory facts if new           │
│     personal information was revealed         │
│     (AgentEngine MemoryBank upsert)               │
│  5. Log skill extraction event → BigQuery     │
└───────────────────────────────────────────────┘
        │
        ▼ (next request using similar intent)
┌───────────────────────────────────────────────┐
│  RAG Retrieval surfaces learned skill         │
│  Agent reuses procedure without re-learning   │
└───────────────────────────────────────────────┘
```

---

## 7. Deployment Topology

```
                        ┌─────────────────────────────┐
                        │      Google Cloud Project    │
                        │                             │
  ┌──────────┐          │  ┌──────────────────────┐   │
  │ Internet │──HTTPS──▶│  │  Cloud Run           │   │
  └──────────┘          │  │  hermes-gateway       │   │
                        │  │  (FastAPI, min 1,     │   │
  ┌──────────┐          │  │   max N instances)    │   │
  │ Telegram │──Webhook▶│  └──────────┬───────────┘   │
  └──────────┘          │             │                │
  ┌──────────┐          │             │ gRPC/REST      │
  │  Slack   │──Webhook▶│  ┌──────────▼───────────┐   │
  └──────────┘          │  │ Vertex AI             │   │
  ┌──────────┐          │  │ Reasoning Engine      │   │
  │  Teams   │──Webhook▶│  │ (Agent Runtime)       │   │
  └──────────┘          │  └──────────┬────────────┘   │
                        │             │                │
  ┌──────────────────┐  │  ┌──────────▼────────────┐   │
  │ Cloud Scheduler  │──┼─▶│  /scheduler/trigger   │   │
  │ (OIDC token)     │  │  └───────────────────────┘   │
  └──────────────────┘  │                              │
                        │  Supporting Services:        │
                        │  ┌───────────┐ ┌──────────┐  │
                        │  │ Firestore │ │BigQuery  │  │
                        │  └───────────┘ └──────────┘  │
                        │  ┌───────────┐ ┌──────────┐  │
                        │  │    GCS    │ │ Secret   │  │
                        │  │  Buckets  │ │ Manager  │  │
                        │  └───────────┘ └──────────┘  │
                        │  ┌───────────────────────┐   │
                        │  │ Vertex AI             │   │
                        │  │  Memory Bank          │   │
                        │  │  RAG Corpus           │   │
                        │  │  Session Service      │   │
                        │  └───────────────────────┘   │
                        └─────────────────────────────┘
```

### 7.1 Cloud Run (Gateway)

- **Service**: `hermes-gateway`
- **Image**: built via Cloud Build, pushed to Artifact Registry
- **Scaling**: min 1 → max N instances (configured via `--max-instances`)
- **Env vars / secrets**: injected from Secret Manager at startup
- **Ingress**: all traffic (public) with Cloud Armor at the load balancer layer
- **Service account**: bound to least-privilege IAM roles for Vertex AI, Firestore, BigQuery, GCS, Secret Manager

### 7.2 Vertex AI Reasoning Engine

- Hosts the ADK Runner and all agent definitions as a managed, auto-scaling deployment
- Communicates with the gateway over authenticated REST/gRPC
- Each agent deployment is versioned; blue/green promotion is handled via the Reasoning Engine API

### 7.3 Cloud Scheduler

- Invokes `POST /scheduler/trigger` on a configurable cron schedule
- Authenticates using an OIDC token (service account with `roles/run.invoker`)
- Used for batch analytics jobs, knowledge-base refresh, and memory consolidation

### 7.4 Data Services

| Service | Usage |
|---------|-------|
| **Firestore** | User profile documents, connector state |
| **BigQuery** | Interaction analytics, LLM quality metrics, skill extraction audit log |
| **GCS** | Task output files, uploaded knowledge documents, RAG source blobs |
| **Secret Manager** | All secrets accessed at runtime via the Secret Manager API (no secrets in env files) |
| **Vertex AI Memory Bank** | Managed episodic memory service; accessed via Vertex AI SDK |
| **Vertex AI RAG** | Managed retrieval-augmented generation corpus; embeddings and retrieval handled by Vertex AI |
