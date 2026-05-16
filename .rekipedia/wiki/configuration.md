---
slug: configuration
title: "Repository Configuration Surfaces"
section: getting-started
tags: [configuration, getting-started]
pin: false
importance: 68
created_at: 2026-05-16T04:11:26Z
rekipedia_version: 0.15.1
---

# Repository Configuration Surfaces

This page documents the repository’s configuration surfaces that affect local development and runtime behavior: environment files, Python/TOML/INI/YAML/JSON config artifacts, and the main application runtime settings. It focuses on what is actually present in the repository rather than generic installation steps.

## Configuration Overview

The repository has a small number of central configuration entry points, but they fan out into several subsystems:

- [`Settings`](config.py#L7) in `config.py` is the main runtime configuration object for the Python services.
- [`agents.yaml`](agents.yaml) defines declarative agent registrations that are loaded by [`load_agents_yaml`](agents/loader.py#L147) and materialized by [`build_agents_from_yaml`](agents/loader.py#L147).
- [`governance/policies.yaml`](governance/policies.yaml) drives policy rules used by [`PolicyEngine`](governance/policy_engine.py#L54).
- [`eval/evalsets/*.json`](eval/evalsets/analytics.evalset.json) provide evaluation inputs for the CLI evaluation runner.
- [`ui/.env.local.example`](ui/.env.local.example) and [`.env.example`](.env.example) are the primary environment templates.
- `pyproject.toml` and `pytest.ini` provide packaging, tooling, and test-runner settings.

The main runtime apps are the gateway service in [`gateway/main.py`](gateway/main.py#L1) and the connector integrations in `connectors/`, which consume values from [`get_settings`](config.py#L163) and the individual configuration files above.

## Configuration File Inventory

| Config file type | Location pattern | Purpose | Notable fields / usage |
|---|---|---|---|
| Environment template | `.env.example` | Root-level template for service/runtime secrets and deployment defaults | Used as a reference for values consumed by [`Settings`](config.py#L7), agent loading, gateway auth, and connector clients |
| Environment template | `ui/.env.local.example` | Frontend runtime environment for the Next.js app | Frontend API/auth endpoints and browser-side runtime variables |
| YAML | `agents.yaml` | Declarative agent catalog for dynamic agent registration | Agent names, builder selection, tools, and environment-variable substitution handled by [`_resolve_env_vars`](agents/loader.py#L125) |
| YAML | `governance/policies.yaml` | Policy rules for content and safety checks | Rule scope, match patterns, and action/response behavior used by [`_load_rules`](governance/policy_engine.py#L93) |
| JSON | `eval/evalsets/*.evalset.json` | Evaluation datasets for offline/CLI evaluation | Scenarios and expected behavior consumed by [`eval.run_eval`](eval/run_eval.py#L16) |
| TOML | `pyproject.toml` | Project metadata, packaging, tool configuration | Build metadata, dependencies, formatting/linting config, Python version constraints |
| INI | `pytest.ini` | Pytest configuration | Test discovery, markers, and default pytest options |
| Markdown / doc templates | `AGENTS.md`, `CLAUDE.md`, `skills/TEMPLATE.md` | Human-readable developer/agent guidance | Operational conventions and template content, not runtime config |

> **Sources:** `.env.example`; `ui/.env.local.example`; `agents.yaml`; `governance/policies.yaml`; `eval/evalsets/analytics.evalset.json`; `pyproject.toml`; `pytest.ini`; `config.py` · L7–L164 · [`Settings`](config.py#L7) · [`get_settings`](config.py#L163) · [`load_agents_yaml`](agents/loader.py#L147) · [`build_agents_from_yaml`](agents/loader.py#L147) · [`_resolve_env_vars`](agents/loader.py#L125) · [`PolicyEngine`](governance/policy_engine.py#L54) · [`_load_rules`](governance/policy_engine.py#L93)

## Runtime Settings in `config.py`

The runtime configuration surface is centered on the [`Settings`](config.py#L7) class. It is the place where the main apps consolidate service-level defaults and environment-driven values. The analysis data shows two helper methods that are important operationally:

- [`Settings.cors_origins_list`](config.py#L139) converts a CORS origins setting into a list.
- [`Settings.inject_litellm_env`](config.py#L142) maps settings into LiteLLM-compatible environment variables.

This tells us the service is not just reading environment variables directly in every module; instead, the application prefers a single settings object, then selectively derives runtime-ready values from it. The `gateway/main.py` app imports [`get_settings`](config.py#L163) and uses it during startup/lifespan and request handling, so `config.py` is the canonical place to look for service behavior overrides.

### What the gateway consumes

The gateway surface in [`gateway/main.py`](gateway/main.py#L1) uses settings to support:

- auth and request handling
- SSE/chat behavior
- task management
- memory/profile operations
- optional observability setup

Even where the code is not directly showing every individual setting field in the analysis data, the structure makes clear that runtime behavior is driven through `Settings` rather than ad hoc constants.

### Config-related helper behavior

The repository also has setup/teardown wizards that read and write environment files:

- [`write_env`](setup_wizard.py#L98) writes a populated environment file.
- [`read_env_value`](setup_wizard.py#L110) and [`read_env`](teardown_wizard.py#L83) parse environment values.
- [`wipe_env_file`](teardown_wizard.py#L323) clears the environment file during teardown.

These utilities are important because they define the lifecycle of local config artifacts: bootstrap creates or updates env state; teardown removes it.

> **Sources:** `config.py` · L7–L164 · [`Settings`](config.py#L7) · [`Settings.cors_origins_list`](config.py#L139) · [`Settings.inject_litellm_env`](config.py#L142) · [`get_settings`](config.py#L163); `gateway/main.py` · L1–L489 · [`lifespan`](gateway/main.py#L63) · [`chat`](gateway/main.py#L152); `setup_wizard.py` · L98–L117 · [`write_env`](setup_wizard.py#L98) · [`read_env_value`](setup_wizard.py#L110); `teardown_wizard.py` · L83–L93 · [`read_env`](teardown_wizard.py#L83) · [`wipe_env_file`](teardown_wizard.py#L323)

## Agent Loading and YAML Configuration

The primary declarative agent configuration is [`agents.yaml`](agents.yaml). It is consumed by [`load_agents_yaml`](scripts/register_agents.py#L23) and then passed to [`build_agents_from_yaml`](agents/loader.py#L147), which performs the actual translation into runtime agent objects.

The loader has three especially relevant helpers:

- [`_tool_factories`](agents/loader.py#L47) maps tool names to implementations.
- [`_custom_builders`](agents/loader.py#L107) maps recognized agent names to bespoke builders.
- [`_resolve_env_vars`](agents/loader.py#L125) substitutes environment-variable references inside YAML values.

This means `agents.yaml` can be more dynamic than a plain static manifest. It is not just a list of names; it can reference env values, declare tools, and select custom or generic builders.

### How environment variables affect agent loading

The tests confirm that env substitution is intentional and supported:

- `TestLoadAgentsYaml.test_resolves_env_var_with_default`
- `TestLoadAgentsYaml.test_resolves_env_var_from_environment`

Those tests correspond to the behavior of [`_resolve_env_vars`](agents/loader.py#L125) and show that agent configuration can change based on runtime environment without code changes.

### Practical effect

If an agent entry in `agents.yaml` is malformed, missing a name, or requests an unknown tool, the loader is designed to skip or warn rather than fail hard in many cases. That makes agent loading a configuration-tolerant surface, useful for gradual rollout and local overrides.

> **Sources:** `agents.yaml`; `scripts/register_agents.py` · L23–L29 · [`load_agents_yaml`](scripts/register_agents.py#L23); `agents/loader.py` · L47–L203 · [`_tool_factories`](agents/loader.py#L47) · [`_custom_builders`](agents/loader.py#L107) · [`_resolve_env_vars`](agents/loader.py#L125) · [`build_agents_from_yaml`](agents/loader.py#L147); `tests/agents/test_agent_loader.py` · L116–L198

## Gateway Authentication and Connector Runtime Settings

The gateway is the main runtime app, and its configuration surface is broader than a simple web server. Authentication, streaming, observability, and task execution all depend on settings and external service configuration.

### Gateway auth

Auth is handled by [`verify_google_token`](gateway/auth.py#L42), which verifies Google-issued tokens for the gateway. This is a runtime setting surface because token verification depends on environment-provided credentials and client configuration, even though the analysis data does not expose every exact variable name. The gateway’s FastAPI app in [`gateway/main.py`](gateway/main.py#L1) relies on this verification path for protected endpoints.

### Connector settings

Connector modules also consume environment-backed configuration:

- Slack webhook handling in [`slack_webhook`](connectors/slack.py#L68) includes request-signature verification via [`_verify_slack_signature`](connectors/slack.py#L44).
- Teams webhook handling in [`teams_webhook`](connectors/teams.py#L93) validates incoming tokens through [`_verify_teams_token`](connectors/teams.py#L66) and uses JWKS fetching in [`_get_jwks`](connectors/teams.py#L50).
- Telegram integration in [`telegram_webhook`](connectors/telegram.py#L61) uses message-sending helpers such as [`_send_message`](connectors/telegram.py#L40).
- The MCP connector surface in [`get_configured_mcp_tools`](tools/mcp_connector.py#L96) is explicitly configuration-driven and loads toolsets based on environment/runtime configuration.

These are the settings surfaces most likely to vary between local dev and deployment.

### Environment variables and connector behavior

In practice, environment variables influence:

- whether agent definitions expand to different tools or endpoints
- whether gateway auth is enabled and validates Google tokens
- which connector webhooks/signature validators are active
- which external services are available to tools such as BigQuery, Drive, Gmail, Storage, and Scheduler

> **Sources:** `gateway/auth.py` · L42–L110 · [`verify_google_token`](gateway/auth.py#L42); `gateway/main.py` · L63–L489 · [`lifespan`](gateway/main.py#L63); `connectors/slack.py` · L44–L143 · [`_verify_slack_signature`](connectors/slack.py#L44) · [`slack_webhook`](connectors/slack.py#L68); `connectors/teams.py` · L50–L185 · [`_get_jwks`](connectors/teams.py#L50) · [`_verify_teams_token`](connectors/teams.py#L66) · [`teams_webhook`](connectors/teams.py#L93); `connectors/telegram.py` · L40–L100 · [`_send_message`](connectors/telegram.py#L40) · [`telegram_webhook`](connectors/telegram.py#L61); `tools/mcp_connector.py` · L96–L123 · [`get_configured_mcp_tools`](tools/mcp_connector.py#L96)

## YAML, JSON, TOML, and INI Artifacts

### YAML artifacts

The repository uses YAML primarily for operational manifests and policy rules:

- [`agents.yaml`](agents.yaml) defines agents and their toolkits.
- [`governance/policies.yaml`](governance/policies.yaml) defines policy checks.
- `infra/clouddeploy.yaml` is a deployment artifact, but because this page excludes CI-only config and installation details, it is best treated as deployment infrastructure rather than a core runtime surface.

### JSON artifacts

The JSON config artifacts are evaluation fixtures, not production runtime settings:

- `eval/evalsets/analytics.evalset.json`
- `eval/evalsets/hr.evalset.json`
- `eval/evalsets/it_helpdesk.evalset.json`

They feed the evaluation runner in [`eval/run_eval.py`](eval/run_eval.py#L16). These files are useful for regression testing and behavior validation but should not be confused with production configuration.

### TOML and INI

- `pyproject.toml` controls package metadata and toolchain configuration.
- `pytest.ini` controls test discovery and execution defaults.

These files matter for contributors, but they do not usually affect live app behavior beyond build-time and test-time interpretation.

> **Sources:** `agents.yaml`; `governance/policies.yaml`; `eval/evalsets/analytics.evalset.json`; `eval/evalsets/hr.evalset.json`; `eval/evalsets/it_helpdesk.evalset.json`; `eval/run_eval.py` · L16–L22 · [`parse_args`](eval/run_eval.py#L16); `pyproject.toml`; `pytest.ini`

## Environment Variables: Agent Loading, Gateway Auth, and Connectors

The repository’s environment-variable strategy is centered on template-driven deployment and runtime substitution.

### Agent loading

Agent YAML values can be parameterized, with [`_resolve_env_vars`](agents/loader.py#L125) resolving references at load time. This is what allows `agents.yaml` entries to vary by environment without editing the file itself.

### Gateway auth

The gateway auth surface uses Google token verification in [`verify_google_token`](gateway/auth.py#L42). In practice, authentication behavior will depend on runtime environment values for credentials, audience, and related identity configuration.

### Connectors

Connector modules use environment settings to connect to third-party APIs and verify inbound requests:

- Slack: signature validation and client initialization in [`_get_slack_client`](connectors/slack.py#L40)
- Teams: token verification and JWKS retrieval in [`_verify_teams_token`](connectors/teams.py#L66) and [`_get_jwks`](connectors/teams.py#L50)
- Telegram: bot messaging path in [`_send_message`](connectors/telegram.py#L40)
- MCP: connector tool selection in [`get_configured_mcp_tools`](tools/mcp_connector.py#L96)

If you change environment variables, the most visible effects will typically be:
1. different agents being loaded or parameterized
2. auth succeeding or failing at the gateway edge
3. connectors enabling/disabling integrations or failing to authenticate

> **Sources:** `agents/loader.py` · L125–L130 · [`_resolve_env_vars`](agents/loader.py#L125); `gateway/auth.py` · L42–L110 · [`verify_google_token`](gateway/auth.py#L42); `connectors/slack.py` · L40–L143 · [`_get_slack_client`](connectors/slack.py#L40); `connectors/teams.py` · L50–L185 · [`_get_jwks`](connectors/teams.py#L50) · [`_verify_teams_token`](connectors/teams.py#L66); `connectors/telegram.py` · L40–L100 · [`_send_message`](connectors/telegram.py#L40); `tools/mcp_connector.py` · L96–L123 · [`get_configured_mcp_tools`](tools/mcp_connector.py#L96)

## Notable Runtime Settings by Main App

| App / module | Configuration source | What it controls |
|---|---|---|
| [`gateway/main.py`](gateway/main.py#L1) | [`get_settings`](config.py#L163) and auth helpers | Gateway startup, chat behavior, session/memory APIs, task handling, observability setup |
| [`connectors/*`](connectors/slack.py#L1) | Environment and request metadata | Webhook verification, reply routing, connector-specific credentials |
| [`agents/loader.py`](agents/loader.py#L1) | `agents.yaml` + environment variables | Which agents exist, which tools they get, and whether custom builders are used |
| [`governance/policy_engine.py`](governance/policy_engine.py#L1) | `governance/policies.yaml` | Which policy rules are active and how responses/prompts are evaluated |
| [`eval/run_eval.py`](eval/run_eval.py#L1) | JSON eval sets | Which scenarios are run in offline evaluation |

> **Sources:** `gateway/main.py` · L1–L489; `connectors/slack.py` · L1–L143; `agents/loader.py` · L1–L203; `governance/policy_engine.py` · L1–L119; `eval/run_eval.py` · L1–L22

## Summary

The configuration model is intentionally layered:

- **Environment templates** define deployment-time variables.
- **YAML manifests** define operational behavior for agents and governance.
- **JSON eval sets** define test scenarios.
- **TOML/INI** define packaging and test tooling.
- **`config.py`** centralizes runtime settings for the main services.

For day-to-day usage, the most important files are `.env.example`, `ui/.env.local.example`, `agents.yaml`, `governance/policies.yaml`, and `config.py`. Those are the artifacts that most directly shape how the gateway, agents, and connectors behave at runtime.

> **Sources:** `.env.example`; `ui/.env.local.example`; `agents.yaml`; `governance/policies.yaml`; `config.py` · L7–L164