"""
memory/memcell_models.py

Pydantic models for EverOS-inspired structured memory cells.

A MemCell is the atomic unit of long-term memory, inspired by the biological
"engram" lifecycle from EverOS/EverCore. Each cell captures four components:

    E (Episode)   — 3rd-person narrative summary with coreferences resolved
    F (Facts)     — atomic, verifiable statements optimised for precise retrieval
    P (Foresight) — forward-looking inferences with explicit validity intervals
    M (Metadata)  — timestamps, agent name, memory type, user id

References:
    EverOS/EverCore: https://github.com/EverMind-AI/EverOS
    Paper: https://arxiv.org/abs/2601.02163
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """Taxonomy of memory types — richer than a flat blob."""
    SKILL = "skill"
    PREFERENCE = "preference"
    RELATIONSHIP = "relationship"
    KNOWLEDGE = "knowledge"
    TASK_PATTERN = "task_pattern"
    CORE = "core"


class Foresight(BaseModel):
    """
    A forward-looking inference with an optional expiry date.

    EverOS innovation: time-bounded predictions are automatically filtered
    at retrieval time — passive memory decay without destructive deletion.

    Examples:
        {"inference": "User is preparing for a job interview next week",
         "valid_until": "2026-06-07"}
        {"inference": "User prefers concise responses in technical tasks",
         "valid_until": null}   # permanent preference
    """
    inference: str = Field(description="The forward-looking inference or prediction.")
    valid_until: Optional[str] = Field(
        default=None,
        description=(
            "ISO date string (YYYY-MM-DD) after which this inference is stale. "
            "Null means no expiry (permanent fact/preference)."
        ),
    )

    def is_valid(self, as_of: Optional[date] = None) -> bool:
        """Return True if this foresight is still valid as of the given date (default: today)."""
        if self.valid_until is None:
            return True
        check_date = as_of or date.today()
        try:
            expiry = date.fromisoformat(self.valid_until)
            return check_date <= expiry
        except ValueError:
            # Malformed date — keep the inference rather than silently drop it
            return True


class MemCell(BaseModel):
    """
    A single structured memory cell — the atomic unit of long-term memory.

    Fields map to the EverOS MemCell schema:
        E → episode
        F → facts
        P → foresight
        M → (metadata: memcell_id, agent_name, memory_type, user_id, created_at)
    """

    memcell_id: str = Field(description="Unique identifier: <agent>_<timestamp_ms>")
    agent_name: str = Field(description="Name of the agent that generated this cell.")
    user_id: str = Field(description="User this memory belongs to.")
    memory_type: MemoryType = Field(
        default=MemoryType.KNOWLEDGE,
        description="Semantic category of this memory.",
    )

    # E — Episode
    episode: str = Field(
        description=(
            "3rd-person narrative summary of the interaction. "
            "All pronouns resolved; captures the semantic core."
        )
    )

    # F — Atomic Facts
    facts: list[str] = Field(
        default_factory=list,
        description="Discrete, verifiable statements optimised for BM25/vector retrieval.",
    )

    # P — Foresight
    foresight: list[Foresight] = Field(
        default_factory=list,
        description="Forward-looking inferences with optional expiry dates.",
    )

    # M — Metadata
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def active_foresight(self, as_of: Optional[date] = None) -> list[Foresight]:
        """Return only foresight items that are still valid today (or as_of date)."""
        return [f for f in self.foresight if f.is_valid(as_of)]

    def to_prompt_text(self, as_of: Optional[date] = None) -> str:
        """
        Format this MemCell for injection into a system prompt.

        Expired foresight is silently filtered — passive memory decay.
        """
        lines: list[str] = [f"[Memory — {self.memory_type.value}]"]
        lines.append(f"Summary: {self.episode}")

        if self.facts:
            lines.append("Facts:")
            for fact in self.facts:
                lines.append(f"  • {fact}")

        active = self.active_foresight(as_of)
        if active:
            lines.append("Context:")
            for f in active:
                expiry = f" (until {f.valid_until})" if f.valid_until else ""
                lines.append(f"  → {f.inference}{expiry}")

        return "\n".join(lines)

    def to_firestore_dict(self) -> dict:
        """Serialise for Firestore storage."""
        return {
            "memcell_id": self.memcell_id,
            "agent_name": self.agent_name,
            "user_id": self.user_id,
            "memory_type": self.memory_type.value,
            "episode": self.episode,
            "facts": self.facts,
            "foresight": [f.model_dump() for f in self.foresight],
            "created_at": self.created_at,
        }

    @classmethod
    def from_firestore_dict(cls, data: dict) -> "MemCell":
        """Deserialise from a Firestore document dict."""
        data = dict(data)
        if "foresight" in data and isinstance(data["foresight"], list):
            data["foresight"] = [Foresight(**f) for f in data["foresight"]]
        return cls(**data)
