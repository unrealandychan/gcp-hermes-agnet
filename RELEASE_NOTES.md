# RELEASE_NOTES.md

All notable changes to the Hermes GCP Agent Platform are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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

## [Unreleased]

### Added

**`AGENTS.md` — AI & contributor onboarding guide** (closes #1)
- Root-level `AGENTS.md` that documents project structure, conventions, and how to add new agents, tools, and skills.
- Read by AI coding assistants (Claude Code, Hermes Agent, GitHub Copilot, Cursor) to understand codebase conventions without guessing.
- Includes a Pitfalls section covering `get_settings()` lru_cache, test mocking patterns, and context budget usage.

**Skills system — human-readable skill files** (closes #2)
- `skills/TEMPLATE.md` — copy-paste template for writing skills in YAML frontmatter + Markdown body format.
- `skills/examples/` — 3 seed skills: `analytics-retention-query`, `it-vpn-access-request`, `hr-pto-balance-query`.
- `memory/skill_loader.py` — `SkillLoader` scans `skills/` directory, parses frontmatter, returns `Skill` objects. Fully offline, no GCP required.
- `tests/memory/test_skill_loader.py` — 11 unit tests covering happy path, missing frontmatter, invalid YAML, TEMPLATE skip, subdirectory recursion.
- Users can now add skills by creating `.md` files — no Python required.

**Config-driven agent registry** (closes #3)
- `agents.yaml` — declarative agent registry at repo root. Add new agents by editing YAML; no Python changes needed.
- `agents/loader.py` — `AgentLoader` reads `agents.yaml`, resolves `${ENV_VAR:-default}` substitution, builds sub-agents via registered custom builders or a generic `LlmAgent` fallback.
- `agents/orchestrator.py` — refactored to use `AgentLoader` instead of hardcoded imports. Orchestrator instruction no longer hardcodes agent names.
- `tests/agents/test_agent_loader.py` — 9 unit tests: YAML parsing, env var substitution, missing name field, unknown tool warning, custom builder dispatch.

**Memory: user profile + context budget guard** (closes #4)
- `memory/user_profile.py` — `UserProfile` Pydantic model + Firestore-backed `get_or_create_profile()` / `update_profile()`. Separates *who the user is* (profile) from *what the agent has learned* (skills).
- `memory/context_budget.py` — `build_context_summary()` and `prioritise_memory()`: two-tier memory injection with configurable token budget (`MEMORY_CONTEXT_BUDGET_TOKENS`, default 2000). Prevents silent context window exhaustion in long sessions.
- `tests/memory/test_user_profile.py` — 7 unit tests (Firestore mocked).
- `tests/memory/test_context_budget.py` — 9 unit tests covering budget enforcement, priority ordering, empty inputs, Tier 1/2 combination.

**Tool stubs for module-level use** (required by TaskAgent)
- `tools/bigquery_tool.py` — added `run_bigquery_query()` module-level function.
- `tools/search_tool.py` — added `search_knowledge_base()` module-level function.
- `tools/storage_tool.py` — added `read_gcs_file()` / `write_gcs_file()` module-level functions.

### Fixed

- `gateway/observability.py` `agent_span` — `isinstance(span, Span)` raised `TypeError` when OpenTelemetry `Span` was a MagicMock stub (pre-existing bug). Fixed by guarding with `isinstance(Span, type)` before the isinstance check. Affected 3 pre-existing test failures.
- `tests/agents/test_agent_builds.py` `TestOrchestratorBuild.test_has_four_sub_agents` — updated assertion from `== 4` to `>= 4` to accommodate the config-driven loader (which reads from `agents.yaml` and may include 5+ agents).

### Test Coverage

| Module | Tests | Status |
|---|---|---|
| `memory/skill_loader.py` | 11 | ✅ All pass |
| `memory/user_profile.py` | 7 | ✅ All pass |
| `memory/context_budget.py` | 9 | ✅ All pass |
| `agents/loader.py` | 9 | ✅ All pass |
| All existing tests | 54 | ✅ All pass (+ 3 pre-existing fixed) |
| **Total** | **90** | ✅ 90/90 |

---

## [0.1.0] — Initial PoC

- Vertex AI Reasoning Engine + Cloud Run gateway
- 5 hardcoded domain agents (Analytics, IT Helpdesk, HR, Developer, Task)
- Self-learning skills via SkillExtractor → Vertex AI RAG
- Model Armor prompt/response screening
- OpenTelemetry + Cloud Trace observability
- Telegram / Slack / Teams connectors
- Fully offline test suite (all GCP/ADK services mocked)
