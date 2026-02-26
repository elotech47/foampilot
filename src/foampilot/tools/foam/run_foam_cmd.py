"""Execute OpenFOAM commands inside the Docker container."""

import json
import re
import time
from typing import Any

import structlog

from foampilot import config
from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)

# Detect residual lines in solver output
_RE_RESIDUAL = re.compile(
    r"Solving for (\w+),.*?Initial residual = ([\d.eE+\-]+),.*?Final residual = ([\d.eE+\-]+)"
)
_RE_CONTINUITY = re.compile(r"time step continuity errors.*?cumulative = ([\d.eE+\-]+)")
_RE_EXEC_TIME = re.compile(r"ExecutionTime = ([\d.]+)\s*s")


class RunFoamCmdTool(Tool):
    """Execute an OpenFOAM command (solver or utility) inside the Docker container."""

    name = "run_foam_cmd"
    description = (
        "Execute an OpenFOAM command (e.g., 'simpleFoam', 'blockMesh', 'checkMesh') "
        "inside the OpenFOAM Docker container. Returns structured output rather than "
        "raw log text. For solvers, returns convergence summary."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The OpenFOAM command to run (e.g., 'simpleFoam', 'blockMesh -dict system/blockMeshDict')",
            },
            "case_dir": {
                "type": "string",
                "description": "Absolute path to the case directory inside the container",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 3600)",
                "default": 3600,
            },
            "log_file": {
                "type": "string",
                "description": "Optional: write stdout to this log file in the case dir",
            },
        },
        "required": ["command", "case_dir"],
    }
    permission_level = PermissionLevel.APPROVE

    def __init__(self, docker_client=None) -> None:
        self._docker = docker_client

    def execute(
        self,
        command: str,
        case_dir: str,
        timeout: int = 3600,
        log_file: str | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        from foampilot.version.registry import VersionRegistry

        # Validate command against version profile
        profile = VersionRegistry.get().active()
        solver = command.split()[0]
        if solver not in profile.MESH_UTILITIES and solver not in profile.POST_PROCESSING_UTILITIES:
            if not profile.validate_solver(solver):
                log.warning(
                    "unknown_foam_command",
                    command=solver,
                    version=profile.VERSION,
                )
                # Don't block — just warn. Utilities not in our list may still be valid.

        if self._docker is None:
            return ToolResult.fail(
                "Docker client not available. Cannot execute OpenFOAM commands."
            )

        try:
            return self._run_in_docker(command, case_dir, timeout, log_file, profile)
        except Exception as exc:
            return ToolResult.fail(f"Docker execution failed: {exc}")

    def _run_in_docker(self, command, case_dir, timeout, log_file, profile):
        from foampilot.docker.client import DockerClient
        client = DockerClient(docker_sdk=self._docker)

        source_cmd = f"source /opt/openfoam{profile.VERSION}/etc/bashrc"
        full_cmd = f"bash -c '{source_cmd} && cd {case_dir} && {command}'"
        if log_file:
            full_cmd = f"bash -c '{source_cmd} && cd {case_dir} && {command} 2>&1 | tee {log_file}'"

        result = client.exec_command(full_cmd, timeout=timeout)

        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", -1)

        # Parse residuals from output
        residuals = self._parse_residuals(stdout)
        exec_time = self._parse_exec_time(stdout)

        return ToolResult.ok(
            data={
                "command": command,
                "case_dir": case_dir,
                "exit_code": exit_code,
                "success": exit_code == 0,
                "residuals_summary": residuals,
                "execution_time_s": exec_time,
                "stdout_tail": stdout[-2000:] if len(stdout) > 2000 else stdout,
                "stderr_tail": stderr[-500:] if len(stderr) > 500 else stderr,
            },
            token_hint=400,
        )

    def _parse_residuals(self, stdout: str) -> dict:
        """Extract final residuals per field from solver output."""
        final: dict[str, float] = {}
        for match in _RE_RESIDUAL.finditer(stdout):
            field = match.group(1)
            final_res = float(match.group(3))
            final[field] = final_res  # last value wins
        return final

    def _parse_exec_time(self, stdout: str) -> float | None:
        matches = list(_RE_EXEC_TIME.finditer(stdout))
        if matches:
            return float(matches[-1].group(1))
        return None
