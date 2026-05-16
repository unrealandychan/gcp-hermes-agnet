"""Offline unit tests for governance/policy_engine.py (Issue #7)."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from governance.policy_engine import (
    PolicyEngine,
    PolicyResult,
    PolicyRule,
    build_policy_engine,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

POLICIES_PATH = Path(__file__).parents[2] / "governance" / "policies.yaml"


def make_engine() -> PolicyEngine:
    engine = build_policy_engine(POLICIES_PATH)
    assert engine is not None
    return engine


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_policy_engine_loads_rules():
    engine = make_engine()
    assert len(engine.rules) >= 5


def test_check_response_passes_clean_text():
    engine = make_engine()
    result = engine.check_response("any_agent", "Here is a summary of your request.")
    assert result.passed is True
    assert result.action == "allow"
    assert result.violated_policy_id is None


def test_block_large_purchase_response():
    engine = make_engine()
    result = engine.check_response("finance_agent", "I approved the $500,000 transaction.")
    assert result.passed is False
    assert result.violated_policy_id == "block_large_purchases"
    assert result.action == "block"


def test_escalate_legal_advice():
    engine = make_engine()
    result = engine.check_response(
        "hr_agent",
        "You should consult a lawyer about the contract liability.",
    )
    assert result.passed is False
    assert result.action == "escalate"


def test_warn_pii_ssn():
    engine = make_engine()
    result = engine.check_response("any_agent", "Your SSN is 123-45-6789, please verify.")
    assert result.passed is False
    assert result.violated_policy_id == "warn_pii_exposure"
    assert result.action == "warn"


def test_warn_pii_credit_card():
    engine = make_engine()
    result = engine.check_response("any_agent", "Card ending in 4111 1111 1111 1111 was charged.")
    assert result.passed is False
    assert result.action == "warn"


def test_scope_limits_rule_to_specific_agents():
    engine = make_engine()
    # credential rule only applies to developer_agent / it_helpdesk_agent
    text = "password = supersecret123"
    assert engine.check_response("developer_agent", text).passed is False
    # should PASS for an agent outside the scope
    assert engine.check_response("hr_agent", text).passed is True


def test_check_prompt_mirrors_check_response():
    engine = make_engine()
    result = engine.check_prompt("developer_agent", "api_key = ABCDEF1234567890")
    assert result.passed is False
    assert result.action == "block"


def test_build_policy_engine_returns_none_on_missing_file(tmp_path):
    missing = tmp_path / "nonexistent.yaml"
    engine = build_policy_engine(missing)
    assert engine is None


def test_policy_result_fields():
    result = PolicyResult(
        passed=False,
        violated_policy_id="test_id",
        reason="test reason",
        action="block",
    )
    assert result.passed is False
    assert result.violated_policy_id == "test_id"


def test_policy_rule_applies_to_all():
    rule = PolicyRule(
        id="r1",
        description="desc",
        agent_scope="all",
        rule_type="warn",
        pattern=r"test",
    )
    assert rule.applies_to("any_agent") is True
    assert rule.applies_to("another") is True


def test_policy_rule_applies_to_list():
    rule = PolicyRule(
        id="r2",
        description="desc",
        agent_scope=["agent_a", "agent_b"],
        rule_type="block",
        pattern=r"test",
    )
    assert rule.applies_to("agent_a") is True
    assert rule.applies_to("agent_c") is False
