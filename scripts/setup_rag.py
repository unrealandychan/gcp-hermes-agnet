"""
scripts/setup_rag.py

One-time setup script: creates the two RAG corpora needed by Hermes.

  1. hermes-knowledge-corpus  — enterprise documents (runbooks, policies, schemas)
  2. hermes-skills-corpus     — self-generated agent skills

Usage:
    python scripts/setup_rag.py

Outputs the corpus resource names — add them to your .env file.
"""
from __future__ import annotations

import logging

import vertexai
from vertexai.preview import rag

from config import get_settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_EMBEDDING_MODEL = "publishers/google/models/text-embedding-004"


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
    settings = get_settings()
    vertexai.init(project=settings.gcp_project_id, location=settings.gcp_location)

    knowledge_name = create_corpus(
        display_name="hermes-knowledge-corpus",
        description="Enterprise knowledge base: runbooks, policies, schemas, documentation.",
    )
    skills_name = create_corpus(
        display_name="hermes-skills-corpus",
        description="Self-generated agent skills and learned procedures.",
    )

    print("\n── Add these to your .env file ──────────────────────────────")
    print(f"KNOWLEDGE_CORPUS_NAME={knowledge_name}")
    print(f"SKILLS_CORPUS_NAME={skills_name}")
    print("─────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
