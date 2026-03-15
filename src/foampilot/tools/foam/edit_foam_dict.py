"""Surgical edits to OpenFOAM dictionary entries."""

import json
import re
from pathlib import Path
from typing import Any

import structlog

from foampilot.core.paths import resolve_host_path
from foampilot.core.permissions import PermissionLevel
from foampilot.index.parser import FoamFileParser, parse_foam_file
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)

# String patterns that must NOT be quoted in OpenFOAM dict files.
# These are OpenFOAM-specific syntactic constructs, not word strings.
_NO_QUOTE_PATTERNS = [
    re.compile(r"^\["),              # Dimension sets:  [0 1 -1 0 0 0 0] 1e-5
    re.compile(r"^uniform\s+"),      # uniform (0 0 0)  or  uniform 0
    re.compile(r"^nonuniform\s+"),   # nonuniform fields
    re.compile(r"^\("),              # Raw vector/list: (0 0 0)
    re.compile(r"^[0-9eE+\-.]+$"),  # Plain numbers as strings
]

# Match bracket-vector notation [x, y, z] used by LLMs but invalid in OpenFOAM.
# Only matches brackets whose content contains at least one comma — this preserves
# OpenFOAM dimension sets like [0 2 -1 0 0 0 0] which must stay as brackets.
_BRACKET_VEC_RE = re.compile(r"\[([^\[\]]*,[^\[\]]*)\]")


def _normalize_foam_string(value: str) -> str:
    """Normalise LLM-produced OpenFOAM strings to valid syntax.

    Converts ``[x, y, z]`` → ``(x y z)`` so vectors are written correctly.
    OpenFOAM uses parentheses for vectors/lists, not brackets.
    """
    def _to_paren(m: re.Match) -> str:
        inner = re.sub(r",\s*", " ", m.group(1)).strip()
        return f"({inner})"

    return _BRACKET_VEC_RE.sub(_to_paren, value)


def _foam_value_to_str(value: Any) -> str:
    """Convert a Python value back to OpenFOAM dictionary syntax."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "( " + " ".join(_foam_value_to_str(v) for v in value) + " )"
    if isinstance(value, str):
        # Normalise bracket-vectors to parentheses first
        value = _normalize_foam_string(value)
        # Check if this value should NOT be quoted (OpenFOAM native syntax)
        stripped = value.strip()
        for pattern in _NO_QUOTE_PATTERNS:
            if pattern.match(stripped):
                return value  # Return as-is — quoting would break OpenFOAM parsing
        # Only quote plain word/label strings that contain spaces or special chars
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
        "'boundaryField.inlet.value'). "
        "Set action='rename_key' to rename a top-level block (e.g. PIMPLE→PISO). "
        "Set action='delete_key' to remove a key entirely."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the OpenFOAM dictionary file.",
            },
            "key_path": {
                "type": "string",
                "description": "Dot-notation path to the key (e.g. 'SIMPLE.nNonOrthogonalCorrectors')",
            },
            "new_value": {
                "description": "New value to set (string, number, boolean, or list). "
                "For action='rename_key', this is the new key name. "
                "For action='delete_key', this is ignored.",
            },
            "action": {
                "type": "string",
                "enum": ["set", "rename_key", "delete_key"],
                "description": "Action to perform. Default 'set' edits the value. "
                "'rename_key' renames the key itself (e.g. PIMPLE→PISO). "
                "'delete_key' removes the key and its value/block.",
                "default": "set",
            },
        },
        "required": ["path", "key_path"],
    }
    permission_level = PermissionLevel.NOTIFY

    def execute(self, path: str, key_path: str, new_value: Any = None, action: str = "set", **kwargs: Any) -> ToolResult:
        if action == "rename_key":
            return self._rename_key(path, key_path, new_value)
        if action == "delete_key":
            return self._delete_key(path, key_path)
        if new_value is None:
            return ToolResult.fail("new_value is required for action='set'")
        return self._set_value(path, key_path, new_value)

    def _rename_key(self, path: str, key_path: str, new_key_name: Any) -> ToolResult:
        """Rename a key in the file text (e.g. PIMPLE → PISO)."""
        if not new_key_name or not isinstance(new_key_name, str):
            return ToolResult.fail("new_value must be the new key name (string) for rename_key")

        file_path = resolve_host_path(path)
        if not file_path.exists():
            return ToolResult.fail(f"File not found: {path} (resolved to {file_path})")

        text = file_path.read_text()
        old_key = key_path.split(".")[-1]

        # Match the key as a standalone word (block header or key-value entry)
        pattern = rf"\b{re.escape(old_key)}\b"
        new_text, count = re.subn(pattern, new_key_name, text, count=1)

        if count == 0:
            return ToolResult.fail(f"Key '{old_key}' not found in {path}")

        file_path.write_text(new_text)
        log.info("foam_dict_key_renamed", path=path, old_key=old_key, new_key=new_key_name)
        return ToolResult.ok(data={"path": path, "old_key": old_key, "new_key": new_key_name, "action": "rename_key"})

    def _delete_key(self, path: str, key_path: str) -> ToolResult:
        """Delete a key-value entry or block from the file."""
        file_path = resolve_host_path(path)
        if not file_path.exists():
            return ToolResult.fail(f"File not found: {path} (resolved to {file_path})")

        text = file_path.read_text()
        leaf_key = key_path.split(".")[-1]

        # Strip quotes for matching
        search_key = leaf_key
        if search_key.startswith('"') and search_key.endswith('"'):
            search_key = search_key[1:-1]

        # Try to delete a "key value;" line
        quoted_pattern = rf'^\s*"{re.escape(search_key)}"\s+[^;{{}}]*;\s*$'
        plain_pattern = rf"^\s*\b{re.escape(search_key)}\b\s+[^;{{}}]*;\s*$"
        new_text = re.sub(quoted_pattern, "", text, count=1, flags=re.MULTILINE)
        if new_text == text:
            new_text = re.sub(plain_pattern, "", text, count=1, flags=re.MULTILINE)

        if new_text == text:
            return ToolResult.fail(f"Key '{leaf_key}' not found in {path} for deletion")

        file_path.write_text(new_text)
        log.info("foam_dict_key_deleted", path=path, key=leaf_key)
        return ToolResult.ok(data={"path": path, "key_path": key_path, "action": "delete_key"})

    def _set_value(self, path: str, key_path: str, new_value: Any) -> ToolResult:
        file_path = resolve_host_path(path)
        if not file_path.exists():
            return ToolResult.fail(f"File not found: {path} (resolved to {file_path})")

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
        leaf_key = key_path.split(".")[-1]
        foam_val = _foam_value_to_str(new_value)

        # Strip surrounding quotes from the key (OpenFOAM regex keys like
        # "(U|k|epsilon|omega|R|nuTilda)" are stored with quotes in parsed form).
        search_key = leaf_key
        if search_key.startswith('"') and search_key.endswith('"'):
            search_key = search_key[1:-1]

        # Try quoted form first (as it appears in the actual file text)
        quoted_key = f'"{search_key}"'
        pattern_quoted = rf'({re.escape(quoted_key)}\s+)[^;{{}}]+?(;)'
        new_text, count = re.subn(pattern_quoted, rf"\g<1>{foam_val}\2", text, count=1)

        if count == 0:
            # Try unquoted (plain keyword)
            pattern_plain = rf"(\b{re.escape(search_key)}\s+)[^;{{}}]+?(;)"
            new_text, count = re.subn(pattern_plain, rf"\g<1>{foam_val}\2", text, count=1)

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
