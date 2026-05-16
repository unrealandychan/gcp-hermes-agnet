---
slug: installation-and-setup
title: "Getting Started: Install and Bootstrap"
section: getting-started
tags: [getting-started, configuration]
pin: false
importance: 74
created_at: 2026-05-16T04:11:22Z
rekipedia_version: 0.15.1
---

# Getting Started: Install and Bootstrap

This page documents the practical steps to install, configure, and bootstrap the project for local development. It focuses on environment prerequisites, Python and Node setup, dependency installation, and the main build/start commands. It also calls out the repository’s setup entry points, especially [`setup_wizard.py`](setup_wizard.py) and [`scripts/setup_rag.py`](scripts/setup_rag.py), which are the clearest system-initialization scripts in the codebase.

## Prerequisites

Before bootstrapping, make sure the required tooling and external services are available.

### Local tooling

The repository indicates a Python-backed application with a companion UI in `ui/`. The presence of [`pyproject.toml`](pyproject.toml), [`requirements.txt`](requirements.txt), and [`ui/package.json`](ui/package.json) shows that you need both a Python environment and a Node.js environment.

Recommended baseline prerequisites:

- Python matching the project’s pinned version in [`.python-version`](.python-version)
- Node.js and npm for the frontend workspace under `ui/`
- Access to Google Cloud tooling if you intend to use the project’s bootstrap scripts that configure cloud resources, because [`setup_wizard.py`](setup_wizard.py) includes GCP-oriented steps such as `bootstrap_gcp`, `setup_rag`, and `deploy_cloud_run`
- Optional: Docker, if you want to inspect or build containerized deployments via [`Dockerfile.gateway`](Dockerfile.gateway)

### Configuration files to review first

The repo ships with:
- [`.env.example`](.env.example) for environment variable defaults
- [`agents.yaml`](agents.yaml) for agent registration inputs
- [`governance/policies.yaml`](governance/policies.yaml) for policy configuration
- [`ui/.env.local.example`](ui/.env.local.example) for UI-side environment values

These files are important because the bootstrap flow is configuration-driven rather than hard-coded.

> **Sources:** `.python-version` · `.env.example` · `ui/.env.local.example` · `ui/package.json` · `pyproject.toml` · `requirements.txt` · `Dockerfile.gateway` · [`setup_wizard.py`](setup_wizard.py#L1)

## Python Environment Setup

The backend and bootstrap scripts are Python-based, so the first step is to create and activate a Python environment that matches the repository’s version constraints.

### Version alignment

The project includes [`.python-version`](.python-version), which is the clearest version pin visible in the repository layout. Use that version for the virtual environment to minimize dependency drift.

### Typical virtual environment workflow

A standard local setup sequence is:

```bash
python -m venv .venv
source .venv/bin/activate
python --version
```

If you are using `uv`, `poetry`, or another environment manager, align it to the version in [`.python-version`](.python-version). The repo’s build command list includes `uv build`, suggesting `uv` is a supported tooling path for Python packaging.

### Python dependencies

The project has both [`requirements.txt`](requirements.txt) and [`pyproject.toml`](pyproject.toml). The bootstrap helper [`install_python_deps`](setup_wizard.py#L506-L512) indicates that Python dependencies are installed as part of the setup flow, rather than requiring manual piecemeal installation.

A typical install command is:

```bash
pip install -r requirements.txt
```

Or, if you use `uv`:

```bash
uv sync
```

The exact mechanism is not fully expanded in the static analysis, but the presence of `uv build` in the build commands strongly suggests `uv` is part of the intended developer workflow.

> **Sources:** `.python-version` · `pyproject.toml` · `requirements.txt` · [`setup_wizard.py`](setup_wizard.py#L506-L512)

## Node Environment Setup

The `ui/` directory is a separate Node workspace. Its `package.json` declares the frontend dependencies and scripts used to build and run the Next.js application.

### Recommended setup

Install Node.js using your preferred version manager, then install frontend dependencies in `ui/`:

```bash
cd ui
npm install
```

The evidence shows the UI depends on packages such as `next`, `react`, `react-dom`, `next-auth`, and `react-markdown` (`ui/package.json`), which confirms that a working Node/npm toolchain is required.

### UI environment variables

The frontend includes [`ui/.env.local.example`](ui/.env.local.example). Copy this into a local `.env.local` file and fill in the environment-specific values expected by the UI.

```bash
cp ui/.env.local.example ui/.env.local
```

Because the UI communicates with the backend gateway and authentication flow, this environment file is part of the normal bootstrapping process.

> **Sources:** `ui/package.json` · `ui/.env.local.example`

## Dependency Installation

The repository’s installation flow is split between Python and Node dependencies.

### Python dependency installation

The primary Python install path is captured by [`install_python_deps`](setup_wizard.py#L506-L512). While the implementation details are not spelled out in the payload, the visible repository signals point to:

```bash
pip install -r requirements.txt
```

or a lockfile-aware workflow if you are using `uv`.

### Node dependency installation

For the UI workspace:

```bash
cd ui
npm install
```

This step is required before running any frontend build or start command.

### Optional environment bootstrap files

The project includes `.env.example` and `ui/.env.local.example`, which should be copied and customized before running setup scripts. The codebase also contains [`config.py`](config.py) and the [`Settings`](config.py#L7-L159) class, showing that environment variables are central to configuration loading.

> **Sources:** `.env.example` · `ui/.env.local.example` · `requirements.txt` · `ui/package.json` · [`config.py`](config.py#L1-L1) · [`Settings`](config.py#L7-L159)

## Primary Build and Start Commands

The analysis data explicitly lists the main build commands used by this repository.

| Command | Purpose | Expected Result |
|---|---|---|
| `uv build` | Build the Python package/distribution | Produces build artifacts for the Python project |
| `npm run build` | Build the Next.js UI (`next build`) | Creates an optimized production build in `ui/` |
| `npm start` | Start the Next.js UI (`next start`) | Runs the compiled frontend in production mode |

These are the canonical build/start commands surfaced by the static analysis. In practice, you would run them after both dependency trees are installed and environment files are populated.

### Common development start pattern

A typical bootstrap sequence looks like this:

```bash
# Python environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Node UI
cd ui
npm install
npm run build
npm start
```

If you are working only on the Python side, `uv build` is the repository’s documented build command. For the UI, `npm run build` and `npm start` are the main production-oriented commands.

> **Sources:** [`build_commands`](#) are derived from analysis evidence · `ui/package.json` · [`setup_wizard.py`](setup_wizard.py#L506-L512)

## Bootstrap Entry Points and Initialization Scripts

Several scripts in the repository are clearly intended to initialize or prepare the system.

### Main setup wizard

The most important bootstrap entry point is [`setup_wizard.py`](setup_wizard.py). Its symbol map shows a structured sequence of setup functions:

- [`preflight`](setup_wizard.py#L121-L167)
- [`gather_config`](setup_wizard.py#L171-L211)
- [`bootstrap_gcp`](setup_wizard.py#L244-L316)
- [`setup_rag`](setup_wizard.py#L320-L371)
- [`deploy_agent`](setup_wizard.py#L375-L414)
- [`seed_demo_data`](setup_wizard.py#L418-L430)
- [`setup_memory_bank`](setup_wizard.py#L433-L454)
- [`deploy_cloud_run`](setup_wizard.py#L458-L502)
- [`install_python_deps`](setup_wizard.py#L506-L512)
- [`print_summary`](setup_wizard.py#L516-L553)

This script appears to be the project’s all-in-one bootstrap wizard. It is the best place to start if you want to prepare the full system from a fresh checkout.

### RAG setup helper

[`scripts/setup_rag.py`](scripts/setup_rag.py) is another initialization entry point. Its [`main`](scripts/setup_rag.py#L43-L59) function and [`create_corpus`](scripts/setup_rag.py#L29-L40) helper indicate that it is dedicated to RAG corpus initialization.

### Other preparation scripts

Other repository entry points that may be relevant during setup:

- [`scripts/register_agents.py`](scripts/register_agents.py) — appears to register agents from [`agents.yaml`](agents.yaml)
- [`scripts/demo/seed_knowledge_base.py`](scripts/demo/seed_knowledge_base.py) — seeds demo knowledge content
- [`scripts/demo/seed_bigquery.py`](scripts/demo/seed_bigquery.py) — seeds BigQuery demo data
- [`scripts/demo/e2e_test.py`](scripts/demo/e2e_test.py) — test harness for exercising the system after setup
- [`teardown_wizard.py`](teardown_wizard.py) — cleanup companion for reversing bootstrap actions

### What the setup wizard does not imply

This page is intentionally about installation and bootstrap only. It does not explain the runtime architecture or API behavior of the gateway, agents, or tools. It only identifies the scripts that initialize the environment and the project state.

> **Sources:** [`setup_wizard.py`](setup_wizard.py#L1-L1) · [`preflight`](setup_wizard.py#L121-L167) · [`gather_config`](setup_wizard.py#L171-L211) · [`bootstrap_gcp`](setup_wizard.py#L244-L316) · [`setup_rag`](setup_wizard.py#L320-L371) · [`deploy_agent`](setup_wizard.py#L375-L414) · [`seed_demo_data`](setup_wizard.py#L418-L430) · [`setup_memory_bank`](setup_wizard.py#L433-L454) · [`deploy_cloud_run`](setup_wizard.py#L458-L502) · [`install_python_deps`](setup_wizard.py#L506-L512) · [`print_summary`](setup_wizard.py#L516-L553) · [`scripts/setup_rag.py`](scripts/setup_rag.py#L1-L1) · [`create_corpus`](scripts/setup_rag.py#L29-L40) · [`main`](scripts/setup_rag.py#L43-L59) · [`scripts/register_agents.py`](scripts/register_agents.py#L1-L1) · [`scripts/demo/seed_knowledge_base.py`](scripts/demo/seed_knowledge_base.py#L1-L1) · [`scripts/demo/seed_bigquery.py`](scripts/demo/seed_bigquery.py#L1-L1) · [`scripts/demo/e2e_test.py`](scripts/demo/e2e_test.py#L1-L1) · [`teardown_wizard.py`](teardown_wizard.py#L1-L1)

## Setup Step Summary

The following table consolidates the practical bootstrap path.

| Step | Command | Purpose | Expected Result |
|---|---|---|---|
| 1 | `python --version` | Confirm Python version matches [`.python-version`](.python-version) | Compatible Python runtime available |
| 2 | `python -m venv .venv && source .venv/bin/activate` | Create and activate an isolated Python environment | Local virtualenv is active |
| 3 | `pip install -r requirements.txt` | Install backend and bootstrap dependencies | Python packages installed successfully |
| 4 | `cd ui && npm install` | Install frontend dependencies | Node modules installed in `ui/node_modules` |
| 5 | `cp .env.example .env` | Create local backend environment config | Backend configuration file exists |
| 6 | `cp ui/.env.local.example ui/.env.local` | Create local UI environment config | UI configuration file exists |
| 7 | `uv build` | Build the Python package | Python build artifacts created |
| 8 | `cd ui && npm run build` | Build the frontend | Next.js production build succeeds |
| 9 | `cd ui && npm start` | Start the built frontend | UI runs in production mode |
| 10 | `python setup_wizard.py` | Run end-to-end bootstrap workflow | System initialization steps execute |

This table is the shortest actionable path from clone to a working local bootstrap.

> **Sources:** `.python-version` · `.env.example` · `ui/.env.local.example` · `requirements.txt` · `ui/package.json` · [`setup_wizard.py`](setup_wizard.py#L1-L1)