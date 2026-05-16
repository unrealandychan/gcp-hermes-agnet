---
slug: testing
title: "Testing Strategy and Execution Guide"
section: internals
tags: [testing, internals]
pin: false
importance: 65
created_at: 2026-05-16T04:12:34Z
rekipedia_version: 0.15.1
---

# Testing Strategy and Execution Guide

## Overview

This repository uses a predominantly unit-test-oriented strategy built around `pytest`, with most tests focused on deterministic logic, boundary handling, and graceful degradation paths. The suite is organised by subsystem under `tests/`, and the current coverage strongly emphasises the core internal modules that make up the agent runtime: agent construction/loading, the FastAPI gateway, governance policy checks, memory management, and evaluation utilities.

A notable characteristic of the suite is its heavy use of mocks, monkeypatching, and local stand-ins for third-party SDK types. That matches the codebase architecture well: many production paths talk to external services such as Vertex AI, Firestore, BigQuery, Google Workspace, and OpenTelemetry. The tests deliberately avoid relying on those services, instead asserting that modules behave correctly when dependencies are present, absent, or failing.

At a high level, the suite checks:

- agent builders return the expected ADK agent shapes
- YAML-driven agent loading handles valid and invalid configurations
- gateway endpoints enforce auth, model-armor checks, and session isolation
- policy rules load and evaluate as expected
- memory helpers respect token budgets and fail closed or gracefully where intended
- evaluation metrics and offline evaluation entry points behave predictably
- core connector abstractions propagate success/failure correctly

The current suite does **not** appear to include broad end-to-end browser/UI tests, nor does it deeply exercise production integrations against live GCP services. Those concerns are mostly outside the scope of the present tests and are handled via isolated unit tests and a demo-style script.

## How to Run the Tests

The repository exposes two direct pytest commands in the available analysis data: the default invocation and a more explicit quiet run with shortened tracebacks. Both are standard local developer entry points.

| Command | Purpose | Notes |
|---|---|---|
| `pytest` | Run the full test suite using repository defaults | Best for day-to-day local verification |
| `python -m pytest tests/ -q --tb=short` | Run only tests under `tests/`, quieter output, shorter tracebacks | Useful for focused local runs or CI-like terminal output |

Because the suite is `pytest`-based, you can also use standard pytest selectors and filters, for example:

```bash
pytest tests/gateway/test_main_chat.py -q
pytest tests/memory/test_memory_bank.py -k "FormatForPrompt or BuildMemoryBank"
pytest tests/agents/test_agent_loader.py -vv
```

`pytest.ini` and `conftest.py` are present at the repository root, and the test-specific helpers live in [`tests/conftest.py`](tests/conftest.py#L1) rather than the application root conftest. That separation suggests the test harness is intentionally self-contained.

> **Sources:** `pytest.ini` · `conftest.py` · `tests/conftest.py` · `tests/conftest.py#L1` · `tests/eval/test_eval_metrics.py` · `tests/gateway/test_main_chat.py` · `tests/memory/test_memory_bank.py`

## Test Directory Layout

The `tests/` tree mirrors the main runtime modules, which makes it easy to find coverage for a given subsystem. The layout visible in the analysis data is:

| Directory / File | Coverage Focus |
|---|---|
| `tests/agents/` | Agent builders and YAML-driven agent loading |
| `tests/gateway/` | FastAPI gateway, auth, observability, and chat/session endpoints |
| `tests/governance/` | Policy engine and policy rule evaluation |
| `tests/memory/` | Memory budgeting, cross-corpus retrieval, memory bank facade, skill loading |
| `tests/eval/` | Offline scoring metrics and eval runner behaviour |
| `tests/tools/` | Connector/tool wrappers such as MCP and model armor |
| `tests/test_teardown_wizard.py` | Teardown helper coverage at the top level |
| `tests/conftest.py` | Shared test doubles and environment scaffolding |

This structure closely tracks the production package layout (`agents/`, `gateway/`, `governance/`, `memory/`, `tools/`, `eval/`). That makes subsystem coverage easy to reason about: most production modules have at least one dedicated test file, and many have a dedicated test class per function or method cluster.

A key pattern is that tests tend to be grouped by behaviour rather than by raw function count. For example, [`tests/memory/test_memory_bank.py`](tests/memory/test_memory_bank.py#L1) contains multiple classes covering different methods on [`HermesMemoryBank`](memory/memory_bank.py#L56), rather than a single monolithic file of unrelated assertions.

> **Sources:** `tests/agents/test_agent_builds.py` · `tests/agents/test_agent_loader.py` · `tests/gateway/test_agent_gateway.py` · `tests/gateway/test_main_chat.py` · `tests/gateway/test_observability.py` · `tests/governance/test_policy_engine.py` · `tests/memory/test_context_budget.py` · `tests/memory/test_cross_corpus.py` · `tests/memory/test_memory_bank.py` · `tests/eval/test_eval_metrics.py` · `tests/tools/test_mcp_connector.py` · `tests/tools/test_model_armor.py` · `tests/test_teardown_wizard.py`

## Major Test Areas and Covered Subsystems

The table below maps the major test areas to the subsystems they exercise.

| Test Area | Test Files | Covered Subsystems |
|---|---|---|
| Agent construction | `tests/agents/test_agent_builds.py` | [`agents.analytics`](agents/analytics.py#L1), [`agents.hr`](agents/hr.py#L1), [`agents.it_helpdesk`](agents/it_helpdesk.py#L1), [`agents.developer`](agents/developer.py#L1), [`agents.orchestrator`](agents/orchestrator.py#L1) |
| Agent YAML loading | `tests/agents/test_agent_loader.py` | [`agents.loader`](agents/loader.py#L1), custom builders, env-var interpolation |
| Gateway runtime | `tests/gateway/test_agent_gateway.py`, `tests/gateway/test_main_chat.py`, `tests/gateway/test_observability.py` | [`gateway.agent_gateway`](gateway/agent_gateway.py#L1), [`gateway.main`](gateway/main.py#L1), [`gateway.observability`](gateway/observability.py#L1), [`gateway.auth`](gateway/auth.py#L1), [`gateway.tasks`](gateway/tasks.py#L1) |
| Governance | `tests/governance/test_policy_engine.py` | [`governance.policy_engine`](governance/policy_engine.py#L1) |
| Memory utilities | `tests/memory/test_context_budget.py`, `tests/memory/test_cross_corpus.py`, `tests/memory/test_memory_bank.py`, `tests/memory/test_skill_loader.py`, `tests/memory/test_user_profile.py` | [`memory.context_budget`](memory/context_budget.py#L1), [`memory.cross_corpus`](memory/cross_corpus.py#L1), [`memory.memory_bank`](memory/memory_bank.py#L1), [`memory.skill_loader`](memory/skill_loader.py#L1), [`memory.user_profile`](memory/user_profile.py#L1) |
| Evaluation | `tests/eval/test_eval_metrics.py` | [`eval.metrics`](eval/metrics.py#L1), [`eval.online_monitor`](eval/online_monitor.py#L1), [`eval.run_eval`](eval/run_eval.py#L1) |
| Tool wrappers | `tests/tools/test_mcp_connector.py`, `tests/tools/test_model_armor.py` | [`tools.mcp_connector`](tools/mcp_connector.py#L1), [`tools.model_armor`](tools/model_armor.py#L1) |
| Setup / teardown helpers | `tests/test_teardown_wizard.py` | [`teardown_wizard`](teardown_wizard.py#L1) |

A few coverage themes stand out:

- **Fail-open / graceful-degradation paths** are tested heavily in gateway, observability, and memory modules.
- **Parameterised business rules** are tested in governance and evaluation logic.
- **SDK-adapter code** is validated mostly by mocked calls and return-shape assertions rather than live service calls.

> **Sources:** `tests/agents/test_agent_builds.py` · `tests/agents/test_agent_loader.py` · `tests/gateway/test_agent_gateway.py` · `tests/gateway/test_main_chat.py` · `tests/gateway/test_observability.py` · `tests/governance/test_policy_engine.py` · `tests/memory/test_context_budget.py` · `tests/memory/test_cross_corpus.py` · `tests/memory/test_memory_bank.py` · `tests/eval/test_eval_metrics.py` · `tests/tools/test_mcp_connector.py` · `tests/tools/test_model_armor.py` · `tests/test_teardown_wizard.py`

## Pytest Usage, Fixtures, and Test Patterns

### Pytest Style in the Suite

The suite is clearly written for `pytest` rather than `unittest`. That shows up in several ways:

- plain test functions like `test_high_groundedness_when_keywords_present()` in [`tests/eval/test_eval_metrics.py`](tests/eval/test_eval_metrics.py#L21)
- class-based grouping without inheritance, e.g. `TestGenerateMemories` in [`tests/memory/test_memory_bank.py`](tests/memory/test_memory_bank.py#L41)
- direct use of `tmp_path`, `monkeypatch`, `caplog`, and similar pytest fixtures
- monkeypatching module globals and imported SDK modules
- `setup_method` / `teardown_method` hooks where a class wants per-test patch lifecycle control

This is a very “unit test with seams” style: the tests isolate the code under test by substituting fake SDK modules and replacing network-heavy dependencies before import-time or at setup time.

### Notable Shared Test Doubles

The central fixture hub is [`tests/conftest.py`](tests/conftest.py#L1). It defines several reusable stand-ins:

- [`_FakeLlmAgent`](tests/conftest.py#L30) for `google.adk.agents.LlmAgent`
- [`_FakeLoopAgent`](tests/conftest.py#L39) for loop-style agents
- [`_FakeEventSourceResponse`](tests/conftest.py#L148) so FastAPI can accept SSE response types without pulling in the real implementation
- `_noop_limit` and `_register_all` helpers to neutralise or register external integration points

These fakes are important because they let tests assert the structure of agent objects without constructing real ADK instances or network clients.

### Common Testing Patterns

| Pattern | Where Seen | Why It Matters |
|---|---|---|
| `setup_method` / `teardown_method` manual patch control | `tests/agents/test_agent_builds.py`, `tests/agents/test_agent_loader.py` | Ensures each test gets fresh mocks and cleanup |
| `tmp_path`-backed temporary YAML/files | `tests/agents/test_agent_loader.py`, `tests/governance/test_policy_engine.py` | Exercises file parsing and missing-file branches |
| `monkeypatch` environment overrides | `tests/agents/test_agent_loader.py`, `tests/eval/test_eval_metrics.py` | Validates env-dependent configuration without touching real env state |
| `caplog` warning assertions | `tests/agents/test_agent_loader.py` | Confirms malformed config is skipped with diagnostics |
| Fake SDK module injection | `tests/memory/test_memory_bank.py`, `tests/gateway/test_observability.py` | Tests graceful fallback when optional packages are absent |
| Direct method-shape assertions | `tests/gateway/test_agent_gateway.py`, `tests/memory/test_memory_bank.py` | Verifies response payload structure and default handling |

The tests are especially strong at validating **fallback semantics**: if an optional integration is missing or fails, the code should either return a disabled object, an empty iterator, `None`, or a safe default rather than throwing unexpectedly.

> **Sources:** `tests/conftest.py` · `tests/conftest.py#L1` · `tests/conftest.py#L30` · `tests/conftest.py#L39` · `tests/conftest.py#L148` · `tests/agents/test_agent_builds.py` · `tests/agents/test_agent_loader.py` · `tests/eval/test_eval_metrics.py` · `tests/gateway/test_observability.py` · `tests/memory/test_memory_bank.py`

## Test Command Table

| Command | When to Use | Scope |
|---|---|---|
| `pytest` | Run everything locally | Entire repository test suite |
| `python -m pytest tests/ -q --tb=short` | Shorter output, explicit tests-only invocation | Everything under `tests/` |
| `pytest tests/gateway/test_main_chat.py` | Debug a single gateway file | One subsystem |
| `pytest -k memory` | Focus on memory-related tests | Subset by name |
| `pytest -x` | Stop on first failure | Fast feedback during debugging |

The first two commands are the only ones explicitly present in the analysis data, but the additional examples are standard pytest usage consistent with the suite’s structure.

```bash
pytest
python -m pytest tests/ -q --tb=short
```

> **Sources:** `test_commands` · `pytest.ini`

## What the Current Suite Covers — and What It Doesn’t

### Covered Well

The existing suite does a solid job covering:

- deterministic pure logic, such as [`score_response`](eval/metrics.py#L23) and [`prioritise_memory`](memory/context_budget.py#L94)
- configuration-driven assembly paths, such as [`build_agents_from_yaml`](agents/loader.py#L147) and [`build_policy_engine`](governance/policy_engine.py#L111)
- gateway safety checks and routing behaviour, including [`AgentGatewayClient.send_message`](gateway/agent_gateway.py#L94), [`chat`](gateway/main.py#L152), and [`agent_span`](gateway/observability.py#L86)
- memory bank facade methods like [`HermesMemoryBank.fetch_memories`](memory/memory_bank.py#L321) and [`HermesMemoryBank.purge_memories`](memory/memory_bank.py#L166)
- error handling and graceful degradation across external-service boundaries

### Not Covered or Lightly Covered

Based on the visible test files, the suite appears weaker on:

- real end-to-end integration with live external services
- browser/UI testing for the `ui/` application
- broad concurrency/load testing of async background flows
- actual Cloud or workspace API behaviour without mocks
- exhaustive regression coverage for every agent/tool interaction path

In other words, the suite is strong for **internal correctness and safety** but not a substitute for integration validation against real infrastructure. That is consistent with its reliance on pytest doubles and explicit “returns empty / disabled / None on failure” assertions.

> **Sources:** `tests/eval/test_eval_metrics.py` · `tests/memory/test_context_budget.py` · `tests/gateway/test_agent_gateway.py` · `tests/gateway/test_main_chat.py` · `tests/gateway/test_observability.py` · `tests/memory/test_memory_bank.py` · `tests/agents/test_agent_loader.py`