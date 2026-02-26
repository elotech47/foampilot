"""Shared fixtures for all tests."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_cases_dir() -> Path:
    return FIXTURES_DIR / "sample_cases"


@pytest.fixture
def sample_logs_dir() -> Path:
    return FIXTURES_DIR / "sample_logs"


@pytest.fixture
def sample_dicts_dir() -> Path:
    return FIXTURES_DIR / "sample_dicts"


@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic client that returns a canned response with no tool calls."""
    client = MagicMock()
    response = MagicMock()
    response.stop_reason = "end_turn"
    response.usage.input_tokens = 100
    response.usage.output_tokens = 50
    text_block = MagicMock()
    text_block.text = "Simulation complete."
    # No tool calls
    response.content = [text_block]
    client.messages.create.return_value = response
    return client


@pytest.fixture
def mock_anthropic_client_with_tool_call():
    """Mock client that makes one tool call then stops."""
    from anthropic.types import ToolUseBlock
    client = MagicMock()

    tool_use = MagicMock(spec=ToolUseBlock)
    tool_use.name = "read_file"
    tool_use.id = "tool_1"
    tool_use.input = {"path": "/tmp/test.txt"}

    tool_response = MagicMock()
    tool_response.stop_reason = "tool_use"
    tool_response.usage.input_tokens = 200
    tool_response.usage.output_tokens = 80
    tool_response.content = [tool_use]

    final_response = MagicMock()
    final_response.stop_reason = "end_turn"
    final_response.usage.input_tokens = 250
    final_response.usage.output_tokens = 60
    text_block = MagicMock()
    text_block.text = "File read successfully."
    final_response.content = [text_block]

    client.messages.create.side_effect = [tool_response, final_response]
    return client
