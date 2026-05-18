---
slug: installation-and-setup
title: "Installation and Setup Guide"
section: general
pin: false
importance: 50
created_at: 2026-05-18T12:37:35Z
rekipedia_version: 0.15.1
---

# Installation and Setup Guide

## Overview

This repository appears to be a Python project centered around an agent orchestration stack, with a command-line smoke test entry point in [`scripts.demo.cloud_smoke_test`](scripts/demo/cloud_smoke_test.py#L1) and configuration managed through [`config`](config.py#L1) / [`Settings`](config.py#L7). The analysis data does not include a `pyproject.toml`, `requirements.txt`, `Dockerfile`, or explicit build commands, so this guide focuses on what is directly evidenced by the codebase and clearly labels any gaps.

The most important setup-related modules are:

- [`Settings`](config.py#L7) for environment-driven configuration
- [`hermes_app.agent`](hermes_app/agent.py#L1) and [`agent`](agent.py#L1), which both bootstrap the application from environment and config
- [`scripts.demo.cloud_smoke_test`](scripts/demo/cloud_smoke_test.py#L1), the visible executable entry point for verifying cloud connectivity
- [`build_task_agent`](agents/task_agent.py#L115) and [`build_aggregator_agent`](agents/aggregator.py#L70), which depend on external agent/provider libraries

> **Sources:** `config.py` · L1–L201 · [`Settings`](config.py#L7) · [`get_settings`](config.py#L200)  
> **Sources:** `scripts/demo/cloud_smoke_test.py` · L1–L212 · [`main`](scripts/demo/cloud_smoke_test.py#L183)

---

## Requirements

### System Requirements

The repository is Python-based and uses modules such as `argparse`, `httpx`, `vertexai`, and `pydantic_settings` as seen in the import graph for [`scripts.demo.cloud_smoke_test`](scripts/demo/cloud_smoke_test.py#L1) and [`config`](config.py#L1). Based on those imports, you should expect:

| Requirement | Evidence | Notes |
|---|---|---|
| Python runtime | Project modules and tests are Python | No version pin was provided in the analysis |
| Network access | [`probe_gateway`](scripts/demo/cloud_smoke_test.py#L47) performs HTTP calls; [`probe_sdk`](scripts/demo/cloud_smoke_test.py#L118) talks to Vertex AI | Needed for cloud smoke tests |
| Google Cloud / Vertex AI access | [`vertexai`](scripts/demo/cloud_smoke_test.py#L1) and [`AgentEngineClient`](scripts/demo/cloud_smoke_test.py#L118) are used | Required for SDK mode |
| External model/provider support | [`build_aggregator_agent`](agents/aggregator.py#L70) and [`build_task_agent`](agents/task_agent.py#L115) call [`get_model`](agents/aggregator.py#L70) / [`get_model`](agents/task_agent.py#L115) | Implies provider configuration is necessary |

### Language and Library Dependencies

The repository references these third-party packages directly:

| Package / Namespace | Where observed | Purpose |
|---|---|---|
| `pydantic_settings` | [`config`](config.py#L1) | Base settings model via [`Settings`](config.py#L7) |
| `httpx` | [`scripts.demo.cloud_smoke_test`](scripts/demo/cloud_smoke_test.py#L1) | Gateway HTTP probing |
| `vertexai` | [`scripts.demo.cloud_smoke_test`](scripts/demo/cloud_smoke_test.py#L1) | SDK-based smoke testing |
| `google.adk.agents` | [`agents.aggregator`](agents/aggregator.py#L1), [`agents.task_agent`](agents/task_agent.py#L1) | Agent construction primitives |
| `dotenv` | [`agent`](agent.py#L1), [`hermes_app.agent`](hermes_app/agent.py#L1) | Loads environment files at startup |

The analysis does not provide a concrete Python version. If you need the exact supported version, check the repository’s packaging metadata once available.

> **Sources:** `config.py` · L1–L201 · [`Settings`](config.py#L7)  
> **Sources:** `agents/aggregator.py` · L1–L81 · [`build_aggregator_agent`](agents/aggregator.py#L70)  
> **Sources:** `agents/task_agent.py` · L1–L237 · [`build_task_agent`](agents/task_agent.py#L115) · [`build_dynamic_parallel_dispatcher`](agents/task_agent.py#L191)

---

## Installation Methods

### From Source

No `build_commands` were provided in the analysis payload, so there is no authoritative source for a repo-specific build workflow. However, the code structure suggests the project is meant to be run directly from source after installing dependencies.

A practical source install flow would be:

```bash
git clone <repository-url>
cd <repository-directory>

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies once you know the packaging layout
pip install -U pip
pip install -e .
```

If the project is not packaged for editable installation, install dependencies manually from the runtime imports implied by the analysis:

```bash
pip install pydantic-settings httpx python-dotenv vertexai pytest
```

Then run the project entry points described below.

#### What to expect after install

- [`get_settings`](config.py#L200) can instantiate [`Settings`](config.py#L7)
- [`agent`](agent.py#L1) or [`hermes_app.agent`](hermes_app/agent.py#L1) can bootstrap the application
- [`scripts.demo.cloud_smoke_test`](scripts/demo/cloud_smoke_test.py#L1) can be used to verify connectivity

> **Sources:** `agent.py` · L1–L1 · [`agent`](agent.py#L1)  
> **Sources:** `hermes_app/agent.py` · L1–L1 · [`hermes_app.agent`](hermes_app/agent.py#L1)  
> **Sources:** `scripts/demo/cloud_smoke_test.py` · L1–L212 · [`main`](scripts/demo/cloud_smoke_test.py#L183)

### Via Package Manager

No `pyproject.toml`, `setup.py`, or `package.json` was included in the analysis data, so package-manager installation can only be described generically.

If a Python package manifest exists in the actual repository, the expected commands are:

```bash
# pip
pip install .

# editable development install
pip install -e .

# uv
uv pip install .

# if the repository publishes a package
pip install <package-name>
```

Because [`config.py`](config.py#L1) uses `pydantic_settings` and the agents import `google.adk.agents`, make sure the package manager resolves those dependencies in the environment where you run the app.

> **Sources:** `config.py` · L1–L201 · [`Settings`](config.py#L7)  
> **Sources:** `agents/aggregator.py` · L1–L81 · [`build_aggregator_agent`](agents/aggregator.py#L70)

### Docker

The analysis did not find a `Dockerfile`, so there is no evidence-based Docker workflow to document. If you add one later, the standard pattern would be:

```bash
docker build -t hermes-app .
docker run --rm -it \
  --env-file .env \
  hermes-app
```

For this repository, Docker support is therefore **not confirmed** from the available data.

> **Sources:** No Dockerfile present in `files_seen`

---

## First Run

The clearest first-run path in the repository is the smoke-test script [`scripts.demo.cloud_smoke_test`](scripts/demo/cloud_smoke_test.py#L1), whose [`main`](scripts/demo/cloud_smoke_test.py#L183) function selects either gateway mode or SDK mode.

### 1. Configure the environment

Before first run, prepare the environment variables consumed by [`Settings`](config.py#L7) and any provider credentials needed by [`inject_litellm_env`](config.py#L146). The application bootstrap files [`agent`](agent.py#L1) and [`hermes_app.agent`](hermes_app/agent.py#L1) both import `dotenv`, indicating `.env` loading is part of startup.

### 2. Run the smoke test

The smoke test supports two execution paths:

- **Gateway mode** via [`probe_gateway`](scripts/demo/cloud_smoke_test.py#L47)
- **SDK mode** via [`probe_sdk`](scripts/demo/cloud_smoke_test.py#L118)

Example invocations:

```bash
# Gateway mode
python -m scripts.demo.cloud_smoke_test \
  --mode gateway \
  --gateway-url https://<your-gateway-url> \
  --message "Hello"

# SDK mode
python -m scripts.demo.cloud_smoke_test \
  --mode sdk \
  --project-id <gcp-project-id> \
  --location <gcp-region> \
  --reasoning-engine-resource-name <engine-resource-name> \
  --user-id <user-id> \
  --message "Hello"
```

The script’s [`parse_args`](scripts/demo/cloud_smoke_test.py#L164) defines the required CLI options, while [`_detect_mode`](scripts/demo/cloud_smoke_test.py#L158) can infer mode from the presence of `--gateway-url`.

### 3. Validate output

[`main`](scripts/demo/cloud_smoke_test.py#L183) prints a result object based on [`SmokeResult`](scripts/demo/cloud_smoke_test.py#L32), which includes the status, mode, and extracted text. If the request succeeds, you should see the response summary printed to stdout.

### 4. Optionally run the application bootstrap

If your target is the main app rather than the smoke test, the bootstrap entry points are [`agent`](agent.py#L1) and [`hermes_app.agent`](hermes_app/agent.py#L1). Both import configuration and load environment before wiring in `agents.orchestrator`:

```bash
python -m agent
# or, if the package is installed
python -m hermes_app.agent
```

The exact serving behavior is not visible in the analysis, so treat this as a startup hint rather than a guaranteed server command.

> **Sources:** `scripts/demo/cloud_smoke_test.py` · L32–L212 · [`SmokeResult`](scripts/demo/cloud_smoke_test.py#L32) · [`probe_gateway`](scripts/demo/cloud_smoke_test.py#L47) · [`probe_sdk`](scripts/demo/cloud_smoke_test.py#L118) · [`parse_args`](scripts/demo/cloud_smoke_test.py#L164) · [`main`](scripts/demo/cloud_smoke_test.py#L183)  
> **Sources:** `agent.py` · L1–L1 · [`agent`](agent.py#L1)  
> **Sources:** `hermes_app/agent.py` · L1–L1 · [`hermes_app.agent`](hermes_app/agent.py#L1)

---

## Environment Variables

The analysis provides the strongest evidence for configuration through [`Settings`](config.py#L7), but not the full field list. Still, several behaviors are explicit:

### Provider / model credentials

[`Settings.inject_litellm_env`](config.py#L146) exports provider API keys into process environment so LiteLLM can discover them automatically. This means the app likely relies on env vars for model-provider authentication.

### CORS origins

[`Settings.cors_origins_list`](config.py#L143) parses comma-separated origins, so a corresponding environment value is expected for cross-origin configuration.

### RAG region validation

[`Settings.validate_rag_regions`](config.py#L166) checks that configured RAG corpus resource names match the application region. This implies environment values for the GCP location and corpus resource names are part of startup configuration.

### Cloud smoke test CLI arguments

The smoke test is also configurable via CLI flags rather than env vars:

- `--gateway-url`
- `--project-id`
- `--location`
- `--reasoning-engine-resource-name`
- `--user-id`
- `--message`
- `--timeout-s`

Because the analysis did not include the actual field names declared on [`Settings`](config.py#L7), this guide avoids inventing exact environment variable names. Use your `.env`, deployment manifests, or the source of [`Settings`](config.py#L7) to confirm the definitive list.

> **Sources:** `config.py` · L7–L201 · [`Settings`](config.py#L7) · [`Settings.cors_origins_list`](config.py#L143) · [`Settings.inject_litellm_env`](config.py#L146) · [`Settings.validate_rag_regions`](config.py#L166)  
> **Sources:** `scripts/demo/cloud_smoke_test.py` · L164–L180 · [`parse_args`](scripts/demo/cloud_smoke_test.py#L164)

---

## Troubleshooting

### “Missing dependency” or import errors

If you see errors for `google.adk`, `pydantic_settings`, `httpx`, `vertexai`, or `dotenv`, the environment is likely missing the runtime dependencies implied by the imports in [`agents.aggregator`](agents/aggregator.py#L1), [`agents.task_agent`](agents/task_agent.py#L1), [`scripts.demo.cloud_smoke_test`](scripts/demo/cloud_smoke_test.py#L1), or [`config`](config.py#L1).

Fix:

```bash
pip install pydantic-settings httpx python-dotenv vertexai pytest
```

If the app still fails, verify that the agent SDK package providing `google.adk.agents` is installed in the active virtual environment.

### Gateway mode fails immediately

[`main`](scripts/demo/cloud_smoke_test.py#L183) uses `_detect_mode` to infer gateway mode only when a gateway URL is present. If you omit `--gateway-url` while expecting gateway behavior, the script may choose SDK mode or fail validation.

Fix:

- Pass `--mode gateway`
- Ensure `--gateway-url` is non-empty
- Confirm the gateway is reachable from your machine

### SDK mode cannot find the reasoning engine

[`probe_sdk`](scripts/demo/cloud_smoke_test.py#L118) calls `vertexai.init(...)`, then attempts `get_reasoning_engine(...)` and `query(...)`. Failures here usually mean one of:

- wrong `--project-id`
- wrong `--location`
- incorrect `--reasoning-engine-resource-name`
- missing GCP authentication

Fix:

- Verify `gcloud auth application-default login` or equivalent credentials
- Confirm the reasoning engine resource name
- Make sure the region matches the engine

### Response parsing issues

The smoke test includes [`_extract_response_text`](scripts/demo/cloud_smoke_test.py#L105) for extracting human-readable output from different response shapes. If output appears blank or malformed, inspect the raw SDK response or gateway SSE stream.

The tests in [`tests/scripts/test_cloud_smoke_test.py`](tests/scripts/test_cloud_smoke_test.py#L1) show that the script expects:
- SSE-style completion markers in gateway mode
- structured response content in SDK mode

### Region mismatch warnings

[`Settings.validate_rag_regions`](config.py#L166) is designed to detect cross-region corpus mismatches before the first request. If it reports warnings, align the RAG corpus resource region with `gcp_location`.

### Agent construction fails

If the main app fails during agent assembly, the issue is likely in one of:

- [`build_aggregator_agent`](agents/aggregator.py#L70)
- [`build_task_agent`](agents/task_agent.py#L115)
- [`build_dynamic_parallel_dispatcher`](agents/task_agent.py#L191)

These functions depend on provider/model configuration and on `google.adk.agents` classes such as `LlmAgent`, `ParallelAgent`, and `SequentialAgent`. Missing provider credentials or incompatible SDK versions are common causes.

> **Sources:** `scripts/demo/cloud_smoke_test.py` · L105–L212 · [`_extract_response_text`](scripts/demo/cloud_smoke_test.py#L105) · [`probe_sdk`](scripts/demo/cloud_smoke_test.py#L118) · [`main`](scripts/demo/cloud_smoke_test.py#L183)  
> **Sources:** `agents/aggregator.py` · L70–L81 · [`build_aggregator_agent`](agents/aggregator.py#L70)  
> **Sources:** `agents/task_agent.py` · L115–L237 · [`build_task_agent`](agents/task_agent.py#L115) · [`build_dynamic_parallel_dispatcher`](agents/task_agent.py#L191)  
> **Sources:** `config.py` · L166–L196 · [`Settings.validate_rag_regions`](config.py#L166)

---

## Notes on Documentation Gaps

The analysis data did **not** include a package manifest, Dockerfile, or concrete build/test commands. This guide therefore documents only evidence-backed setup details and uses conservative examples where necessary. If you want a fully exact installation matrix, the next files to inspect would be:

- `pyproject.toml` or `setup.py` for install commands and Python version constraints
- `requirements.txt` or lockfiles for dependency pinning
- `Dockerfile` for container setup
- the full body of [`Settings`](config.py#L7) for definitive environment variable names

> **Sources:** `files_seen` list provided in analysis payload