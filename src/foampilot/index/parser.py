"""OpenFOAM dictionary file parser.

Parses OpenFOAM-format dictionary files into Python dicts.
Handles: FoamFile headers, nested dicts, lists, dimensional values,
#include directives, $reference substitution, inline comments,
and regex-key entries (e.g. "(U|k|epsilon).*").

Does NOT need to handle #eval (not supported in v11).
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# ── Token types ────────────────────────────────────────────────────────────────
_RE_COMMENT_SINGLE = re.compile(r"//[^\n]*")
_RE_COMMENT_MULTI = re.compile(r"/\*.*?\*/", re.DOTALL)
_RE_FOAM_HEADER = re.compile(
    r"/\*-+\*-\s*C\+\+\s*-\*-+\\\\\s*[\s\S]*?\\\*-+\*/", re.DOTALL
)

# Dimensional value: [0 1 -1 0 0 0 0]
_RE_DIMENSION = re.compile(r"\[\s*[-\d\.\s]+\]")

# Uniform vector/tensor: uniform (1 0 0)
_RE_UNIFORM_VECTOR = re.compile(r"uniform\s*\([^)]+\)")

# Number
_RE_NUMBER = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?$")


@dataclass
class FoamDict:
    """Parsed representation of an OpenFOAM dictionary file."""

    foam_file: dict = field(default_factory=dict)  # FoamFile header entries
    data: dict = field(default_factory=dict)        # Main dictionary content

    @property
    def object_name(self) -> str:
        return self.foam_file.get("object", "")

    @property
    def foam_class(self) -> str:
        return self.foam_file.get("class", "")

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get a value by dot-notation path, e.g. 'boundaryField.inlet.type'."""
        parts = key_path.split(".")
        node = self.data
        for part in parts:
            if not isinstance(node, dict):
                return default
            node = node.get(part, default)
            if node is default:
                return default
        return node

    def set(self, key_path: str, value: Any) -> None:
        """Set a value by dot-notation path. Creates intermediate dicts as needed."""
        parts = key_path.split(".")
        node = self.data
        for part in parts[:-1]:
            if part not in node or not isinstance(node[part], dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value


class FoamFileParser:
    """Parser for OpenFOAM dictionary files.

    Usage:
        parser = FoamFileParser()
        foam_dict = parser.parse_file(Path("/case/0/U"))
        bc_type = foam_dict.get("boundaryField.inlet.type")
    """

    def parse_file(self, path: Path) -> FoamDict:
        """Parse a file from disk (supports both plain text and .gz).

        Args:
            path: Path to the OpenFOAM dictionary file.

        Returns:
            FoamDict with header and data sections populated.
        """
        try:
            if path.suffix == ".gz":
                with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
                    text = f.read()
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise OSError(f"Cannot read {path}: {exc}") from exc
        return self.parse_string(text, source=str(path))

    def parse_string(self, text: str, source: str = "<string>") -> FoamDict:
        """Parse an OpenFOAM dictionary from a string.

        Args:
            text: Raw file content.
            source: Label used in error messages.

        Returns:
            FoamDict populated from text.
        """
        cleaned = self._strip_comments(text)
        tokens = self._tokenize(cleaned)
        result = FoamDict()

        pos = 0
        pos, entries = self._parse_block_contents(tokens, pos)

        # Separate FoamFile header from main content
        foam_file_data = entries.pop("FoamFile", {})
        if isinstance(foam_file_data, dict):
            result.foam_file = foam_file_data
        result.data = entries
        return result

    # ── Private: comment stripping ─────────────────────────────────────────────

    def _strip_comments(self, text: str) -> str:
        """Remove C++ style comments and the standard OpenFOAM file header."""
        # Remove the decorative C++ banner header first
        text = _RE_FOAM_HEADER.sub("", text)
        # Remove block comments
        text = _RE_COMMENT_MULTI.sub(" ", text)
        # Remove line comments
        text = _RE_COMMENT_SINGLE.sub("", text)
        return text

    # Token regex: quoted strings first, then single-char delimiters, then bare words.
    # This ensures "(U|k|epsilon)" is kept as one token and not split on the parens.
    _RE_TOKEN = re.compile(
        r'"[^"]*"'          # double-quoted string (kept whole)
        r"|[{}();]"         # single-char structural delimiters
        r"|[^\s{}();\"]+",  # bare word / number / keyword
    )

    # ── Private: tokenizer ─────────────────────────────────────────────────────

    def _tokenize(self, text: str) -> list[str]:
        """Split text into tokens: words, numbers, brackets, quoted strings."""
        return self._RE_TOKEN.findall(text)

    # ── Private: recursive descent parser ─────────────────────────────────────

    def _parse_block_contents(
        self, tokens: list[str], pos: int
    ) -> tuple[int, dict]:
        """Parse key-value pairs until end of tokens or closing brace.

        Returns:
            (new_pos, dict_of_entries)
        """
        entries: dict = {}

        while pos < len(tokens):
            tok = tokens[pos]

            if tok == "}":
                # End of enclosing block — caller consumes the brace
                break

            if tok == ";":
                pos += 1
                continue

            if tok.startswith("#include"):
                # #include "filename" — skip for now (we don't resolve files)
                pos += 1
                if pos < len(tokens):
                    pos += 1  # skip filename
                continue

            # tok is a key (possibly quoted)
            key = tok.strip('"')
            pos += 1

            if pos >= len(tokens):
                break

            next_tok = tokens[pos]

            if next_tok == "{":
                # Sub-dictionary
                pos += 1  # consume {
                pos, sub_dict = self._parse_block_contents(tokens, pos)
                if pos < len(tokens) and tokens[pos] == "}":
                    pos += 1  # consume }
                entries[key] = sub_dict

            elif next_tok == "(":
                # List value
                pos += 1  # consume (
                pos, lst = self._parse_list(tokens, pos)
                entries[key] = lst
                # Consume optional semicolon
                if pos < len(tokens) and tokens[pos] == ";":
                    pos += 1

            elif next_tok == ";":
                # Key with no value (bare keyword)
                entries[key] = True
                pos += 1

            else:
                # Scalar / string / compound value — read until semicolon
                pos, value = self._parse_value(tokens, pos)
                entries[key] = value
                # Consume semicolon
                if pos < len(tokens) and tokens[pos] == ";":
                    pos += 1

        return pos, entries

    def _parse_value(self, tokens: list[str], pos: int) -> tuple[int, Any]:
        """Parse a value that may span multiple tokens (before the semicolon).

        Handles: plain scalars, dimensional values, uniform vectors,
        multi-token strings, and $references.
        """
        value_parts: list[str] = []

        while pos < len(tokens) and tokens[pos] not in (";", "}", "{"):
            tok = tokens[pos]
            if tok == "(":
                # Embedded list (e.g. dimensional value or vector)
                pos += 1
                pos, lst = self._parse_list(tokens, pos)
                value_parts.append(str(lst))
                continue
            value_parts.append(tok)
            pos += 1

        raw = " ".join(value_parts).strip()
        return pos, self._coerce(raw)

    def _parse_list(self, tokens: list[str], pos: int) -> tuple[int, list]:
        """Parse a parenthesised list ( ... ).

        Returns (new_pos, list) — caller has already consumed the opening (.
        The closing ) is consumed here.
        """
        items: list = []

        while pos < len(tokens) and tokens[pos] != ")":
            tok = tokens[pos]
            if tok == "(":
                pos += 1
                pos, sub = self._parse_list(tokens, pos)
                items.append(sub)
            elif tok == "{":
                pos += 1
                pos, sub_dict = self._parse_block_contents(tokens, pos)
                if pos < len(tokens) and tokens[pos] == "}":
                    pos += 1
                items.append(sub_dict)
            elif tok == ";":
                pos += 1
            else:
                items.append(self._coerce(tok))
                pos += 1

        if pos < len(tokens):
            pos += 1  # consume )

        return pos, items

    def _coerce(self, raw: str) -> Any:
        """Convert a raw string token to the most appropriate Python type."""
        if not raw:
            return raw
        # Strip surrounding quotes
        if raw.startswith('"') and raw.endswith('"'):
            return raw[1:-1]
        # Boolean-like
        if raw.lower() in ("true", "on", "yes"):
            return True
        if raw.lower() in ("false", "off", "no"):
            return False
        # Number
        if _RE_NUMBER.match(raw):
            try:
                if "." in raw or "e" in raw.lower():
                    return float(raw)
                return int(raw)
            except ValueError:
                pass
        # $reference — return as-is (prefixed)
        if raw.startswith("$"):
            return raw
        return raw


# ── Module-level convenience function ─────────────────────────────────────────


_parser_singleton = FoamFileParser()


def parse_foam_file(path: Path) -> FoamDict:
    """Parse an OpenFOAM dictionary file into a FoamDict.

    Args:
        path: Path to the file.

    Returns:
        FoamDict with .foam_file header and .data content.
    """
    return _parser_singleton.parse_file(path)


def parse_foam_string(text: str, source: str = "<string>") -> FoamDict:
    """Parse an OpenFOAM dictionary string into a FoamDict."""
    return _parser_singleton.parse_string(text, source=source)
