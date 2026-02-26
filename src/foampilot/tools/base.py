"""Abstract base tool class with permission levels and structured return type."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from foampilot.core.permissions import PermissionLevel


@dataclass
class ToolResult:
    """Structured return type for all tools.

    Tools NEVER raise exceptions — they return ToolResult(success=False, error=...).
    The agent loop feeds errors back to the LLM for diagnosis and retry.
    """

    success: bool
    data: dict | str           # Structured data or summary text
    error: str | None = None   # Error message if failed
    token_hint: int = 0        # Approximate token cost of this result (for budgeting)

    @classmethod
    def ok(cls, data: dict | str, token_hint: int = 0) -> "ToolResult":
        return cls(success=True, data=data, token_hint=token_hint)

    @classmethod
    def fail(cls, error: str) -> "ToolResult":
        return cls(success=False, data={}, error=error)


class Tool(ABC):
    """Abstract base class for all FoamPilot tools.

    Subclasses must define:
    - name: Tool name as seen by the LLM.
    - description: Human/LLM-readable description.
    - input_schema: JSON Schema dict for the tool's parameters.
    - permission_level: AUTO | NOTIFY | APPROVE
    - execute(): The actual implementation.
    """

    name: str = ""
    description: str = ""
    input_schema: dict = {}
    permission_level: PermissionLevel = PermissionLevel.AUTO

    @abstractmethod
    def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool and return a structured result.

        Never raises exceptions — catch all errors and return ToolResult.fail().
        """
        ...

    def to_anthropic_tool(self) -> dict:
        """Convert to the Anthropic API tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
