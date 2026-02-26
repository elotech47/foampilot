"""Shared UI event types and display formatting.

The agent loop emits events and the UI subscribes to them.
This decouples the agent from the display.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class EventType(str, Enum):
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_NOTIFY = "tool_notify"
    TOOL_ERROR = "tool_error"
    APPROVAL_REQUIRED = "approval_required"
    LLM_RESPONSE = "llm_response"
    COMPACTION = "compaction"
    AGENT_DONE = "agent_done"
    PHASE_START = "phase_start"
    SESSION_START = "session_start"
    SESSION_COMPLETE = "session_complete"
    SESSION_ERROR = "session_error"


@dataclass
class AgentEvent:
    """An event emitted by the agent loop for UI consumption."""

    type: EventType
    data: dict[str, Any]

    @classmethod
    def from_dict(cls, d: dict) -> "AgentEvent":
        return cls(type=EventType(d["type"]), data=d.get("data", {}))
