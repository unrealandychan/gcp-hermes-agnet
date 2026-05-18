---
slug: testing
title: "Testing Strategy and How to Run Tests"
section: general
pin: false
importance: 50
created_at: 2026-05-18T12:38:06Z
rekipedia_version: 0.15.1
---

# Testing Strategy and How to Run Tests

## Testing Philosophy

The repository’s test suite is intentionally focused on two high-value areas: agent construction logic and the cloud smoke-test utility. In other words, the tests validate that the system’s orchestration objects are built with the right shape and that the external connectivity probe behaves correctly under mocked success and failure conditions.

The core agent-building path is exercised through [`build_aggregator_agent`](agents/aggregator.py#L70), [`build_task_agent`](agents/task_agent.py#L115), and [`build_dynamic_parallel_dispatcher`](agents/task_agent.py#L191). The tests assert structural properties rather than deep runtime behavior: for example, that the aggregator is an `LlmAgent`, that it has a description, that it has no tools, and that the task pipeline is composed of a `SequentialAgent` containing a `ParallelAgent` followed by an aggregator. This is a strong fit for unit testing because these builders are configuration-heavy and deterministic.

The cloud smoke-test path is exercised via [`probe_gateway`](scripts/demo/cloud_smoke_test.py#L47), [`probe_sdk`](scripts/demo/cloud_smoke_test.py#L118), [`_extract_response_text`](scripts/demo/cloud_smoke_test.py#L105), and [`main`](scripts/demo/cloud_smoke_test.py#L183). These tests mock HTTP responses, SDK clients, and CLI argument handling to validate parsing and control flow without requiring actual Google Cloud or Vertex AI access.

There is no explicit coverage tooling or target recorded in the analysis data, so coverage goals are inferred from the test design rather than measured thresholds. The observable goal is to cover the “shape” and branching behavior of the orchestration code, plus the CLI’s error handling and response parsing. One gap is the helper [`_make_module`](tests/conftest.py#L22), which is used extensively by the test scaffolding but is not directly tested; the analysis flags this as a knowledge gap.

> **Sources:** `tests/agents/test_aggregator.py` · `tests/scripts/test_cloud_smoke_test.py` · `tests/conftest.py` · [`build_aggregator_agent`](agents/aggregator.py#L70) · [`build_task_agent`](agents/task_agent.py#L115) · [`build_dynamic_parallel_dispatcher`](agents/task_agent.py#L191) · [`probe_gateway`](scripts/demo/cloud_smoke_test.py#L47) · [`probe_sdk`](scripts/demo/cloud_smoke_test.py#L118) · [`_extract_response_text`](scripts/demo/cloud_smoke_test.py#L105) · [`main`](scripts/demo/cloud_smoke_test.py#L183)

## Test Structure

The test layout is conventional and clearly separated by feature area:

| Directory / File | Purpose | Notes |
|---|---|---|
| `tests/agents/test_aggregator.py` | Agent-builder tests | Covers [`build_aggregator_agent`](agents/aggregator.py#L70), [`build_task_agent`](agents/task_agent.py#L115), and [`build_dynamic_parallel_dispatcher`](agents/task_agent.py#L191) |
| `tests/scripts/test_cloud_smoke_test.py` | Smoke-test CLI tests | Covers gateway and SDK probe logic in [`scripts/demo/cloud_smoke_test.py`](scripts/demo/cloud_smoke_test.py#L1) |
| `tests/conftest.py` | Shared fixtures and fakes | Provides lightweight stand-ins for external ADK/FastAPI/Starlette-related types |

The `tests/conftest.py` file is especially important because it installs fake implementations such as [`_FakeLlmAgent`](tests/conftest.py#L30), [`_FakeParallelAgent`](tests/conftest.py#L44), [`_FakeSequentialAgent`](tests/conftest.py#L52), and [`_FakeEventSourceResponse`](tests/conftest.py#L186). This allows tests to run without importing or instantiating the real cloud/runtime dependencies. The helper [`_register_all`](tests/conftest.py#L222) appears to register multiple module stubs into `sys.modules`, and the analysis notes that `_make_module` is heavily used by this scaffolding.

The tests are grouped by production module rather than by test type, which makes it easy to find the checks that map to a given implementation file.

> **Sources:** `tests/agents/test_aggregator.py` · `tests/scripts/test_cloud_smoke_test.py` · `tests/conftest.py` · [`_FakeLlmAgent`](tests/conftest.py#L30) · [`_FakeParallelAgent`](tests/conftest.py#L44) · [`_FakeSequentialAgent`](tests/conftest.py#L52) · [`_FakeEventSourceResponse`](tests/conftest.py#L186) · [`_register_all`](tests/conftest.py#L222)

## Running Tests

No explicit `test_commands` were present in the analysis payload, so the commands below follow standard Python/pytest conventions and are the most likely way to run the existing suite.

```bash
# unit tests
pytest tests/agents tests/scripts

# integration tests
pytest tests/scripts/test_cloud_smoke_test.py

# with coverage
pytest --cov=agents --cov=scripts --cov=hermes_app --cov=config --cov-report=term-missing
```

If you want to run the full suite, use:

```bash
pytest
```

For a single file or test function, pytest’s node selection is the most convenient approach:

```bash
pytest tests/agents/test_aggregator.py::TestBuildAggregatorAgent::test_no_tools
pytest tests/scripts/test_cloud_smoke_test.py::test_probe_gateway_success_parses_sse_done
```

The `tests/scripts/test_cloud_smoke_test.py` module is especially suitable for focused runs because it tests discrete code paths in [`probe_gateway`](scripts/demo/cloud_smoke_test.py#L47), [`probe_sdk`](scripts/demo/cloud_smoke_test.py#L118), and [`main`](scripts/demo/cloud_smoke_test.py#L183).

> **Sources:** `tests/agents/test_aggregator.py` · `tests/scripts/test_cloud_smoke_test.py` · [`probe_gateway`](scripts/demo/cloud_smoke_test.py#L47) · [`probe_sdk`](scripts/demo/cloud_smoke_test.py#L118) · [`main`](scripts/demo/cloud_smoke_test.py#L183)

## Test Categories

### Unit Tests

The unit tests live primarily in [`tests/agents/test_aggregator.py`](tests/agents/test_aggregator.py#L1). They verify the structure of the agent graph produced by the builder functions:

- [`TestBuildAggregatorAgent`](tests/agents/test_aggregator.py#L27) checks that [`build_aggregator_agent`](agents/aggregator.py#L70) returns an LLM-style agent, has an appropriate description, and has no tools.
- [`TestBuildTaskAgentSequentialPipeline`](tests/agents/test_aggregator.py#L45) asserts that [`build_task_agent`](agents/task_agent.py#L115) produces a `SequentialAgent` with two children, where the first is a `ParallelAgent` and the second is the aggregator.
- [`TestBuildDynamicParallelDispatcher`](tests/agents/test_aggregator.py#L86) validates the request-time synthesis behavior of [`build_dynamic_parallel_dispatcher`](agents/task_agent.py#L191), including the “no agents found” branch and the “pipeline ends with aggregator” branch.

These tests rely on shared fakes from [`tests/conftest.py`](tests/conftest.py#L1), including fake agent classes that stand in for `google.adk.agents.LlmAgent`, `ParallelAgent`, and `SequentialAgent`. They also use `monkeypatch` to swap out synthesis behavior and to force specific runtime paths.

#### Key fixtures and mocks

- [`settings`](tests/agents/test_aggregator.py#L17) fixture constructs a [`Settings`](config.py#L7) object for agent builders.
- Fake ADK agents from [`tests/conftest.py`](tests/conftest.py#L30) keep the tests isolated from the real SDK.
- `monkeypatch` is used to override synthesis results and to emulate edge cases.

> **Sources:** `tests/agents/test_aggregator.py` · `tests/conftest.py` · [`build_aggregator_agent`](agents/aggregator.py#L70) · [`build_task_agent`](agents/task_agent.py#L115) · [`build_dynamic_parallel_dispatcher`](agents/task_agent.py#L191) · [`Settings`](config.py#L7)

### Integration Tests

The integration-style tests are concentrated in [`tests/scripts/test_cloud_smoke_test.py`](tests/scripts/test_cloud_smoke_test.py#L1). They exercise the smoke-test utility’s behavior as a command-line-facing integration point, but with external systems mocked:

- [`test_probe_gateway_success_parses_sse_done`](tests/scripts/test_cloud_smoke_test.py#L9) verifies that [`probe_gateway`](scripts/demo/cloud_smoke_test.py#L47) parses server-sent-event output and extracts a final result.
- [`test_probe_gateway_fails_on_http_error`](tests/scripts/test_cloud_smoke_test.py#L35) checks error handling when the gateway responds with an HTTP failure.
- [`test_probe_sdk_success_uses_existing_engine_by_name`](tests/scripts/test_cloud_smoke_test.py#L57) validates that [`probe_sdk`](scripts/demo/cloud_smoke_test.py#L118) uses an existing reasoning engine by name.
- [`test_main_gateway_missing_url_fails`](tests/scripts/test_cloud_smoke_test.py#L83) verifies CLI validation in [`main`](scripts/demo/cloud_smoke_test.py#L183).
- [`test_extract_response_text_formats`](tests/scripts/test_cloud_smoke_test.py#L88) covers [`_extract_response_text`](scripts/demo/cloud_smoke_test.py#L105).
- [`test_main_sdk_mode_success`](tests/scripts/test_cloud_smoke_test.py#L95) checks the top-level flow in SDK mode.

These tests are more integration-like because they validate how the CLI and probe functions cooperate, but they still avoid real cloud calls via mocks.

> **Sources:** `tests/scripts/test_cloud_smoke_test.py` · [`probe_gateway`](scripts/demo/cloud_smoke_test.py#L47) · [`probe_sdk`](scripts/demo/cloud_smoke_test.py#L118) · [`_extract_response_text`](scripts/demo/cloud_smoke_test.py#L105) · [`main`](scripts/demo/cloud_smoke_test.py#L183)

## Writing New Tests

When adding new tests, follow the existing layout and keep tests close to the module they exercise:

| Production file | Put new tests in |
|---|---|
| `agents/aggregator.py` | `tests/agents/test_aggregator.py` |
| `agents/task_agent.py` | `tests/agents/test_aggregator.py` unless a dedicated file is introduced |
| `scripts/demo/cloud_smoke_test.py` | `tests/scripts/test_cloud_smoke_test.py` |
| shared fixtures | `tests/conftest.py` |

A few conventions are visible in the current suite:

1. **Prefer structural assertions for agent builders.**  
   The tests for [`build_task_agent`](agents/task_agent.py#L115) do not try to execute real agent workflows; they verify composition, counts, and ordering.

2. **Use fakes instead of live dependencies.**  
   The helpers in [`tests/conftest.py`](tests/conftest.py#L1) exist specifically to avoid importing heavy runtime services.

3. **Patch behavior at the narrowest seam.**  
   For example, tests for [`build_dynamic_parallel_dispatcher`](agents/task_agent.py#L191) monkeypatch the synthesis layer instead of reconstructing the whole app.

4. **Name tests after the observable behavior.**  
   Test names like `test_dynamic_pipeline_ends_with_aggregator` are descriptive and make failures easy to interpret.

To run a single test while iterating:

```bash
pytest tests/agents/test_aggregator.py::TestBuildDynamicParallelDispatcher::test_dynamic_pipeline_ends_with_aggregator
pytest tests/scripts/test_cloud_smoke_test.py::test_main_sdk_mode_success
```

If you need to create new fixtures or stubs, place them in [`tests/conftest.py`](tests/conftest.py#L1) so they are available across the suite. Be aware that the analysis identified [`_make_module`](tests/conftest.py#L22) as a helper with no direct test coverage despite being called frequently.

> **Sources:** `tests/agents/test_aggregator.py` · `tests/scripts/test_cloud_smoke_test.py` · `tests/conftest.py` · [`_make_module`](tests/conftest.py#L22) · [`build_task_agent`](agents/task_agent.py#L115) · [`build_dynamic_parallel_dispatcher`](agents/task_agent.py#L191)

## CI/CD

No CI configuration files were found in the provided analysis data, and `ci_files` is empty. That means there is no observable pipeline definition to document from the repository snapshot. Based on the current evidence, we can only say that CI/CD configuration was not present in the inspected files.

If CI is added later, the most likely useful checks would be:

- `pytest` for the full suite
- `pytest --cov ...` for coverage reporting
- lint/static analysis for Python formatting and import correctness
- optional smoke-test execution against staging endpoints

For now, the repository’s test strategy appears to rely on local pytest execution plus mocked external services, with no documented automation pipeline in-tree.

> **Sources:** `ci_files` from analysis payload · `tests/agents/test_aggregator.py` · `tests/scripts/test_cloud_smoke_test.py`