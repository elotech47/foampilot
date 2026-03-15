"""Benchmark execution orchestrator.

Runs FoamPilot benchmark cases and collects results.
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
import structlog

log = structlog.get_logger(__name__)

CASES_DIR = Path(__file__).parent / "cases"
RESULTS_DIR = Path(__file__).parent / "results"

# ── ANSI colours for terminal output ─────────────────────────────────────────
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_MAGENTA = "\033[35m"
_BLUE = "\033[34m"

_PHASE_COLOR = {
    "clarifying": _CYAN,
    "consulting": _MAGENTA,
    "setup": _YELLOW,
    "meshing": _BLUE,
    "running": _GREEN,
    "analyzing": _CYAN,
}


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


class _ConsoleProgress:
    """Prints live progress to the terminal during eval runs."""

    def __init__(self, case_name: str) -> None:
        self._case = case_name
        self._tool_count = 0
        self._turn_count = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_usd = 0.0
        self._events: list[dict] = []

    @property
    def events(self) -> list[dict]:
        return self._events

    @property
    def tool_count(self) -> int:
        return self._tool_count

    @property
    def token_summary(self) -> dict:
        return {
            "total_input_tokens": self._total_input_tokens,
            "total_output_tokens": self._total_output_tokens,
            "total_cost_usd": round(self._total_cost_usd, 4),
        }

    def __call__(self, event: dict) -> None:
        self._events.append(event)
        t = event.get("type", "")
        d = event.get("data", {})

        if t == "phase_start":
            phase = d.get("phase", "?")
            color = _PHASE_COLOR.get(phase, _DIM)
            print(f"  {_DIM}{_ts()}{_RESET}  {color}{_BOLD}▶ PHASE: {phase.upper()}{_RESET}")

        elif t == "tool_call":
            self._tool_count += 1
            tool = d.get("tool", "?")
            inp = d.get("input", {})
            summary = self._summarise_input(inp)
            print(f"  {_DIM}{_ts()}{_RESET}  {_YELLOW}⚙ tool[{self._tool_count}]{_RESET} {_BOLD}{tool}{_RESET} {_DIM}{summary}{_RESET}")

        elif t == "tool_result":
            tool = d.get("tool", "?")
            ok = d.get("success", False)
            if ok:
                print(f"  {_DIM}{_ts()}{_RESET}  {_GREEN}✓ {tool}{_RESET} {_DIM}OK{_RESET}")
            else:
                err = d.get("error", "unknown error")
                print(f"  {_DIM}{_ts()}{_RESET}  {_RED}✗ {tool}{_RESET} {_RED}{err[:120]}{_RESET}")

        elif t == "llm_response":
            self._turn_count += 1
            text = d.get("text", "")
            preview = text[:100].replace("\n", " ").strip()
            if len(text) > 100:
                preview += "…"
            print(f"  {_DIM}{_ts()}{_RESET}  {_MAGENTA}💭 LLM turn {self._turn_count}{_RESET} {_DIM}{preview}{_RESET}")

        elif t == "session_start":
            sid = d.get("session_id", "?")
            print(f"  {_DIM}{_ts()}{_RESET}  {_CYAN}● Session {sid} started{_RESET}")

        elif t == "session_complete":
            print(f"  {_DIM}{_ts()}{_RESET}  {_GREEN}{_BOLD}● Session complete{_RESET}")

        elif t == "phase_token_summary":
            phase = d.get("phase", "?")
            inp = d.get("total_input_tokens", 0)
            out = d.get("total_output_tokens", 0)
            cost = d.get("total_cost_usd", 0.0)
            self._total_input_tokens += inp
            self._total_output_tokens += out
            self._total_cost_usd += cost
            print(
                f"  {_DIM}{_ts()}{_RESET}  {_BLUE}$ {phase}{_RESET} "
                f"{_DIM}{inp:,}in + {out:,}out tokens, ${cost:.4f}{_RESET}"
            )

        elif t == "llm_error":
            err = d.get("error", "?")
            print(f"  {_DIM}{_ts()}{_RESET}  {_RED}{_BOLD}✗ LLM ERROR: {err[:200]}{_RESET}")

        elif t == "session_error":
            err = d.get("error", "?")
            print(f"  {_DIM}{_ts()}{_RESET}  {_RED}{_BOLD}● Session error: {err[:150]}{_RESET}")

    @staticmethod
    def _summarise_input(inp: dict) -> str:
        if not inp:
            return ""
        parts = []
        for k, v in list(inp.items())[:3]:
            val = str(v)[:50] if isinstance(v, str) else json.dumps(v)[:50]
            parts.append(f"{k}={val}")
        suffix = f" +{len(inp)-3} more" if len(inp) > 3 else ""
        return " ".join(parts) + suffix


class BenchmarkRunner:
    """Runs benchmark cases against FoamPilot and collects results.

    Args:
        cases_dir: Directory containing tier1/, tier2/, tier3/ YAML files.
        results_dir: Directory where run results are saved.
        quiet: Suppress console progress output.
    """

    def __init__(
        self,
        cases_dir: Path | None = None,
        results_dir: Path | None = None,
        quiet: bool = False,
    ) -> None:
        self._cases_dir = cases_dir or CASES_DIR
        self._results_dir = results_dir or RESULTS_DIR
        self._results_dir.mkdir(parents=True, exist_ok=True)
        self._quiet = quiet

    def run_case(self, case_name: str) -> dict:
        """Run a single benchmark case by name."""
        case_spec = self._find_case(case_name)
        if case_spec is None:
            raise ValueError(f"Benchmark case not found: {case_name}")
        return self._execute(case_spec)

    def run_suite(self, tier: str) -> list[dict]:
        """Run all cases in a tier."""
        tier_dir = self._cases_dir / tier
        if not tier_dir.exists():
            raise FileNotFoundError(f"Tier directory not found: {tier_dir}")

        cases = sorted(tier_dir.glob("*.yaml"))
        if not self._quiet:
            print(f"\n{_BOLD}Running {tier} — {len(cases)} case(s){_RESET}\n")

        results = []
        for i, yaml_file in enumerate(cases, 1):
            with open(yaml_file) as f:
                case_spec = yaml.safe_load(f)
            if not self._quiet:
                print(f"{_DIM}─── [{i}/{len(cases)}] ───{_RESET}")
            result = self._execute(case_spec)
            results.append(result)

        self._print_summary(results)
        return results

    def run_all(self) -> list[dict]:
        """Run all benchmark cases across all tiers."""
        all_results = []
        for tier in ("tier1", "tier2", "tier3"):
            try:
                results = self.run_suite(tier)
                all_results.extend(results)
            except FileNotFoundError:
                log.warning("tier_not_found", tier=tier)
                if not self._quiet:
                    print(f"{_YELLOW}⚠ Tier {tier} not found, skipping{_RESET}")

        if len(all_results) > 0:
            self._print_summary(all_results)
        return all_results

    def _find_case(self, case_name: str) -> dict | None:
        for yaml_file in self._cases_dir.rglob("*.yaml"):
            with open(yaml_file) as f:
                spec = yaml.safe_load(f)
            if spec.get("name") == case_name:
                return spec
        return None

    def _execute(self, case_spec: dict) -> dict:
        """Execute a single benchmark case and score it."""
        from foampilot.core.orchestrator import Orchestrator
        from foampilot import config

        case_name = case_spec["name"]
        run_id = str(uuid.uuid4())[:8]

        if not self._quiet:
            print(f"\n{_BOLD}{_CYAN}▶ Benchmark: {case_name}{_RESET} {_DIM}(run {run_id}){_RESET}")
            prompt_preview = case_spec["prompt"][:120].replace("\n", " ")
            if len(case_spec["prompt"]) > 120:
                prompt_preview += "…"
            print(f"  {_DIM}Prompt: {prompt_preview}{_RESET}")
            print()

        log.info("benchmark_start", case=case_name, run_id=run_id)

        active_version = config.OPENFOAM_VERSION
        compatible = case_spec.get("compatible_versions", [str(active_version)])
        if str(active_version) not in [str(v) for v in compatible]:
            log.warning(
                "benchmark_version_incompatible",
                case=case_name,
                required=compatible,
                active=active_version,
            )
            if not self._quiet:
                print(f"  {_YELLOW}⚠ Version mismatch: need {compatible}, have v{active_version}{_RESET}")

        progress = _ConsoleProgress(case_name) if not self._quiet else None

        def event_cb(event: dict) -> None:
            if progress:
                progress(event)

        start_time = time.time()

        cases_dir = config.CASES_DIR / f"benchmark_{case_name}_{run_id}"

        try:
            orchestrator = Orchestrator(
                cases_dir=cases_dir.parent,
                event_callback=event_cb,
            )
            final_state = orchestrator.run(case_spec["prompt"])
            success = True
            error_msg = None
        except Exception as exc:
            final_state = None
            success = False
            error_msg = str(exc)
            log.error("benchmark_execution_failed", case=case_name, error=error_msg)

        elapsed = time.time() - start_time

        from benchmarks.scorer import score_result
        score_data = score_result(
            case_spec=case_spec,
            final_state=final_state,
            tool_calls_used=progress.tool_count if progress else 0,
            elapsed_s=elapsed,
            error=error_msg,
        )

        tokens = progress.token_summary if progress else {}

        result = {
            "case": case_name,
            "run_id": run_id,
            "score": score_data["total_score"],
            "scores": score_data,
            "tool_calls": progress.tool_count if progress else 0,
            "elapsed_s": round(elapsed, 1),
            "success": success,
            "error": error_msg,
            "tokens": tokens,
        }

        result_file = self._results_dir / f"{case_name}_{run_id}.json"
        result_file.write_text(json.dumps(result, indent=2, default=str))
        log.info("benchmark_complete", case=case_name, score=result["score"])

        if not self._quiet:
            score_color = _GREEN if result["score"] >= 70 else (_YELLOW if result["score"] >= 40 else _RED)
            status = f"{_GREEN}PASS{_RESET}" if success else f"{_RED}FAIL{_RESET}"
            cost_str = f"${tokens.get('total_cost_usd', 0):.4f}" if tokens else "n/a"
            print(
                f"\n  {_BOLD}Result:{_RESET} {status}"
                f"  {_BOLD}Score:{_RESET} {score_color}{result['score']:.0f}/100{_RESET}"
                f"  {_DIM}Tools: {result['tool_calls']}  Time: {elapsed:.0f}s  Cost: {cost_str}{_RESET}"
            )
            if error_msg:
                print(f"  {_RED}Error: {error_msg[:200]}{_RESET}")
            print()

        return result

    def _print_summary(self, results: list[dict]) -> None:
        """Print a summary table of all results."""
        if self._quiet or not results:
            return

        print(f"\n{'='*72}")
        print(f"{_BOLD}  BENCHMARK SUMMARY{_RESET}")
        print(f"{'='*72}")
        print(f"  {'Case':<25} {'Score':>6} {'Tools':>6} {'Time':>7} {'Cost':>9} {'Status':>8}")
        print(f"  {'─'*25} {'─'*6} {'─'*6} {'─'*7} {'─'*9} {'─'*8}")

        total_score = 0
        total_cost = 0.0
        for r in results:
            sc = r["score"]
            total_score += sc
            cost = r.get("tokens", {}).get("total_cost_usd", 0.0)
            total_cost += cost
            color = _GREEN if sc >= 70 else (_YELLOW if sc >= 40 else _RED)
            status = f"{_GREEN}OK{_RESET}" if r["success"] else f"{_RED}FAIL{_RESET}"
            print(
                f"  {r['case']:<25} {color}{sc:>5.0f}{_RESET}% "
                f"{r['tool_calls']:>5} {r['elapsed_s']:>6.0f}s "
                f"${cost:>7.4f} {status:>8}"
            )

        avg = total_score / len(results) if results else 0
        avg_color = _GREEN if avg >= 70 else (_YELLOW if avg >= 40 else _RED)
        print(f"  {'─'*25} {'─'*6} {'─'*6} {'─'*7} {'─'*9} {'─'*8}")
        print(
            f"  {_BOLD}{'Average/Total':<25}{_RESET} "
            f"{avg_color}{_BOLD}{avg:>5.0f}{_RESET}% "
            f"{_DIM}{' '*6} {' '*7} ${total_cost:>7.4f}{_RESET}"
        )
        print(f"{'='*72}\n")
