# RELEASE_NOTES.md

All notable changes to the Hermes GCP Agent Platform are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Phase 3] — Memory Bank Complete Implementation + CI

### Memory Bank — Full CRUD (memory/memory_bank.py)
- `generate_memories()`: added `wait_for_completion=False` — true fire-and-forget async generation; agent never blocks waiting for memory writes
- `ingest_events()`: new — stream conversation events via IngestEvents RPC; more production-grade than generate_memories(), SDK batches events automatically
- `purge_memories()`: new — bulk-delete all memories for a user with optional `dry_run` mode; powers the fixed DELETE /memories endpoint
- `delete_memory()`: new — delete a specific memory by resource name
- `create_memory()`: new — directly write a memory fact without LLM extraction (memory-as-a-tool pattern)
- `update_memory()`: new — correct/update an existing memory fact
- `retrieve_profiles()`: new — retrieve structured user memory profile (higher-level than fetch_memories)
- Updated module docstring to list all 10 public methods
- 17 new unit tests (total memory bank tests: 39)

### Gateway — Memory CRUD Endpoints (gateway/main.py)
- `_memory_bank` global: `HermesMemoryBank` initialized in lifespan; graceful skip if `MEMORY_BANK_RESOURCE_NAME` not set
- `DELETE /memories/{user_id}`: **fixed** — replaced broken `_runner.memory_service.delete_memories` stub (ADK Runner has no `memory_service` attribute) with real `_memory_bank.purge_memories()` call
- `GET /memories/{user_id}`: new — returns `{memories: [...], profiles: [...]}` (owner-only)
- `POST /memories/{user_id}`: new — create memory fact with `{fact: str}` body, returns 201 with resource name (owner-only)
- Updated module docstring to list all 5 memory endpoints

### CI — GitHub Actions
- `.github/workflows/ci.yml`: new — pytest matrix on Python 3.11 + 3.12
- Triggers on push to `main`, `feat/**`, `fix/**` and all PRs to `main`
- Lightweight test deps only (heavy GCP SDKs stubbed out, no credentials needed)
- **219/219 tests pass** on both Python versions

---

## [Phase 2 Bugfixes] — Architecture Bugs Fixed

### memory/cross_corpus.py
- `retrieve_cross_corpus()` converted to `async def`
- SDK calls wrapped in `asyncio.to_thread()` + `asyncio.gather()` for true parallel corpus queries
- No longer blocks the event loop under concurrent requests

### eval/online_monitor.py
- `build_online_monitor()` now calls `get_settings()` to obtain `project_id` (was hardcoded/missing)
- Added `try/except` around BigQuery client initialization — graceful degradation if BigQuery is unavailable

### gateway/main.py
- `PolicyEngine` fully wired into `POST /chat`:
  - Prompt check: if `action == "block"` → HTTP 400 with policy reason
  - Response check: if `action == "block"` → response text replaced with `[Response blocked by governance policy]` + warning log
- Previously PolicyEngine was imported and built but not applied to requests

---

## [Phase 1 + 2] — Gemini Enterprise Agent Platform Integration

### Issue #5 — VertexAiMemoryBank (native long-term memory)
- Replace RAG-upload memory hack with official `VertexAiMemoryBank` API
- `memory/memory_bank.py`: `HermesMemoryBank` wrapper — generate, fetch, list revisions
- `memory/skill_learning.py`: fire-and-forget `_persist_to_memory_bank()` on every turn
- `setup_wizard.py`: auto-create MemoryBank resource, write resource name to `.env`
- `config.py`: `MEMORY_BANK_RESOURCE_NAME` setting
- 27 offline unit tests

### Issue #6 — Agent Evaluation Service
- `eval/metrics.py`: offline `EvalMetrics` scoring (groundedness, task_completion, safety)
- `eval/run_eval.py`: CLI runner — `--dry-run`, exits 1 if avg overall score < 0.6
- `eval/evalsets/`: 3 evalsets (Analytics, IT Helpdesk, HR) × 5 test cases each
- `eval/online_monitor.py`: async BigQuery quality logging per agent turn
- 15 offline unit tests

### Issue #7 — Semantic Governance Policies
- `governance/policies.yaml`: 5 declarative policies (purchase limits, legal escalation, PII, credential disclosure, medical)
- `governance/policy_engine.py`: regex-based `check_response()` / `check_prompt()` with agent-scoped rules
- 12 offline unit tests

### Issue #8 — Agent Registry
- `registry/agent_registry.py`: `HermesAgentRegistry` — register, list, get agents via Vertex AI Agent Registry
- `scripts/register_agents.py`: CLI to sync `agents.yaml` → Agent Registry (`--dry-run` supported)
- 8 offline unit tests

### Issue #9 — Agent Gateway
- `gateway/agent_gateway.py`: governed routing via Gemini Enterprise Agent Gateway
- `AgentGatewayClient`: async send + stream, graceful fallback to direct Runner when gateway is disabled
- `config.py`: `AGENT_GATEWAY_ENDPOINT`, `AGENT_GATEWAY_API_KEY`, `AGENT_GATEWAY_TIMEOUT_SECONDS`
- 13 offline unit tests

### Issue #10 — Cross Corpus RAG
- `memory/cross_corpus.py`: query multiple RAG corpora, merge + re-rank by score, deduplicate, top-k
- `build_cross_corpus_retriever()`: reads corpus list from settings
- 9 offline unit tests

### Teardown
- `teardown_wizard.py`: single command to delete ALL GCP resources (PoC cleanup)
- Idempotent, graceful, safe dependency order
- Double confirmation (`yes` required) — project never deleted
- 26 offline unit tests

---

## [Unreleased → Phase 1] — Config-Driven Platform & Memory Foundation

### AGENTS.md — AI & contributor onboarding guide (closes #1)
- Root-level `AGENTS.md` that documents project structure, conventions, and how to add new agents, tools, and skills
- Read by AI coding assistants (Claude Code, Hermes Agent, GitHub Copilot, Cursor) to understand codebase conventions without guessing
- Includes a Pitfalls section covering `get_settings()` lru_cache, test mocking patterns, and context budget usage

### Skills system — human-readable skill files (closes #2)
- `skills/TEMPLATE.md` — copy-paste template for writing skills in YAML frontmatter + Markdown body format
- `skills/examples/` — 3 seed skills: `analytics-retention-query`, `it-vpn-access-request`, `hr-pto-balance-query`
- `memory/skill_loader.py` — `SkillLoader` scans `skills/` directory, parses frontmatter, returns `Skill` objects. Fully offline, no GCP required
- `tests/memory/test_skill_loader.py` — 11 unit tests
- Users can now add skills by creating `.md` files — no Python required

### Config-driven agent registry (closes #3)
- `agents.yaml` — declarative agent registry at repo root
- `agents/loader.py` — `AgentLoader` reads `agents.yaml`, resolves `${ENV_VAR:-default}` substitution
- `agents/orchestrator.py` — refactored to use `AgentLoader` instead of hardcoded imports
- `tests/agents/test_agent_loader.py` — 9 unit tests

### Memory: user profile + context budget guard (closes #4)
- `memory/user_profile.py` — `UserProfile` Pydantic model + Firestore-backed CRUD
- `memory/context_budget.py` — two-tier memory injection with configurable token budget (`MEMORY_CONTEXT_BUDGET_TOKENS`, default 2000)
- 7 + 9 offline unit tests

### Tool stubs for module-level use
- `tools/bigquery_tool.py` — `run_bigquery_query()` module-level function
- `tools/search_tool.py` — `search_knowledge_base()` module-level function
- `tools/storage_tool.py` — `read_gcs_file()` / `write_gcs_file()` module-level functions

### Fixed
- `gateway/observability.py` `agent_span` — `isinstance(span, Span)` raised `TypeError` when OpenTelemetry `Span` was a MagicMock stub. Fixed by guarding with `isinstance(Span, type)` before the isinstance check
- `tests/agents/test_agent_builds.py` — updated assertion from `== 4` to `>= 4` to accommodate config-driven loader

### Test Coverage
| Module | Tests | Status |
|---|---|---|
| `memory/skill_loader.py` | 11 | ✅ |
| `memory/user_profile.py` | 7 | ✅ |
| `memory/context_budget.py` | 9 | ✅ |
| `agents/loader.py` | 9 | ✅ |
| All existing tests | 54 | ✅ |
| **Subtotal** | **90** | ✅ |

---

## [0.1.0] — Initial PoC

- Vertex AI Reasoning Engine + Cloud Run gateway
- 5 hardcoded domain agents (Analytics, IT Helpdesk, HR, Developer, Task)
- Self-learning skills via SkillExtractor → Vertex AI RAG
- Model Armor prompt/response screening
- OpenTelemetry + Cloud Trace observability
- Telegram / Slack / Teams connectors
- Fully offline test suite (all GCP/ADK services mocked)
