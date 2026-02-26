"""Post-processing data extraction from OpenFOAM results."""

import re
from pathlib import Path
from typing import Any

import structlog

from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)


class ExtractDataTool(Tool):
    """Extract post-processing data from OpenFOAM result directories.

    Currently supports: listing available time directories, reading postProcessing/ output.
    """

    name = "extract_data"
    description = (
        "Extract post-processing data from an OpenFOAM case. "
        "Can list available time directories, read force coefficients, "
        "residuals files, and other postProcessing output."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "case_dir": {
                "type": "string",
                "description": "Absolute path to the case directory",
            },
            "operation": {
                "type": "string",
                "enum": ["list_times", "read_forces", "read_residuals", "list_post_processing"],
                "description": "What data to extract",
            },
            "function_object": {
                "type": "string",
                "description": "For read_forces: name of the forces functionObject",
                "default": "forces",
            },
        },
        "required": ["case_dir", "operation"],
    }
    permission_level = PermissionLevel.AUTO

    def execute(
        self,
        case_dir: str,
        operation: str,
        function_object: str = "forces",
        **kwargs: Any,
    ) -> ToolResult:
        case_path = Path(case_dir)
        if not case_path.exists():
            return ToolResult.fail(f"Case directory not found: {case_dir}")

        try:
            if operation == "list_times":
                return self._list_times(case_path)
            elif operation == "list_post_processing":
                return self._list_post_processing(case_path)
            elif operation == "read_forces":
                return self._read_forces(case_path, function_object)
            elif operation == "read_residuals":
                return self._read_residuals(case_path)
            else:
                return ToolResult.fail(f"Unknown operation: {operation}")
        except Exception as exc:
            return ToolResult.fail(f"Data extraction failed: {exc}")

    def _list_times(self, case_path: Path) -> ToolResult:
        """List available time directories."""
        times = []
        for d in sorted(case_path.iterdir()):
            if d.is_dir():
                try:
                    float(d.name)
                    times.append(d.name)
                except ValueError:
                    pass
        return ToolResult.ok(data={"time_directories": times, "count": len(times)})

    def _list_post_processing(self, case_path: Path) -> ToolResult:
        """List available post-processing function objects."""
        pp_dir = case_path / "postProcessing"
        if not pp_dir.exists():
            return ToolResult.ok(data={"function_objects": [], "note": "No postProcessing directory found"})
        objects = [d.name for d in pp_dir.iterdir() if d.is_dir()]
        return ToolResult.ok(data={"function_objects": objects})

    def _read_forces(self, case_path: Path, function_object: str) -> ToolResult:
        """Read force coefficient data from postProcessing."""
        pp_dir = case_path / "postProcessing" / function_object
        if not pp_dir.exists():
            return ToolResult.fail(f"No postProcessing/{function_object} directory found")

        data_files = list(pp_dir.rglob("*.dat")) + list(pp_dir.rglob("*.csv"))
        if not data_files:
            return ToolResult.fail(f"No data files found in postProcessing/{function_object}")

        # Read the last data file
        data_file = sorted(data_files)[-1]
        lines = data_file.read_text().splitlines()
        # Return last 20 rows
        return ToolResult.ok(
            data={
                "file": str(data_file.relative_to(case_path)),
                "last_rows": lines[-20:] if len(lines) > 20 else lines,
                "total_rows": len(lines),
            }
        )

    def _read_residuals(self, case_path: Path) -> ToolResult:
        """Read residuals from postProcessing/residuals if available."""
        pp_dir = case_path / "postProcessing" / "residuals"
        if not pp_dir.exists():
            # Fallback: find any solver log
            logs = list(case_path.glob("log.*")) + list(case_path.glob("*.log"))
            if logs:
                from foampilot.tools.foam.parse_log import parse_solver_log
                text = sorted(logs)[-1].read_text(errors="replace")
                return ToolResult.ok(data=parse_solver_log(text))
            return ToolResult.fail("No residuals data found")

        data_files = list(pp_dir.rglob("*.dat"))
        if not data_files:
            return ToolResult.fail("No residual data files found")

        data_file = sorted(data_files)[-1]
        lines = data_file.read_text().splitlines()
        return ToolResult.ok(
            data={
                "file": str(data_file.relative_to(case_path)),
                "last_rows": lines[-50:],
                "total_rows": len(lines),
            }
        )
