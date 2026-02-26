"""Plot solver convergence residuals."""

import re
from pathlib import Path
from typing import Any

import structlog

from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)

_RE_RESIDUAL = re.compile(
    r"Solving for (\w+),.*?Initial residual = ([\d.eE+\-]+)"
)
_RE_TIME = re.compile(r"^Time = ([\d.eE+\-]+)", re.MULTILINE)


class PlotResidualsTool(Tool):
    """Parse a solver log and generate a residual convergence plot."""

    name = "plot_residuals"
    description = (
        "Parse an OpenFOAM solver log file and generate a residual convergence plot. "
        "Saves the plot as a PNG file and returns the path."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "log_path": {
                "type": "string",
                "description": "Absolute path to the solver log file",
            },
            "output_path": {
                "type": "string",
                "description": "Absolute path for the output PNG (default: next to log file)",
            },
        },
        "required": ["log_path"],
    }
    permission_level = PermissionLevel.AUTO

    def execute(
        self, log_path: str, output_path: str | None = None, **kwargs: Any
    ) -> ToolResult:
        try:
            import matplotlib
            matplotlib.use("Agg")  # Non-interactive backend
            import matplotlib.pyplot as plt
        except ImportError:
            return ToolResult.fail("matplotlib not installed. Run: pip install matplotlib")

        log_file = Path(log_path)
        if not log_file.exists():
            return ToolResult.fail(f"Log file not found: {log_path}")

        text = log_file.read_text(encoding="utf-8", errors="replace")

        # Extract (time, field, residual) triples
        times = [float(m.group(1)) for m in _RE_TIME.finditer(text)]
        time_idx = 0
        field_data: dict[str, list] = {}
        current_time = times[0] if times else 0

        for m in _RE_TIME.finditer(text):
            pass  # already collected

        # Map line positions to time values
        time_positions = [(m.start(), float(m.group(1))) for m in _RE_TIME.finditer(text)]
        residual_positions = [
            (m.start(), m.group(1), float(m.group(2)))
            for m in _RE_RESIDUAL.finditer(text)
        ]

        # Assign each residual to a time step
        for res_pos, field, value in residual_positions:
            current_t = 0.0
            for t_pos, t_val in time_positions:
                if t_pos <= res_pos:
                    current_t = t_val
                else:
                    break
            if field not in field_data:
                field_data[field] = []
            if not field_data[field] or field_data[field][-1][0] != current_t:
                field_data[field].append((current_t, value))

        if not field_data:
            return ToolResult.fail("No residual data found in log file")

        # Generate plot
        fig, ax = plt.subplots(figsize=(10, 6))
        for field, data in sorted(field_data.items()):
            if data:
                ts = [d[0] for d in data]
                rs = [d[1] for d in data]
                ax.semilogy(ts, rs, label=field, linewidth=1.5)

        ax.set_xlabel("Time / Iteration")
        ax.set_ylabel("Initial Residual")
        ax.set_title("Solver Convergence")
        ax.legend(loc="upper right")
        ax.grid(True, which="both", alpha=0.3)
        ax.set_ylim(bottom=1e-10)

        if output_path is None:
            output_path = str(log_file.parent / (log_file.stem + "_residuals.png"))

        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        log.info("residuals_plotted", output=output_path)
        return ToolResult.ok(
            data={
                "output_path": output_path,
                "fields_plotted": list(field_data.keys()),
                "time_steps": len(times),
            }
        )
