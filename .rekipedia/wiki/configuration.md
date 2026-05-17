---
slug: configuration
title: "Configuration Reference for Hermes Memory Bank"
section: general
pin: false
importance: 50
created_at: 2026-05-17T12:38:29Z
rekipedia_version: 0.15.1
---

# Configuration Reference for Hermes Memory Bank

## Overview

This repository snapshot is centered on the memory subsystem implemented in [`memory/memory_bank.py`](memory/memory_bank.py#L1). Based on the analysis data, the configuration surface is intentionally small: the code reads runtime settings via a `config` module and uses those values to build and operate a Vertex AI-backed memory bank. The primary observable configuration key is `MEMORY_BANK_RESOURCE_NAME`, which determines whether a reusable memory bank can be instantiated or whether the system degrades gracefully and returns `None` from [`build_memory_bank`](memory/memory_bank.py#L411).

A notable constraint of this snapshot is that no standalone configuration files were detected in `files_seen`; only implementation and test Python files are present. As a result, there are no YAML, TOML, JSON, or `.env` files to enumerate. The configuration below is derived from the runtime behavior visible in [`_get_vertexai_client`](memory/memory_bank.py#L41-L74), [`build_memory_bank`](memory/memory_bank.py#L411-L427), and [`create_memory_bank`](memory/memory_bank.py#L432-L498), as well as the test coverage in [`tests/memory/test_memory_bank.py`](tests/memory/test_memory_bank.py#L1-L495).

## Configuration Files

No dedicated configuration files were found in this repository slice.

| File | Purpose | Evidence |
|------|---------|----------|
| _None detected_ | No YAML/TOML/JSON/.env files are present in `files_seen`. Runtime configuration appears to be sourced from a Python `config` module rather than file-based config. | [`memory/memory_bank.py`](memory/memory_bank.py#L1-L498), [`tests/memory/test_memory_bank.py`](tests/memory/test_memory_bank.py#L1-L495) |

> **Sources:** `memory/memory_bank.py` · L1–L498 · [`memory.memory_bank`](memory/memory_bank.py#L1) · `tests/memory/test_memory_bank.py` · L1–L495 · [`tests.memory.test_memory_bank`](tests/memory/test_memory_bank.py#L1)

## Configuration Reference

The analysis exposes one explicitly observable setting and one implied optional runtime input. The table below is limited to what can be supported from the code and tests.

### `config.MEMORY_BANK_RESOURCE_NAME`

This setting is accessed indirectly through [`get_settings`](memory/memory_bank.py#L41-L74) and [`build_memory_bank`](memory/memory_bank.py#L411-L427). When it is missing or empty, [`build_memory_bank`](memory/memory_bank.py#L411-L427) returns `None`, allowing the application to continue without memory-backed personalization.

| Key | Type | Default | Required | Description |
|-----|------|---------|----------|-------------|
| `MEMORY_BANK_RESOURCE_NAME` | string | `None` / empty | No | Full Vertex AI Agent Engine resource name used to connect to an existing memory bank, e.g. `projects/.../locations/.../reasoningEngines/...`. If unset or blank, memory bank construction is skipped and the feature is disabled gracefully. |

### `project` and `location` parameters for client construction

These are not file-based configuration keys, but they are configuration inputs that affect runtime behavior in [`_get_vertexai_client(project, location)`](memory/memory_bank.py#L41-L74) and [`create_memory_bank(project, location, display_name)`](memory/memory_bank.py#L432-L498). If the caller does not supply them, `_get_vertexai_client` falls back to settings values via `get_settings()`.

| Key | Type | Default | Required | Description |
|-----|------|---------|----------|-------------|
| `project` | string | Settings fallback | No | Google Cloud project used when creating a Vertex AI client or Agent Engine resource. If omitted, the function falls back to configured settings. |
| `location` | string | Settings fallback | No | Vertex AI region used for client/resource creation. If omitted, the function falls back to configured settings. |
| `display_name` | string | Internal default (not fully visible in analysis) | No | Human-readable name for a newly created memory-bank Agent Engine. Tests show the function supports a custom `display_name` and searches existing engines by this value. |

> **Sources:** `memory/memory_bank.py` · L41–L74, L411–L498 · [`_get_vertexai_client`](memory/memory_bank.py#L41) · [`build_memory_bank`](memory/memory_bank.py#L411) · [`create_memory_bank`](memory/memory_bank.py#L432)

## Configuration Examples

Because no standalone config files were found, the examples below show the minimum observable runtime configuration in a Python-centric style.

### Minimal configuration

This is the smallest viable setup for enabling memory support: define the memory bank resource name in the settings layer and let the code build a `HermesMemoryBank` from it.

```python
# config.py (conceptual example based on runtime behavior)
MEMORY_BANK_RESOURCE_NAME = "projects/my-project/locations/us-central1/reasoningEngines/1234567890"
```

With that value present, [`build_memory_bank`](memory/memory_bank.py#L411-L427) can return a [`HermesMemoryBank`](memory/memory_bank.py#L79-L406) instance; without it, the function returns `None`.

### Full-featured configuration

A fuller setup includes explicit client/resource parameters and a custom display name for provisioning a new backend via [`create_memory_bank`](memory/memory_bank.py#L432-L498).

```python
# config.py (conceptual example based on runtime behavior)
MEMORY_BANK_RESOURCE_NAME = "projects/my-project/locations/us-central1/reasoningEngines/1234567890"
PROJECT = "my-project"
LOCATION = "us-central1"

# When provisioning a new memory bank, the call may use:
# create_memory_bank(project=PROJECT, location=LOCATION, display_name="hermes-memory-bank")
```

This matches the code path that resolves project/location from explicit arguments or settings, then creates or reuses an Agent Engine resource before returning its resource name.

> **Sources:** `memory/memory_bank.py` · L41–L74, L411–L498 · [`_get_vertexai_client`](memory/memory_bank.py#L41) · [`build_memory_bank`](memory/memory_bank.py#L411) · [`create_memory_bank`](memory/memory_bank.py#L432)

## Runtime Configuration

The available runtime overrides are inferred from the function signatures and the tests in [`tests/memory/test_memory_bank.py`](tests/memory/test_memory_bank.py#L1-L495).

### Explicit function arguments

The following inputs override settings-based defaults when the functions are called directly:

| Override | Applies to | Behavior |
|----------|------------|----------|
| `project` | [`_get_vertexai_client`](memory/memory_bank.py#L41-L74), [`create_memory_bank`](memory/memory_bank.py#L432-L498) | If provided, it takes precedence over values from `get_settings()`. |
| `location` | [`_get_vertexai_client`](memory/memory_bank.py#L41-L74), [`create_memory_bank`](memory/memory_bank.py#L432-L498) | If provided, it takes precedence over values from `get_settings()`. |
| `display_name` | [`create_memory_bank`](memory/memory_bank.py#L432-L498) | Changes the friendly name used to search for existing Agent Engine resources before creating a new one. |
| `dry_run` | [`HermesMemoryBank.purge_memories`](memory/memory_bank.py#L187-L225) | Prevents deletion and returns the count of memories that would be deleted. |
| `top_k` | [`HermesMemoryBank.fetch_memories`](memory/memory_bank.py#L331-L367) | Controls how many relevant memories the SDK should return. |
| `max_tokens` | [`HermesMemoryBank.format_for_prompt`](memory/memory_bank.py#L381-L406) | Caps prompt-snippet size when formatting fetched memories. |

### Environment variables

No environment-variable parser or `.env` file was visible in the provided analysis. However, because the code relies on a `config` module, environment variables may still be used indirectly by that module. That mechanism is not evidenced here, so it should be treated as an implementation detail outside the analyzed files.

### CLI flags

No CLI entry points or command-line flags are present in the analysis data. There is no evidence of direct command-line overrides for configuration in this snapshot.

> **Sources:** `memory/memory_bank.py` · L41–L498 · [`_get_vertexai_client`](memory/memory_bank.py#L41) · [`HermesMemoryBank.purge_memories`](memory/memory_bank.py#L187) · [`HermesMemoryBank.fetch_memories`](memory/memory_bank.py#L331) · [`HermesMemoryBank.format_for_prompt`](memory/memory_bank.py#L381) · [`create_memory_bank`](memory/memory_bank.py#L432) · `tests/memory/test_memory_bank.py` · L1–L495

## Validation

There is no evidence of Pydantic models, JSON Schema, or formal config-file validation in the provided repository slice. Validation appears to be done defensively at runtime through conditional checks and exception handling in the Python code.

### Observed validation and fallback behavior

- [`build_memory_bank`](memory/memory_bank.py#L411-L427) checks whether `MEMORY_BANK_RESOURCE_NAME` is present. If it is missing or empty, the function returns `None`.
- [`_get_vertexai_client`](memory/memory_bank.py#L41-L74) falls back to settings when `project` or `location` are not passed explicitly.
- Several methods wrap SDK calls in `try/except` blocks and degrade gracefully:
  - [`generate_memories`](memory/memory_bank.py#L105-L141) swallows exceptions and logs debug output.
  - [`fetch_memories`](memory/memory_bank.py#L331-L367) returns an empty list on failure.
  - [`format_for_prompt`](memory/memory_bank.py#L381-L406) returns an empty string if no memories are available or retrieval fails.
  - [`purge_memories`](memory/memory_bank.py#L187-L225) returns `0` on exception.
  - [`delete_memory`](memory/memory_bank.py#L227-L248), [`create_memory`](memory/memory_bank.py#L250-L283), and [`update_memory`](memory/memory_bank.py#L285-L313) return failure indicators rather than propagating SDK exceptions.
- [`create_memory_bank`](memory/memory_bank.py#L432-L498) searches existing engines before creating a new one and raises a `RuntimeError` only when the SDK returns an unexpected result shape.

### Test evidence for validation paths

The tests explicitly exercise the fallback and failure behavior:
- missing/empty `MEMORY_BANK_RESOURCE_NAME` returns `None` in [`TestBuildMemoryBank`](tests/memory/test_memory_bank.py#L222-L268)
- SDK errors are swallowed in [`TestGenerateMemories`](tests/memory/test_memory_bank.py#L58-L111), [`TestFetchMemories`](tests/memory/test_memory_bank.py#L116-L155), [`TestFormatForPrompt`](tests/memory/test_memory_bank.py#L173-L217), [`TestPurgeMemories`](tests/memory/test_memory_bank.py#L378-L406), [`TestDeleteMemory`](tests/memory/test_memory_bank.py#L411-L429), [`TestCreateMemory`](tests/memory/test_memory_bank.py#L434-L455), and [`TestUpdateMemory`](tests/memory/test_memory_bank.py#L460-L482)

In short, configuration validation is pragmatic rather than schema-driven: values are checked just enough to decide whether to enable memory support, and operational errors are contained to preserve application availability.

> **Sources:** `memory/memory_bank.py` · L41–L498 · [`_get_vertexai_client`](memory/memory_bank.py#L41) · [`HermesMemoryBank.generate_memories`](memory/memory_bank.py#L105) · [`HermesMemoryBank.fetch_memories`](memory/memory_bank.py#L331) · [`HermesMemoryBank.format_for_prompt`](memory/memory_bank.py#L381) · [`HermesMemoryBank.purge_memories`](memory/memory_bank.py#L187) · [`build_memory_bank`](memory/memory_bank.py#L411) · [`create_memory_bank`](memory/memory_bank.py#L432)