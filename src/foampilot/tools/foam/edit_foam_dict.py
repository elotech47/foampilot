"""Surgical edits to OpenFOAM dictionary entries."""

import json
from pathlib import Path
from typing import Any

import structlog

from foampilot.core.permissions import PermissionLevel
from foampilot.index.parser import FoamFileParser, parse_foam_file
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)


def _foam_value_to_str(value: Any) -> str:
    """Convert a Python value back to OpenFOAM dictionary syntax."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "( " + " ".join(_foam_value_to_str(v) for v in value) + " )"
    if isinstance(value, str):
        # Quote if it contains spaces or special characters
        if " " in value or any(c in value for c in "(){};\n"):
            return f'"{value}"'
        return value
    return str(value)


class EditFoamDictTool(Tool):
    """Edit a specific key in an OpenFOAM dictionary file using dot-notation path.

    Example: key_path="SIMPLE.nNonOrthogonalCorrectors", new_value=2
    """

    name = "edit_foam_dict"
    description = (
        "Edit a specific key-value entry in an OpenFOAM dictionary file. "
        "Use dot-notation for nested keys (e.g., 'SIMPLE.nNonOrthogonalCorrectors', "
        "'boundaryField.inlet.value'). Returns the before and after values."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the OpenFOAM dictionary file",
            },
            "key_path": {
                "type": "string",
                "description": "Dot-notation path to the key (e.g. 'SIMPLE.nNonOrthogonalCorrectors')",
            },
            "new_value": {
                "description": "New value to set (string, number, boolean, or list)",
            },
        },
        "required": ["path", "key_path", "new_value"],
    }
    permission_level = PermissionLevel.NOTIFY

    def execute(self, path: str, key_path: str, new_value: Any, **kwargs: Any) -> ToolResult:
        file_path = Path(path)
        if not file_path.exists():
            return ToolResult.fail(f"File not found: {path}")

        try:
            foam = parse_foam_file(file_path)
        except Exception as exc:
            return ToolResult.fail(f"Failed to parse {path}: {exc}")

        old_value = foam.get(key_path)

        # Apply the edit
        foam.set(key_path, new_value)

        # Write back using text replacement for safety
        try:
            new_text = self._write_back(file_path, key_path, new_value, foam)
            file_path.write_text(new_text)
        except Exception as exc:
            log.warning("edit_foam_dict_write_fallback", error=str(exc))
            # Fallback: rewrite the entire file from parsed structure
            try:
                self._rewrite_file(file_path, foam)
            except Exception as exc2:
                return ToolResult.fail(f"Failed to write changes to {path}: {exc2}")

        log.info("foam_dict_edited", path=path, key=key_path, old=old_value, new=new_value)

        return ToolResult.ok(
            data={
                "path": path,
                "key_path": key_path,
                "old_value": old_value,
                "new_value": new_value,
            }
        )

    def _write_back(self, file_path: Path, key_path: str, new_value: Any, foam) -> str:
        """Attempt to do a surgical text replacement for the changed key."""
        import re

        text = file_path.read_text()
        # Get the leaf key name
        leaf_key = key_path.split(".")[-1]
        foam_val = _foam_value_to_str(new_value)

        # Try to replace: "<leaf_key>  <anything>;" with "<leaf_key>  <new_value>;"
        pattern = rf"(\b{re.escape(leaf_key)}\s+)[^;{{}}]+?(;)"
        replacement = rf"\g<1>{foam_val}\2"
        new_text, count = re.subn(pattern, replacement, text, count=1)

        if count == 0:
            raise ValueError(f"Key '{leaf_key}' not found in file text for regex replacement")

        return new_text

    def _rewrite_file(self, file_path: Path, foam) -> None:
        """Fallback: reconstruct the file. Preserves comments header, rewrites body."""
        # This is a simple reconstruction — will lose comments in the body
        lines = [
            "/*--------------------------------*- C++ -*----------------------------------*\\",
            "  FoamPilot-generated file",
            "\\*---------------------------------------------------------------------------*/",
            f"FoamFile",
            "{",
        ]
        for k, v in foam.foam_file.items():
            lines.append(f"    {k:<12} {v};")
        lines.append("}")
        lines.append("// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //")
        lines.append("")
        lines.extend(self._dict_to_lines(foam.data, indent=0))
        lines.append("")
        lines.append("// ************************************************************************* //")
        file_path.write_text("\n".join(lines))

    def _dict_to_lines(self, d: dict, indent: int) -> list[str]:
        pad = "    " * indent
        lines = []
        for k, v in d.items():
            if isinstance(v, dict):
                lines.append(f"{pad}{k}")
                lines.append(f"{pad}{{")
                lines.extend(self._dict_to_lines(v, indent + 1))
                lines.append(f"{pad}}}")
            elif isinstance(v, list):
                lines.append(f"{pad}{k:<20} {_foam_value_to_str(v)};")
            else:
                lines.append(f"{pad}{k:<20} {_foam_value_to_str(v)};")
        return lines
