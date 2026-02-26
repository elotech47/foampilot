"""Write a complete OpenFOAM dictionary file."""

from pathlib import Path
from typing import Any

import structlog

from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)


class WriteFoamFileTool(Tool):
    """Write or overwrite a complete OpenFOAM dictionary file with given content."""

    name = "write_foam_file"
    description = (
        "Write a complete OpenFOAM dictionary file to disk. "
        "Use this when you need to create or fully replace a file. "
        "For targeted edits to an existing file, prefer edit_foam_dict."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to write the file",
            },
            "content": {
                "type": "string",
                "description": "Complete file content in OpenFOAM dictionary format",
            },
        },
        "required": ["path", "content"],
    }
    permission_level = PermissionLevel.NOTIFY

    def execute(self, path: str, content: str, **kwargs: Any) -> ToolResult:
        file_path = Path(path)
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            existed = file_path.exists()
            file_path.write_text(content)
            action = "overwritten" if existed else "created"
            log.info("foam_file_written", path=path, action=action, bytes=len(content))
            return ToolResult.ok(
                data={
                    "path": path,
                    "action": action,
                    "bytes_written": len(content),
                }
            )
        except Exception as exc:
            return ToolResult.fail(f"Failed to write {path}: {exc}")
