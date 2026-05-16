---
slug: repository-structure
title: "Repository Map"
section: architecture
tags: [architecture, repository-structure, overview]
pin: false
importance: 92
created_at: 2026-05-16T04:11:20Z
rekipedia_version: 0.15.1
---

# Repository Map

This page is a navigation-first map of the repository: what lives where, how to find major areas quickly, and which files anchor each top-level directory. It intentionally avoids deep architectural or API discussion.

## Annotated Repository Tree

```text
.
├── .env.example                  # Sample environment variables for local setup
├── .gitignore                    # Ignore rules
├── .python-version               # Python runtime pin
├── AGENTS.md                    # Agent-facing guidance
├── CLAUDE.md                    # Assistant / workflow guidance
├── Dockerfile.gateway           # Container image for the gateway
├── README.md                    # Project overview and entry point for humans
├── RELEASE_NOTES.md             # Release history
├── agents.yaml                  # Declarative agent registry/configuration
├── config.py                    # Central application settings
├── conftest.py                  # Repository-wide pytest fixtures
├── pyproject.toml               # Python project metadata and tooling config
├── pytest.ini                   # Pytest configuration
├── requirements.txt             # Python dependency pinning
├── setup_wizard.py              # Interactive bootstrap wizard
├── teardown_wizard.py           # Interactive teardown wizard
├── docs/                        # Markdown documentation
├── eval/                        # Evaluation harness, metrics, and eval sets
├── gateway/                     # FastAPI-based gateway / server entrypoint
├── governance/                  # Policy definitions and policy engine
├── infra/                       # Deployment and infrastructure scripts
├── memory/                      # Memory bank, skills, profiles, retrieval helpers
├── models/                      # Model/provider resolution helpers
├── registry/                   # Agent registry abstraction
├── scripts/                     # Operational scripts and demos
├── skills/                      # Skill templates and examples
├── tests/                       # Automated tests
├── tools/                       # Tool integrations and connectors
├── connectors/                  # Chat platform connectors
└── ui/                          # TypeScript/Next.js web UI
```

## Repository Layout by Top-Level Directory

| Path | Purpose | Key Files | Notes |
|---|---|---|---|
| `agents/` | Agent definitions and assembly helpers | `agents/__init__.py`, `agents/analytics.py`, `agents/developer.py`, `agents/hr.py`, `agents/it_helpdesk.py`, `agents/loader.py`, `agents/orchestrator.py`, `agents/task_agent.py` | Houses the main agent-building code. The loader and orchestrator files are the most useful starting points when searching for how agents are created and registered. |
| `connectors/` | Platform-facing chat connectors | `connectors/runner.py`, `connectors/slack.py`, `connectors/teams.py`, `connectors/telegram.py` | Contains entry points for external messaging channels and a generic runner. Good place to look when tracing inbound/outbound chat integration. |
| `gateway/` | Runtime server and request handling | `gateway/main.py`, `gateway/agent_gateway.py`, `gateway/auth.py`, `gateway/tasks.py`, `gateway/observability.py` | Main server package. Includes the app startup path, task handling, auth helpers, and tracing setup. |
| `memory/` | Memory and skill persistence helpers | `memory/memory_bank.py`, `memory/cross_corpus.py`, `memory/context_budget.py`, `memory/skill_loader.py`, `memory/skill_store.py`, `memory/user_profile.py` | Centralizes memory-bank access, skill ingestion/loading, prompt budgeting, and user profile helpers. |
| `tools/` | Tool wrappers and external service adapters | `tools/bigquery_tool.py`, `tools/calendar_tool.py`, `tools/drive_tool.py`, `tools/gmail_tool.py`, `tools/mcp_connector.py`, `tools/model_armor.py`, `tools/scheduler_tool.py`, `tools/search_tool.py`, `tools/storage_tool.py` | A collection of utility integrations used by agents. The naming makes the service boundary clear: search, storage, workspace apps, scheduling, and MCP support. |
| `eval/` | Evaluation and monitoring code | `eval/metrics.py`, `eval/online_monitor.py`, `eval/run_eval.py`, `eval/evalsets/*.json` | Contains offline eval scoring, online monitoring configuration, and prebuilt eval sets. Useful for quality and regression checks. |
| `ui/` | TypeScript/Next.js frontend | `ui/package.json`, `ui/next.config.ts`, `ui/src/app/page.tsx`, `ui/src/app/chat/page.tsx`, `ui/src/lib/api.ts`, `ui/src/components/MessageBubble.tsx`, `ui/src/types/chat.ts` | The only major non-Python codebase area. Holds the chat UI, API client, and shared TypeScript types. |
| `scripts/` | Utility, deployment, and demo scripts | `scripts/deploy.py`, `scripts/register_agents.py`, `scripts/setup_rag.py`, `scripts/demo/e2e_test.py`, `scripts/demo/seed_bigquery.py`, `scripts/demo/seed_knowledge_base.py`, `scripts/demo/showcase.sh` | Operational scripts and reproducible demos live here. Subdirectory `scripts/demo/` is especially useful for end-to-end workflows and sample data setup. |
| `tests/` | Automated test suite | `tests/agents/*`, `tests/gateway/*`, `tests/memory/*`, `tests/tools/*`, `tests/eval/*`, `tests/governance/*`, `tests/registry/*`, `tests/conftest.py` | Mirrors the source tree with focused tests per subsystem. `tests/conftest.py` contains broader test doubles and registration helpers. |
| `docs/` | Human documentation | `docs/README.md` is absent; notable files include `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/cost-estimation.md` | Markdown documentation for deeper reading. This map page intentionally stays at the directory-navigation level rather than reproducing those details. |
| `infra/` | Infrastructure and deployment assets | `infra/clouddeploy.yaml`, `infra/setup.sh` | Deployment-oriented assets and provisioning helpers. |
| `models/` | Model provider selection helpers | `models/provider.py` | Small but important module for resolving and obtaining model backends. |
| `registry/` | Agent registry implementation | `registry/agent_registry.py` | Encapsulates agent registration and lookup. |
| `governance/` | Policy engine and policy data | `governance/policies.yaml`, `governance/policy_engine.py` | Contains policy rules and the engine that loads/evaluates them. |
| `skills/` | Skill templates and examples | `skills/TEMPLATE.md`, `skills/examples/analytics-retention-query.md`, `skills/examples/hr-pto-balance-query.md`, `skills/examples/it-vpn-access-request.md` | Lightweight knowledge assets intended to be copied or adapted into new skills. |
| `docs/`, `scripts/`, `tests/` | Cross-cutting repository support areas | See above | These three directories are often the fastest path to understanding how the repo is used in practice: docs explain, scripts operate, tests validate. |

## Language and File-Type Breakdown

The repository has a mixed-language footprint:

| Language / Format | Evidence in Repository | Typical Areas |
|---|---|---|
| Python | `config.py`, `gateway/*.py`, `memory/*.py`, `tools/*.py`, `scripts/*.py`, `tests/*.py` | Core runtime, automation, test suite, and service integrations |
| TypeScript | `ui/next.config.ts`, `ui/src/**/*.tsx`, `ui/src/**/*.ts` | Frontend app, API client, and shared UI types |
| Markdown | `README.md`, `RELEASE_NOTES.md`, `docs/*.md`, `skills/**/*.md`, `scripts/demo/README.md` | Human-readable docs, skill templates, and demo instructions |
| YAML | `agents.yaml`, `governance/policies.yaml`, `infra/clouddeploy.yaml`, `.github/workflows/ci.yml` | Configuration, policy, and CI/deployment definitions |
| JSON | `eval/evalsets/*.evalset.json`, `ui/package.json` | Eval fixtures and frontend package metadata |
| Shell | `infra/setup.sh`, `scripts/demo/showcase.sh` | Environment setup and demo orchestration |

The codebase is primarily Python, with a substantial TypeScript frontend and a sizable Markdown documentation/knowledge layer. That mixed footprint is worth remembering when navigating the repository: backend behavior usually lives in Python packages, while UI concerns live under `ui/`.

## Navigation Guide: Where to Start

### For backend runtime work
Start with `gateway/main.py` and `gateway/tasks.py`, then move into `agents/`, `tools/`, and `memory/` as needed. The runtime is split across several packages, so locating the right subsystem is usually faster than searching from the root.

### For agent configuration or onboarding
Check `agents.yaml`, `scripts/register_agents.py`, and `agents/loader.py`. If you are changing how agents are declared or discovered, these files are the best first stop.

### For demos and operational workflows
Look in `scripts/demo/` for end-to-end flows, sample content, and data seeding helpers. `scripts/deploy.py` and `infra/` are the natural follow-on for deployment tasks.

### For frontend navigation
Open `ui/src/app/page.tsx` for the login landing page and `ui/src/app/chat/page.tsx` for the main chat experience. Shared client logic lives in `ui/src/lib/api.ts`.

### For testing and validation
Use `tests/` as the mirror of the codebase. The grouping by feature area makes it easy to find coverage for a specific module family.

> **Sources:** `README.md` · `agents.yaml` · `config.py` · `setup_wizard.py` · `teardown_wizard.py` · `docs/ARCHITECTURE.md` · `eval/run_eval.py` · `gateway/main.py` · `memory/memory_bank.py` · `tools/search_tool.py` · `ui/src/app/chat/page.tsx` · `scripts/deploy.py` · `tests/conftest.py`