# RELEASE_NOTES.md

All notable changes to the Hermes GCP Agent Platform are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Feature] — ADK Eval Framework + agents-cli Integration (Issue #23)

### Problem
The test suite was fully offline unit tests — no evaluation of actual agent
response quality, tool selection correctness, or instruction adherence.
There was no structured way to detect regressions in agent behaviour
between code changes.

### Changes

#### eval/metrics.py — Extended
- Added `score_tool_trajectory(expected, actual) → ToolTrajectoryScore` —
  set-based precision/recall/F1 for tool call correctness. Mirrors
  `tool_trajectory_avg_score` from `agents-cli eval run`.
- Added `score_rubric(response, rubric) → RubricScore` — offline heuristic
  scoring against a written quality criterion. Approximates
  `rubric_based_final_response_quality_v1` for CI without GCP credentials.
- Both functions are fully offline and deterministic.

#### eval/run_eval.py — Extended
- Added `--config eval/eval_config.json --all` mode to run every evalset in
  one command.
- Composite scoring: `keyword × 0.4 + tool_f1 × 0.3 + rubric × 0.3`.
- Output table now shows keyword / tool / rubric / overall columns.
- `--output <path>` writes all results to JSON for CI artifact storage.
- `--threshold` flag overrides the default pass threshold.

#### eval/eval_config.json — New file
- Central eval configuration: 5 evalset entries, metric weights,
  pass threshold (0.8 production / 0.6 offline), agents-cli CLI reference.

#### eval/evalsets/developer.evalset.json — New file
- 5 cases: code review, retry logic, FastAPI structure, AttributeError debug,
  unit test generation. Each case has `tool_trajectory` and `rubric` fields.

#### eval/evalsets/task_agent.evalset.json — New file
- 5 cases: multi-agent onboarding, report + email, ticket escalation,
  project setup, budget alert. Tests multi-agent delegation patterns.

#### eval/evalsets/*.evalset.json — Enriched
- All existing evalsets (analytics, hr, it_helpdesk) updated with optional
  `tool_trajectory` and `rubric` fields for richer evaluation.

#### tests/eval/test_eval_metrics.py — Extended (31 tests, +21 new)
- `score_tool_trajectory`: 7 tests — perfect match, partial, no match,
  empty expected, agent transfer (`transfer_to_agent:HRAgent`).
- `score_rubric`: 5 tests — pass, short fail, toxic fail, score bounds, empty rubric.
- `run_eval.py` CLI: developer/task_agent evalsets, `--all --config` mode,
  no-args exit code.

#### AGENTS.md
- Added **Evaluation** section: metric table, evalset catalogue, evalset format,
  run commands (offline + agents-cli), eval-fix loop, threshold explanation.

#### README.md
- `What's New` updated: eval framework bullet, test count 222 → 304.
- `Testing` section: new **Run evaluations (offline)** subsection with
  commands and composite scoring explanation.

### Test count
**304 tests** — up from 288. All passing.

### How to use

```bash
# Offline CI — no credentials needed
python eval/run_eval.py --config eval/eval_config.json --all --dry-run

# Production eval — LLM-as-judge via agents-cli
pip install google-agents-cli
agents-cli eval run --config eval/eval_config.json
```

---

## [Feature] — AggregatorAgent + ADK Web UI Local Debug

### Problem
When TaskAgent dispatched parallel specialists via `ParallelDispatcher`, each agent
produced its own reply independently — users could receive multiple fragmented
responses in the same turn instead of one cohesive answer.

Additionally, local debugging required running the full FastAPI gateway, which needs
GCP credentials and is harder to inspect than a native ADK dev tool.

### Changes

#### agents/aggregator.py — New file
- `AggregatorAgent`: an `LlmAgent` that reads all specialist outputs already written
  to the session and synthesises them into one structured reply (Summary → per-domain
  sections → Next Steps). No external tools — reads context only.

#### agents/task_agent.py — SequentialPipeline replaces bare ParallelDispatcher
- Introduced `SequentialAgent("SequentialPipeline")` wrapping
  `[ParallelDispatcher, AggregatorAgent]` — specialists still run in parallel,
  but AggregatorAgent always consolidates before responding to the user.
- `build_dynamic_parallel_dispatcher()` return type changed from `ParallelAgent`
  to `SequentialAgent` (`DynamicSequentialPipeline`) for runtime JIT synthesis.
- `_TASK_AGENT_INSTRUCTION` updated: TaskAgent now transfers to `SequentialPipeline`
  (not `ParallelDispatcher`) for independent multi-domain tasks.

#### config.py
- Added `agent_model_aggregator: str = "gemini-2.5-flash"` — independently
  configurable so a lighter/different model can be swapped in for aggregation.

#### tests/conftest.py
- Added `_FakeSequentialAgent` stub and `SequentialAgent` export.
- Stubbed `google.adk.models` and `google.adk.models.lite_llm` to prevent
  test-isolation failures when real package imports pollute `sys.modules`.

#### tests/agents/test_aggregator.py — New file (12 tests)
- `TestBuildAggregatorAgent`: name, description, no tools
- `TestBuildTaskAgentSequentialPipeline`: pipeline structure, child order, 4 specialists
- `TestBuildDynamicParallelDispatcher`: None-on-empty, returns SequentialAgent, ends with AggregatorAgent

#### hermes_app/ — New ADK app entry point
- `hermes_app/__init__.py` + `hermes_app/agent.py`: exposes `root_agent` for
  `adk web` / `adk run` / `adk api_server`.
- Local debug command:
  ```
  adk web . --session_service_uri=sqlite:///local_sessions.db --reload_agents
  ```
  Opens browser UI at http://localhost:8000 with trace viewer, session history,
  and live reload. No GCP credentials required.

### Test count
**222/222 passing** (+12 from this release)

---

## [Hotfix] — SDK Migration: VertexAiMemoryBank → AgentEngine Memories API

> **Root cause:** `google-cloud-aiplatform >= 1.112` removed the standalone
> `vertexai.preview.memory_bank.MemoryBank` class. Memory is now managed via
> `vertexai.Client.agent_engines.memories.*` on any `AgentEngine` resource.
> The old import path `from google.cloud.aiplatform.agent_engines import VertexAiMemoryBank`
> no longer exists in the package, causing a startup `ModuleNotFoundError`.

### memory/memory_bank.py — Full Rewrite (SDK >= 1.112)
- **Removed** `_get_memory_bank_module()` helper and `vertexai.preview.memory_bank.MemoryBank` usage
- **Added** `_get_vertexai_client()` factory returning `vertexai.Client` (lazy, cached per instance)
- `HermesMemoryBank._bank` → `HermesMemoryBank._client`: holds `vertexai.Client` instead of SDK bank object
- `generate_memories()`: migrated from `bank.generate_memories(conversation=..., scope=..., wait_for_completion=False)` → `client.agent_engines.memories.generate(name=..., scope=..., direct_contents_source={...})`
- `ingest_events()`: migrated from `bank.ingest_events(events=[ConversationEvent(...)], scope=...)` → `client.agent_engines.memories.ingest_events(name=..., scope=..., direct_contents_source={...})`. Role normalisation: `"agent"` → `"model"` (Vertex AI content format)
- `fetch_memories()`: migrated from `bank.fetch_memories(scope=..., top_k=...)` → `client.agent_engines.memories.retrieve(name=..., scope=..., similarity_search_params={...})`
- `purge_memories()`: migrated from `bank.purge_memories(scope=..., force=...)` → list + `client.agent_engines.memories.purge(name=..., filter=..., force=...)`; dry_run now skips purge call entirely
- `delete_memory()`: migrated from `bank.memories.delete(name=...)` → `client.agent_engines.memories.delete(name=...)`
- `create_memory()`: migrated from `bank.memories.create(scope=..., fact=...)` → `client.agent_engines.memories.create(name=..., scope=..., fact=...)`
- `update_memory()`: migrated from `bank.memories.update(name=..., fact=...)` → `client.agent_engines.memories.update(name=..., fact=...)` (unchanged interface)
- `retrieve_profiles()`: **not supported** in AgentEngine memories API — now returns `[]` with log warning (use `fetch_memories()` instead)
- `list_revisions()`: **not supported** in AgentEngine memories API — now returns `[]` with log warning
- `create_memory_bank()`: migrated from `MemoryBank.create(display_name=...)` → `client.agent_engines.create(config={...})`. Idempotency: lists existing engines and returns matching `display_name` instead of creating a duplicate
- Updated module docstring with full migration notes

### tests/memory/test_memory_bank.py — Full Rewrite
- All 42 tests rewritten to mock `memory.memory_bank._get_vertexai_client` instead of `_get_memory_bank_module`
- `_make_mock_client()` helper replaces `_make_mock_module()`: returns `(mock_client, mock_memories)` pair reflecting new SDK shape
- Tests for `retrieve_profiles` / `list_revisions` updated to assert `== []` (unsupported in new SDK)
- `TestPurgeMemories.test_dry_run_*`: updated to assert `mock_memories.purge.assert_not_called()` (new dry_run semantics)
- `TestCreateMemoryBank`: replaced conflict-exception flow with idempotent list-and-match flow
- **210/210 tests pass**

### tests/conftest.py
- `vertexai` mock: added `Client=_MockVertexaiClient` with full `agent_engines.memories.*` stub
- Added `_mock_memories` with stubs for all 8 SDK methods: `generate`, `ingest_events`, `retrieve`, `list`, `create`, `update`, `delete`, `purge`
- Removed duplicate `_vertexai = _make_module(...)` definition (kept only the one with `Client=`)

### docs/ARCHITECTURE.md
- Replaced all `VertexAiMemoryBank` references with `AgentEngine MemoryBank`

### README.md
- Updated component table, architecture ASCII, and memory CRUD section to reflect new SDK class name
- Removed `retrieve_profiles` from method list (unsupported in SDK >= 1.112)

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
