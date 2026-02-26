"""Write arbitrary files to the filesystem."""

from pathlib import Path
from typing import Any

import structlog

from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)


class WriteFileTool(Tool):
    """Write a text file to the filesystem."""

    name = "write_file"
    description = "Write text content to a file. Creates parent directories if needed."
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to write"},
            "content": {"type": "string", "description": "Text content to write"},
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
            log.info("file_written", path=path, action="overwritten" if existed else "created")
            return ToolResult.ok(
                data={
                    "path": path,
                    "bytes_written": len(content),
                    "action": "overwritten" if existed else "created",
                }
            )
        except Exception as exc:
            return ToolResult.fail(f"Failed to write {path}: {exc}")
