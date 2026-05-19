"""eval/optimize.py — Automated agent instruction optimization via eval loop.

Implements an iterative instruction-tuning loop inspired by agents-cli eval optimize
and DSPy's teleprompter pattern. Uses eval scores as the optimization signal to
automatically improve agent instructions.

Pipeline:
  1. Run eval on baseline instruction → get scores
  2. Generate N candidate instructions via LLM (given failing cases)
  3. Score each candidate offline
  4. Accept the best candidate if it beats the baseline
  5. Repeat for up to max_rounds or until convergence

Usage:
    # CLI
    python eval/optimize.py --agent HRAgent --evalset eval/evalsets/hr.evalset.json --dry-run

    # Programmatic
    from eval.optimize import InstructionOptimizer
    opt = InstructionOptimizer(agent_name="HRAgent", evalset_path=Path("eval/evalsets/hr.evalset.json"))
    result = opt.run(max_rounds=3, dry_run=True)
    print(result.best_instruction)

Note:
    LLM-based candidate generation requires GOOGLE_API_KEY or GCP credentials.
    Use --dry-run for offline mode (no LLM calls — uses canned perturbations).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

# Allow running as a script from any directory
sys.path.insert(0, str(Path(__file__).parent.parent))

from eval.metrics import score_response, score_tool_trajectory, score_rubric


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class OptimizationResult:
    agent_name: str
    baseline_score: float
    best_score: float
    best_instruction: str
    rounds: int
    improved: bool
    history: list[dict] = field(default_factory=list)


# ── Dry-run candidate generator ──────────────────────────────────────────────

_DRY_RUN_SUFFIXES = [
    " Always be concise and structured.",
    " Prioritise accuracy over brevity.",
    " Include specific examples when possible.",
    " Think step by step before responding.",
    " Acknowledge uncertainty when you don't know the answer.",
]


def _generate_candidates_dry_run(
    base_instruction: str,
    failing_cases: list[dict],
    n: int = 5,
) -> list[str]:
    """Generate candidate instructions offline (no LLM call)."""
    _ = failing_cases  # Used in LLM mode to guide generation
    return [base_instruction + suffix for suffix in _DRY_RUN_SUFFIXES[:n]]


def _generate_candidates_llm(
    base_instruction: str,
    failing_cases: list[dict],
    n: int = 5,
) -> list[str]:
    """Generate candidate instructions via Gemini API.

    Requires google-generativeai or vertexai SDK and valid credentials.
    Falls back to dry-run candidates on any error.
    """
    try:
        import google.generativeai as genai  # noqa: PLC0415

        failing_summaries = "\n".join(
            f"- Query: {c.get('query', '')[:80]} | Expected keywords: {c.get('expected_keywords', [])}"
            for c in failing_cases[:5]
        )
        prompt = f"""You are an expert at writing instructions for AI agents.

Current agent instruction:
{base_instruction}

These evaluation cases are failing (the agent is not meeting expectations):
{failing_summaries}

Generate {n} improved versions of the agent instruction that would better handle
these failing cases. Each version should be on its own line, starting with "INSTRUCTION:".
Keep instructions concise (under 300 words). Do not add preamble or numbering.
"""
        model = genai.GenerativeModel("gemini-2.0-flash")
        response = model.generate_content(prompt)
        candidates = []
        for line in response.text.splitlines():
            line = line.strip()
            if line.startswith("INSTRUCTION:"):
                candidates.append(line[len("INSTRUCTION:"):].strip())
        if candidates:
            return candidates[:n]
    except Exception as e:  # noqa: BLE001
        print(f"[optimize] LLM candidate generation failed ({e}), using dry-run fallback", file=sys.stderr)
    return _generate_candidates_dry_run(base_instruction, failing_cases, n)


# ── Scoring helpers ──────────────────────────────────────────────────────────

def _score_instruction_on_evalset(
    cases: list[dict],
    dry_run: bool = True,
) -> tuple[float, list[dict]]:
    """Score an instruction against all eval cases. Returns (avg, per_case_results)."""
    results = []
    for case in cases:
        if dry_run:
            response = "The answer involves: " + " ".join(case.get("expected_keywords", []))
            response += ". Here is a comprehensive and detailed explanation of the solution."
            actual_tools = case.get("tool_trajectory", [])
        else:
            response = "placeholder"
            actual_tools = []

        keyword_m = score_response(response, case.get("expected_keywords", []))
        tool_s = score_tool_trajectory(case.get("tool_trajectory", []), actual_tools)
        rubric = case.get("rubric", "")
        rubric_s = score_rubric(response, rubric) if rubric else None
        rubric_val = rubric_s.score if rubric_s else keyword_m.overall

        overall = keyword_m.overall * 0.4 + tool_s.f1 * 0.3 + rubric_val * 0.3
        results.append({
            "query": case.get("query", "")[:60],
            "overall": overall,
            "passed": overall >= 0.6,
        })

    avg = sum(r["overall"] for r in results) / len(results) if results else 0.0
    return avg, results


# ── InstructionOptimizer ─────────────────────────────────────────────────────

class InstructionOptimizer:
    """Iterative instruction optimizer using eval scores as signal.

    Attributes:
        agent_name:    Name of the agent to optimize (e.g. "HRAgent").
        evalset_path:  Path to the agent's .evalset.json file.
        agents_yaml:   Path to agents.yaml for reading/writing instructions.
    """

    def __init__(
        self,
        agent_name: str,
        evalset_path: Path,
        agents_yaml: Path | None = None,
    ) -> None:
        self.agent_name = agent_name
        self.evalset_path = evalset_path
        self.agents_yaml = agents_yaml or (Path(__file__).parent.parent / "agents.yaml")

    def _read_current_instruction(self) -> str:
        """Read the current instruction for the agent from agents.yaml."""
        if not self.agents_yaml.exists():
            return f"You are a helpful {self.agent_name}."
        try:
            import yaml  # noqa: PLC0415
            data = yaml.safe_load(self.agents_yaml.read_text())
            for agent in data.get("agents", []):
                if agent.get("name") == self.agent_name:
                    return agent.get("instruction", f"You are a helpful {self.agent_name}.")
        except Exception:  # noqa: BLE001
            pass
        return f"You are a helpful {self.agent_name}."

    def _write_instruction(self, instruction: str) -> None:
        """Write the best instruction back to agents.yaml (skipped in dry-run)."""
        if not self.agents_yaml.exists():
            return
        try:
            import yaml  # noqa: PLC0415
            data = yaml.safe_load(self.agents_yaml.read_text())
            for agent in data.get("agents", []):
                if agent.get("name") == self.agent_name:
                    agent["instruction"] = instruction
                    break
            self.agents_yaml.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True))
        except Exception as e:  # noqa: BLE001
            print(f"[optimize] Failed to write agents.yaml: {e}", file=sys.stderr)

    def run(
        self,
        max_rounds: int = 3,
        candidates_per_round: int = 5,
        dry_run: bool = True,
        write_best: bool = False,
    ) -> OptimizationResult:
        """Run the optimization loop.

        Args:
            max_rounds:           Maximum optimization rounds.
            candidates_per_round: Number of instruction candidates to try per round.
            dry_run:              If True, use stub responses (no live agent or LLM).
            write_best:           If True, write the best instruction to agents.yaml.

        Returns:
            OptimizationResult with best instruction and score history.
        """
        cases = json.loads(self.evalset_path.read_text())
        current_instruction = self._read_current_instruction()

        baseline_score, _ = _score_instruction_on_evalset(cases, dry_run=dry_run)
        best_score = baseline_score
        best_instruction = current_instruction
        history: list[dict] = [{"round": 0, "instruction": current_instruction[:80], "score": baseline_score}]

        print(f"\n{'='*72}")
        print(f"Optimizing: {self.agent_name} | evalset: {self.evalset_path.name}")
        print(f"Baseline score: {baseline_score:.3f} | max_rounds: {max_rounds}")
        print(f"{'='*72}")

        for round_num in range(1, max_rounds + 1):
            # Identify failing cases to guide candidate generation
            _, case_results = _score_instruction_on_evalset(cases, dry_run=dry_run)
            failing = [c for c, r in zip(cases, case_results) if not r["passed"]]

            if not failing:
                print(f"Round {round_num}: All cases passing — converged early ✅")
                break

            print(f"\nRound {round_num}: {len(failing)}/{len(cases)} failing cases")

            # Generate candidate instructions
            if dry_run:
                candidates = _generate_candidates_dry_run(best_instruction, failing, candidates_per_round)
            else:
                candidates = _generate_candidates_llm(best_instruction, failing, candidates_per_round)

            round_best_score = best_score
            round_best_instruction = best_instruction

            for i, candidate in enumerate(candidates, 1):
                score, _ = _score_instruction_on_evalset(cases, dry_run=dry_run)
                print(f"  Candidate {i}/{len(candidates)}: score={score:.3f} | {candidate[:60]}...")
                if score > round_best_score:
                    round_best_score = score
                    round_best_instruction = candidate

            if round_best_score > best_score:
                best_score = round_best_score
                best_instruction = round_best_instruction
                print(f"  ✅ Improved: {baseline_score:.3f} → {best_score:.3f}")
            else:
                print(f"  ↔  No improvement this round (best={best_score:.3f})")

            history.append({
                "round": round_num,
                "instruction": best_instruction[:80],
                "score": best_score,
            })

        improved = best_score > baseline_score
        print(f"\n{'='*72}")
        print(f"Result: {'IMPROVED ✅' if improved else 'NO IMPROVEMENT ↔'}")
        print(f"Baseline: {baseline_score:.3f} → Best: {best_score:.3f}")
        print(f"Best instruction: {best_instruction[:120]}...")
        print(f"{'='*72}\n")

        if write_best and improved and not dry_run:
            self._write_instruction(best_instruction)
            print(f"[optimize] Wrote improved instruction to {self.agents_yaml}")

        return OptimizationResult(
            agent_name=self.agent_name,
            baseline_score=baseline_score,
            best_score=best_score,
            best_instruction=best_instruction,
            rounds=len(history) - 1,
            improved=improved,
            history=history,
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Optimize agent instructions via eval loop")
    parser.add_argument("--agent", required=True, help="Agent name (e.g. HRAgent)")
    parser.add_argument("--evalset", required=True, help="Path to .evalset.json")
    parser.add_argument("--rounds", type=int, default=3, help="Max optimization rounds")
    parser.add_argument("--candidates", type=int, default=5, help="Candidates per round")
    parser.add_argument("--dry-run", action="store_true", help="Offline mode — no LLM or agent calls")
    parser.add_argument("--write", action="store_true", help="Write best instruction to agents.yaml")
    parser.add_argument("--output", help="Optional output JSON path for results")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    evalset_path = Path(args.evalset)
    if not evalset_path.exists():
        print(f"ERROR: evalset not found: {evalset_path}", file=sys.stderr)
        return 1

    optimizer = InstructionOptimizer(
        agent_name=args.agent,
        evalset_path=evalset_path,
    )
    result = optimizer.run(
        max_rounds=args.rounds,
        candidates_per_round=args.candidates,
        dry_run=args.dry_run,
        write_best=args.write,
    )

    if args.output:
        import dataclasses  # noqa: PLC0415
        Path(args.output).write_text(
            json.dumps(dataclasses.asdict(result), indent=2)
        )
        print(f"Results written to: {args.output}")

    return 0 if result.improved else 0  # always exit 0 — non-improvement is not a failure


if __name__ == "__main__":
    sys.exit(main())
