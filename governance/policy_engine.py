"""Semantic Governance — Policy Engine (Issue #7)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_POLICIES_PATH = Path(__file__).parent / "policies.yaml"


@dataclass
class PolicyRule:
    id: str
    description: str
    agent_scope: list[str] | str  # list of agent names or 'all'
    rule_type: str  # 'block' | 'escalate' | 'warn'
    pattern: str

    def applies_to(self, agent_name: str) -> bool:
        if self.agent_scope == "all":
            return True
        return agent_name in self.agent_scope

    def matches(self, text: str) -> bool:
        try:
            return bool(re.search(self.pattern, text))
        except re.error as exc:
            logger.warning("Invalid regex in policy %s: %s", self.id, exc)
            return False


@dataclass
class PolicyResult:
    passed: bool
    violated_policy_id: Optional[str]
    reason: str
    action: str  # 'allow' | 'block' | 'escalate' | 'warn'


_ACTION_MAP = {
    "block": "block",
    "escalate": "escalate",
    "warn": "warn",
}


class PolicyEngine:
    def __init__(self, rules: list[PolicyRule]) -> None:
        self._rules = rules

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check(self, agent_name: str, text: str) -> PolicyResult:
        for rule in self._rules:
            if not rule.applies_to(agent_name):
                continue
            if rule.matches(text):
                action = _ACTION_MAP.get(rule.rule_type, "warn")
                return PolicyResult(
                    passed=False,
                    violated_policy_id=rule.id,
                    reason=f"Policy '{rule.id}' matched: {rule.description}",
                    action=action,
                )
        return PolicyResult(passed=True, violated_policy_id=None, reason="All policies passed.", action="allow")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_response(self, agent_name: str, response: str) -> PolicyResult:
        """Check an agent response against all applicable policies."""
        return self._check(agent_name, response)

    def check_prompt(self, agent_name: str, prompt: str) -> PolicyResult:
        """Check a user prompt against all applicable policies."""
        return self._check(agent_name, prompt)

    @property
    def rules(self) -> list[PolicyRule]:
        return list(self._rules)


def _load_rules(path: Path = _POLICIES_PATH) -> list[PolicyRule]:
    with open(path, "r") as fh:
        data = yaml.safe_load(fh)
    rules = []
    for item in data.get("policies", []):
        scope = item.get("agent_scope", "all")
        rules.append(
            PolicyRule(
                id=item["id"],
                description=item.get("description", ""),
                agent_scope=scope,
                rule_type=item.get("rule_type", "warn"),
                pattern=item["pattern"],
            )
        )
    return rules


def build_policy_engine(path: Path | None = None) -> Optional[PolicyEngine]:
    """Build a PolicyEngine from policies.yaml. Returns None on failure."""
    try:
        rules = _load_rules(path or _POLICIES_PATH)
        logger.info("PolicyEngine loaded %d rules.", len(rules))
        return PolicyEngine(rules)
    except Exception as exc:  # noqa: BLE001
        logger.warning("PolicyEngine unavailable: %s", exc)
        return None
