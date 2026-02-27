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
    """Copy an OpenFOAM tutorial case into the session's case directory."""

    name = "copy_tutorial"
    description = (
        "Copy an OpenFOAM tutorial case into the working case directory as the starting "
        "point for a simulation. The tutorial_path is the relative path from the tutorials "
        "root (as returned by search_tutorials). The destination is fixed automatically — "
        "do NOT pass a destination parameter."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "tutorial_path": {
                "type": "string",
                "description": "Relative path to the tutorial case from the tutorials root "
                               "(e.g., 'legacy/incompressible/icoFoam/cavity/cavity')",
            },
        },
        "required": ["tutorial_path"],
    }
    permission_level = PermissionLevel.NOTIFY

    def __init__(self, case_dir: Path | None = None) -> None:
        self._case_dir = case_dir

    def execute(self, tutorial_path: str, **kwargs: Any) -> ToolResult:
        tutorials_root = config.TUTORIALS_DIR
        src = tutorials_root / tutorial_path

        if not src.exists():
            return ToolResult.fail(
                f"Tutorial not found: {src}. "
                f"Tutorials root is {tutorials_root}. "
                f"Use search_tutorials to find a valid path."
            )

        if self._case_dir is None:
            return ToolResult.fail("CopyTutorialTool has no case_dir — internal configuration error.")

        dest = self._case_dir
        dest.mkdir(parents=True, exist_ok=True)

        try:
            # dirs_exist_ok=True merges into the pre-created case directory
            # (the orchestrator always creates it before agents run)
            shutil.copytree(str(src), str(dest), dirs_exist_ok=True)

            copied = [str(f.relative_to(dest)) for f in dest.rglob("*") if f.is_file()]
            log.info("tutorial_copied", src=str(src), dest=str(dest), files=len(copied))

            return ToolResult.ok(
                data={
                    "source": str(src),
                    "destination": str(dest),
                    "files_copied": len(copied),
                    "files": copied[:50],
                }
            )
        except Exception as exc:
            return ToolResult.fail(f"Failed to copy tutorial: {exc}")
