---
slug: contributing
title: "Contributing Guide"
section: development
tags: [contributing, development]
pin: false
importance: 46
created_at: 2026-05-16T04:12:41Z
rekipedia_version: 0.15.1
---

# Contributing Guide

This repository is a multi-part Python and TypeScript codebase, so the best contributions start with a clear local setup and a good understanding of which subsystem you are touching. This page focuses on contributor workflow rather than architecture or API details. For subsystem overviews, see the project docs in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/API.md`](docs/API.md). For repo-specific operational notes, also check [`README.md`](README.md), [`AGENTS.md`](AGENTS.md), [`CLAUDE.md`](CLAUDE.md), and `.github/copilot-instructions.md` for working conventions.

## Local Development Setup

The repository includes both Python services and a Next.js UI. In practice, you will usually need both environments available if your change crosses the backend/frontend boundary.

### Python environment

The Python side is managed with standard project files such as [`pyproject.toml`](pyproject.toml), [`requirements.txt`](requirements.txt), [`pytest.ini`](pytest.ini), and [`conftest.py`](conftest.py). A `.python-version` file is present, so aligning your interpreter with the pinned version is recommended before running tests or packaging commands.

Typical setup steps are:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install -e .
```

If you use `uv`, the repository already documents build execution via `uv build`. That is a good indicator that modern Python packaging is supported, but the exact workflow should still follow the project’s own instructions in [`README.md`](README.md) and [`AGENTS.md`](AGENTS.md).

### TypeScript / UI environment

The UI lives under [`ui/`](ui) and is a separate Next.js app with its own [`package.json`](ui/package.json) and local env template at [`ui/.env.local.example`](ui/.env.local.example). Common local setup is:

```bash
cd ui
npm install
npm run dev
```

To build or smoke-test the UI, use the repo’s documented commands:

```bash
npm run build
npm start
```

### Environment configuration

The root also contains `.env.example`, and Python configuration is centralized in [`config.py`](config.py), especially [`Settings`](config.py#L7). If your change adds a new environment variable, make sure you update the relevant example file and any configuration parsing code in tandem.

> **Sources:** `pyproject.toml` · `requirements.txt` · `pytest.ini` · `conftest.py` · `config.py` · `ui/package.json` · `ui/.env.local.example` · [`Settings`](config.py#L7)

## Test Execution

The repository’s test suite is Python-first, with targeted unit tests for gateway, memory, governance, registry, and agent-building behavior. The documented top-level commands are:

```bash
pytest
python -m pytest tests/ -q --tb=short
```

### Recommended test strategy

Use focused tests first, then broaden to the full suite:

| Change area | Suggested command(s) |
|---|---|
| Single module / function | `pytest tests/<area>/test_<file>.py -q` |
| Gateway changes | `pytest tests/gateway -q` |
| Memory changes | `pytest tests/memory -q` |
| Agent loader / registry | `pytest tests/agents -q` and `pytest tests/registry -q` |
| Governance changes | `pytest tests/governance -q` |
| Eval / scoring changes | `pytest tests/eval -q` |
| Full verification | `pytest` |

There is also an eval entry point, [`eval/run_eval.py`](eval/run_eval.py), which is covered by tests in [`tests/eval/test_eval_metrics.py`](tests/eval/test_eval_metrics.py). If your change affects evaluation logic, run those tests explicitly rather than relying on unrelated suites.

### What the existing tests suggest

The test layout shows the repository expects:

- unit-level validation of builder functions such as [`build_agent`](agents/__init__.py#L11) and [`build_task_agent`](agents/task_agent.py#L160)
- gateway behavior around [`chat`](gateway/main.py#L152), [`list_sessions`](gateway/main.py#L247), and memory endpoints
- memory logic around [`build_context_summary`](memory/context_budget.py#L37), [`retrieve_cross_corpus`](memory/cross_corpus.py#L64), and [`HermesMemoryBank`](memory/memory_bank.py#L56)
- policy enforcement in [`PolicyEngine`](governance/policy_engine.py#L54)

If you change one of those areas, keep or extend the targeted assertions instead of only adding broad integration coverage.

> **Sources:** `pytest.ini` · `tests/gateway/test_main_chat.py` · `tests/memory/test_context_budget.py` · `tests/memory/test_cross_corpus.py` · `tests/memory/test_memory_bank.py` · `tests/governance/test_policy_engine.py` · `tests/eval/test_eval_metrics.py` · [`build_agent`](agents/__init__.py#L11) · [`build_task_agent`](agents/task_agent.py#L160) · [`chat`](gateway/main.py#L152) · [`build_context_summary`](memory/context_budget.py#L37) · [`retrieve_cross_corpus`](memory/cross_corpus.py#L64) · [`HermesMemoryBank`](memory/memory_bank.py#L56) · [`PolicyEngine`](governance/policy_engine.py#L54)

## Code Style Expectations

This repository’s style is easiest to infer from its tooling and test conventions.

### Python style

The presence of [`pyproject.toml`](pyproject.toml) and the checked-in `.ruff_cache/` strongly suggests Ruff-based linting/formatting is part of the workflow. Even though this page does not repeat lint commands, contributors should expect:

- type-aware, explicit helper functions
- small modules with focused responsibilities
- defensive error handling in integration points
- tests that mock external services rather than calling them directly

The codebase also tends to separate pure business logic from I/O-heavy wrappers. For example, memory and policy components expose deterministic helpers such as [`prioritise_memory`](memory/context_budget.py#L94) and [`PolicyRule.matches`](governance/policy_engine.py#L31), while cloud-facing code lives in tool wrappers and gateway adapters.

### TypeScript style

The UI code under [`ui/src/`](ui/src) is organized as React/Next.js application code with typed API helpers in [`ui/src/lib/api.ts`](ui/src/lib/api.ts) and shared shapes in [`ui/src/types/chat.ts`](ui/src/types/chat.ts). When modifying UI code:

- keep request/response contracts aligned with the backend
- use the existing typed interfaces rather than ad hoc object literals
- prefer small presentational components like [`MessageBubble`](ui/src/components/MessageBubble.tsx)
- avoid duplicating backend state logic in the browser when a shared API helper already exists

### Testing and maintainability norms

The tests show a strong preference for scenario-based names, explicit fixtures/mocks, and narrow assertions. For example, gateway tests validate disabled-versus-enabled paths in [`AgentGatewayClient`](gateway/agent_gateway.py#L63), while memory tests probe fallback behavior in methods like [`HermesMemoryBank.fetch_memories`](memory/memory_bank.py#L321) and [`HermesMemoryBank.format_for_prompt`](memory/memory_bank.py#L383).

In short: keep changes small, make side effects observable, and add tests for both the happy path and the “configuration missing / service unavailable” path.

> **Sources:** `pyproject.toml` · `.ruff_cache/CACHEDIR.TAG` · [`prioritise_memory`](memory/context_budget.py#L94) · [`PolicyRule.matches`](governance/policy_engine.py#L31) · [`MessageBubble`](ui/src/components/MessageBubble.tsx#L8) · [`ui/src/lib/api.ts`](ui/src/lib/api.ts) · [`ui/src/types/chat.ts`](ui/src/types/chat.ts) · [`AgentGatewayClient`](gateway/agent_gateway.py#L63) · [`HermesMemoryBank.fetch_memories`](memory/memory_bank.py#L321) · [`HermesMemoryBank.format_for_prompt`](memory/memory_bank.py#L383)

## Where to Look for Subsystem-Specific Guidance

This repository already includes several places where subsystem behavior is documented more deeply. Start there before changing code.

### Repository-level guidance files

| File | What it is useful for |
|---|---|
| [`README.md`](README.md) | Quick start, project purpose, and high-level usage notes |
| [`AGENTS.md`](AGENTS.md) | Agent-specific conventions and repository workflow guidance |
| [`CLAUDE.md`](CLAUDE.md) | Assistant-oriented notes that often include repository norms |
| [`.github/copilot-instructions.md`](.github/copilot-instructions.md) | Editor/assistant conventions and coding guidance |
| [`RELEASE_NOTES.md`](RELEASE_NOTES.md) | Recent changes and behavior shifts that may affect expectations |

### Subsystem docs

For code ownership areas, use the relevant documentation page rather than reverse-engineering from scratch:

- **Architecture:** [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **API reference:** [`docs/API.md`](docs/API.md)
- **Cost and operational considerations:** [`docs/cost-estimation.md`](docs/cost-estimation.md)
- **Demo and smoke-test workflow:** [`scripts/demo/README.md`](scripts/demo/README.md)
- **Skill authoring:** [`skills/TEMPLATE.md`](skills/TEMPLATE.md)

### Code areas worth reading before editing

- Agent composition: [`agents/loader.py`](agents/loader.py), [`agents/orchestrator.py`](agents/orchestrator.py), [`agents/task_agent.py`](agents/task_agent.py)
- Gateway and HTTP behavior: [`gateway/main.py`](gateway/main.py), [`gateway/tasks.py`](gateway/tasks.py), [`gateway/auth.py`](gateway/auth.py)
- Memory and retrieval: [`memory/memory_bank.py`](memory/memory_bank.py), [`memory/cross_corpus.py`](memory/cross_corpus.py), [`memory/skill_loader.py`](memory/skill_loader.py)
- Tool adapters: [`tools/`](tools)
- UI contract layer: [`ui/src/lib/api.ts`](ui/src/lib/api.ts), [`ui/src/app/chat/page.tsx`](ui/src/app/chat/page.tsx)

If your change is cross-cutting, read the doc page for the subsystem first, then inspect the unit tests for the expected edge cases.

> **Sources:** `README.md` · `AGENTS.md` · `CLAUDE.md` · `.github/copilot-instructions.md` · `RELEASE_NOTES.md` · `docs/ARCHITECTURE.md` · `docs/API.md` · `docs/cost-estimation.md` · `scripts/demo/README.md` · `skills/TEMPLATE.md`

## Cross-Language Change Checklist

When a change touches both Python and TypeScript, make sure the backend contract and frontend usage stay in sync.

### Checklist

- [ ] Update the Python endpoint, request model, or response model in the relevant gateway file, such as [`gateway/main.py`](gateway/main.py) or [`gateway/tasks.py`](gateway/tasks.py)
- [ ] Update the corresponding UI client helper in [`ui/src/lib/api.ts`](ui/src/lib/api.ts)
- [ ] Update the shared UI types in [`ui/src/types/chat.ts`](ui/src/types/chat.ts) if the payload shape changed
- [ ] Verify the UI page/component using that helper, often [`ui/src/app/chat/page.tsx`](ui/src/app/chat/page.tsx) or [`ui/src/components/MessageBubble.tsx`](ui/src/components/MessageBubble.tsx)
- [ ] Add or adjust Python tests under `tests/gateway/` or the subsystem under change
- [ ] Run the relevant Python test subset and the UI build
- [ ] Confirm any environment variable changes are reflected in both root and UI `.env` templates

### Practical example of keeping things aligned

If you add a new field to chat messages, you would typically need to update:

1. [`ChatEvent`](gateway/main.py#L141) or [`ChatRequest`](gateway/main.py#L136)
2. [`streamChat`](ui/src/lib/api.ts#L17) or another UI helper
3. [`Message`](ui/src/types/chat.ts#L3)
4. any consumer in [`ui/src/app/chat/page.tsx`](ui/src/app/chat/page.tsx)

That keeps the backend schema, frontend types, and presentation logic consistent.

> **Sources:** [`ChatRequest`](gateway/main.py#L136) · [`ChatEvent`](gateway/main.py#L141) · [`streamChat`](ui/src/lib/api.ts#L17) · [`Message`](ui/src/types/chat.ts#L3) · [`ui/src/app/chat/page.tsx`](ui/src/app/chat/page.tsx)

## Suggested Workflow for Contributors

A safe default workflow for changes in this repository is:

1. Read the relevant subsystem guide in `docs/`.
2. Inspect the nearest tests for the behavior you want to change.
3. Make the smallest possible code change in the owning module.
4. Update the UI adapter or shared types if the backend contract changed.
5. Add regression tests for both success and failure paths.
6. Run the targeted test subset before a full-suite pass.
7. If applicable, run the UI build after backend contract changes.

This repository is organized to support small, testable changes, so contributors who work incrementally will usually have the best experience.

> **Sources:** `docs/ARCHITECTURE.md` · `docs/API.md` · `tests/` · [`ui/src/lib/api.ts`](ui/src/lib/api.ts) · [`ui/src/types/chat.ts`](ui/src/types/chat.ts)