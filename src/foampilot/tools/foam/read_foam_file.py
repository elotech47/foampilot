"""Read and parse an OpenFOAM dictionary file into structured data."""

from pathlib import Path
from typing import Any

from foampilot.core.permissions import PermissionLevel
from foampilot.index.parser import parse_foam_file
from foampilot.tools.base import Tool, ToolResult


class ReadFoamFileTool(Tool):
    """Parse an OpenFOAM dictionary file and return its structured content."""

    name = "read_foam_file"
    description = (
        "Read and parse an OpenFOAM dictionary file (controlDict, fvSchemes, 0/U, etc.) "
        "into structured JSON. Returns the parsed key-value structure — NOT raw text. "
        "Use this instead of read_file for OpenFOAM dictionary files."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the OpenFOAM dictionary file",
            },
        },
        "required": ["path"],
    }
    permission_level = PermissionLevel.AUTO

    def execute(self, path: str, **kwargs: Any) -> ToolResult:
        file_path = Path(path)
        if not file_path.exists():
            return ToolResult.fail(f"File not found: {path}")
        if not file_path.is_file():
            return ToolResult.fail(f"Not a file: {path}")
        try:
            foam = parse_foam_file(file_path)
            return ToolResult.ok(
                data={
                    "path": str(path),
                    "object": foam.object_name,
                    "class": foam.foam_class,
                    "foam_file": foam.foam_file,
                    "data": foam.data,
                },
                token_hint=min(len(str(foam.data)) // 4, 2000),
            )
        except Exception as exc:
            return ToolResult.fail(f"Failed to parse {path}: {exc}")
