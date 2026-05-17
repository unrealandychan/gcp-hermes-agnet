---
slug: cli-and-api
title: "Memory Bank CLI and Programmatic API Reference"
section: general
pin: false
importance: 50
created_at: 2026-05-17T12:36:19Z
rekipedia_version: 0.15.1
---

# Memory Bank CLI and Programmatic API Reference

## Overview

This repository snapshot contains a single implementation module, [`memory.memory_bank`](memory/memory_bank.py#L1), plus a comprehensive test suite in [`tests.memory.test_memory_bank`](tests/memory/test_memory_bank.py#L1). The code focuses on a `HermesMemoryBank` facade over Vertex AI Agent Engine memories, with helper functions for constructing the client and provisioning the backing Agent Engine resource. The test coverage confirms the supported workflows and the error-handling expectations for each API surface.

A notable limitation of the analyzed code is that **no CLI entry points are present in the provided files**: the analysis data shows `entry_points: []` and no command-line wrapper module, `argparse` parser, or console script definition. Accordingly, the CLI section below documents the absence of discovered commands rather than inventing one.

> **Sources:** `memory/memory_bank.py` · L1–L498 · [`memory.memory_bank`](memory/memory_bank.py#L1), [`HermesMemoryBank`](memory/memory_bank.py#L79), [`build_memory_bank`](memory/memory_bank.py#L411), [`create_memory_bank`](memory/memory_bank.py#L432)

## CLI Reference

### No CLI commands were discovered

The analysis did not identify any CLI commands, subcommands, or console-script entry points in the repository snapshot. There are no command handlers, no `if __name__ == "__main__"` block, and no build metadata in the provided data that would expose a command-line interface. The practical implication is that this code is intended to be consumed as a **programmatic library**, not as a user-facing CLI tool.

If you need a CLI, the obvious external-facing operations to wrap would be:

- creating the memory bank resource via [`create_memory_bank(project, location, display_name)`](memory/memory_bank.py#L432)
- constructing a configured facade via [`build_memory_bank()`](memory/memory_bank.py#L411)
- generating, fetching, purging, or editing memories through [`HermesMemoryBank`](memory/memory_bank.py#L79)

### Suggested usage pattern for a future CLI

Although not present in the codebase, a minimal wrapper would likely expose commands such as:

- `memory-bank create`
- `memory-bank fetch`
- `memory-bank purge`
- `memory-bank ingest`

However, those commands are **not evidenced** in the repository snapshot and are not documented here as implemented behavior.

## Programmatic API

### `_get_vertexai_client(project, location)`

- **Signature:** [`_get_vertexai_client(project, location)`](memory/memory_bank.py#L41)
- **Purpose:** Returns a `vertexai.Client` instance, using explicit `project` and `location` values when provided, or falling back to settings.
- **Behavior:** The docstring states that it raises `ImportError` with a helpful message if the installed SDK is too old. The function calls `get_settings()` and reads settings via `getattr`, which means it is resilient to missing config attributes.
- **Return value:** A Vertex AI client instance.

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `project` | unspecified | none | Explicit GCP project ID; if falsy, settings are used instead |
| `location` | unspecified | none | Explicit Vertex AI region; if falsy, settings are used instead |

**Example usage**

```python
from memory.memory_bank import _get_vertexai_client

client = _get_vertexai_client(project="my-project", location="us-central1")
```

> **Sources:** `memory/memory_bank.py` · L41–L74 · [`_get_vertexai_client`](memory/memory_bank.py#L41), [`get_settings`](memory/memory_bank.py#L41), [`VertexClient`](memory/memory_bank.py#L41)

### `HermesMemoryBank`

- **Signature:** [`HermesMemoryBank`](memory/memory_bank.py#L79)
- **Purpose:** Application-level facade over Vertex AI Agent Engine memories.
- **Design:** The class encapsulates lazy client initialization through [`_ensure_client()`](memory/memory_bank.py#L98) and provides async methods for memory lifecycle operations.
- **Return value:** Class instance.

**Constructor**

- **Signature:** [`__init__(self, resource_name)`](memory/memory_bank.py#L92)

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `resource_name` | string-like | required | Full Agent Engine resource name, e.g. `projects/my-project/locations/us-central1/reasoningEngines/1234567890` |

**Example usage**

```python
from memory.memory_bank import HermesMemoryBank

bank = HermesMemoryBank(
    resource_name="projects/my-project/locations/us-central1/reasoningEngines/1234567890"
)
```

> **Sources:** `memory/memory_bank.py` · L79–L94 · [`HermesMemoryBank`](memory/memory_bank.py#L79)

### `HermesMemoryBank.generate_memories(self, user_id, user_text, agent_text, agent_name)`

- **Signature:** [`generate_memories(self, user_id, user_text, agent_text, agent_name)`](memory/memory_bank.py#L105)
- **Purpose:** Distills a conversation turn into durable memories.
- **Operational notes:** The docstring states this is called from `skill_learning_callback` in a fire-and-forget pattern after every agent turn. The implementation wraps blocking SDK work in `asyncio.to_thread`.
- **Return value:** Not explicitly documented in the analysis data; the method is used as an async side-effect operation.

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `user_id` | string-like | required | Authenticated user identifier |
| `user_text` | string-like | required | User message text |
| `agent_text` | string-like | required | Agent response text |
| `agent_name` | string-like | optional | Optional agent name for metadata |

**Example usage**

```python
await bank.generate_memories(
    user_id="u123",
    user_text="I use a VPN for work",
    agent_text="I'll remember that preference.",
    agent_name="Hermes",
)
```

> **Sources:** `memory/memory_bank.py` · L105–L141 · [`HermesMemoryBank.generate_memories`](memory/memory_bank.py#L105)

### `HermesMemoryBank.ingest_events(self, user_id, events)`

- **Signature:** [`ingest_events(self, user_id, events)`](memory/memory_bank.py#L143)
- **Purpose:** Streams conversation events to Memory Bank for automatic batched memory generation.
- **Operational notes:** The docstring explicitly describes this as more production-grade than `generate_memories()` because the SDK batches events and triggers generation automatically via the IngestEvents RPC. The tests confirm that event roles are normalized so `agent` becomes `model`.
- **Return value:** Not explicitly documented in the analysis data; the method operates via SDK side effects.

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `user_id` | string-like | required | Authenticated user identifier |
| `events` | list[dict] | required | Event dictionaries containing `role` and `text` keys |

**Example usage**

```python
await bank.ingest_events(
    user_id="u1",
    events=[
        {"role": "user", "text": "How do I reset my VPN?"},
        {"role": "agent", "text": "Go to Settings > VPN > Reset."},
    ],
)
```

> **Sources:** `memory/memory_bank.py` · L143–L185 · [`HermesMemoryBank.ingest_events`](memory/memory_bank.py#L143)

### `HermesMemoryBank.purge_memories(self, user_id, dry_run)`

- **Signature:** [`purge_memories(self, user_id, dry_run)`](memory/memory_bank.py#L187)
- **Purpose:** Bulk-deletes all memories for a user.
- **Behavior:** If `dry_run` is true, the method returns the count of memories that would be deleted without making the destructive API call.
- **Return value:** Number of memories deleted, or would-be deleted on dry run.

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `user_id` | string-like | required | User whose memories should be deleted |
| `dry_run` | bool | required | If true, count only; do not delete |

**Example usage**

```python
deleted = await bank.purge_memories(user_id="u123", dry_run=True)
print(f"Would delete {deleted} memories")
```

> **Sources:** `memory/memory_bank.py` · L187–L225 · [`HermesMemoryBank.purge_memories`](memory/memory_bank.py#L187)

### `HermesMemoryBank.delete_memory(self, memory_resource_name)`

- **Signature:** [`delete_memory(self, memory_resource_name)`](memory/memory_bank.py#L227)
- **Purpose:** Deletes a specific memory by full resource name.
- **Return value:** `True` on success, `False` on failure.

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `memory_resource_name` | string-like | required | Full resource name, e.g. `projects/p/locations/l/reasoningEngines/e/memories/m` |

**Example usage**

```python
ok = await bank.delete_memory(
    "projects/p/locations/l/reasoningEngines/e/memories/m"
)
```

> **Sources:** `memory/memory_bank.py` · L227–L248 · [`HermesMemoryBank.delete_memory`](memory/memory_bank.py#L227)

### `HermesMemoryBank.create_memory(self, user_id, fact)`

- **Signature:** [`create_memory(self, user_id, fact)`](memory/memory_bank.py#L250)
- **Purpose:** Writes a memory fact directly, bypassing LLM extraction/consolidation.
- **Use case:** The docstring identifies this as useful for a “memory-as-a-tool” pattern where the agent explicitly chooses what to remember.
- **Return value:** New memory resource name, or `None` on failure.

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `user_id` | string-like | required | User this memory belongs to |
| `fact` | string | required | Plain-text fact to store |

**Example usage**

```python
memory_name = await bank.create_memory(
    user_id="u123",
    fact="Prefers concise answers with examples.",
)
```

> **Sources:** `memory/memory_bank.py` · L250–L283 · [`HermesMemoryBank.create_memory`](memory/memory_bank.py#L250)

### `HermesMemoryBank.update_memory(self, memory_resource_name, new_fact)`

- **Signature:** [`update_memory(self, memory_resource_name, new_fact)`](memory/memory_bank.py#L285)
- **Purpose:** Updates an existing memory with corrected content.
- **Return value:** `True` on success, `False` on failure.

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `memory_resource_name` | string-like | required | Full resource name of the memory to update |
| `new_fact` | string | required | Corrected or updated fact text |

**Example usage**

```python
ok = await bank.update_memory(
    memory_resource_name="projects/p/locations/l/reasoningEngines/e/memories/m",
    new_fact="Prefers concise answers and prefers code samples in Python.",
)
```

> **Sources:** `memory/memory_bank.py` · L285–L313 · [`HermesMemoryBank.update_memory`](memory/memory_bank.py#L285)

### `HermesMemoryBank.retrieve_profiles(self, user_id)`

- **Signature:** [`retrieve_profiles(self, user_id)`](memory/memory_bank.py#L315)
- **Purpose:** Backward-compatibility stub for structured memory profiles.
- **Behavior:** The docstring states this API is not available in the current Agent Engine memories API (SDK >= 1.112), so it returns an empty list.
- **Return value:** Empty list.

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `user_id` | string-like | required | User identifier |

**Example usage**

```python
profiles = await bank.retrieve_profiles(user_id="u123")
# profiles is always []
```

> **Sources:** `memory/memory_bank.py` · L315–L329 · [`HermesMemoryBank.retrieve_profiles`](memory/memory_bank.py#L315)

### `HermesMemoryBank.fetch_memories(self, user_id, query, top_k)`

- **Signature:** [`fetch_memories(self, user_id, query, top_k)`](memory/memory_bank.py#L331)
- **Purpose:** Retrieves the most relevant memories for a user.
- **Operational notes:** The docstring says this is called at session start by `PreloadMemoryTool` to inject context into the system prompt. Tests verify it passes `top_k` and scope information to the SDK and that it gracefully degrades to `str(memory)` when a memory object lacks a `fact` attribute.
- **Return value:** List of memory strings.

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `user_id` | string-like | required | User identifier |
| `query` | string | required | Search query for retrieval |
| `top_k` | integer | required | Number of memories to retrieve |

**Example usage**

```python
memories = await bank.fetch_memories(
    user_id="u123",
    query="VPN setup",
    top_k=5,
)
```

> **Sources:** `memory/memory_bank.py` · L331–L367 · [`HermesMemoryBank.fetch_memories`](memory/memory_bank.py#L331)

### `HermesMemoryBank.list_revisions(self, user_id)`

- **Signature:** [`list_revisions(self, user_id)`](memory/memory_bank.py#L369)
- **Purpose:** Returns revision history for a user’s memories.
- **Behavior:** The docstring states revision history is not directly exposed in the current SDK, so this returns an empty list for backward compatibility.
- **Return value:** Empty list.

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `user_id` | string-like | required | User identifier |

**Example usage**

```python
revisions = await bank.list_revisions(user_id="u123")
```

> **Sources:** `memory/memory_bank.py` · L369–L379 · [`HermesMemoryBank.list_revisions`](memory/memory_bank.py#L369)

### `HermesMemoryBank.format_for_prompt(self, user_id, query, max_tokens)`

- **Signature:** [`format_for_prompt(self, user_id, query, max_tokens)`](memory/memory_bank.py#L381)
- **Purpose:** Fetches memories and formats them as a system prompt snippet.
- **Behavior:** Returns an empty string when no memories are found or when the memory bank is unavailable. The docstring states the caller in `gateway/main.py` injects the resulting text into the session prompt, although that file is not present in the analysis data.
- **Return value:** Prompt-formatted string.

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `user_id` | string-like | required | User identifier |
| `query` | string | required | Search query used to fetch memories |
| `max_tokens` | integer | required | Token budget for the formatted snippet |

**Example usage**

```python
snippet = await bank.format_for_prompt(
    user_id="u123",
    query="work preferences",
    max_tokens=200,
)
if snippet:
    system_prompt = f"{snippet}\n\nYou are a helpful assistant."
```

> **Sources:** `memory/memory_bank.py` · L381–L406 · [`HermesMemoryBank.format_for_prompt`](memory/memory_bank.py#L381)

### `build_memory_bank()`

- **Signature:** [`build_memory_bank()`](memory/memory_bank.py#L411)
- **Purpose:** Builds a `HermesMemoryBank` from settings.
- **Behavior:** Returns `None` if `MEMORY_BANK_RESOURCE_NAME` is not configured, enabling graceful degradation.
- **Return value:** `HermesMemoryBank` instance or `None`.

**Parameters**

None.

**Example usage**

```python
from memory.memory_bank import build_memory_bank

bank = build_memory_bank()
if bank is None:
    print("Memory Bank not configured")
```

> **Sources:** `memory/memory_bank.py` · L411–L427 · [`build_memory_bank`](memory/memory_bank.py#L411)

### `create_memory_bank(project, location, display_name)`

- **Signature:** [`create_memory_bank(project, location, display_name)`](memory/memory_bank.py#L432)
- **Purpose:** Creates a new Agent Engine resource to serve as the MemoryBank.
- **Behavior:** Safe to call multiple times; returns an existing resource if one with the same display name is found. The migration note explains that in SDK >= 1.112 there is no standalone `VertexAiMemoryBank` class, so the function creates a lightweight Agent Engine dedicated to memory storage.
- **Return value:** The resource name of the created or existing Agent Engine.

**Parameters**

| Parameter | Type | Default | Description |
|--------|------|---------|-------------|
| `project` | string-like | required | GCP project |
| `location` | string-like | required | Vertex AI region |
| `display_name` | string | required | Human-readable name used to find or create the engine |

**Example usage**

```python
from memory.memory_bank import create_memory_bank

resource_name = create_memory_bank(
    project="my-project",
    location="us-central1",
    display_name="Hermes Memory Bank",
)
print(resource_name)
```

> **Sources:** `memory/memory_bank.py` · L432–L498 · [`create_memory_bank`](memory/memory_bank.py#L432)

## Integration Examples

### End-to-end workflow: provision, store, retrieve, and format

A realistic integration pattern is:

1. Provision a Memory Bank resource with [`create_memory_bank()`](memory/memory_bank.py#L432).
2. Build a facade with [`HermesMemoryBank`](memory/memory_bank.py#L79).
3. Record user/agent interactions with [`ingest_events()`](memory/memory_bank.py#L143) or [`generate_memories()`](memory/memory_bank.py#L105).
4. Retrieve relevant memories with [`fetch_memories()`](memory/memory_bank.py#L331).
5. Convert them into a prompt snippet with [`format_for_prompt()`](memory/memory_bank.py#L381).

```python
import asyncio
from memory.memory_bank import HermesMemoryBank, create_memory_bank

async def main():
    resource_name = create_memory_bank(
        project="my-project",
        location="us-central1",
        display_name="Hermes Memory Bank",
    )

    bank = HermesMemoryBank(resource_name=resource_name)

    await bank.ingest_events(
        user_id="u123",
        events=[
            {"role": "user", "text": "I’m setting up a new VPN."},
            {"role": "agent", "text": "I can help with that."},
        ],
    )

    memories = await bank.fetch_memories(
        user_id="u123",
        query="VPN setup",
        top_k=5,
    )

    prompt_snippet = await bank.format_for_prompt(
        user_id="u123",
        query="VPN setup",
        max_tokens=200,
    )

    print(memories)
    print(prompt_snippet)

asyncio.run(main())
```

### Operational workflow: direct writes and cleanup

For admin or tool-driven workflows, you can bypass extraction and manage memories directly:

```python
async def admin_workflow(bank: HermesMemoryBank):
    memory_name = await bank.create_memory(
        user_id="u123",
        fact="Prefers short answers and Python examples.",
    )

    if memory_name:
        await bank.update_memory(
            memory_resource_name=memory_name,
            new_fact="Prefers concise answers with Python snippets.",
        )

    deleted_count = await bank.purge_memories(user_id="u123", dry_run=False)
    print(f"Deleted {deleted_count} memories")
```

### CLI/API combined workflow

Because no CLI is present in the analyzed files, there is no real command-line integration to demonstrate. If a CLI were added in the future, the intended flow would likely mirror the programmatic calls above:

- a `create` command would wrap [`create_memory_bank()`](memory/memory_bank.py#L432)
- a `fetch` command would wrap [`fetch_memories()`](memory/memory_bank.py#L331)
- a `purge` command would wrap [`purge_memories()`](memory/memory_bank.py#L187)

At present, consumers should call the API directly from application code or orchestration scripts.

> **Sources:** `memory/memory_bank.py` · L105–L498 · [`HermesMemoryBank`](memory/memory_bank.py#L79), [`create_memory_bank`](memory/memory_bank.py#L432), [`build_memory_bank`](memory/memory_bank.py#L411), [`format_for_prompt`](memory/memory_bank.py#L381)