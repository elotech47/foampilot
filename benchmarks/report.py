"""Generate HTML/markdown benchmark reports from result files."""

from __future__ import annotations

import json
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


def generate_markdown_report(results_dir: Path | None = None) -> str:
    """Generate a markdown summary of all benchmark results."""
    results_dir = results_dir or RESULTS_DIR
    result_files = sorted(results_dir.glob("*.json"))

    if not result_files:
        return "No benchmark results found."

    results = []
    for f in result_files:
        try:
            data = json.loads(f.read_text())
            results.append(data)
        except Exception:
            continue

    lines = [
        "# FoamPilot Benchmark Report",
        "",
        f"Total runs: {len(results)}",
        "",
        "| Case | Score | Tool Calls | Time (s) | Converged |",
        "|------|-------|------------|----------|-----------|",
    ]

    for r in sorted(results, key=lambda x: x.get("case", "")):
        case = r.get("case", "?")
        score = r.get("score", 0)
        tool_calls = r.get("tool_calls", "?")
        elapsed = r.get("elapsed_s", "?")
        converged = "✓" if r.get("scores", {}).get("convergence", 0) > 50 else "✗"
        lines.append(f"| {case} | {score:.1f} | {tool_calls} | {elapsed} | {converged} |")

    avg_score = sum(r.get("score", 0) for r in results) / len(results) if results else 0
    lines += [
        "",
        f"**Average score: {avg_score:.1f}/100**",
    ]

    return "\n".join(lines)


if __name__ == "__main__":
    print(generate_markdown_report())
