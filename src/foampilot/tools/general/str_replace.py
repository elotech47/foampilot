"""Generic string replacement in files."""

from pathlib import Path
from typing import Any

import structlog

from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)


class StrReplaceTool(Tool):
    """Replace a specific string in a file with a new string.

    The old_string must appear exactly once in the file to ensure a safe, targeted edit.
    Use replace_all=true to replace all occurrences.
    """

    name = "str_replace"
    description = (
        "Replace a specific string in a file with a new string. "
        "The old_string must be unique in the file (or use replace_all=true). "
        "For OpenFOAM dictionary edits, prefer edit_foam_dict instead."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file"},
            "old_string": {"type": "string", "description": "The exact text to replace"},
            "new_string": {"type": "string", "description": "The replacement text"},
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences (default: false)",
                "default": False,
            },
        },
        "required": ["path", "old_string", "new_string"],
    }
    permission_level = PermissionLevel.NOTIFY

    def execute(
        self,
        path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        file_path = Path(path)
        if not file_path.exists():
            return ToolResult.fail(f"File not found: {path}")

        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            count = text.count(old_string)

            if count == 0:
                return ToolResult.fail(
                    f"String not found in {path}. "
                    "Check for exact whitespace, quotes, and newlines."
                )
            if count > 1 and not replace_all:
                return ToolResult.fail(
                    f"old_string appears {count} times in {path}. "
                    "Provide more context to make it unique, or set replace_all=true."
                )

            if replace_all:
                new_text = text.replace(old_string, new_string)
                replacements = count
            else:
                new_text = text.replace(old_string, new_string, 1)
                replacements = 1

            file_path.write_text(new_text)
            log.info("str_replaced", path=path, replacements=replacements)

            return ToolResult.ok(
                data={"path": path, "replacements_made": replacements}
            )
        except Exception as exc:
            return ToolResult.fail(f"Failed to edit {path}: {exc}")
