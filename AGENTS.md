# AGENTS.md — GCP Hermes Agent Platform

This file is read by AI coding assistants (Claude Code, Hermes Agent, GitHub Copilot, Cursor)
and human contributors. It describes how this codebase is structured, how to extend it, and
the conventions that keep everything consistent.

**Read this before making any changes.**

---

## Project Overview

A production-grade, self-learning multi-agent platform running on Google Cloud.
- **Runtime:** Google ADK + Vertex AI Reasoning Engine + Cloud Run
- **Pattern:** Orchestrator routes to domain sub-agents; each agent learns from interactions
- **Testing:** Fully offline — all GCP/ADK services are mocked in `tests/conftest.py`

---

## Project Structure

```
agents/          # Sub-agent builders (one file per domain)
  loader.py      # AgentLoader — reads agents.yaml, builds agents dynamically
  orchestrator.py
  analytics.py / hr.py / it_helpdesk.py / developer.py / task_agent.py
agents.yaml      # Declarative agent registry — add new agents here, not in Python

skills/          # Human-readable skill files (.md with YAML frontmatter)
  TEMPLATE.md    # Copy this to create a new skill
  examples/      # Seeded example skills for each domain

memory/
  skill_extractor.py   # LLM-based skill extraction from interactions
  skill_learning.py    # after_agent_callback — fires after every turn
  skill_loader.py      # Loads skills/*.md files into RAG corpus
  skill_store.py       # Vertex AI RAG CRUD
  skill_models.py      # Pydantic Skill model
  user_profile.py      # User profile store (Firestore) — who the user is
  context_budget.py    # Guards context window: prioritises memory by tier

tools/           # ADK FunctionTool wrappers
models/          # LiteLLM provider factory
connectors/      # Telegram / Slack / Teams webhook handlers
gateway/         # FastAPI app (auth, /chat, /tasks, observability)
infra/           # GCP bootstrap (setup.sh, clouddeploy.yaml)
scripts/         # deploy.py, setup_rag.py, demo/
tests/
  conftest.py    # All GCP/ADK stubs — no credentials needed
  agents/
  gateway/
  memory/
```

---

## How to Add a New Sub-Agent

The preferred approach: **edit `agents.yaml` only** — no Python required.

```yaml
# agents.yaml
agents:
  - name: FinanceAgent
    description: "Financial reporting, P&L queries, budget forecasting"
    model: ${AGENT_MODEL_FINANCE:-gemini-2.0-flash}
    tools: [bigquery, search, storage]
```

Valid tool names: `bigquery`, `search`, `storage`, `rag_knowledge`, `code_sandbox`, `mcp_filesystem`, `mcp_sse`.

**If you need custom logic** (e.g. a tool unique to that agent):
1. Create `agents/finance.py` with a `build_finance_agent(settings) -> LlmAgent` function
2. Register it in `agents/loader.py` `_CUSTOM_BUILDERS` dict
3. Add a test in `tests/agents/test_agent_builds.py`

---

## How to Add a New Tool

1. Create `tools/your_tool.py`:
```python
from google.adk.agents import LlmAgent  # not needed for tools
from google.adk.tools import FunctionTool

def your_function(param: str) -> str:
    """Docstring becomes the tool description shown to the LLM."""
    ...
    return result

def make_your_tool() -> FunctionTool:
    return FunctionTool(func=your_function)
```

2. Add the tool name to `agents/loader.py` `_TOOL_FACTORIES` dict:
```python
_TOOL_FACTORIES = {
    ...
    "your_tool": tools.your_tool.make_your_tool,
}
```

3. Add a unit test in `tests/tools/` — mock all external calls.

4. Add the tool key to any agent's `tools:` list in `agents.yaml`.

---

## How to Add a Skill (No Code Required)

Skills are `.md` files in `skills/`. They are loaded into the RAG corpus at startup.

1. Copy `skills/TEMPLATE.md` to `skills/your-skill-name.md`
2. Fill in the YAML frontmatter and steps
3. The skill is auto-seeded on next gateway startup

See `skills/TEMPLATE.md` for the full format.

---

## Running Tests

```bash
# All tests — fully offline, no GCP credentials needed
python -m pytest tests/ -v

# Specific area
python -m pytest tests/agents/ -v
python -m pytest tests/memory/ -v
python -m pytest tests/gateway/ -v
```

**Never add a test that requires real GCP credentials.** Mock everything using the patterns
in `tests/conftest.py`. New GCP services follow the same stub pattern already established there.

---

## Deploying

```bash
# Staging
python scripts/deploy.py --env staging

# Production
python scripts/deploy.py --env production
```

Prerequisites: `gcloud` authenticated as project owner, `.env` populated from `.env.example`.

---

## Key Conventions

### Async-first
All agent callbacks, gateway endpoints, and memory operations must be `async`. Use
`asyncio.to_thread()` to wrap blocking SDK calls (see `skill_store._upload_skill` for example).

### Settings singleton
`config.get_settings()` is `@lru_cache`. **Never call `Settings()` directly** — always use
`get_settings()`. This ensures tests can mock settings once and have it propagate everywhere.

### Fire-and-forget for learning
Skill extraction happens in `asyncio.create_task()` to avoid blocking user responses.
Do not `await` anything in `after_agent_callback` that involves LLM calls or RAG uploads.

### Context budget
When injecting memory into system prompts, always call `memory.context_budget.prioritise_memory()`
first. The default budget is `MEMORY_CONTEXT_BUDGET_TOKENS=2000`. This prevents silent context
window exhaustion in long sessions.

### Agent descriptions matter
ADK's AutoFlow routing is driven by each sub-agent's `description` field. Keep descriptions
specific, domain-focused, and keyword-rich. Vague descriptions cause mis-routing.

---

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| `get_settings()` returns stale values in tests | Use `get_settings.cache_clear()` in test teardown |
| Adding a new GCP service import breaks offline tests | Add it to the stub registry in `tests/conftest.py` |
| `asyncio.create_task()` in tests raises "no running loop" | Use `pytest-asyncio` with `@pytest.mark.asyncio` |
| RAG `retrieval_query` is synchronous but called in async context | Wrap in `asyncio.to_thread()` |
| Large memory injection silently fills context window | Always use `context_budget.prioritise_memory()` |
| `agents.yaml` env var substitution not working | Use `${VAR:-default}` syntax, not `$VAR` |

---

## rekipedia Codebase Knowledge Base

This repository has been scanned by [rekipedia](https://github.com/unrealandychan/rekipedia).
A structured wiki, symbol index, and RAG embeddings are in `.rekipedia/`.

### Ask questions about this codebase

```bash
reki ask "<your question>"
# Examples:
reki ask "how does authentication work?"
reki ask "what is the entry point of the application?"
reki ask "which modules are most critical?"
```

### MCP server (for Claude Code, Cursor, and other MCP-aware agents)

```bash
reki mcp
```

Available MCP tools: `ask`, `search_nodes`, `get_context`, `get_relationships`, `get_hub_nodes`, `get_impact`

> Tip: `.mcp.json` in the repo root auto-configures the MCP server for Claude Code.
