---
slug: installation-and-setup
title: "Installation and Setup Guide"
section: general
pin: false
importance: 50
created_at: 2026-05-17T12:36:37Z
rekipedia_version: 0.15.1
---

# Installation and Setup Guide

This guide covers how to install, configure, and verify the memory-bank component implemented in [`memory/memory_bank.py`](memory/memory_bank.py#L1). The codebase snapshot available here is focused on a single implementation module and its tests in [`tests/memory/test_memory_bank.py`](tests/memory/test_memory_bank.py#L1), so the setup instructions below are based on what is observable in that code rather than on a full repository manifest.

## Requirements

### Runtime and platform expectations

The implementation in [`memory.memory_bank`](memory/memory_bank.py#L1) is Python-based and uses:

- `asyncio` for async wrappers and background execution
- `logging` for operational messages
- `typing` for type annotations
- `vertexai` for the Vertex AI Agent Engine memory APIs
- a local `config` module, accessed via `get_settings()` in several entry points

The main facade, [`HermesMemoryBank`](memory/memory_bank.py#L79), is designed to work against Vertex AI Agent Engine memories and expects a resource name such as:

`projects/my-project/locations/us-central1/reasoningEngines/1234567890`

The helper [`_get_vertexai_client(project, location)`](memory/memory_bank.py#L41) indicates two important setup requirements:

1. The installed Vertex AI SDK must be new enough to provide `VertexClient`.
2. If `project` / `location` are not supplied, the code falls back to settings from [`get_settings()`](memory/memory_bank.py#L41).

### Python version

No `pyproject.toml`, `package.json`, or explicit build metadata is present in the supplied analysis data, so the exact Python version cannot be confirmed from the repository snapshot. What is clear is that the code uses modern async syntax and `from __future__` imports, so a recent Python 3 release is expected.

### External dependencies

The direct runtime dependency that is clearly evidenced is:

| Dependency | Why it is needed | Evidence |
|---|---|---|
| `vertexai` | Provides `VertexClient`, memory generation, retrieval, purge, create, update, and delete operations | [`memory/memory_bank.py`](memory/memory_bank.py#L1) |
| local `config` module | Supplies project/location/resource-name configuration via `get_settings()` | [`memory/memory_bank.py`](memory/memory_bank.py#L41), [`memory/memory_bank.py`](memory/memory_bank.py#L411) |

The tests additionally rely on:

- `pytest`
- `unittest.mock`
- `types.SimpleNamespace`

> **Sources:** `memory/memory_bank.py` · L1–L498 · [`HermesMemoryBank`](memory/memory_bank.py#L79), [`_get_vertexai_client`](memory/memory_bank.py#L41), [`build_memory_bank`](memory/memory_bank.py#L411) · `tests/memory/test_memory_bank.py` · L1–L495 · [`TestBuildMemoryBank`](tests/memory/test_memory_bank.py#L222)

## Installation Methods

### From Source

No build commands were provided in the analysis payload, so the repository’s exact bootstrap steps cannot be reconstructed. However, the code is pure Python and the tests import the module directly, so a source install is likely straightforward.

A practical source workflow would be:

```bash
git clone <repository-url>
cd <repository-dir>
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install vertexai pytest
```

If your environment uses the local `config` module, ensure that package or module is importable before running the code.

Because the implementation wraps the SDK calls in `asyncio.to_thread()` in methods like [`generate_memories`](memory/memory_bank.py#L105) and [`fetch_memories`](memory/memory_bank.py#L331), there is no special build step beyond dependency installation.

### Via Package Manager

No `pyproject.toml`, `setup.py`, `package.json`, or similar packaging manifest is visible in the provided analysis, so there is no repository-specific package-manager install command to cite. If this code is part of a larger Python project, the usual patterns would be:

```bash
pip install .
# or
uv pip install .
```

If the project is published to an index, installation would likely look like:

```bash
pip install <package-name>
```

At minimum, the code requires the Vertex AI SDK compatible with [`VertexClient`](memory/memory_bank.py#L41).

### Docker

No `Dockerfile` is present in the analysis data, so Docker-based installation cannot be confirmed. If you add container support later, the container should include:

- a Python runtime
- the Vertex AI SDK
- whatever provides the local `config` module
- credentials for Google Cloud / Vertex AI access

A generic container invocation would look like:

```bash
docker build -t hermes-memory-bank .
docker run --rm -e GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp.json hermes-memory-bank
```

This is illustrative only; the repository snapshot does not prove that the project currently supports Docker.

> **Sources:** `memory/memory_bank.py` · L41–L498 · [`_get_vertexai_client`](memory/memory_bank.py#L41), [`build_memory_bank`](memory/memory_bank.py#L411), [`create_memory_bank`](memory/memory_bank.py#L432)

## First Run

The primary runtime entry point exposed by the module is the memory facade [`HermesMemoryBank`](memory/memory_bank.py#L79). The first-run flow depends on whether you already have a Memory Bank resource configured.

### 1. Configure a memory resource name

The helper [`build_memory_bank()`](memory/memory_bank.py#L411) returns `None` if `MEMORY_BANK_RESOURCE_NAME` is not configured. The tests confirm that both `None` and empty string values are treated as “not configured” in [`TestBuildMemoryBank`](tests/memory/test_memory_bank.py#L222).

So your first step is to ensure the relevant setting exists in your config layer. The code reads from settings via `get_settings()` and then accesses `MEMORY_BANK_RESOURCE_NAME` with `getattr`.

### 2. Create the Agent Engine-backed memory store if needed

If you do not yet have a resource name, use [`create_memory_bank(project, location, display_name)`](memory/memory_bank.py#L432) to create one. The function is designed to be idempotent:

- it lists existing engines
- if one matches the display name, it returns the existing engine’s resource name
- otherwise it creates a new one

This is the most direct “bootstrap” path for a new deployment.

### 3. Build the facade

Once configured, call:

```python
from memory.memory_bank import build_memory_bank

bank = build_memory_bank()
```

If successful, `bank` will be an instance of [`HermesMemoryBank`](memory/memory_bank.py#L79). If not configured or if creation fails, the function degrades gracefully and returns `None`.

### 4. Use the memory APIs

The facade exposes methods for common operations:

- [`generate_memories`](memory/memory_bank.py#L105) for automatic extraction after a conversation turn
- [`ingest_events`](memory/memory_bank.py#L143) for batched event ingestion
- [`fetch_memories`](memory/memory_bank.py#L331) for prompt-time retrieval
- [`format_for_prompt`](memory/memory_bank.py#L381) for ready-to-inject context strings
- CRUD-like operations such as [`create_memory`](memory/memory_bank.py#L250), [`update_memory`](memory/memory_bank.py#L285), and [`delete_memory`](memory/memory_bank.py#L227)

A minimal first-run example would be:

```python
import asyncio
from memory.memory_bank import build_memory_bank

async def main():
    bank = build_memory_bank()
    if bank is None:
        print("Memory bank not configured")
        return

    memories = await bank.fetch_memories(user_id="u123", query="VPN setup", top_k=5)
    print(memories)

asyncio.run(main())
```

> **Sources:** `memory/memory_bank.py` · L79–L498 · [`HermesMemoryBank`](memory/memory_bank.py#L79), [`build_memory_bank`](memory/memory_bank.py#L411), [`create_memory_bank`](memory/memory_bank.py#L432) · `tests/memory/test_memory_bank.py` · L222–L330 · [`TestBuildMemoryBank`](tests/memory/test_memory_bank.py#L222), [`TestCreateMemoryBank`](tests/memory/test_memory_bank.py#L273)

## Environment Variables

The provided analysis does not expose a `.env` file, config module source, or explicit environment-variable declarations. That means we can only infer configuration usage from code.

### Observable configuration inputs

The following values are clearly expected to come from settings and may ultimately be sourced from environment variables in the wider application:

| Setting | Used by | Purpose |
|---|---|---|
| `MEMORY_BANK_RESOURCE_NAME` | [`build_memory_bank`](memory/memory_bank.py#L411) | Controls whether a `HermesMemoryBank` is instantiated |
| project / location settings | [`_get_vertexai_client`](memory/memory_bank.py#L41) | Default Vertex AI project and region when explicit args are omitted |

The `create_memory_bank` flow also depends on project and location values, and uses a `display_name` to find or create the backing Agent Engine.

### Suggested environment setup

If your local config system maps settings to env vars, you will likely need something like:

```bash
export MEMORY_BANK_RESOURCE_NAME="projects/.../locations/.../reasoningEngines/..."
export GOOGLE_CLOUD_PROJECT="my-project"
export GOOGLE_CLOUD_LOCATION="us-central1"
```

This mapping is an informed guess; the exact variable names are not present in the supplied data.

### SDK compatibility concern

The docstring on [`_get_vertexai_client`](memory/memory_bank.py#L41) explicitly says it “raises ImportError with a helpful message if the SDK is too old.” If you see that error, your environment almost certainly has an outdated Vertex AI SDK and needs an upgrade.

> **Sources:** `memory/memory_bank.py` · L41–L74 · [`_get_vertexai_client`](memory/memory_bank.py#L41), [`build_memory_bank`](memory/memory_bank.py#L411)

## Troubleshooting

### `build_memory_bank()` returns `None`

This is expected when the memory resource is not configured. The implementation explicitly returns `None` if `MEMORY_BANK_RESOURCE_NAME` is missing or empty. Check:

- your settings source
- whether the environment variable or config entry is actually present
- whether the resource name string is non-empty and correctly formatted

Relevant behavior is exercised in [`TestBuildMemoryBank`](tests/memory/test_memory_bank.py#L222).

### ImportError mentioning Vertex AI / old SDK

The helper [`_get_vertexai_client`](memory/memory_bank.py#L41) is designed to fail fast if the installed SDK is too old to provide `VertexClient`. Fix by upgrading the Vertex AI package in your environment.

### No memories returned from `fetch_memories()`

[`fetch_memories`](memory/memory_bank.py#L331) returns an empty list on errors and when no results are found. If you are seeing no context:

- verify the user ID is correct
- verify the query matches known memory content
- verify the backing Agent Engine has memories stored
- check logs for swallowed exceptions

### `format_for_prompt()` returns an empty string

[`format_for_prompt`](memory/memory_bank.py#L381) intentionally returns an empty string when there are no memories or when retrieval fails. This is a safe fallback for prompt injection. If you expected content, troubleshoot `fetch_memories()` first.

### Memory generation appears to do nothing

[`generate_memories`](memory/memory_bank.py#L105) is fire-and-forget and wraps the blocking SDK call in `asyncio.to_thread()`. If it fails, the exception is swallowed after logging a debug message. This means:

- the app won’t crash
- you must inspect logs to see failures
- client initialization is lazy, so the first call is also the first real connectivity test

### SDK batch ingestion behaves differently than direct generation

Use [`ingest_events`](memory/memory_bank.py#L143) when you want the SDK to batch events automatically. The tests show it normalizes event roles, including mapping agent-like roles to model roles. If your event payload does not use the expected `role` and `text` keys, ingestion may not behave as intended.

### Create/update/delete operations fail silently

The methods [`create_memory`](memory/memory_bank.py#L250), [`update_memory`](memory/memory_bank.py#L285), [`delete_memory`](memory/memory_bank.py#L227), and [`purge_memories`](memory/memory_bank.py#L187) all handle exceptions by logging and returning safe fallback values (`None`, `False`, or `0`). This is deliberate. Troubleshooting should focus on:

- credentials
- project/region correctness
- resource names
- API permissions

> **Sources:** `memory/memory_bank.py` · L105–L406 · [`generate_memories`](memory/memory_bank.py#L105), [`ingest_events`](memory/memory_bank.py#L143), [`purge_memories`](memory/memory_bank.py#L187), [`delete_memory`](memory/memory_bank.py#L227), [`create_memory`](memory/memory_bank.py#L250), [`update_memory`](memory/memory_bank.py#L285), [`fetch_memories`](memory/memory_bank.py#L331), [`format_for_prompt`](memory/memory_bank.py#L381) · `tests/memory/test_memory_bank.py` · L58–L495 · [`TestGenerateMemories`](tests/memory/test_memory_bank.py#L58), [`TestFetchMemories`](tests/memory/test_memory_bank.py#L116), [`TestFormatForPrompt`](tests/memory/test_memory_bank.py#L173), [`TestCreateMemoryBank`](tests/memory/test_memory_bank.py#L273)