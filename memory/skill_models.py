"""
memory/skill_models.py

Pydantic models for a learned skill stored in the RAG skills corpus.
A skill is a structured procedure extracted from a successful agent interaction.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class Skill(BaseModel):
    """A single versioned, agent-generated skill."""

    skill_id: str = Field(description="Unique identifier: <agent_name>_<slug>")
    agent_name: str = Field(description="Name of the agent that generated this skill.")
    domain: str = Field(description="Short domain tag, e.g. 'analytics', 'it', 'hr'.")
    trigger: str = Field(
        description="Natural language description of when to apply this skill."
    )
    procedure: list[str] = Field(
        description="Ordered list of steps to execute this skill."
    )
    example_query: str = Field(description="Example user query that matches this skill.")
    version: int = Field(default=1, description="Monotonically increasing version number.")
    is_current: bool = Field(default=True, description="False for archived versions.")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_rag_text(self) -> str:
        """Serialise to text suitable for RAG corpus ingestion."""
        return (
            f"SKILL: {self.skill_id} (v{self.version})\n"
            f"AGENT: {self.agent_name}\n"
            f"DOMAIN: {self.domain}\n"
            f"TRIGGER: {self.trigger}\n"
            f"EXAMPLE: {self.example_query}\n"
            f"PROCEDURE:\n"
            + "\n".join(f"  {i+1}. {step}" for i, step in enumerate(self.procedure))
            + f"\nCREATED: {self.created_at}\n"
            f"IS_CURRENT: {self.is_current}\n"
        )

    def to_metadata(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "agent_name": self.agent_name,
            "domain": self.domain,
            "version": str(self.version),
            "is_current": str(self.is_current),
            "created_at": self.created_at,
        }

    @classmethod
    def from_json(cls, raw: str) -> "Skill":
        data = json.loads(raw)
        return cls(**data)
