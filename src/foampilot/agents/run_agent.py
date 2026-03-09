"""Run agent — executes the solver and monitors convergence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import structlog

from foampilot.agents.base_agent import BaseAgent
from foampilot.core.subagent import SubagentConfig, run_subagent
from foampilot.prompts.run import get_run_prompt
from foampilot.tools.foam.edit_foam_dict import EditFoamDictTool
from foampilot.tools.foam.parse_log import ParseLogTool
from foampilot.tools.foam.read_foam_file import ReadFoamFileTool
from foampilot.tools.foam.run_foam_cmd import RunFoamCmdTool

log = structlog.get_logger(__name__)


class RunAgent(BaseAgent):
    """Executes the OpenFOAM solver and monitors convergence."""

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
            "parse_log": ParseLogTool(docker_client=self._docker),
            "read_foam_file": ReadFoamFileTool(),
            "edit_foam_dict": EditFoamDictTool(),
        }

        cfg = SubagentConfig(
            name="run",
            system_prompt=get_run_prompt(case_dir=case_dir.resolve()),
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
