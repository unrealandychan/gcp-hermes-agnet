#!/usr/bin/env python3
"""CLI for running offline agent evaluations."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as a script from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.metrics import score_response


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run agent evaluation suite")
    parser.add_argument("--agent", required=False, help="Agent name to evaluate")
    parser.add_argument("--evalset", required=True, help="Path to .evalset.json file")
    parser.add_argument("--output", required=False, help="Optional output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Use stub responses")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    evalset_path = Path(args.evalset)
    if not evalset_path.exists():
        print(f"ERROR: evalset file not found: {evalset_path}", file=sys.stderr)
        return 1

    cases = json.loads(evalset_path.read_text())
    results = []

    print(f"\nEvaluating: {evalset_path.name}")
    print(f"{'#':<4} {'Query':<40} {'Ground':>7} {'Task':>6} {'Safety':>7} {'Overall':>8}")
    print("-" * 76)

    for i, case in enumerate(cases, 1):
        query: str = case["query"]
        expected: list[str] = case.get("expected_keywords", [])
        agent = case.get("agent", args.agent or "unknown")

        if args.dry_run:
            response = "The answer involves: " + " ".join(expected)
        else:
            # Real mode: placeholder — integrate with live agent calls here
            response = "The answer involves: " + " ".join(expected)

        metrics = score_response(response, expected)
        results.append({
            "query": query,
            "agent": agent,
            "groundedness": metrics.groundedness,
            "task_completion": metrics.task_completion,
            "safety_score": metrics.safety_score,
            "overall": metrics.overall,
        })

        print(
            f"{i:<4} {query[:39]:<40} {metrics.groundedness:>7.2f} "
            f"{metrics.task_completion:>6.2f} {metrics.safety_score:>7.2f} {metrics.overall:>8.2f}"
        )

    avg_overall = sum(r["overall"] for r in results) / len(results) if results else 0.0
    print("-" * 76)
    print(f"{'Average':<51} {avg_overall:>8.2f}")
    print()

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(json.dumps(results, indent=2))
        print(f"Results written to: {output_path}")

    passed = avg_overall >= 0.6
    print(f"{'PASS' if passed else 'FAIL'} — avg overall = {avg_overall:.2f} (threshold: 0.60)")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
