"""Read arbitrary files from the filesystem."""

from pathlib import Path
from typing import Any

from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult

_MAX_CHARS = 10_000  # Limit raw file content to prevent context overflow


class ReadFileTool(Tool):
    """Read a text file from the filesystem and return its content."""

    name = "read_file"
    description = (
        "Read a text file from the filesystem. "
        "For OpenFOAM dictionary files, prefer read_foam_file for structured parsing. "
        "Returns raw text content, truncated to 10,000 characters if needed."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file",
            },
            "start_line": {
                "type": "integer",
                "description": "First line to read (1-indexed, default: 1)",
                "default": 1,
            },
            "num_lines": {
                "type": "integer",
                "description": "Number of lines to read (default: all)",
            },
        },
        "required": ["path"],
    }
    permission_level = PermissionLevel.AUTO

    def execute(
        self,
        path: str,
        start_line: int = 1,
        num_lines: int | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        file_path = Path(path)
        if not file_path.exists():
            return ToolResult.fail(f"File not found: {path}")
        if not file_path.is_file():
            return ToolResult.fail(f"Not a file: {path}")

        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            total_lines = len(lines)

            start = max(0, start_line - 1)
            end = (start + num_lines) if num_lines else total_lines
            selected = lines[start:end]
            content = "\n".join(selected)

            truncated = False
            if len(content) > _MAX_CHARS:
                content = content[:_MAX_CHARS]
                truncated = True

            return ToolResult.ok(
                data={
                    "path": path,
                    "content": content,
                    "total_lines": total_lines,
                    "lines_shown": f"{start + 1}-{min(end, total_lines)}",
                    "truncated": truncated,
                },
                token_hint=len(content) // 4,
            )
        except Exception as exc:
            return ToolResult.fail(f"Failed to read {path}: {exc}")
