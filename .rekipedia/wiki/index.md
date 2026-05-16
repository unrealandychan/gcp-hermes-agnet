---
slug: index
title: "Overview"
section: getting-started
tags: [overview, getting-started, repository-structure]
pin: false
importance: 100
created_at: 2026-05-16T04:11:18Z
rekipedia_version: 0.15.1
---

# Overview

## What it is

This repository is a multi-agent orchestration platform for building, routing, governing, evaluating, and deploying domain-specific AI agents. It combines Python-based agent construction and runtime services with connector integrations, evaluation tooling, memory and skill management, and a Next.js UI for chat and session management. The core developer workflow is centered on assembling agents in [`agents`](agents/__init__.py#L1), exposing them through the gateway in [`gateway/main.py`](gateway/main.py#L1), and connecting them to external systems via the tools and connector layers such as [`tools/mcp_connector.py`](tools/mcp_connector.py#L1) and [`connectors/runner.py`](connectors/runner.py#L1).

The repo also includes deployment automation and environment bootstrapping for cloud and local setup, notably [`setup_wizard.py`](setup_wizard.py#L1), [`scripts/deploy.py`](scripts/deploy.py#L1), [`scripts/setup_rag.py`](scripts/setup_rag.py#L1), and [`teardown_wizard.py`](teardown_wizard.py#L1).

> **Sources:** `agents/__init__.py` · `gateway/main.py` · `tools/mcp_connector.py` · `connectors/runner.py` · `setup_wizard.py` · `scripts/deploy.py` · `scripts/setup_rag.py` · `teardown_wizard.py`

## Key Features

- **Agent orchestration**
  - Builds specialized agents for analytics, HR, IT helpdesk, and developer workflows through factory functions such as [`build_analytics_agent`](agents/analytics.py#L37) and [`build_orchestrator`](agents/orchestrator.py#L34).
  - Supports YAML-driven agent registration and dynamic construction via [`load_agents_yaml`](scripts/register_agents.py#L23) and [`build_agents_from_yaml`](agents/loader.py#L147).
  - Includes a task-oriented agent path with planner/executor composition in [`build_task_agent`](agents/task_agent.py#L160).

- **Gateway and runtime APIs**
  - Exposes chat, memory, task, and scheduler endpoints in [`gateway/main.py`](gateway/main.py#L1), with request/response models like [`ChatRequest`](gateway/main.py#L136) and [`TaskRequest`](gateway/main.py#L338).
  - Wraps an agent runtime client in [`AgentGatewayClient`](gateway/agent_gateway.py#L63) for sending and streaming messages to a reasoning engine or managed gateway backend.
  - Adds observability hooks through [`setup_tracing`](gateway/observability.py#L37) and [`agent_span`](gateway/observability.py#L86).

- **Gateway / connector integrations**
  - Integrates with Slack, Teams, and Telegram webhooks through [`slack_webhook`](connectors/slack.py#L68), [`teams_webhook`](connectors/teams.py#L93), and [`telegram_webhook`](connectors/telegram.py#L61).
  - Provides a connector runner abstraction via [`run_agent`](connectors/runner.py#L34), enabling execution of agents across platforms.
  - Includes tool connectors for Google Workspace, BigQuery, storage, search, scheduling, and MCP-based toolsets in [`tools/`](tools/__init__.py#L1).

- **Evaluation and monitoring**
  - Defines evaluation scoring in [`score_response`](eval/metrics.py#L23) and the [`EvalMetrics`](eval/metrics.py#L13) dataclass.
  - Supports online monitoring with [`build_online_monitor`](eval/online_monitor.py#L58) and [`log_quality_score`](eval/online_monitor.py#L21).
  - Ships evalsets for common domains under `eval/evalsets/`, and a CLI entry point in [`eval/run_eval.py`](eval/run_eval.py#L1).

- **Deployment and operational tooling**
  - Bootstraps infrastructure and cloud deployment via [`bootstrap_gcp`](setup_wizard.py#L244), [`deploy_cloud_run`](setup_wizard.py#L458), and [`scripts/deploy.py`](scripts/deploy.py#L1).
  - Provides teardown automation for cloud resources with granular cleanup functions like [`delete_cloud_run`](teardown_wizard.py#L112) and [`disable_apis`](teardown_wizard.py#L305).
  - Includes repository-level config and environment support through [`Settings`](config.py#L7) and the `.env.example` template.

> **Sources:** `agents/analytics.py` · `agents/orchestrator.py` · `agents/loader.py` · `agents/task_agent.py` · `gateway/main.py` · `gateway/agent_gateway.py` · `gateway/observability.py` · `connectors/slack.py` · `connectors/teams.py` · `connectors/telegram.py` · `connectors/runner.py` · `tools/` · `eval/metrics.py` · `eval/online_monitor.py` · `eval/run_eval.py` · `setup_wizard.py` · `teardown_wizard.py` · `config.py`

## Quick Start

This repository uses Python packaging for the backend and a separate Next.js app for the UI. Based on the available build commands, the minimal build/start sequence is:

```bash
# Backend package build
uv build

# UI build
cd ui
npm run build  # next build

# UI runtime start
npm start  # next start
```

If you want to validate the backend and UI together during development, the repository’s test suite and setup scripts indicate a broader workflow that typically includes environment bootstrap, agent registration, and optional demo data seeding. A practical next step after building is to review the setup tooling in [`setup_wizard.py`](setup_wizard.py#L1) and the deployment helper [`scripts/deploy.py`](scripts/deploy.py#L1), since they define the operational path for getting a deployed stack running.

### Recommended first steps

1. Inspect `.env.example` and [`config.py`](config.py#L1) to understand required environment settings.
2. Build the backend with `uv build`.
3. Build the frontend under `ui/` with `npm run build`.
4. Start the UI with `npm start`.
5. Explore the chat gateway in [`gateway/main.py`](gateway/main.py#L1) and the agent factories in [`agents/__init__.py`](agents/__init__.py#L1).

> **Sources:** `pyproject.toml` · `ui/package.json` · `config.py` · `setup_wizard.py` · `scripts/deploy.py` · `gateway/main.py` · `agents/__init__.py`

## Repository Map

```text
.
├── agents/
├── connectors/
├── docs/
├── eval/
├── gateway/
├── governance/
├── infra/
├── memory/
├── models/
├── registry/
├── scripts/
├── skills/
├── tests/
├── tools/
└── ui/
```

A few notable top-level files also shape the project experience:

- `setup_wizard.py` and `teardown_wizard.py` for environment lifecycle management
- `agents.yaml` for declarative agent registration
- `Dockerfile.gateway` for gateway containerization
- `infra/` for deployment manifests and scripts
- `docs/` for deeper architecture and API references

> **Sources:** `setup_wizard.py` · `teardown_wizard.py` · `agents.yaml` · `Dockerfile.gateway` · `infra/clouddeploy.yaml` · `docs/ARCHITECTURE.md` · `docs/API.md`

## Architecture at a Glance

At a high level, the codebase separates concerns into agent construction, runtime gateway/API handling, external connectors and tools, memory and governance, and deployment orchestration. The most useful next read is [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), which should be treated as the primary architecture entry point for understanding how the agent factories, gateway endpoints, memory systems, and deployment tooling fit together. For API-level details, see [`docs/API.md`](docs/API.md). This landing page intentionally avoids module internals so you can orient quickly before diving into those deeper architecture pages.

> **Sources:** `docs/ARCHITECTURE.md` · `docs/API.md`