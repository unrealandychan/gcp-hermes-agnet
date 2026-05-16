"""
scripts/deploy.py

Deploy the Hermes agent graph to Vertex AI Agent Runtime (Reasoning Engine).

Usage:
    python scripts/deploy.py [--update <resource_name>]

Options:
    --update  Resource name of an existing Reasoning Engine to update.
              If omitted, creates a new engine.

After deploy, the REASONING_ENGINE_RESOURCE_NAME is printed.
Add it to your .env file.
"""
from __future__ import annotations

import argparse
import logging

import vertexai
from vertexai import agent_engines

from agents import build_agent, build_adk_app
from config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _ensure_bucket(bucket: str, project: str, location: str) -> None:
    """Create the GCS staging bucket if it does not exist."""
    from google.cloud import storage
    from google.api_core.exceptions import Conflict

    bucket_name = bucket.removeprefix("gs://")
    client = storage.Client(project=project)
    try:
        client.get_bucket(bucket_name)
        logger.info("Staging bucket already exists: %s", bucket)
    except Exception:
        logger.info("Creating staging bucket %s in %s …", bucket, location)
        try:
            new_bucket = client.bucket(bucket_name)
            new_bucket.storage_class = "STANDARD"
            client.create_bucket(new_bucket, location=location, project=project)
            logger.info("Staging bucket created: %s", bucket)
        except Conflict:
            logger.info("Staging bucket already exists (race): %s", bucket)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy Hermes to Agent Runtime.")
    parser.add_argument("--update", metavar="RESOURCE_NAME", help="Update existing engine.")
    args = parser.parse_args()

    settings = get_settings()

    # Ensure staging bucket exists before vertexai.init — SDK auto-creates
    # in wrong project if bucket is missing, causing 404 NotFound.
    _ensure_bucket(
        settings.gcp_staging_bucket,
        settings.gcp_project_id,
        settings.gcp_location,
    )

    vertexai.init(
        project=settings.gcp_project_id,
        location=settings.gcp_location,
        staging_bucket=settings.gcp_staging_bucket,
    )

    # build_agent() returns the raw ADK BaseAgent (orchestrator).
    # agent_engines.AdkApp wraps it exactly once — the deploy-time wrapper.
    # Do NOT use build_adk_app() here; that returns AdkApp already and
    # passing AdkApp(agent=AdkApp(...)) causes Pydantic ValidationError at runtime.
    raw_agent = build_agent()

    wrapped_app = agent_engines.AdkApp(
        agent=raw_agent,
        enable_tracing=True,
    )

    requirements = [
        "google-cloud-aiplatform[agent_engines,adk]>=1.112",
        "google-cloud-bigquery>=3.25.0",
        "google-cloud-storage>=2.18.0",
        "fastapi>=0.115.0",
        "pydantic>=2.7.0",
        "pydantic-settings>=2.3.0",
        "httpx>=0.27.0",
        "tenacity>=8.3.0",
    ]

    # All local packages that must be shipped to the Reasoning Engine container.
    # Vertex AI cloudpickles the agent, so every imported local module must be
    # present at runtime — include every top-level package directory.
    extra_packages = [
        "./agents",
        "./memory",
        "./tools",
        "./governance",
        "./registry",
        "./eval",
        "./connectors",
        "./gateway",
        "./models",
        "./skills",
        "./config.py",
        "./agents.yaml",
    ]

    deploy_config = {
        "display_name": "Hermes Enterprise Agent",
        "description": "Multi-domain enterprise agent with self-learning capabilities.",
        # Pass env vars into the Reasoning Engine snapshot so it can find
        # the correct RAG corpora at runtime (without these, it falls back
        # to us-central1 defaults and raises PermissionDenied).
        "env_vars": {
            "GCP_PROJECT_ID":           settings.gcp_project_id,
            "GCP_LOCATION":             settings.gcp_location,
            "KNOWLEDGE_CORPUS_NAME":    settings.knowledge_corpus_name,
            "SKILLS_CORPUS_NAME":       settings.skills_corpus_name,
            "MEMORY_BANK_RESOURCE_NAME": settings.memory_bank_resource_name,
        },
    }

    if args.update:
        logger.info("Updating existing engine: %s", args.update)
        engine = agent_engines.update(
            resource_name=args.update,
            agent_engine=wrapped_app,
            requirements=requirements,
            extra_packages=extra_packages,
            **deploy_config,
        )
        resource_name = engine.resource_name
    else:
        logger.info("Creating new Reasoning Engine in project=%s location=%s …",
                    settings.gcp_project_id, settings.gcp_location)
        engine = agent_engines.create(
            agent_engine=wrapped_app,
            requirements=requirements,
            extra_packages=extra_packages,
            **deploy_config,
        )
        resource_name = engine.resource_name

    logger.info("✓ Deploy complete.")
    logger.info("REASONING_ENGINE_RESOURCE_NAME=%s", resource_name)
    logger.info("Add this to your .env file.")


if __name__ == "__main__":
    main()
