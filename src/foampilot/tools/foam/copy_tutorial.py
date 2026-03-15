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
                               "(e.g., 'incompressibleFluid/cavity')",
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

        src_files = [f for f in src.rglob("*") if f.is_file()]
        if not src_files:
            return ToolResult.fail(
                f"Tutorial directory exists but contains no files: {src}. "
                f"This is a stub/skeleton directory. "
                f"Use search_tutorials to find a tutorial with actual content."
            )

        if self._case_dir is None:
            return ToolResult.fail("CopyTutorialTool has no case_dir — internal configuration error.")

        dest = self._case_dir
        dest.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copytree(str(src), str(dest), dirs_exist_ok=True)

            copied_names = sorted(str(f.relative_to(src)) for f in src_files)
            log.info(
                "tutorial_copied",
                src=str(src),
                dest=str(dest),
                files=len(copied_names),
                file_list=copied_names,
            )

            return ToolResult.ok(
                data={
                    "source": str(src),
                    "destination": str(dest),
                    "files_copied": len(copied_names),
                    "files": copied_names[:50],
                }
            )
        except Exception as exc:
            return ToolResult.fail(f"Failed to copy tutorial: {exc}")
