#!/usr/bin/env python3
"""CLI script to register agents from agents.yaml into the Hermes Agent Registry (Issue #8)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import yaml

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parents[1]))

from registry.agent_registry import AgentRecord, build_registry

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def load_agents_yaml(path: Path) -> list[dict]:
    with open(path, "r") as fh:
        data = yaml.safe_load(fh)
    agents = data.get("agents", [])
    if not isinstance(agents, list):
        raise ValueError("agents.yaml must have a top-level 'agents' list.")
    return agents


def build_record(raw: dict) -> AgentRecord:
    return AgentRecord(
        name=raw["name"],
        description=raw.get("description", ""),
        agent_type=raw.get("agent_type", "custom"),
        endpoint=raw.get("endpoint", ""),
        version=raw.get("version", "1.0.0"),
        tags=raw.get("tags", []),
    )


async def run(args: argparse.Namespace) -> None:
    agents_file = Path(args.file)
    if not agents_file.exists():
        logger.error("agents.yaml not found: %s", agents_file)
        sys.exit(1)

    raw_agents = load_agents_yaml(agents_file)
    logger.info("Found %d agent(s) in %s.", len(raw_agents), agents_file)

    if args.dry_run:
        for raw in raw_agents:
            record = build_record(raw)
            logger.info("[DRY-RUN] Would register: %s (type=%s, version=%s)", record.name, record.agent_type, record.version)
        return

    registry = build_registry()
    if registry is None:
        logger.error("Registry unavailable. Aborting.")
        sys.exit(1)

    for raw in raw_agents:
        record = build_record(raw)
        resource_id = await registry.register_agent(record)
        logger.info("Registered '%s' → %s", record.name, resource_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Register agents from agents.yaml into Hermes Agent Registry.")
    parser.add_argument(
        "--file",
        default="agents.yaml",
        help="Path to agents.yaml (default: agents.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be registered without making API calls.",
    )
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
