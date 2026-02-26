"""The fundamental FoamPilot agent loop.

Implements the core decide → act → observe → repeat cycle.
Handles tool dispatch, token tracking, compaction, and permission checks.
"""

from dataclasses import dataclass
from typing import Any

import structlog
from anthropic import Anthropic
from anthropic.types import Message, ToolUseBlock

from foampilot import config
from foampilot.core.compaction import compact_conversation
from foampilot.core.permissions import PermissionChecker, PermissionDeniedError
from foampilot.core.token_tracker import TokenTracker

log = structlog.get_logger(__name__)


@dataclass
class AgentLoopResult:
    """Final result returned when the agent loop exits."""

    final_response: str
    turn_count: int
    token_summary: dict
    stopped_reason: str  # "end_turn" | "max_turns" | "error" | "permission_denied"


class AgentLoop:
    """Core agent loop that manages the LLM ↔ tool ↔ message cycle.

    Args:
        system_prompt: The system prompt injected at the start of every request.
        tools: A dict mapping tool name → Tool instance.
        client: Anthropic API client (created from config if not provided).
        permission_checker: Permission checker (created from config if not provided).
        approval_callback: Called when APPROVE-level tool needs confirmation.
            Receives (tool_name, tool_input) and must return True to proceed.
        event_callback: Optional callable for UI event streaming.
            Called with event dicts: {"type": ..., "data": ...}
    """

    def __init__(
        self,
        system_prompt: str,
        tools: dict[str, Any],
        client: Anthropic | None = None,
        permission_checker: PermissionChecker | None = None,
        approval_callback: Any | None = None,
        event_callback: Any | None = None,
    ) -> None:
        self._system_prompt = system_prompt
        self._tools = tools
        self._client = client or Anthropic(api_key=config.ANTHROPIC_API_KEY)
        self._permission = permission_checker or PermissionChecker()
        self._approval_callback = approval_callback
        self._event_cb = event_callback
        self._token_tracker = TokenTracker()

    def _emit(self, event_type: str, data: dict) -> None:
        if self._event_cb:
            self._event_cb({"type": event_type, "data": data})

    def _anthropic_tools(self) -> list[dict]:
        return [t.to_anthropic_tool() for t in self._tools.values()]

    def _call_llm(self, messages: list[dict], turn: int) -> Message:
        response = self._client.messages.create(
            model=config.MODEL,
            max_tokens=8192,
            system=self._system_prompt,
            tools=self._anthropic_tools(),
            messages=messages,
        )
        self._token_tracker.record(
            turn=turn,
            model=config.MODEL,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        return response

    def _execute_tool(self, tool_use: ToolUseBlock, messages: list[dict]) -> dict:
        """Execute a single tool call and return the tool_result message dict."""
        tool_name = tool_use.name
        tool_input = tool_use.input

        tool = self._tools.get(tool_name)
        if tool is None:
            result_content = f"Error: Unknown tool '{tool_name}'"
            self._emit("tool_error", {"tool": tool_name, "error": result_content})
            return {
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result_content,
                "is_error": True,
            }

        # Permission check
        if self._permission.requires_approval(tool.permission_level):
            self._emit("approval_required", {"tool": tool_name, "input": tool_input})
            approved = True
            if self._approval_callback:
                approved = self._approval_callback(tool_name, tool_input)
            if not approved:
                raise PermissionDeniedError(f"User denied execution of tool '{tool_name}'")

        if self._permission.should_notify(tool.permission_level):
            self._emit("tool_notify", {"tool": tool_name, "input": tool_input})

        self._emit("tool_call", {"tool": tool_name, "input": tool_input})

        result = tool.execute(**tool_input)

        self._emit("tool_result", {"tool": tool_name, "success": result.success, "data": result.data})

        content = result.data if result.success else f"Error: {result.error}"
        if isinstance(content, dict):
            import json
            content = json.dumps(content)

        return {
            "type": "tool_result",
            "tool_use_id": tool_use.id,
            "content": str(content),
            "is_error": not result.success,
        }

    def run(self, user_message: str, initial_messages: list[dict] | None = None) -> AgentLoopResult:
        """Run the agent loop until the LLM stops calling tools or limits are hit.

        Args:
            user_message: The initial user request.
            initial_messages: Optional prior conversation to resume from.

        Returns:
            AgentLoopResult with final response and statistics.
        """
        messages: list[dict] = list(initial_messages or [])
        messages.append({"role": "user", "content": user_message})

        turn = 0
        final_response = ""
        stopped_reason = "end_turn"

        while turn < config.MAX_TURNS:
            turn += 1
            log.info("agent_turn_start", turn=turn)

            # Compact if context is getting large
            if self._token_tracker.should_compact() and len(messages) > 1:
                log.info("compaction_triggered", turn=turn)
                self._emit("compaction", {"turn": turn})
                messages = compact_conversation(messages, client=self._client)

            try:
                response = self._call_llm(messages, turn)
            except Exception as exc:
                log.error("llm_call_failed", turn=turn, error=str(exc))
                stopped_reason = "error"
                final_response = f"LLM call failed: {exc}"
                break

            self._emit("llm_response", {
                "turn": turn,
                "stop_reason": response.stop_reason,
                "has_tool_calls": any(isinstance(b, ToolUseBlock) for b in response.content),
            })

            # Extract text content and tool calls
            text_blocks = [b for b in response.content if hasattr(b, "text")]
            tool_use_blocks = [b for b in response.content if isinstance(b, ToolUseBlock)]

            if text_blocks:
                final_response = text_blocks[-1].text  # type: ignore[attr-defined]

            # Append assistant message
            messages.append({"role": "assistant", "content": response.content})

            # No tool calls → agent is done
            if not tool_use_blocks or response.stop_reason == "end_turn":
                stopped_reason = "end_turn"
                break

            # Execute all tool calls, collect results
            tool_results = []
            try:
                for tool_use in tool_use_blocks:
                    result_dict = self._execute_tool(tool_use, messages)
                    tool_results.append(result_dict)
            except PermissionDeniedError as exc:
                log.warning("permission_denied", error=str(exc))
                stopped_reason = "permission_denied"
                final_response = str(exc)
                break

            # Append tool results as user message
            messages.append({"role": "user", "content": tool_results})

        else:
            stopped_reason = "max_turns"
            log.warning("max_turns_reached", max_turns=config.MAX_TURNS)

        self._emit("agent_done", {
            "stopped_reason": stopped_reason,
            "turns": turn,
            **self._token_tracker.summary(),
        })

        return AgentLoopResult(
            final_response=final_response,
            turn_count=turn,
            token_summary=self._token_tracker.summary(),
            stopped_reason=stopped_reason,
        )
