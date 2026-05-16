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

from agents import build_adk_app
from config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy Hermes to Agent Runtime.")
    parser.add_argument("--update", metavar="RESOURCE_NAME", help="Update existing engine.")
    args = parser.parse_args()

    settings = get_settings()
    vertexai.init(
        project=settings.gcp_project_id,
        location=settings.gcp_location,
        staging_bucket=settings.gcp_staging_bucket,
    )

    adk_app = build_adk_app()

    # Wrap the ADK app in agent_engines.AdkApp (required since google-adk >= 1.x)
    wrapped_app = agent_engines.AdkApp(
        agent=adk_app,
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
