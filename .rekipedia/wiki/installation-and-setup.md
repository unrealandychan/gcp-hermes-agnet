---
slug: installation-and-setup
title: "Installation and Setup Guide"
section: general
pin: false
importance: 50
created_at: 2026-05-17T05:01:09Z
rekipedia_version: 0.15.1
---

# Installation and Setup Guide

This guide covers how to prepare a development environment for the repository, install dependencies, and verify that the memory bank module works as expected. The codebase in the provided analysis is centered on [`memory.memory_bank`](memory/memory_bank.py#L1), which wraps the Vertex AI Agent Engine memories API via the [`HermesMemoryBank`](memory/memory_bank.py#L79) facade.

## Requirements

### Python and runtime expectations

The repository is Python-based and includes a `requirements.txt` file, so a standard virtual environment workflow is the most appropriate setup path. The code in [`memory.memory_bank`](memory/memory_bank.py#L1) uses:

- `asyncio` for async orchestration
- `logging` for operational logging
- `typing` for type hints
- `vertexai` for Google Vertex AI integration
- `config` for application settings access

Because the implementation calls `asyncio.to_thread(...)` in methods such as [`HermesMemoryBank.generate_memories`](memory/memory_bank.py#L105) and [`HermesMemoryBank.fetch_memories`](memory/memory_bank.py#L331), it must be run on a reasonably modern Python version with `asyncio.to_thread` support. In practice, that means Python 3.9+ is a safe baseline.

### External service dependency

This project depends on Google Vertex AI Agent Engine Memories. The implementation is not a local-only memory store: the core facade methods such as [`create_memory_bank`](memory/memory_bank.py#L432), [`create_memory`](memory/memory_bank.py#L250), [`fetch_memories`](memory/memory_bank.py#L331), and [`ingest_events`](memory/memory_bank.py#L143) call into the Vertex SDK.

To use the project against real services, you will need:

| Requirement | Why it is needed |
|---|---|
| Google Cloud project | Used by Vertex AI client initialization |
| Vertex AI access enabled | Required for Agent Engine and memories operations |
| Correct region/location | Used when creating or resolving the memory bank resource |
| SDK access credentials | Required by the Vertex client |

The helper [`_get_vertexai_client`](memory/memory_bank.py#L41) explicitly falls back to configuration settings when `project` or `location` are not passed, so environment/configuration is part of setup.

### Repository dependencies

The presence of [`requirements.txt`](requirements.txt) indicates dependency management is pinned via pip-style requirements. The analysis did not include the actual file contents, so the exact package list is not visible here. However, the tests in [`tests/memory/test_memory_bank.py`](tests/memory/test_memory_bank.py#L1) clearly assume the presence of `pytest` and mocking support.

> **Sources:** `memory/memory_bank.py` · L1–L470 · [`memory.memory_bank`](memory/memory_bank.py#L1), [`HermesMemoryBank`](memory/memory_bank.py#L79), [`_get_vertexai_client`](memory/memory_bank.py#L41)  
> `requirements.txt` · file present in repository

## Installation Methods

### From Source

The repository does not provide `build_commands` in the analysis payload, so there is no evidence of a custom build system. The safest source-install workflow is a conventional virtual environment plus dependency installation from `requirements.txt`.

#### Step 1: Clone the repository

```bash
git clone <repository-url>
cd <repository-directory>
```

#### Step 2: Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
```

#### Step 3: Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

If you are working on the memory module specifically, this should bring in the Vertex SDK and any support libraries used by the tests.

#### Step 4: Verify the package can be imported

Because the memory module is available under `memory/memory_bank.py`, a basic import check is useful:

```bash
python -c "from memory.memory_bank import HermesMemoryBank; print(HermesMemoryBank)"
```

This confirms that the package layout is correct and that the installed dependencies satisfy import-time requirements.

> **Sources:** `requirements.txt` · file present in repository  
> `memory/memory_bank.py` · L1–L470 · [`HermesMemoryBank`](memory/memory_bank.py#L79), [`build_memory_bank`](memory/memory_bank.py#L411), [`create_memory_bank`](memory/memory_bank.py#L432)

### Via Package Manager

The analysis did not detect a `pyproject.toml` or `package.json`, so there is no evidence of a Poetry, uv, npm, or pnpm package manifest. The only explicit dependency manifest present is [`requirements.txt`](requirements.txt), which means installation via pip is the documented path.

#### Recommended pip install

```bash
pip install -r requirements.txt
```

#### Optional editable-style development install

If the repository is structured as a Python package and you want local edits to be immediately reflected, you can also install the project itself in editable mode after dependencies are installed:

```bash
pip install -e .
```

Note: this is a standard Python workflow suggestion; the analysis does not show whether a packaging configuration file exists, so editable install may or may not be supported without additional repository context.

> **Sources:** `requirements.txt` · file present in repository

### Docker

No `Dockerfile` was present in the analysis data, so there is no evidence that the repository ships an official container workflow. If you need one, it would have to be added manually.

A typical Docker workflow for a Python service would look like this, but treat it as an example rather than repository-specific guidance:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "-c", "from memory.memory_bank import build_memory_bank; print(build_memory_bank())"]
```

Build and run:

```bash
docker build -t hermes-memory .
docker run --rm hermes-memory
```

Because `build_memory_bank()` returns `None` when `MEMORY_BANK_RESOURCE_NAME` is unset, this container would likely start without a configured backend unless you inject the needed environment variables.

> **Sources:** `memory/memory_bank.py` · L411–L427 · [`build_memory_bank`](memory/memory_bank.py#L411)  
> No `Dockerfile` found in `files_seen`

## First Run

The first run depends on whether you are just validating the local Python environment or connecting to a real Vertex AI memory bank.

### Local sanity check

A quick way to verify the repository is installed correctly is to exercise the helper that builds the memory facade from settings:

```bash
python - <<'PY'
from memory.memory_bank import build_memory_bank
bank = build_memory_bank()
print(bank)
PY
```

If `MEMORY_BANK_RESOURCE_NAME` is not configured, [`build_memory_bank`](memory/memory_bank.py#L411) is designed to degrade gracefully and return `None`. That is expected behavior, not an error.

### Creating or reusing a memory bank

To actually use the backend, you need a full Agent Engine resource name, such as:

`projects/my-project/locations/us-central1/reasoningEngines/1234567890`

This is documented directly on [`HermesMemoryBank`](memory/memory_bank.py#L79). If you do not already have such a resource, the helper [`create_memory_bank(project, location, display_name)`](memory/memory_bank.py#L432) can create one.

Example workflow:

```python
from memory.memory_bank import create_memory_bank, HermesMemoryBank

resource_name = create_memory_bank(
    project="my-project",
    location="us-central1",
    display_name="hermes-memory-bank",
)

bank = HermesMemoryBank(resource_name=resource_name)
```

### Typical first interaction

Once instantiated, the facade supports both direct memory writes and retrieval:

```python
await bank.create_memory(user_id="u123", fact="Uses VPN on Monday mornings")
memories = await bank.fetch_memories(user_id="u123", query="VPN")
print(memories)
```

For chat-style usage, [`format_for_prompt`](memory/memory_bank.py#L381) converts relevant memories into a system-prompt snippet, which is meant to be injected by the caller.

> **Sources:** `memory/memory_bank.py` · L79–L470 · [`HermesMemoryBank`](memory/memory_bank.py#L79), [`create_memory_bank`](memory/memory_bank.py#L432), [`create_memory`](memory/memory_bank.py#L250), [`fetch_memories`](memory/memory_bank.py#L331), [`format_for_prompt`](memory/memory_bank.py#L381)

## Environment Variables

The analysis did not include the contents of configuration files, so only a small set of environment-driven settings can be stated with confidence.

### Observed configuration hook

The code imports `config` and calls `get_settings()` in several places, notably:

- [`_get_vertexai_client`](memory/memory_bank.py#L41)
- [`build_memory_bank`](memory/memory_bank.py#L411)

From the function docstrings and behavior, the following configuration field is clearly supported:

| Setting | Purpose | Required? |
|---|---|---|
| `MEMORY_BANK_RESOURCE_NAME` | Full Agent Engine resource name for the memory backend | Yes, for real backend usage |

If `MEMORY_BANK_RESOURCE_NAME` is missing or empty, [`build_memory_bank`](memory/memory_bank.py#L411) returns `None` and the application can continue without memory persistence.

### Vertex client project/location fallback

[`_get_vertexai_client(project, location)`](memory/memory_bank.py#L41) falls back to values from settings when explicit parameters are not provided. The exact setting names are not shown in the analysis, so they should be confirmed in the repository’s `config` module before relying on them in production.

### Practical setup example

A typical shell-based setup might look like this:

```bash
export MEMORY_BANK_RESOURCE_NAME="projects/my-project/locations/us-central1/reasoningEngines/1234567890"
```

If the config module reads additional Vertex settings from the environment, they will need to be set as well, but those names are not evidenced in the available analysis.

> **Sources:** `memory/memory_bank.py` · L41–L74 · [`_get_vertexai_client`](memory/memory_bank.py#L41)  
> `memory/memory_bank.py` · L411–L427 · [`build_memory_bank`](memory/memory_bank.py#L411)  
> `memory/memory_bank.py` · L79–L94 · [`HermesMemoryBank`](memory/memory_bank.py#L79)

## Troubleshooting

### `build_memory_bank()` returns `None`

This usually means `MEMORY_BANK_RESOURCE_NAME` is not set, is blank, or the config lookup failed. The behavior is intentional: [`build_memory_bank`](memory/memory_bank.py#L411) is designed to return `None` when the memory bank is not configured.

**Fix:**

- Set `MEMORY_BANK_RESOURCE_NAME`
- Confirm it contains a full resource path
- Restart the process after updating environment variables

### Vertex SDK import errors

[`_get_vertexai_client`](memory/memory_bank.py#L41) raises an `ImportError` with a helpful message when the Vertex SDK is too old. Since the analysis does not show the exact dependency version pin, this is a common setup issue if your environment has a stale Google SDK.

**Fix:**

```bash
pip install --upgrade -r requirements.txt
```

If that does not help, explicitly upgrade the Vertex SDK package used by the repository.

### Missing project or location context

When project/location are not passed to [`create_memory_bank`](memory/memory_bank.py#L432) or client initialization helpers, the code falls back to settings. If those settings are absent, client creation may fail or default incorrectly.

**Fix:**

- Pass `project` and `location` explicitly to [`create_memory_bank`](memory/memory_bank.py#L432)
- Ensure your settings source provides the needed defaults
- Verify the active Google Cloud credentials have access to the target project

### Network or API permission failures

Methods such as [`create_memory`](memory/memory_bank.py#L250), [`update_memory`](memory/memory_bank.py#L285), [`delete_memory`](memory/memory_bank.py#L227), and [`fetch_memories`](memory/memory_bank.py#L331) all depend on external Vertex API calls. In the tests, failures are often swallowed and converted to safe defaults, but in real usage these failures usually indicate authorization or connectivity problems.

**Fix:**

- Check Google Cloud authentication
- Confirm Vertex AI is enabled in the project
- Confirm the resource name points to the correct region
- Verify the runtime has outbound network access

### No memories returned on startup

[`fetch_memories`](memory/memory_bank.py#L331) and [`format_for_prompt`](memory/memory_bank.py#L381) will return empty results if there are no stored memories or if retrieval fails.

**Fix:**

- Confirm memories were ingested via [`generate_memories`](memory/memory_bank.py#L105) or [`ingest_events`](memory/memory_bank.py#L143)
- Check that the `user_id` matches the one used when storing memories
- Use a query that matches the expected facts

> **Sources:** `memory/memory_bank.py` · L41–L470 · [`_get_vertexai_client`](memory/memory_bank.py#L41), [`build_memory_bank`](memory/memory_bank.py#L411), [`create_memory_bank`](memory/memory_bank.py#L432), [`fetch_memories`](memory/memory_bank.py#L331), [`format_for_prompt`](memory/memory_bank.py#L381)