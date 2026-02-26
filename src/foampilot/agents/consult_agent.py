"""Consultation agent — gathers requirements and produces a SimulationSpec."""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from foampilot.core.subagent import SubagentConfig, run_subagent
from foampilot.prompts.consult import get_consult_prompt
from foampilot.tools.registry import ToolRegistry

log = structlog.get_logger(__name__)


class ConsultAgent:
    """Analyzes a user's simulation request and produces a structured SimulationSpec.

    Args:
        event_callback: Optional callable for UI event streaming.
        approval_callback: Called for APPROVE-level tool calls.
    """

    def __init__(
        self,
        event_callback: Any | None = None,
        approval_callback: Any | None = None,
    ) -> None:
        self._event_cb = event_callback
        self._approval_cb = approval_callback

    def run(self, user_request: str) -> dict:
        """Run consultation for the given user request.

        Args:
            user_request: Natural language simulation description.

        Returns:
            SimulationSpec as a dict (JSON-serializable).
        """
        # ConsultAgent only needs read-only tools
        registry = ToolRegistry()  # empty — consult uses LLM reasoning, no tools needed

        cfg = SubagentConfig(
            name="consult",
            system_prompt=get_consult_prompt(),
            tools=registry.all(),
            max_turns=10,
            event_callback=self._event_cb,
            approval_callback=self._approval_cb,
        )

        task = (
            f"Analyze this simulation request and produce a SimulationSpec JSON:\n\n"
            f"{user_request}"
        )

        result = run_subagent(cfg, task)

        # Extract JSON from the response
        spec = self._extract_json(result.final_response)
        log.info("consult_complete", solver=spec.get("solver"), physics=spec.get("physics"))
        return spec

    def _extract_json(self, text: str) -> dict:
        """Extract a JSON object from the LLM response text."""
        # Try to find a ```json ... ``` block
        match = re.search(r"```json\s*([\s\S]+?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find a raw { ... } block
        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        log.warning("consult_json_extraction_failed", text_preview=text[:200])
        # Return minimal spec as fallback
        return {
            "solver": "simpleFoam",
            "physics": {"type": "incompressible_steady_turbulent"},
            "assumptions": ["Could not parse full spec — using defaults"],
            "_raw_response": text,
        }
