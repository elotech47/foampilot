"""Unit tests for TokenTracker."""

import pytest
from foampilot.core.token_tracker import TokenTracker


def test_initial_state():
    tracker = TokenTracker()
    assert tracker.total_input_tokens == 0
    assert tracker.total_output_tokens == 0
    assert tracker.total_cost_usd == 0.0
    assert tracker.context_utilization == 0.0
    assert not tracker.should_compact()


def test_record_and_totals():
    tracker = TokenTracker()
    tracker.record(turn=1, model="claude-sonnet-4-5-20250929", input_tokens=1000, output_tokens=500)
    tracker.record(turn=2, model="claude-sonnet-4-5-20250929", input_tokens=2000, output_tokens=300)
    assert tracker.total_input_tokens == 3000
    assert tracker.total_output_tokens == 800


def test_cost_calculation():
    tracker = TokenTracker()
    # 1M input tokens at $3/M = $3.00
    # 1M output tokens at $15/M = $15.00
    tracker.record(turn=1, model="claude-sonnet-4-5-20250929", input_tokens=1_000_000, output_tokens=1_000_000)
    assert abs(tracker.total_cost_usd - 18.0) < 0.01


def test_should_compact_below_threshold():
    tracker = TokenTracker(_context_window=200_000, _threshold=0.70)
    tracker.record(turn=1, model="claude-sonnet-4-5-20250929", input_tokens=100_000, output_tokens=1000)
    # 100k / 200k = 50% — below threshold
    assert not tracker.should_compact()


def test_should_compact_above_threshold():
    tracker = TokenTracker(_context_window=200_000, _threshold=0.70)
    tracker.record(turn=1, model="claude-sonnet-4-5-20250929", input_tokens=150_000, output_tokens=1000)
    # 150k / 200k = 75% — above threshold
    assert tracker.should_compact()


def test_summary_keys():
    tracker = TokenTracker()
    tracker.record(turn=1, model="claude-sonnet-4-5-20250929", input_tokens=500, output_tokens=200)
    summary = tracker.summary()
    assert "turns" in summary
    assert "total_input_tokens" in summary
    assert "total_output_tokens" in summary
    assert "total_cost_usd" in summary
    assert "context_utilization_pct" in summary
