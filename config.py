"""Shared configuration loaded from environment / .env file."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # GCP Core
    gcp_project_id: str = "hermes-agent-prod"
    gcp_location: str = "us-central1"
    gcp_staging_bucket: str = "gs://hermes-agent-artifacts"

    # Agent Runtime
    reasoning_engine_resource_name: str = ""

    # RAG Corpora
    # IMPORTANT: corpus region MUST match gcp_location.
    # e.g. if gcp_location=us-central1, corpus must be in us-central1.
    # Cross-region RAG calls will fail with PermissionDenied.
    knowledge_corpus_name: str = ""
    skills_corpus_name: str = ""

    # API Gateway
    gateway_port: int = 8080
    cors_origins: str = "http://localhost:3000"

    # Auth
    google_client_id: str = ""
    # Set DISABLE_AUTH=true in .env to skip Google ID-token validation locally.
    # NEVER enable this in production — it opens every endpoint to anonymous access.
    disable_auth: bool = False

    # Tool Service URLs
    bigquery_tool_url: str = "http://localhost:8081"
    storage_tool_url: str = "http://localhost:8082"
    search_tool_url: str = "http://localhost:8083"

    # ── LLM Models ────────────────────────────────────────────────────────────
    # Specify models per agent role.  Use bare Gemini IDs for native Vertex AI,
    # or "<provider>/<model>" for LiteLLM-backed providers (OpenAI, Anthropic,
    # Azure, Bedrock, Ollama, etc.).
    #
    # Examples:
    #   gemini-2.5-flash              → Gemini on Vertex AI (default)
    #   gemini-2.5-flash              → Latest Gemini Flash
    #   gemini-2.5-flash-lite         → Cheapest Gemini (good for background tasks)
    #   openai/gpt-4o                 → OpenAI GPT-4o via LiteLLM
    #   openai/gpt-4o-mini            → Cheaper OpenAI option
    #   anthropic/claude-sonnet-4-5   → Anthropic Claude Sonnet 4.5 via LiteLLM
    #   anthropic/claude-3-5-haiku-20241022 → Cheap Claude option
    #   azure/my-gpt4o-deployment     → Azure OpenAI via LiteLLM
    #   ollama/llama3                 → Local Ollama (dev/testing only)
    agent_model_orchestrator: str = "gemini-2.5-flash"
    agent_model_analytics: str = "gemini-2.5-flash"
    agent_model_it_helpdesk: str = "gemini-2.5-flash"
    agent_model_hr: str = "gemini-2.5-flash"
    agent_model_developer: str = "gemini-2.5-flash"
    agent_model_task_planner: str = "gemini-2.5-flash"
    agent_model_task_executor: str = "gemini-2.5-flash"
    agent_model_aggregator: str = "gemini-2.5-flash"
    # SkillExtractor runs on every turn — use a lightweight model to cut costs
    agent_model_skill_extractor: str = "gemini-2.5-flash-lite"

    # ── LLM Provider API Keys (used by LiteLLM) ───────────────────────────────
    # These are passed to LiteLLM via environment variables automatically.
    # You only need to set the key for the provider(s) you actually use.
    openai_api_key: str = ""          # for openai/* models
    anthropic_api_key: str = ""       # for anthropic/* models
    azure_api_key: str = ""           # for azure/* models
    azure_api_base: str = ""          # Azure endpoint URL
    azure_api_version: str = ""       # e.g. "2024-02-01"
    cohere_api_key: str = ""          # for cohere/* models

    # ── Firestore ─────────────────────────────────────────────────────────────
    # Collection used to persist long-running task state.
    firestore_task_collection: str = "hermes_tasks"

    # ── Cloud Scheduler ───────────────────────────────────────────────────────
    # Public URL of this Cloud Run gateway (used as scheduler callback target).
    # Example: https://hermes-gateway-abc123-uc.a.run.app
    gateway_url: str = ""
    # GCP location for Cloud Scheduler jobs — must match Cloud Run region.
    scheduler_location: str = "us-central1"
    # Service account email used for OIDC token on scheduler → gateway calls.
    # Must be the same SA running the Cloud Run service (or a dedicated one).
    scheduler_service_account: str = ""

    # ── Google Workspace ──────────────────────────────────────────────────────
    # G Suite / Google Workspace primary domain (e.g. "acme.com").
    workspace_domain: str = ""
    # Admin email to impersonate via domain-wide delegation.
    workspace_admin_email: str = ""
    # Local path to the service account JSON key file with domain-wide delegation.
    workspace_credentials_path: str = ""

    # ── Connectors ────────────────────────────────────────────────────────────
    # Telegram
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""  # set when registering the webhook

    # Slack
    slack_bot_token: str = ""          # xoxb-... Bot User OAuth Token
    slack_signing_secret: str = ""     # from Slack App → Basic Information

    # Microsoft Teams
    teams_app_id: str = ""             # Azure Bot registration App ID
    teams_app_password: str = ""       # Azure Bot registration App Password

    # ── Agent Gateway (centralised routing + security) ────────────────────
    agent_gateway_endpoint: str = ""
    agent_gateway_api_key: str = ""
    agent_gateway_timeout_seconds: int = 60
    agent_gateway_model_armor_delegate: bool = True

    # ── Vertex AI Memory Bank (native long-term user memory) ─────────────────
    # Resource name created by setup_wizard.py.
    # Leave blank to disable MemoryBank (graceful degradation — skills RAG still works).
    memory_bank_resource_name: str = ""

    # ── Model Armor ───────────────────────────────────────────────────────────
    # Template ID created in the GCP console or via gcloud.
    # Leave blank to disable prompt/response screening (safe default for dev).
    model_armor_template_id: str = ""

    # ── MCP (Model Context Protocol) ─────────────────────────────────────────
    # Filesystem MCP server: expose a local directory to the agent via MCP.
    mcp_filesystem_path: str = ""
    # Remote SSE MCP server URL (e.g. a custom tool server).
    mcp_sse_server_url: str = ""
    mcp_sse_auth_token: str = ""

    # ── Agent Observability ───────────────────────────────────────────────────
    # Set false to disable Cloud Trace (useful for local dev without GCP creds).
    enable_cloud_trace: bool = True

    # ── Agent Lifecycle Limits ────────────────────────────────────────────────
    # Maximum concurrently *running* synthesised agents per session.
    max_agents_per_session: int = 20
    # Maximum nesting depth for sub-agent delegation chains (root = depth 0).
    max_delegation_depth: int = 5

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def inject_litellm_env(self) -> None:
        """
        Export provider API keys into the process environment so that LiteLLM
        can pick them up automatically.  Call once at application startup.
        """
        import os

        _env_map = {
            "OPENAI_API_KEY": self.openai_api_key,
            "ANTHROPIC_API_KEY": self.anthropic_api_key,
            "AZURE_API_KEY": self.azure_api_key,
            "AZURE_API_BASE": self.azure_api_base,
            "AZURE_API_VERSION": self.azure_api_version,
            "COHERE_API_KEY": self.cohere_api_key,
        }
        for env_var, value in _env_map.items():
            if value and env_var not in os.environ:
                os.environ[env_var] = value


    def validate_rag_regions(self) -> list[str]:
        """
        Check that all configured RAG corpus resource names are in the same
        region as gcp_location.  Returns a list of warning strings (empty = OK).

        Call at startup to catch cross-region mismatches before the first request.
        Example bad config: gcp_location=us-central1 but corpus in us-central1.
        """
        import re
        warnings: list[str] = []
        corpus_fields = {
            "KNOWLEDGE_CORPUS_NAME": self.knowledge_corpus_name,
            "SKILLS_CORPUS_NAME": self.skills_corpus_name,
            "MEMORY_BANK_RESOURCE_NAME": self.memory_bank_resource_name,
        }
        # resource names look like: projects/.../locations/<region>/ragCorpora/...
        _loc_re = re.compile(r"/locations/([^/]+)/")
        for field, resource_name in corpus_fields.items():
            if not resource_name:
                continue
            m = _loc_re.search(resource_name)
            if not m:
                continue
            corpus_region = m.group(1)
            if corpus_region != self.gcp_location:
                warnings.append(
                    f"{field} is in '{corpus_region}' but GCP_LOCATION='{self.gcp_location}'. "
                    f"Cross-region RAG calls will fail with PermissionDenied. "
                    f"Rebuild the corpus in '{self.gcp_location}' or update GCP_LOCATION."
                )
        return warnings


@lru_cache
def get_settings() -> Settings:
    return Settings()
