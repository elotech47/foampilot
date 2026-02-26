"""Analysis agent — post-processes, validates, and visualizes results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from foampilot.core.subagent import SubagentConfig, run_subagent
from foampilot.prompts.analyze import get_analyze_prompt
from foampilot.tools.foam.extract_data import ExtractDataTool
from foampilot.tools.foam.parse_log import ParseLogTool
from foampilot.tools.foam.read_foam_file import ReadFoamFileTool
from foampilot.tools.viz.plot_field import PlotFieldTool
from foampilot.tools.viz.plot_residuals import PlotResidualsTool

log = structlog.get_logger(__name__)


class AnalyzeAgent:
    """Post-processes simulation results, validates physics, and generates plots.

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

    def run(self, case_dir: Path, state: Any) -> dict:
        """Run post-processing and analysis for the completed simulation.

        Args:
            case_dir: Path to the case directory.
            state: SimulationState with context about what was done.

        Returns:
            AnalysisResult dict with computed quantities, validation checks, plot paths.
        """
        tools = {
            "extract_data": ExtractDataTool(),
            "parse_log": ParseLogTool(),
            "read_foam_file": ReadFoamFileTool(),
            "plot_residuals": PlotResidualsTool(),
            "plot_field": PlotFieldTool(),
        }

        cfg = SubagentConfig(
            name="analyze",
            system_prompt=get_analyze_prompt(),
            tools=tools,
            max_turns=20,
            event_callback=self._event_cb,
            approval_callback=self._approval_cb,
        )

        solver = state.simulation_spec.get("solver", "unknown") if state.simulation_spec else "unknown"
        task = (
            f"Post-process and validate the results of a {solver} simulation at: {case_dir}\n\n"
            "Steps:\n"
            "1. List available time directories (extract_data with list_times)\n"
            "2. Generate a residuals convergence plot (plot_residuals)\n"
            "3. Extract and validate key quantities\n"
            "4. Report any physical inconsistencies\n\n"
            "Return a JSON summary with computed quantities and validation status."
        )

        result = run_subagent(cfg, task)
        log.info("analysis_complete", case_dir=str(case_dir))
        return {"response": result.final_response}
