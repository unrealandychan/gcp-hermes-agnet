# Multi-Agent Collaboration & Dynamic Agent Synthesis

This document explains how the system decomposes tasks, dynamically assembles
the right agents, and dispatches them in parallel or sequentially.

---

## Architecture Overview

```
User Request
     │
     ▼
┌────────────────────────────────────────────────────────────────────┐
│  Orchestrator (LlmAgent)                                           │
│  Single-domain → routes directly to specialist                     │
│  Multi-domain  → routes to TaskAgent                               │
└──────────────────────────┬─────────────────────────────────────────┘
                           │ transfer_to_agent("TaskAgent")
                           ▼
┌────────────────────────────────────────────────────────────────────┐
│  TaskAgent (LlmAgent — planner)                                    │
│                                                                    │
│  1. Receives task                                                  │
│  2. AgentSynthesizer assembles the right agents from:             │
│       • agent_registry.yaml  (domain keyword scoring)             │
│       • Skills corpus        (learned procedures → micro-agents)  │
│  3. Decides: parallel vs sequential dispatch                       │
│                                                                    │
│  sub_agents (dynamic, task-specific):                              │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  ParallelDispatcher (ParallelAgent)                         │  │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐│  │
│  │  │ AnalyticsAgt │ │   HRAgent    │ │  ITHelpdeskAgent     ││  │
│  │  │   (or any    │ │   (or any    │ │  (or any synthesised ││  │
│  │  │  synthesised)│ │  synthesised)│ │     micro-agent)     ││  │
│  │  └──────────────┘ └──────────────┘ └──────────────────────┘│  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                    │
│  Individual agents also available for sequential dispatch          │
└────────────────────────────────────────────────────────────────────┘
```

---

## How Agent Synthesis Works

Each request synthesises a **fresh, task-specific agent set** — the combination
changes based on what the task actually needs.

### Step 1 — Registry scoring

`agent_registry.yaml` defines 11+ agent templates across 3 tiers:

| Tier | Examples |
|------|---------|
| Core (always considered) | AnalyticsAgent, HRAgent, ITHelpdeskAgent, DeveloperAgent |
| Specialist (domain-matched) | FinanceAgent, LegalAgent, SecurityAgent, MarketingAgent, DataEngineerAgent, CustomerSupportAgent, CalendarSchedulerAgent |
| Skill-materialised | Synthesised at runtime from learned skills corpus |

Each template has `domain` keywords. The synthesiser scores templates by
keyword overlap with the task and picks the top matches.

### Step 2 — Skill hydration

`AgentSynthesizer` searches the **skills corpus** (RAG) for procedures that
match the task. Each matching skill becomes an **ephemeral micro-agent** with:
- A procedure-aware instruction (exact steps from the learned skill)
- Domain-appropriate tools
- A unique name: `Skill_<skill_id>`

### Step 3 — Merge & dispatch

Skill-hydrated agents (higher specificity) take precedence over registry
templates covering the same domain. Final set is capped at 6 agents.

**Parallel** when sub-tasks are independent → `ParallelDispatcher`
**Sequential** when sub-tasks depend on each other → `transfer_to_agent`

---

## Use Cases

### Example 1 — New Employee Onboarding (Parallel)

**Prompt:**
> "Onboard John Li as Engineering Manager starting next Monday.
> He needs a laptop, VPN access, and a desk on Floor 3.
> Also update the headcount report."

**Synthesised agents:** `HRAgent`, `ITHelpdeskAgent`, `AnalyticsAgent`
**Dispatch:** PARALLEL — all three tasks are fully independent

```
TaskAgent
  └── ParallelDispatcher
        ├── HRAgent         → create employee record, send onboarding email,
        │                     explain PTO/benefits policy
        ├── ITHelpdeskAgent → raise laptop request ticket, generate VPN
        │                     setup instructions, assign desk
        └── AnalyticsAgent  → update headcount BigQuery table for Eng Manager
```

**Aggregated response:**
```
✅ HR: John Li created in HRIS. Onboarding email sent. PTO: 15 days/year.
✅ IT: Laptop ticket #4821 raised (MacBook Pro M4). VPN guide attached.
      Desk 3-F-042 assigned.
✅ Analytics: Headcount updated — Engineering now 47 (+1).

⚠️  Still needed: John's personal email for account creation (IT blocked on this).
```

---

### Example 2 — Incident Response (Sequential — dependent steps)

**Prompt:**
> "Checkout API 5xx errors spiking since 14:30.
> Pull BigQuery error logs for the last 90 minutes, then write a post-mortem."

**Synthesised agents:** `AnalyticsAgent`, `DeveloperAgent`
**Dispatch:** SEQUENTIAL — post-mortem needs BQ results first

```
TaskAgent
  ├── [Step 1] AnalyticsAgent
  │     → SELECT error_code, COUNT(*), endpoint
  │       FROM prod_logs
  │       WHERE timestamp > TIMESTAMP_SUB(NOW(), INTERVAL 90 MINUTE)
  │         AND status_code >= 500
  │       GROUP BY 1,2,3 ORDER BY 2 DESC
  │     ← Returns: 1,847 errors; /checkout/payment: 1,203 (65%); root cause: DB timeout
  │
  └── [Step 2] DeveloperAgent (uses Step 1 output)
        → Generates post-mortem template pre-filled with:
          - Timeline, affected endpoints, error counts
          - Probable root cause (DB connection pool exhausted)
          - Action items: increase pool size, add circuit breaker
```

---

### Example 3 — Monthly Business Review Pack (Parallel)

**Prompt:**
> "Prepare our October MBR pack: Q3 revenue by region, headcount by department,
> open P1 incidents, and any security audit findings from last month."

**Synthesised agents:** `AnalyticsAgent`, `HRAgent`, `ITHelpdeskAgent`, `SecurityAgent`
**Dispatch:** PARALLEL — all four sections are independent

```
TaskAgent
  └── ParallelDispatcher
        ├── AnalyticsAgent  → Q3 revenue by region (BigQuery)
        ├── HRAgent         → Headcount by department (HRIS)
        ├── ITHelpdeskAgent → Open P1 incidents + status
        └── SecurityAgent   → Security audit findings (knowledge base)
```

**Aggregated response:** structured MBR pack with four sections, ready to paste
into slides.

---

### Example 4 — Finance + Legal Review (Specialist agents synthesised)

**Prompt:**
> "We're renewing the AWS contract. Pull last year's cloud spend by service,
> and flag any GDPR compliance concerns in the renewal terms."

**Synthesised agents:** `FinanceAgent`, `LegalAgent`, `AnalyticsAgent`
**Dispatch:** PARALLEL

```
TaskAgent
  └── ParallelDispatcher
        ├── AnalyticsAgent → BigQuery: cloud spend by AWS service, last 12 months
        ├── FinanceAgent   → Cost breakdown vs budget; flag overspend categories
        └── LegalAgent     → Review renewal terms for GDPR obligations,
                             data processing addendum requirements
```

> **Note:** `FinanceAgent` and `LegalAgent` are Tier-2 specialist templates —
> they are only synthesised when the task involves finance/legal keywords.
> They are never loaded for unrelated tasks.

---

### Example 5 — Skill-hydrated micro-agent (Learned procedure)

After the system processes enough similar requests, the skills corpus learns
procedures. Example: after 5+ BigQuery revenue queries, a skill is stored:

```
SKILL: analytics_bq_revenue_by_region (v3)
TRIGGER: When user asks for revenue breakdown by region or geography
PROCEDURE:
  1. Identify date range from user request (default: last full quarter)
  2. Query: SELECT region, SUM(revenue) FROM sales.orders WHERE ...
  3. Join with regions table for display names
  4. Return sorted descending with % of total
```

On the next revenue request, synthesiser creates:

```
Skill_analytics_bq_revenue_by_region (ephemeral micro-agent)
  instruction: [exact procedure above]
  tools: [bigquery, search]
```

This agent is **more specific** than the generic `AnalyticsAgent` and takes
precedence in the merged set — the system gets smarter with each use.

---

### Example 6 — Single domain (No TaskAgent, direct route)

**Prompt:**
> "What is our parental leave policy?"

**Synthesised agents:** `HRAgent` only
**Dispatch:** Orchestrator routes directly — no TaskAgent needed

```
Orchestrator → HRAgent (direct, single domain)
```

No synthesis overhead for simple requests.

---

## Parallel vs Sequential Decision Guide

| Condition | Use |
|-----------|-----|
| Sub-tasks need different data sources independently | **ParallelDispatcher** |
| Each agent works from the original request only | **ParallelDispatcher** |
| Agent B needs Agent A's output | **Sequential** |
| Only one domain involved | **Sequential (or direct)** |
| Order matters (e.g. query → analyse → report) | **Sequential** |

---

## How to Add a New Agent

### Option A — Add to `agent_registry.yaml` (recommended, no code)

```yaml
- name: FinanceAgent
  description: "Financial reporting, P&L, budget, cost analysis, invoices"
  domain: [finance, budget, cost, invoice, expense, revenue, forecast]
  tools: [bigquery, search, storage]
  priority: 2
  instruction: |
    You are a Finance specialist. Handle financial queries, P&L analysis,
    and budget tracking. Always include currency and time period context.
```

The synthesiser will automatically include this agent when tasks contain
finance-related keywords. **No Python changes needed.**

### Option B — Add a custom builder (for complex tool logic)

1. Create `agents/finance.py`:

```python
from google.adk.agents import LlmAgent
from config import Settings
from models.provider import get_model

def build_finance_agent(settings: Settings) -> LlmAgent:
    return LlmAgent(
        name="FinanceAgent",
        model=get_model(settings.agent_model_default),
        description="Financial reporting, P&L queries, and budget forecasting",
        instruction="You are a Finance specialist...",
        tools=[...],
    )
```

2. Register in `agents/loader.py` `_custom_builders`:

```python
from agents.finance import build_finance_agent
# inside _custom_builders():
"FinanceAgent": build_finance_agent,
```

3. Add to `agents.yaml` as well so it loads at deploy time.

---

## Configuration Reference

| Env var | Description |
|---------|-------------|
| `AGENT_MODEL_DEFAULT` | Default model for synthesised agents |
| `AGENT_MODEL_TASK_PLANNER` | Model for TaskAgent planner |
| `AGENT_MODEL_ORCHESTRATOR` | Model for Orchestrator |
| `AGENT_MODEL_ANALYTICS` | Model override for AnalyticsAgent |
| `AGENT_MODEL_HR` | Model override for HRAgent |
| `AGENT_MODEL_IT_HELPDESK` | Model override for ITHelpdeskAgent |
| `AGENT_MODEL_DEVELOPER` | Model override for DeveloperAgent |
| `SKILLS_CORPUS_NAME` | Vertex AI RAG corpus for learned skills |
| `KNOWLEDGE_CORPUS_NAME` | Vertex AI RAG corpus for knowledge base |
