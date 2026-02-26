"""Benchmark execution orchestrator.

Runs FoamPilot benchmark cases and collects results.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

import yaml
import structlog

log = structlog.get_logger(__name__)

CASES_DIR = Path(__file__).parent / "cases"
RESULTS_DIR = Path(__file__).parent / "results"


class BenchmarkRunner:
    """Runs benchmark cases against FoamPilot and collects results.

    Args:
        cases_dir: Directory containing tier1/, tier2/, tier3/ YAML files.
        results_dir: Directory where run results are saved.
    """

    def __init__(
        self,
        cases_dir: Path | None = None,
        results_dir: Path | None = None,
    ) -> None:
        self._cases_dir = cases_dir or CASES_DIR
        self._results_dir = results_dir or RESULTS_DIR
        self._results_dir.mkdir(parents=True, exist_ok=True)

    def run_case(self, case_name: str) -> dict:
        """Run a single benchmark case by name.

        Args:
            case_name: Name of the case (e.g., 'lid_driven_cavity').

        Returns:
            Result dict with score and details.
        """
        case_spec = self._find_case(case_name)
        if case_spec is None:
            raise ValueError(f"Benchmark case not found: {case_name}")
        return self._execute(case_spec)

    def run_suite(self, tier: str) -> list[dict]:
        """Run all cases in a tier.

        Args:
            tier: 'tier1', 'tier2', or 'tier3'.

        Returns:
            List of result dicts.
        """
        tier_dir = self._cases_dir / tier
        if not tier_dir.exists():
            raise FileNotFoundError(f"Tier directory not found: {tier_dir}")

        results = []
        for yaml_file in sorted(tier_dir.glob("*.yaml")):
            with open(yaml_file) as f:
                case_spec = yaml.safe_load(f)
            result = self._execute(case_spec)
            results.append(result)
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
        log.info("benchmark_start", case=case_name, run_id=run_id)

        # Check version compatibility
        active_version = config.OPENFOAM_VERSION
        compatible = case_spec.get("compatible_versions", [str(active_version)])
        if str(active_version) not in [str(v) for v in compatible]:
            log.warning(
                "benchmark_version_incompatible",
                case=case_name,
                required=compatible,
                active=active_version,
            )

        tool_calls_used = [0]
        events_log = []

        def event_cb(event):
            events_log.append(event)
            if event.get("type") == "tool_call":
                tool_calls_used[0] += 1

        start_time = time.time()

        from foampilot import config as c
        cases_dir = c.CASES_DIR / f"benchmark_{case_name}_{run_id}"

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

        # Score the result
        from benchmarks.scorer import score_result
        score_data = score_result(
            case_spec=case_spec,
            final_state=final_state,
            tool_calls_used=tool_calls_used[0],
            elapsed_s=elapsed,
            error=error_msg,
        )

        result = {
            "case": case_name,
            "run_id": run_id,
            "score": score_data["total_score"],
            "scores": score_data,
            "tool_calls": tool_calls_used[0],
            "elapsed_s": round(elapsed, 1),
            "success": success,
            "error": error_msg,
        }

        # Save result
        result_file = self._results_dir / f"{case_name}_{run_id}.json"
        result_file.write_text(json.dumps(result, indent=2, default=str))
        log.info("benchmark_complete", case=case_name, score=result["score"])

        return result
