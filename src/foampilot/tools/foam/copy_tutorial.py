"""Clone a tutorial case as a starting template for a new simulation."""

import shutil
from pathlib import Path
from typing import Any

import structlog

from foampilot import config
from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)


class CopyTutorialTool(Tool):
    """Copy an OpenFOAM tutorial case to a new working directory."""

    name = "copy_tutorial"
    description = (
        "Copy an OpenFOAM tutorial case to a new working directory as the starting point "
        "for a simulation. The tutorial_path is the relative path from the tutorials root "
        "(as returned by search_tutorials)."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "tutorial_path": {
                "type": "string",
                "description": "Relative path to the tutorial case from the tutorials root "
                               "(e.g., 'incompressibleFluid/cavity')",
            },
            "destination": {
                "type": "string",
                "description": "Absolute path to the destination directory for the case",
            },
        },
        "required": ["tutorial_path", "destination"],
    }
    permission_level = PermissionLevel.NOTIFY

    def execute(self, tutorial_path: str, destination: str, **kwargs: Any) -> ToolResult:
        tutorials_root = config.TUTORIALS_DIR
        src = tutorials_root / tutorial_path

        if not src.exists():
            return ToolResult.fail(
                f"Tutorial not found: {src}. "
                f"Tutorials root is {tutorials_root}."
            )

        dest = Path(destination)
        if dest.exists():
            return ToolResult.fail(
                f"Destination already exists: {dest}. Remove it first or choose a different path."
            )

        try:
            shutil.copytree(str(src), str(dest))
            # List copied files
            copied = []
            for f in dest.rglob("*"):
                if f.is_file():
                    copied.append(str(f.relative_to(dest)))

            log.info("tutorial_copied", src=str(src), dest=str(dest), files=len(copied))

            return ToolResult.ok(
                data={
                    "source": str(src),
                    "destination": str(dest),
                    "files_copied": len(copied),
                    "files": copied[:50],  # Limit list to prevent context overflow
                }
            )
        except Exception as exc:
            return ToolResult.fail(f"Failed to copy tutorial: {exc}")
