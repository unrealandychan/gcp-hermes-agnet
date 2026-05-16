"""
scripts/setup_rag.py

One-time setup script: creates the RAG corpora needed by Hermes.

  1. hermes-knowledge-corpus  — enterprise documents (runbooks, policies, schemas)
  2. hermes-skills-corpus     — self-generated agent skills
  3. hermes-memory-bank       — per-user long-term memory (MemoryBankService)

Usage:
    python scripts/setup_rag.py                         # uses GCP_LOCATION from .env
    python scripts/setup_rag.py --region us-central1  # override region

Outputs the corpus resource names — add them to your .env file.

IMPORTANT: Run this in the SAME region as your Reasoning Engine.
Cross-region RAG calls will fail with PermissionDenied.
"""
from __future__ import annotations

import argparse
import logging

import vertexai
from vertexai.preview import rag

from config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "publishers/google/models/text-embedding-004"


def _ensure_serverless_mode(project_id: str, region: str) -> None:
    """Switch RAG Engine to Serverless mode (required for new projects in us-central1)."""
    try:
        rag_engine_config_name = f"projects/{project_id}/locations/{region}/ragEngineConfig"
        new_config = rag.RagEngineConfig(
            name=rag_engine_config_name,
            rag_managed_db_config=rag.RagManagedDbConfig(mode=rag.Serverless()),
        )
        rag.rag_data.update_rag_engine_config(rag_engine_config=new_config)
        logger.info("RAG Engine switched to Serverless mode.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not switch RAG Engine to Serverless mode: %s", exc)


def create_corpus(display_name: str, description: str) -> str:
    """Create a RAG corpus and return its resource name."""
    embedding_config = rag.EmbeddingModelConfig(
        publisher_model=_EMBEDDING_MODEL,
    )
    corpus = rag.create_corpus(
        display_name=display_name,
        description=description,
        embedding_model_config=embedding_config,
    )
    logger.info("Created corpus: %s  →  %s", display_name, corpus.name)
    return corpus.name


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Hermes RAG corpora")
    parser.add_argument(
        "--region",
        default=None,
        help="GCP region (overrides GCP_LOCATION in .env). "
             "Must match your Reasoning Engine region.",
    )
    args = parser.parse_args()

    settings = get_settings()
    region = args.region or settings.gcp_location

    logger.info("Creating RAG corpora in region: %s", region)
    vertexai.init(project=settings.gcp_project_id, location=region)

    # Switch to Serverless mode first (required for new projects in us-central1)
    _ensure_serverless_mode(settings.gcp_project_id, region)

    knowledge_name = create_corpus(
        display_name="hermes-knowledge-corpus",
        description="Enterprise knowledge base: runbooks, policies, schemas, documentation.",
    )
    skills_name = create_corpus(
        display_name="hermes-skills-corpus",
        description="Self-generated agent skills and learned procedures.",
    )
    memory_name = create_corpus(
        display_name="hermes-memory-bank",
        description="Per-user long-term memory for Hermes MemoryBankService.",
    )

    print("\n── Add these to your .env file ──────────────────────────────")
    print(f"GCP_LOCATION={region}")
    print(f"KNOWLEDGE_CORPUS_NAME={knowledge_name}")
    print(f"SKILLS_CORPUS_NAME={skills_name}")
    print(f"MEMORY_BANK_RESOURCE_NAME={memory_name}")
    print("─────────────────────────────────────────────────────────────")
    print("\n⚠️  After updating .env, redeploy the Reasoning Engine:")
    print("   python scripts/deploy.py --update <REASONING_ENGINE_RESOURCE_NAME>\n")


if __name__ == "__main__":
    main()
