"""Case setup agent — finds tutorial template and modifies it for the user's case."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import structlog

from foampilot.core.subagent import SubagentConfig, run_subagent
from foampilot.prompts.setup import get_setup_prompt
from foampilot.tools.foam.copy_tutorial import CopyTutorialTool
from foampilot.tools.foam.edit_foam_dict import EditFoamDictTool
from foampilot.tools.foam.read_foam_file import ReadFoamFileTool
from foampilot.tools.foam.search_tutorials import SearchTutorialsTool
from foampilot.tools.foam.write_foam_file import WriteFoamFileTool
from foampilot.tools.general.read_file import ReadFileTool
from foampilot.tools.general.str_replace import StrReplaceTool

log = structlog.get_logger(__name__)


class SetupAgent:
    """Finds the best tutorial template and adapts it for the simulation spec.

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

    def run(self, simulation_spec: dict, case_dir: Path) -> dict:
        """Run case setup for the given simulation spec.

        Args:
            simulation_spec: SimulationSpec dict from ConsultAgent.
            case_dir: Target directory to create the case in.

        Returns:
            SetupResult dict with files_modified, tutorial_source, assumptions.
        """
        tools = {
            "search_tutorials": SearchTutorialsTool(),
            "copy_tutorial": CopyTutorialTool(),
            "read_foam_file": ReadFoamFileTool(),
            "edit_foam_dict": EditFoamDictTool(),
            "write_foam_file": WriteFoamFileTool(),
            "read_file": ReadFileTool(),
            "str_replace": StrReplaceTool(),
        }

        cfg = SubagentConfig(
            name="setup",
            system_prompt=get_setup_prompt(),
            tools=tools,
            max_turns=30,
            event_callback=self._event_cb,
            approval_callback=self._approval_cb,
        )

        task = (
            f"Set up an OpenFOAM case for the following simulation specification:\n\n"
            f"```json\n{json.dumps(simulation_spec, indent=2)}\n```\n\n"
            f"Target case directory: {case_dir}\n\n"
            "Use search_tutorials to find the best matching template, copy it, then modify it."
        )

        result = run_subagent(cfg, task)
        return self._extract_result(result.final_response, str(case_dir))

    def _extract_result(self, text: str, case_dir: str) -> dict:
        """Extract setup result JSON from the agent response."""
        match = re.search(r"```json\s*([\s\S]+?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        match = re.search(r"\{[\s\S]+\}", text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return {
            "case_dir": case_dir,
            "tutorial_source": "unknown",
            "files_modified": [],
            "assumptions": [],
        }
