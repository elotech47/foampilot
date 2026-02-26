"""Unit tests for the core AgentLoop."""

from unittest.mock import MagicMock

import pytest
from foampilot.core.agent_loop import AgentLoop
from foampilot.core.permissions import PermissionChecker, PermissionLevel
from foampilot.tools.base import PermissionLevel as ToolPermissionLevel, Tool, ToolResult


class _EchoTool(Tool):
    """Simple test tool that echoes its input."""

    name = "echo"
    description = "Echo back the input"
    input_schema = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }
    permission_level = PermissionLevel.AUTO

    def execute(self, message: str, **kwargs) -> ToolResult:
        return ToolResult(success=True, data={"echoed": message})


def _make_client_no_tools(text: str = "Done.") -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    tb = MagicMock()
    tb.text = text
    response.content = [tb]
    client.messages.create.return_value = response
    return client


def test_agent_loop_no_tool_calls(mock_anthropic_client):
    loop = AgentLoop(
        system_prompt="You are a test agent.",
        tools={},
        client=mock_anthropic_client,
    )
    result = loop.run("Hello")
    assert result.stopped_reason == "end_turn"
    assert result.turn_count == 1
    assert result.final_response == "Simulation complete."


def test_agent_loop_tracks_tokens(mock_anthropic_client):
    loop = AgentLoop(
        system_prompt="Test",
        tools={},
        client=mock_anthropic_client,
    )
    result = loop.run("test message")
    assert result.token_summary["total_input_tokens"] == 100
    assert result.token_summary["total_output_tokens"] == 50


def test_agent_loop_permission_auto_approve():
    """AUTO permission tools run without asking approval callback."""
    from anthropic.types import ToolUseBlock
    tool = _EchoTool()

    client = MagicMock()
    tool_use = MagicMock(spec=ToolUseBlock)
    tool_use.name = "echo"
    tool_use.id = "t1"
    tool_use.input = {"message": "hello"}

    tool_response = MagicMock()
    tool_response.stop_reason = "tool_use"
    tool_response.usage.input_tokens = 200
    tool_response.usage.output_tokens = 80
    tool_response.content = [tool_use]

    final_response = MagicMock()
    final_response.stop_reason = "end_turn"
    final_response.usage.input_tokens = 250
    final_response.usage.output_tokens = 60
    tb = MagicMock()
    tb.text = "Echo done."
    final_response.content = [tb]

    client.messages.create.side_effect = [tool_response, final_response]

    approval_cb = MagicMock(return_value=True)
    loop = AgentLoop(
        system_prompt="Test",
        tools={"echo": tool},
        client=client,
        approval_callback=approval_cb,
    )
    result = loop.run("Echo hello")
    # AUTO tools should never invoke the approval callback
    approval_cb.assert_not_called()
    assert result.stopped_reason == "end_turn"


def test_agent_loop_unknown_tool_returns_error():
    from anthropic.types import ToolUseBlock

    client = MagicMock()
    tool_use = MagicMock(spec=ToolUseBlock)
    tool_use.name = "nonexistent_tool"
    tool_use.id = "t1"
    tool_use.input = {}

    tool_response = MagicMock()
    tool_response.stop_reason = "tool_use"
    tool_response.usage.input_tokens = 200
    tool_response.usage.output_tokens = 80
    tool_response.content = [tool_use]

    final_response = MagicMock()
    final_response.stop_reason = "end_turn"
    final_response.usage.input_tokens = 200
    final_response.usage.output_tokens = 40
    tb = MagicMock()
    tb.text = "Tool not found error handled."
    final_response.content = [tb]

    client.messages.create.side_effect = [tool_response, final_response]

    loop = AgentLoop(system_prompt="Test", tools={}, client=client)
    result = loop.run("call unknown tool")
    # Should not crash — error is fed back to LLM
    assert result.stopped_reason == "end_turn"
