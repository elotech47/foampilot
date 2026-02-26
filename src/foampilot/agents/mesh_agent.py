"""Meshing agent — generates and validates the computational mesh."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from foampilot.core.subagent import SubagentConfig, run_subagent
from foampilot.prompts.mesh import get_mesh_prompt
from foampilot.tools.foam.check_mesh import CheckMeshTool
from foampilot.tools.foam.edit_foam_dict import EditFoamDictTool
from foampilot.tools.foam.read_foam_file import ReadFoamFileTool
from foampilot.tools.foam.run_foam_cmd import RunFoamCmdTool
from foampilot.tools.general.read_file import ReadFileTool

log = structlog.get_logger(__name__)


class MeshAgent:
    """Generates and validates the computational mesh for a case.

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

    def run(self, case_dir: Path) -> dict:
        """Generate and validate the mesh for the given case directory.

        Args:
            case_dir: Path to the case directory.

        Returns:
            MeshResult dict with quality metrics and pass/fail.
        """
        tools = {
            "run_foam_cmd": RunFoamCmdTool(docker_client=self._docker),
            "check_mesh": CheckMeshTool(docker_client=self._docker),
            "read_foam_file": ReadFoamFileTool(),
            "edit_foam_dict": EditFoamDictTool(),
            "read_file": ReadFileTool(),
        }

        cfg = SubagentConfig(
            name="mesh",
            system_prompt=get_mesh_prompt(),
            tools=tools,
            max_turns=20,
            event_callback=self._event_cb,
            approval_callback=self._approval_cb,
        )

        task = (
            f"Generate and validate the mesh for the OpenFOAM case at: {case_dir}\n\n"
            "Run blockMesh (or snappyHexMesh if configured), then run checkMesh. "
            "If the mesh quality fails, attempt to fix it. "
            "Return a JSON summary with the mesh quality metrics."
        )

        result = run_subagent(cfg, task)

        # Try to extract structured mesh quality from response
        import json, re
        match = re.search(r"\{[\s\S]+\}", result.final_response)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return {
            "passed": False,
            "issues": ["Could not extract mesh quality from agent response"],
        }
