"""Token usage monitoring, budgets, and cost estimation.

Tracks per-turn input/output tokens and cumulative session cost.
Exposes should_compact() based on a configurable threshold.
"""

from dataclasses import dataclass, field

import structlog

from foampilot import config

log = structlog.get_logger(__name__)

# Approximate cost per million tokens (USD) — update as pricing changes
_COST_PER_M_INPUT = {
    "claude-sonnet-4-5-20250929": 3.00,
    "claude-opus-4-5": 15.00,
}
_COST_PER_M_OUTPUT = {
    "claude-sonnet-4-5-20250929": 15.00,
    "claude-opus-4-5": 75.00,
}


@dataclass
class TurnUsage:
    turn: int
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def cost_usd(self) -> float:
        in_cost = _COST_PER_M_INPUT.get(self.model, 3.00) * self.input_tokens / 1_000_000
        out_cost = _COST_PER_M_OUTPUT.get(self.model, 15.00) * self.output_tokens / 1_000_000
        return in_cost + out_cost


@dataclass
class TokenTracker:
    """Tracks token consumption across the full agent session."""

    _turns: list[TurnUsage] = field(default_factory=list)
    _context_window: int = field(default_factory=lambda: config.CONTEXT_WINDOW_TOKENS)
    _threshold: float = field(default_factory=lambda: config.COMPACTION_THRESHOLD)

    def record(
        self,
        turn: int,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        """Record token usage for one agent turn."""
        usage = TurnUsage(
            turn=turn,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )
        self._turns.append(usage)
        log.info(
            "token_usage",
            turn=turn,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(usage.cost_usd, 5),
            context_pct=round(self.context_utilization * 100, 1),
        )

    @property
    def total_input_tokens(self) -> int:
        return sum(t.input_tokens for t in self._turns)

    @property
    def total_output_tokens(self) -> int:
        return sum(t.output_tokens for t in self._turns)

    @property
    def total_cost_usd(self) -> float:
        return sum(t.cost_usd for t in self._turns)

    @property
    def context_utilization(self) -> float:
        """Fraction of context window used based on latest turn's input tokens."""
        if not self._turns:
            return 0.0
        latest_input = self._turns[-1].input_tokens
        return min(latest_input / self._context_window, 1.0)

    def should_compact(self) -> bool:
        """Return True when context utilization exceeds the configured threshold."""
        return self.context_utilization >= self._threshold

    def summary(self) -> dict:
        return {
            "turns": len(self._turns),
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "context_utilization_pct": round(self.context_utilization * 100, 1),
        }
