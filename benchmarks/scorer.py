"""Automated scoring for FoamPilot benchmark runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def score_result(
    case_spec: dict,
    final_state: Any | None,
    tool_calls_used: int,
    elapsed_s: float,
    error: str | None,
) -> dict:
    """Score a benchmark run against the expected outcomes.

    Args:
        case_spec: The YAML benchmark specification dict.
        final_state: The SimulationState from the orchestrator (or None on failure).
        tool_calls_used: Number of tool calls made.
        elapsed_s: Wall-clock seconds elapsed.
        error: Error message if the run failed.

    Returns:
        Dict with component scores and total (0-100).
    """
    expected = case_spec.get("expected", {})
    scoring = case_spec.get("scoring", {})
    max_tool_calls = case_spec.get("max_tool_calls", 50)

    scores: dict[str, float] = {}

    # ── Setup correctness ─────────────────────────────────────────────────────
    setup_score = 0.0
    if final_state is not None and final_state.case_dir:
        case_path = Path(str(final_state.case_dir))
        files_present = expected.get("files_present", [])
        if files_present:
            found = sum(1 for f in files_present if (case_path / f).exists())
            setup_score = found / len(files_present)
        else:
            setup_score = 1.0 if case_path.exists() else 0.0
    scores["setup_correctness"] = setup_score * 100

    # ── Convergence ────────────────────────────────────────────────────────────
    convergence_score = 0.0
    if expected.get("converged"):
        if final_state and final_state.convergence_data.get("converged"):
            convergence_score = 1.0
    elif not expected.get("converged"):
        # For transient cases: score based on completing without crash
        if final_state and str(final_state.phase) != "error":
            convergence_score = 1.0
    scores["convergence"] = convergence_score * 100

    # ── Mesh quality ───────────────────────────────────────────────────────────
    mesh_score = 0.0
    if expected.get("mesh_passed"):
        if final_state and final_state.mesh_quality.get("passed"):
            mesh_score = 1.0
    else:
        mesh_score = 1.0  # Mesh check not required
    scores["mesh"] = mesh_score * 100

    # ── Efficiency ─────────────────────────────────────────────────────────────
    efficiency_score = 1.0
    if max_tool_calls > 0:
        usage_ratio = tool_calls_used / max_tool_calls
        efficiency_score = max(0.0, 1.0 - max(0.0, usage_ratio - 0.5) * 2)
    scores["efficiency"] = efficiency_score * 100

    # ── Assumption quality ─────────────────────────────────────────────────────
    assumption_score = 0.5  # Default: neutral
    if final_state and final_state.assumptions:
        # Having explicit assumptions is good
        assumption_score = min(1.0, len(final_state.assumptions) / 3 * 0.8 + 0.2)
    scores["assumption_quality"] = assumption_score * 100

    # ── Weighted total ─────────────────────────────────────────────────────────
    weights = {
        "setup_correctness": scoring.get("setup_correctness_weight", 0.30),
        "convergence": scoring.get("convergence_weight", 0.25),
        "mesh": scoring.get("mesh_passed_weight", 0.10),
        "efficiency": scoring.get("efficiency_weight", 0.10),
        "assumption_quality": scoring.get("assumption_quality_weight", 0.10),
    }

    # Normalize weights to sum to 1
    total_weight = sum(weights.values())
    if total_weight > 0:
        weights = {k: v / total_weight for k, v in weights.items()}

    total = sum(scores.get(k, 0) * w for k, w in weights.items())
    scores["total_score"] = round(total, 1)
    scores["component_weights"] = weights

    return scores
