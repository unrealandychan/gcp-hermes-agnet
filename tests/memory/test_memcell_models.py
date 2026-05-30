"""
tests/memory/test_memcell_models.py

Unit tests for MemCell Pydantic models — fully offline, no GCP required.
"""
from __future__ import annotations

from datetime import date

import pytest

from memory.memcell_models import Foresight, MemCell, MemoryType


# ── Foresight tests ────────────────────────────────────────────────────────────

class TestForesight:
    def test_no_expiry_is_always_valid(self):
        f = Foresight(inference="User prefers dark mode", valid_until=None)
        assert f.is_valid() is True
        assert f.is_valid(as_of=date(2030, 1, 1)) is True

    def test_future_expiry_is_valid(self):
        f = Foresight(inference="User has interview", valid_until="2099-12-31")
        assert f.is_valid() is True

    def test_past_expiry_is_invalid(self):
        f = Foresight(inference="User preparing for exam", valid_until="2020-01-01")
        assert f.is_valid() is False

    def test_expiry_on_exact_day_is_valid(self):
        today = date.today().isoformat()
        f = Foresight(inference="Event today", valid_until=today)
        assert f.is_valid() is True

    def test_malformed_date_keeps_inference(self):
        f = Foresight(inference="Something", valid_until="not-a-date")
        assert f.is_valid() is True  # keep rather than silently drop


# ── MemCell tests ──────────────────────────────────────────────────────────────

class TestMemCell:
    def _make_cell(self, **kwargs) -> MemCell:
        defaults = dict(
            memcell_id="hr_agent_123",
            agent_name="HRAgent",
            user_id="user_42",
            memory_type=MemoryType.PREFERENCE,
            episode="The user asked the HR agent about vacation policy.",
            facts=["User is entitled to 20 days annual leave."],
            foresight=[
                Foresight(inference="User is planning a holiday soon", valid_until="2099-12-31"),
                Foresight(inference="User planning Christmas trip", valid_until="2020-12-25"),
            ],
        )
        defaults.update(kwargs)
        return MemCell(**defaults)

    def test_active_foresight_filters_expired(self):
        cell = self._make_cell()
        active = cell.active_foresight()
        assert len(active) == 1
        assert "holiday" in active[0].inference

    def test_to_prompt_text_excludes_expired_foresight(self):
        cell = self._make_cell()
        text = cell.to_prompt_text()
        assert "holiday" in text
        assert "Christmas" not in text  # expired

    def test_to_prompt_text_includes_episode_and_facts(self):
        cell = self._make_cell()
        text = cell.to_prompt_text()
        assert "HR agent" in text
        assert "20 days" in text

    def test_firestore_round_trip(self):
        cell = self._make_cell()
        d = cell.to_firestore_dict()
        restored = MemCell.from_firestore_dict(d)
        assert restored.memcell_id == cell.memcell_id
        assert restored.episode == cell.episode
        assert len(restored.facts) == len(cell.facts)
        assert len(restored.foresight) == len(cell.foresight)

    def test_memory_type_enum(self):
        cell = self._make_cell(memory_type=MemoryType.SKILL)
        assert cell.memory_type == MemoryType.SKILL
        d = cell.to_firestore_dict()
        assert d["memory_type"] == "skill"

    def test_no_foresight_prompt_text(self):
        cell = self._make_cell(foresight=[])
        text = cell.to_prompt_text()
        assert "Context:" not in text
        assert "Summary:" in text
