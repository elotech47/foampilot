"""Unit tests for conversation compaction."""

from unittest.mock import MagicMock

import pytest
from foampilot.core.compaction import compact_conversation


def _make_client(summary_text: str) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    content_block = MagicMock()
    content_block.text = summary_text
    response.content = [content_block]
    response.usage.output_tokens = 200
    client.messages.create.return_value = response
    return client


def test_compact_returns_single_message():
    messages = [
        {"role": "user", "content": "Run a cavity simulation"},
        {"role": "assistant", "content": "I'll set up the cavity case."},
        {"role": "user", "content": "Looks good."},
    ]
    client = _make_client("Summary: cavity simulation in progress.")
    result = compact_conversation(messages, client=client)
    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert "CONVERSATION SUMMARY" in result[0]["content"]
    assert "Summary: cavity simulation in progress." in result[0]["content"]


def test_compact_calls_llm_once():
    messages = [{"role": "user", "content": "test"}]
    client = _make_client("summary text")
    compact_conversation(messages, client=client)
    assert client.messages.create.call_count == 1


def test_compact_handles_tool_use_blocks():
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "read_file", "input": {"path": "/tmp/f"}},
            ],
        }
    ]
    client = _make_client("summary")
    result = compact_conversation(messages, client=client)
    assert len(result) == 1
