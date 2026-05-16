---
slug: python-api
title: "Public Python API Reference"
section: api-reference
tags: [api, reference]
pin: false
importance: 70
created_at: 2026-05-16T04:12:22Z
rekipedia_version: 0.15.1
---

# Public Python API Reference

## Overview

This page is a symbol-oriented reference for the public runtime Python APIs exposed by the repository’s implementation modules. It is organized by package and intentionally excludes tests, CI helpers, and configuration-only symbols. The focus is on implementation symbols with `role == impl`, especially the APIs most likely to be imported and called by application code or external integrations.

The main public surfaces covered here include agent builders, gateway authentication and chat endpoints, connector webhooks, evaluation helpers, memory utilities, registry access, model resolution, and tool factories. For a quick orientation:

- **Agents** define the agent graph and builder functions such as [`build_agent`](agents/__init__.py#L11) and [`build_orchestrator`](agents/orchestrator.py#L34).
- **Gateway** exposes request/response models like [`ChatRequest`](gateway/main.py#L136) and [`ChatEvent`](gateway/main.py#L141), plus auth via [`verify_google_token`](gateway/auth.py#L42).
- **Connectors** provide entry points such as [`run_agent`](connectors/runner.py#L34), [`slack_webhook`](connectors/slack.py#L68), [`teams_webhook`](connectors/teams.py#L93), and [`telegram_webhook`](connectors/telegram.py#L61).
- **Eval** includes [`EvalMetrics`](eval/metrics.py#L13), [`score_response`](eval/metrics.py#L23), [`MonitorConfig`](eval/online_monitor.py#L15), and [`log_quality_score`](eval/online_monitor.py#L21).
- **Memory** contains the prompt/context helpers and the [`HermesMemoryBank`](memory/memory_bank.py#L56) facade.
- **Tools** expose concrete integration functions for BigQuery, Drive, Gmail, Scheduler, Storage, and Model Armor.
- **Registry** and **models** provide supporting runtime abstractions for agent registration and model selection.

## Agents Package

The `agents` package exposes the core agent construction APIs used by the gateway, deploy scripts, and YAML-driven agent loading. The most important top-level entry point is [`build_agent`](agents/__init__.py#L11), which returns the raw ADK agent used by the local gateway runner. For runtime deployment, [`build_adk_app`](agents/__init__.py#L17) wraps the full agent graph.

### Public APIs

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`build_agent`](agents/__init__.py#L11) | function | Return the raw ADK Agent used by the local gateway runner. |
| [`build_adk_app`](agents/__init__.py#L17) | function | Return an `AdkApp` wrapping the full agent graph for Agent Runtime deploys. |
| [`build_analytics_agent`](agents/analytics.py#L37) | function | Build the analytics agent from runtime settings. |
| [`build_developer_agent`](agents/developer.py#L54) | function | Build the developer agent from runtime settings. |
| [`build_hr_agent`](agents/hr.py#L42) | function | Build the HR agent from runtime settings. |
| [`build_it_helpdesk_agent`](agents/it_helpdesk.py#L42) | function | Build the IT helpdesk agent from runtime settings. |
| [`build_orchestrator`](agents/orchestrator.py#L34) | function | Build the top-level orchestrator agent from settings. |
| [`finish_task`](agents/task_agent.py#L55) | function | Signal that a long-running task is fully complete. |
| [`build_task_agent`](agents/task_agent.py#L160) | function | Build the long-running task LoopAgent. |
| [`build_agents_from_yaml`](agents/loader.py#L147) | function | Load `agents.yaml` and build all configured sub-agents. |

### Notable Loader Helpers

The agent YAML loader provides the main dynamic composition path for configurable deployments. It resolves environment-variable placeholders with [`_resolve_env_vars`](agents/loader.py#L125), parses YAML with [`load_agents_yaml`](agents/loader.py#L133), and materializes agents through [`build_agents_from_yaml`](agents/loader.py#L147). The lower-level generic builder is [`_build_generic`](agents/loader.py#L181).

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`_tool_factories`](agents/loader.py#L47) | function | Map YAML tool names to concrete tool factory callables. |
| [`_custom_builders`](agents/loader.py#L107) | function | Return the registry of known custom agent builders. |
| [`_resolve_env_vars`](agents/loader.py#L125) | function | Substitute `${VAR:-default}` patterns using environment variables. |
| [`load_agents_yaml`](agents/loader.py#L133) | function | Parse `agents.yaml` and return the list of agent config dicts. |
| [`_build_generic`](agents/loader.py#L181) | function | Build a generic `LlmAgent` from a YAML config dict. |

> **Sources:** `agents/__init__.py` · `agents/analytics.py` · `agents/developer.py` · `agents/hr.py` · `agents/it_helpdesk.py` · `agents/loader.py` · `agents/orchestrator.py` · `agents/task_agent.py`

## Gateway Package

The gateway package is the main HTTP-facing runtime surface. It is centered around authentication, request models, SSE streaming chat, memory/task endpoints, and an optional upstream Agent Gateway client.

### Agent Gateway Client API

The Agent Gateway client is a thin async wrapper that can be disabled gracefully. [`AgentGatewayConfig`](gateway/agent_gateway.py#L30) is the configuration object, while [`AgentGatewayClient`](gateway/agent_gateway.py#L63) provides the runtime methods. When disabled, the client intentionally falls through to direct Runner execution.

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`AgentGatewayConfig`](gateway/agent_gateway.py#L30) | class | Configuration for Agent Gateway routing. |
| [`AgentGatewayClient`](gateway/agent_gateway.py#L63) | class | Async client for sending chat requests via Agent Gateway. |
| [`build_agent_gateway`](gateway/agent_gateway.py#L184) | function | Build an `AgentGatewayClient` from settings. |

Key methods on [`AgentGatewayClient`](gateway/agent_gateway.py#L63):

| Method | Summary |
|---|---|
| [`__init__`](gateway/agent_gateway.py#L71) | Store configuration and initialise client state. |
| [`_ensure_client`](gateway/agent_gateway.py#L75) | Lazily create the underlying HTTP client. |
| [`send_message`](gateway/agent_gateway.py#L94) | Send a message and return the JSON response, or `None` on fallback. |
| [`stream_message`](gateway/agent_gateway.py#L137) | Stream SSE events, falling back to an empty iterator on failure. |
| [`close`](gateway/agent_gateway.py#L175) | Close the underlying HTTP client during shutdown. |

### Authentication and Request Models

[`verify_google_token`](gateway/auth.py#L42) validates Google ID tokens and returns decoded claims. It also supports a `DISABLE_AUTH=true` local-development mode that bypasses validation and returns a synthetic local user.

[`ChatRequest`](gateway/main.py#L136) and [`ChatEvent`](gateway/main.py#L141) define the SSE chat API payloads. The chat route [`chat`](gateway/main.py#L152) emits JSON-encoded `ChatEvent` objects, ending with a `type='done'` event.

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`verify_google_token`](gateway/auth.py#L42) | function | Validate a Google ID token and return the decoded claims. |
| [`ChatRequest`](gateway/main.py#L136) | class | Request body for the streaming chat endpoint. |
| [`ChatEvent`](gateway/main.py#L141) | class | SSE event envelope emitted by the chat endpoint. |
| [`chat`](gateway/main.py#L152) | function | Stream chat responses as Server-Sent Events. |
| [`_stream_agent`](gateway/main.py#L203) | function | Yield SSE-formatted JSON strings for each agent event. |
| [`_sse`](gateway/main.py#L242) | function | Wrap an event object as an SSE payload string. |

### Session, Memory, and Task APIs

The gateway exposes user-scoped memory and task operations via runtime endpoints. These are implemented in `gateway/main.py` and backed by `gateway/tasks.py`.

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`list_sessions`](gateway/main.py#L247) | function | List active sessions for the authenticated user. |
| [`clear_memories`](gateway/main.py#L268) | function | Clear all long-term memories for the authenticated user. |
| [`list_memories`](gateway/main.py#L287) | function | Retrieve long-term memories for the authenticated user. |
| [`create_memory`](gateway/main.py#L314) | function | Directly write a memory fact for the authenticated user. |
| [`CreateMemoryRequest`](gateway/main.py#L309) | class | Request body for creating a memory fact. |
| [`submit_task`](gateway/main.py#L345) | function | Submit a long-running task and return a pending task record. |
| [`get_task`](gateway/main.py#L368) | function | Poll the status of a long-running task. |
| [`cancel_task`](gateway/main.py#L399) | function | Cancel a running task, if present. |
| [`list_my_tasks`](gateway/main.py#L414) | function | List all tasks submitted by the authenticated user. |
| [`TaskRequest`](gateway/main.py#L338) | class | Request body for task submission. |

### Scheduler Trigger API

The gateway also exposes a server-to-server scheduler hook for Cloud Scheduler invocations.

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`SchedulerTriggerRequest`](gateway/main.py#L423) | class | Request body for scheduler-triggered task creation. |
| [`scheduler_trigger`](gateway/main.py#L430) | function | Cloud Scheduler webhook that triggers an agent task. |
| [`_verify_scheduler_oidc_token`](gateway/main.py#L460) | function | Verify the scheduler OIDC token and expected service account. |

### Observability

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`setup_tracing`](gateway/observability.py#L37) | function | Initialise OpenTelemetry with the Google Cloud Trace exporter. |
| [`instrument_fastapi`](gateway/observability.py#L69) | function | Auto-instrument a FastAPI app to emit HTTP spans. |
| [`get_tracer`](gateway/observability.py#L80) | function | Return the active tracer or a no-op stub. |
| [`agent_span`](gateway/observability.py#L86) | function | Context manager for one agent turn span. |

Support classes used when tracing is unavailable:

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`_NoopSpan`](gateway/observability.py#L119) | class | No-op span object used when tracing is disabled. |
| [`_NoopTracer`](gateway/observability.py#L130) | class | No-op tracer used when tracing is disabled. |

> **Sources:** `gateway/agent_gateway.py` · `gateway/auth.py` · `gateway/main.py` · `gateway/observability.py` · `gateway/tasks.py`

## Connectors Package

The connector package contains transport-specific runtime entry points that adapt external platforms to the shared agent runner.

### Shared Runner

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`run_agent`](connectors/runner.py#L34) | function | Run the Hermes agent for a connector message and return the full text reply. |
| [`_platform_session_id`](connectors/runner.py#L28) | function | Build a namespaced session ID from platform and user identifier. |

### Slack

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`slack_webhook`](connectors/slack.py#L68) | function | Receive a Slack Events API payload and respond. |
| [`_get_slack_client`](connectors/slack.py#L40) | function | Lazily create or reuse the Slack client. |
| [`_verify_slack_signature`](connectors/slack.py#L44) | function | Verify Slack’s HMAC-SHA256 request signature. |
| [`_split_text`](connectors/slack.py#L146) | function | Split long messages into platform-sized chunks. |

### Microsoft Teams

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`teams_webhook`](connectors/teams.py#L93) | function | Receive a Bot Framework activity from Microsoft Teams and reply. |
| [`_get_jwks`](connectors/teams.py#L50) | function | Fetch the Teams/JWT signing keys. |
| [`_verify_teams_token`](connectors/teams.py#L66) | function | Verify the Bot Framework JWT. |
| [`_send_teams_reply`](connectors/teams.py#L150) | function | Obtain a Bot Framework access token and post a reply. |

### Telegram

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`telegram_webhook`](connectors/telegram.py#L61) | function | Receive a Telegram Update and reply via the Bot API. |
| [`_send_message`](connectors/telegram.py#L40) | function | Send a text reply to a Telegram chat. |
| [`_split_text`](connectors/telegram.py#L50) | function | Split long messages into Telegram-sized chunks. |

> **Sources:** `connectors/runner.py` · `connectors/slack.py` · `connectors/teams.py` · `connectors/telegram.py`

## Eval Package

The eval package contains offline scoring and online quality logging helpers.

### Offline Metrics

[`EvalMetrics`](eval/metrics.py#L13) is the core result container for score computation. [`score_response`](eval/metrics.py#L23) evaluates a response against expected keywords and context, and is explicitly documented as fully offline.

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`EvalMetrics`](eval/metrics.py#L13) | class | Aggregate response quality metrics. |
| [`score_response`](eval/metrics.py#L23) | function | Score a response against expected keywords, fully offline. |

### Online Monitoring

[`MonitorConfig`](eval/online_monitor.py#L15) stores the configuration used by [`log_quality_score`](eval/online_monitor.py#L21), which writes a quality-score row to BigQuery and fails silently by design.

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`MonitorConfig`](eval/online_monitor.py#L15) | class | Configuration for online quality-score logging. |
| [`log_quality_score`](eval/online_monitor.py#L21) | function | Async BigQuery logger for quality-score rows. |
| [`build_online_monitor`](eval/online_monitor.py#L58) | function | Build a `MonitorConfig` from environment-backed settings. |

### CLI Entry Point

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`parse_args`](eval/run_eval.py#L16) | function | Parse CLI arguments for the evaluation runner. |
| [`main`](eval/run_eval.py#L25) | function | Execute the evaluation CLI. |

> **Sources:** `eval/metrics.py` · `eval/online_monitor.py` · `eval/run_eval.py`

## Memory Package

The memory package exposes user context, cross-corpus retrieval, and the `HermesMemoryBank` abstraction used by the gateway and agents.

### Context Budgeting

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`build_context_summary`](memory/context_budget.py#L37) | function | Build a compact memory summary for system-prompt injection. |
| [`prioritise_memory`](memory/context_budget.py#L94) | function | Trim a list of skills to fit within a token budget. |

### Cross-Corpus Retrieval

[`RetrievedContext`](memory/cross_corpus.py#L21) is the result container for corpus retrieval. Retrieval is implemented by [`retrieve_cross_corpus`](memory/cross_corpus.py#L64), with internal helpers [`_query_corpus`](memory/cross_corpus.py#L27) and [`_deduplicate`](memory/cross_corpus.py#L53).

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`RetrievedContext`](memory/cross_corpus.py#L21) | class | Result item for a retrieved chunk from a corpus. |
| [`retrieve_cross_corpus`](memory/cross_corpus.py#L64) | function | Query multiple corpora, merge, sort, and deduplicate results. |

### Memory Bank Facade

[`HermesMemoryBank`](memory/memory_bank.py#L56) is the application-level facade over `VertexAiMemoryBank`. It provides durable-memory create/read/update/delete flows, prompt formatting, and batched ingestion helpers.

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`HermesMemoryBank`](memory/memory_bank.py#L56) | class | Application-level facade over `VertexAiMemoryBank`. |
| [`build_memory_bank`](memory/memory_bank.py#L413) | function | Build a `HermesMemoryBank` from settings. |
| [`create_memory_bank`](memory/memory_bank.py#L434) | function | Create a new MemoryBank resource or reuse an existing one. |

Key methods on [`HermesMemoryBank`](memory/memory_bank.py#L56):

| Method | Summary |
|---|---|
| [`generate_memories`](memory/memory_bank.py#L80) | Distil a conversation turn into durable memories. |
| [`ingest_events`](memory/memory_bank.py#L119) | Stream conversation events for automatic batched memory generation. |
| [`purge_memories`](memory/memory_bank.py#L166) | Bulk-delete all memories for a user. |
| [`delete_memory`](memory/memory_bank.py#L201) | Delete a specific memory by resource name. |
| [`create_memory`](memory/memory_bank.py#L224) | Directly write a memory fact without LLM extraction. |
| [`update_memory`](memory/memory_bank.py#L258) | Update an existing memory with corrected text. |
| [`retrieve_profiles`](memory/memory_bank.py#L288) | Retrieve structured memory profiles for a user. |
| [`fetch_memories`](memory/memory_bank.py#L321) | Retrieve the most relevant memories for a user. |
| [`list_revisions`](memory/memory_bank.py#L360) | Return revision history for a user’s memories. |
| [`format_for_prompt`](memory/memory_bank.py#L383) | Format relevant memories as a prompt snippet. |

### Skill Learning and Skill Store

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`build_skill_learning_callback`](memory/skill_learning.py#L25) | function | Return an after-agent callback bound to an agent name. |
| [`extract_skill`](memory/skill_extractor.py#L72) | function | Run the extractor agent and parse the result. |
| [`load_skills_from_dir`](memory/skill_loader.py#L42) | function | Scan a directory for skill markdown files and parse them. |
| [`Skill`](memory/skill_models.py#L15) | class | A single versioned, agent-generated skill. |
| [`search_skills`](memory/skill_store.py#L36) | function | Retrieve top-k current skills from the skills corpus. |
| [`upsert_skill`](memory/skill_store.py#L115) | function | Insert a new skill or version a near-duplicate. |
| [`get_or_create_profile`](memory/user_profile.py#L68) | function | Fetch a user profile or create a minimal one if absent. |
| [`update_profile`](memory/user_profile.py#L88) | function | Upsert profile fields for a user. |

> **Sources:** `memory/context_budget.py` · `memory/cross_corpus.py` · `memory/memory_bank.py` · `memory/skill_extractor.py` · `memory/skill_learning.py` · `memory/skill_loader.py` · `memory/skill_models.py` · `memory/skill_store.py` · `memory/user_profile.py`

## Tools Package

The tools package contains the runtime integration points used by agents. Most are module-level helper functions intended for direct agent tool wiring.

### BigQuery

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`make_bigquery_tool`](tools/bigquery_tool.py#L85) | function | Build a BigQuery tool wrapper from settings. |
| [`run_bigquery_query`](tools/bigquery_tool.py#L104) | function | Execute a read-only BigQuery SQL query for direct tool use. |
| [`_run_query`](tools/bigquery_tool.py#L37) | function | Execute the underlying query and shape the result payload. |

### Calendar

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`create_calendar_event`](tools/calendar_tool.py#L56) | function | Create a Google Calendar event and invite attendees. |
| [`list_calendar_events`](tools/calendar_tool.py#L111) | function | List calendar events in a date range. |
| [`check_availability`](tools/calendar_tool.py#L155) | function | Check whether attendees are free during a time slot. |

### Drive

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`search_drive_files`](tools/drive_tool.py#L66) | function | Search for files in Google Drive. |
| [`read_drive_file`](tools/drive_tool.py#L109) | function | Read the text content of a Google Drive file. |
| [`list_drive_folder`](tools/drive_tool.py#L162) | function | List the files inside a Google Drive folder. |

### Gmail

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`send_email`](tools/gmail_tool.py#L67) | function | Send an email on behalf of the configured Workspace admin user. |
| [`search_emails`](tools/gmail_tool.py#L110) | function | Search emails in the Gmail inbox. |
| [`get_email`](tools/gmail_tool.py#L154) | function | Read the full content of a specific email. |

### MCP Connector

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`make_filesystem_mcp_toolset`](tools/mcp_connector.py#L34) | function | Create an MCP toolset backed by the filesystem server. |
| [`make_sse_mcp_toolset`](tools/mcp_connector.py#L64) | function | Create an MCP toolset connected to a remote SSE server. |
| [`get_configured_mcp_tools`](tools/mcp_connector.py#L96) | function | Build all configured MCP toolsets from settings. |

### Model Armor

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`ArmorResult`](tools/model_armor.py#L42) | class | Result wrapper for Model Armor screening operations. |
| [`screen_prompt`](tools/model_armor.py#L122) | function | Screen a user prompt before sending it to the agent. |
| [`screen_response`](tools/model_armor.py#L134) | function | Screen a model response before returning it to the user. |

### Scheduler

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`schedule_agent_task`](tools/scheduler_tool.py#L45) | function | Schedule an agent task to run later or on a recurring schedule. |
| [`delete_scheduled_task`](tools/scheduler_tool.py#L160) | function | Delete a previously scheduled agent task. |
| [`list_scheduled_tasks`](tools/scheduler_tool.py#L193) | function | List agent-created Cloud Scheduler jobs. |

### Knowledge Base Search and Storage

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`make_search_tool`](tools/search_tool.py#L16) | function | Build a knowledge-base search tool from settings. |
| [`search_knowledge_base`](tools/search_tool.py#L61) | function | Direct knowledge-base search for tool use. |
| [`make_storage_tool`](tools/storage_tool.py#L86) | function | Build a GCS storage tool from settings. |
| [`read_gcs_file`](tools/storage_tool.py#L119) | function | Read a file from Google Cloud Storage. |
| [`write_gcs_file`](tools/storage_tool.py#L133) | function | Write a file to Google Cloud Storage. |

> **Sources:** `tools/bigquery_tool.py` · `tools/calendar_tool.py` · `tools/drive_tool.py` · `tools/gmail_tool.py` · `tools/mcp_connector.py` · `tools/model_armor.py` · `tools/scheduler_tool.py` · `tools/search_tool.py` · `tools/storage_tool.py`

## Registry Package

The registry package provides a runtime interface for registering and listing agents in Vertex AI’s registry layer, with fallback behavior when unavailable.

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`AgentRecord`](registry/agent_registry.py#L14) | class | Data container describing a registered agent. |
| [`HermesAgentRegistry`](registry/agent_registry.py#L23) | class | Registry backed by Vertex AI agent registry with graceful fallback. |
| [`build_registry`](registry/agent_registry.py#L84) | function | Build a `HermesAgentRegistry`, or return `None` on unrecoverable failure. |

Key methods on [`HermesAgentRegistry`](registry/agent_registry.py#L23):

| Method | Summary |
|---|---|
| [`register_agent`](registry/agent_registry.py#L64) | Register an agent and return its resource ID. |
| [`list_agents`](registry/agent_registry.py#L70) | Return all registered agents. |
| [`get_agent`](registry/agent_registry.py#L75) | Look up a single agent by name. |

> **Sources:** `registry/agent_registry.py`

## Models Package

The models package contains provider-specific model resolution helpers used by agent construction code.

| Symbol | Kind | One-line summary |
|---|---:|---|
| [`resolve_model_str`](models/provider.py#L66) | function | Normalise the raw model string. |
| [`get_model`](models/provider.py#L75) | function | Return the correct ADK model value for the given model string. |
| [`_is_native_gemini`](models/provider.py#L111) | function | Detect native Gemini / Vertex AI model identifiers. |

`get_model` is the primary runtime API here: native Gemini models are returned as plain strings, while non-Gemini providers are wrapped in `google.adk.models.LiteLlm` so that the surrounding agent builders can remain provider-agnostic.

> **Sources:** `models/provider.py`

## Notes on Scope and Exclusions

This reference intentionally omits:

- test-only symbols
- CI or deployment-script internals not exposed as reusable runtime APIs
- config-only classes such as `Settings`
- narrative architecture descriptions

It includes implementation symbols only, using the symbol index and file/line citations for traceability.

> **Sources:** `config.py` · `setup_wizard.py` · `scripts/*` · `tests/*`