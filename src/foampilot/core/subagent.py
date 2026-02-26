"""Subagent spawner with isolated context.

Each subagent gets its own message history and tool subset, preventing
context cross-contamination between phases.
"""

from dataclasses import dataclass
from typing import Any

import structlog

from foampilot.core.agent_loop import AgentLoop, AgentLoopResult
from foampilot.core.permissions import PermissionChecker

log = structlog.get_logger(__name__)


@dataclass
class SubagentConfig:
    """Configuration for a single subagent invocation."""

    name: str
    system_prompt: str
    tools: dict[str, Any]
    max_turns: int = 50
    permission_checker: PermissionChecker | None = None
    event_callback: Any | None = None
    approval_callback: Any | None = None


def run_subagent(cfg: SubagentConfig, task: str) -> AgentLoopResult:
    """Spawn a subagent with isolated context and run it to completion.

    Args:
        cfg: Configuration for the subagent.
        task: The task string to give the subagent as its initial user message.

    Returns:
        AgentLoopResult from the subagent's loop.
    """
    log.info("subagent_start", name=cfg.name, task_preview=task[:80])

    import foampilot.config as c
    original_max = c.MAX_TURNS
    c.MAX_TURNS = cfg.max_turns

    try:
        loop = AgentLoop(
            system_prompt=cfg.system_prompt,
            tools=cfg.tools,
            permission_checker=cfg.permission_checker,
            event_callback=cfg.event_callback,
            approval_callback=cfg.approval_callback,
        )
        result = loop.run(task)
    finally:
        c.MAX_TURNS = original_max

    log.info(
        "subagent_done",
        name=cfg.name,
        turns=result.turn_count,
        stopped_reason=result.stopped_reason,
    )
    return result
