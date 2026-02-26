"""Run agent — executes the solver and monitors convergence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import structlog

from foampilot.core.subagent import SubagentConfig, run_subagent
from foampilot.prompts.run import get_run_prompt
from foampilot.tools.foam.edit_foam_dict import EditFoamDictTool
from foampilot.tools.foam.parse_log import ParseLogTool
from foampilot.tools.foam.read_foam_file import ReadFoamFileTool
from foampilot.tools.foam.run_foam_cmd import RunFoamCmdTool

log = structlog.get_logger(__name__)


class RunAgent:
    """Executes the OpenFOAM solver and monitors convergence.

    Args:
        docker_client: Docker client for running commands.
        event_callback: Optional callable for UI event streaming.
        approval_callback: Called for APPROVE-level tool calls.
    """

    def __init__(
        self,
        docker_client: Any | None = None,
        event_callback: Any | None = None,
        approval_callback: Any | None = None,
    ) -> None:
        self._docker = docker_client
        self._event_cb = event_callback
        self._approval_cb = approval_callback

    def run(self, case_dir: Path, simulation_spec: dict) -> dict:
        """Execute the solver and return convergence results.

        Args:
            case_dir: Path to the case directory.
            simulation_spec: SimulationSpec from ConsultAgent.

        Returns:
            RunResult dict with convergence data and final residuals.
        """
        solver = simulation_spec.get("solver", "simpleFoam")

        tools = {
            "run_foam_cmd": RunFoamCmdTool(docker_client=self._docker),
            "parse_log": ParseLogTool(),
            "read_foam_file": ReadFoamFileTool(),
            "edit_foam_dict": EditFoamDictTool(),
        }

        cfg = SubagentConfig(
            name="run",
            system_prompt=get_run_prompt(),
            tools=tools,
            max_turns=20,
            event_callback=self._event_cb,
            approval_callback=self._approval_cb,
        )

        task = (
            f"Execute {solver} for the OpenFOAM case at: {case_dir}\n\n"
            f"Simulation spec:\n```json\n{json.dumps(simulation_spec, indent=2)}\n```\n\n"
            "Run the solver, then use parse_log to analyze convergence. "
            "If it diverges, diagnose and attempt to fix. "
            "Return a JSON summary with convergence status and final residuals."
        )

        result = run_subagent(cfg, task)

        match = re.search(r"\{[\s\S]+\}", result.final_response)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return {
            "converged": False,
            "final_residuals": {},
            "issues": ["Could not extract run result from agent response"],
        }
