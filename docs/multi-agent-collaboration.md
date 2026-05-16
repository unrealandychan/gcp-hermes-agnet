# Multi-Agent Collaboration

This document describes how TaskAgent orchestrates specialist agents to handle
requests that span multiple domains.

---

## Architecture

```
User Request
     │
     ▼
┌──────────────────────────────────────────────────────────┐
│  Orchestrator (LlmAgent)                                 │
│  Routes to the correct agent based on description        │
└────────────┬─────────────────────────────────────────────┘
             │ transfer_to_agent("TaskAgent")  [multi-domain]
             │ transfer_to_agent("AnalyticsAgent")  [data only]
             │ transfer_to_agent("HRAgent")  [HR only]
             │ ...
             ▼
┌──────────────────────────────────────────────────────────┐
│  TaskAgent (LlmAgent)                                    │
│  Multi-domain planner & coordinator                      │
│                                                          │
│  sub_agents:                                             │
│    ┌──────────────────┐  ┌──────────────────┐           │
│    │  AnalyticsAgent  │  │     HRAgent      │           │
│    │  BigQuery, data  │  │  Policies, PTO   │           │
│    └──────────────────┘  └──────────────────┘           │
│    ┌──────────────────┐  ┌──────────────────┐           │
│    │ ITHelpdeskAgent  │  │ DeveloperAgent   │           │
│    │ Incidents, VPN   │  │ Code, debugging  │           │
│    └──────────────────┘  └──────────────────┘           │
└──────────────────────────────────────────────────────────┘
```

**Key design principles:**
- TaskAgent uses ADK AutoFlow — no explicit routing code needed.
- It delegates ONE sub-task per agent call and waits for the result.
- After all delegations are complete, TaskAgent synthesises a final answer.

---

## Use Cases

### 1 — New Employee Onboarding

**Prompt:**
> "I'm starting on Monday. What laptop will I receive, how do I request VPN
> access, and what is the PTO policy for new hires?"

**Agent flow:**
1. Orchestrator → TaskAgent (multi-domain: IT + HR)
2. TaskAgent → ITHelpdeskAgent: laptop assignment and VPN request process
3. TaskAgent → HRAgent: PTO policy for new employees
4. TaskAgent aggregates both answers into a single onboarding guide

---

### 2 — Incident Response with Analytics

**Prompt:**
> "Our checkout API is returning 5xx errors. Fetch the last hour of error logs
> from BigQuery, then help me write a post-mortem template."

**Agent flow:**
1. Orchestrator → TaskAgent (multi-domain: Analytics + Developer)
2. TaskAgent → AnalyticsAgent: BigQuery query for 5xx errors in last 60 min
3. TaskAgent → DeveloperAgent: generate a post-mortem template using the query results
4. TaskAgent returns error summary + post-mortem template

---

### 3 — Monthly Business Review (MBR) Preparation

**Prompt:**
> "Prepare an MBR pack: Q3 revenue by region from BigQuery, current headcount
> by department, and a list of all open P1 incidents."

**Agent flow:**
1. Orchestrator → TaskAgent (multi-domain: Analytics + HR + IT)
2. TaskAgent → AnalyticsAgent: Q3 revenue by region
3. TaskAgent → HRAgent: headcount by department
4. TaskAgent → ITHelpdeskAgent: open P1 incidents and status
5. TaskAgent aggregates into a structured MBR briefing

---

## How to Add a New Specialist Agent

Follow these steps to make a new agent available for TaskAgent delegation:

### Step 1 — Define the agent in `agents.yaml`

```yaml
- name: FinanceAgent
  description: "Financial reporting, P&L queries, and budget forecasting"
  model: ${AGENT_MODEL_FINANCE:-gemini-2.5-flash}
  tools: [bigquery, search]
```

Keep the `description` specific — ADK uses it for routing decisions.

### Step 2 — (Optional) Create a custom builder

If the agent needs custom tool logic beyond what `agents.yaml` supports,
create `agents/finance.py`:

```python
from google.adk.agents import LlmAgent
from config import Settings
from models.provider import get_model

def build_finance_agent(settings: Settings) -> LlmAgent:
    return LlmAgent(
        name="FinanceAgent",
        model=get_model(settings.agent_model_orchestrator),
        description="Financial reporting, P&L queries, and budget forecasting",
        tools=[...],
    )
```

Then register it in `agents/loader.py` `_custom_builders`:

```python
from agents.finance import build_finance_agent

return {
    ...
    "FinanceAgent": build_finance_agent,
}
```

### Step 3 — The agent is automatically available to TaskAgent

`agents/orchestrator.py` injects all specialist agents (every agent that is
not TaskAgent itself) into `build_task_agent(settings, specialist_agents)`.
No further changes are needed — TaskAgent will route to the new agent via
AutoFlow based on its description.

### Step 4 — Add a test

Add a test class in `tests/agents/test_agent_builds.py` following the
existing patterns.

---

## Configuration Reference

| Setting | Description |
|---------|-------------|
| `AGENT_MODEL_TASK_PLANNER` | Model used by TaskAgent (default: `gemini-2.5-flash`) |
| `AGENT_MODEL_ANALYTICS` | Model for AnalyticsAgent |
| `AGENT_MODEL_HR` | Model for HRAgent |
| `AGENT_MODEL_IT_HELPDESK` | Model for ITHelpdeskAgent |
| `AGENT_MODEL_DEVELOPER` | Model for DeveloperAgent |
