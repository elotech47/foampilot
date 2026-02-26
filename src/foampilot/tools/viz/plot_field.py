"""Plot field data (line profiles, contours) from OpenFOAM results."""

from pathlib import Path
from typing import Any

import structlog

from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)


class PlotFieldTool(Tool):
    """Generate line or contour plots from OpenFOAM postProcessing sample data."""

    name = "plot_field"
    description = (
        "Generate a plot from OpenFOAM postProcessing sample data (line profiles or xy data). "
        "Expects data files produced by the 'sample' or 'probes' function object."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "data_path": {
                "type": "string",
                "description": "Absolute path to the data file (e.g., postProcessing/sample/...)",
            },
            "x_col": {
                "type": "integer",
                "description": "Column index for x-axis (0-indexed, default: 0)",
                "default": 0,
            },
            "y_col": {
                "type": "integer",
                "description": "Column index for y-axis (0-indexed, default: 1)",
                "default": 1,
            },
            "xlabel": {"type": "string", "description": "X-axis label"},
            "ylabel": {"type": "string", "description": "Y-axis label"},
            "title": {"type": "string", "description": "Plot title"},
            "output_path": {"type": "string", "description": "Output PNG path"},
        },
        "required": ["data_path"],
    }
    permission_level = PermissionLevel.AUTO

    def execute(
        self,
        data_path: str,
        x_col: int = 0,
        y_col: int = 1,
        xlabel: str = "x",
        ylabel: str = "y",
        title: str = "Field Profile",
        output_path: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            return ToolResult.fail("matplotlib not installed")

        data_file = Path(data_path)
        if not data_file.exists():
            return ToolResult.fail(f"Data file not found: {data_path}")

        try:
            # Parse whitespace-delimited data, skip comment lines
            xs, ys = [], []
            for line in data_file.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("//"):
                    continue
                cols = line.split()
                if len(cols) > max(x_col, y_col):
                    try:
                        xs.append(float(cols[x_col]))
                        ys.append(float(cols[y_col]))
                    except ValueError:
                        continue

            if not xs:
                return ToolResult.fail("No numeric data found in file")

            fig, ax = plt.subplots(figsize=(8, 5))
            ax.plot(xs, ys, linewidth=1.5, color="steelblue")
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            ax.set_title(title)
            ax.grid(True, alpha=0.3)

            if output_path is None:
                output_path = str(data_file.parent / (data_file.stem + "_plot.png"))

            fig.savefig(output_path, dpi=150, bbox_inches="tight")
            plt.close(fig)

            return ToolResult.ok(data={"output_path": output_path, "points": len(xs)})

        except Exception as exc:
            return ToolResult.fail(f"Plot generation failed: {exc}")
