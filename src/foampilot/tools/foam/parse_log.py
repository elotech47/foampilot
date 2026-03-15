"""Parse solver log files into structured convergence data."""

import re
from pathlib import Path
from typing import Any

import structlog

from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)

_RE_RESIDUAL = re.compile(
    r"Solving for (\w+),\s+Initial residual = ([\d.eE+\-]+),\s+Final residual = ([\d.eE+\-]+)"
)
_RE_CONTINUITY = re.compile(
    r"time step continuity errors.*?cumulative = ([\d.eE+\-]+)"
)
_RE_EXEC_TIME = re.compile(r"ExecutionTime = ([\d.]+)\s*s")
_RE_TIME_STEP = re.compile(r"^Time = ([\d.eE+\-]+)", re.MULTILINE)
_RE_DIVERGE = re.compile(
    r"(DIVergence|FOAM FATAL|Maximum number of iterations|Floating point|nan|inf)",
    re.IGNORECASE,
)
_RE_END = re.compile(r"^\s*End\s*$", re.MULTILINE)


def parse_solver_log(text: str) -> dict:
    """Parse solver log text into a structured convergence summary."""
    # Time steps
    time_steps = [float(m.group(1)) for m in _RE_TIME_STEP.finditer(text)]
    iterations = len(time_steps)

    # Final residuals (last occurrence of each field)
    final_residuals: dict[str, float] = {}
    for match in _RE_RESIDUAL.finditer(text):
        field = match.group(1)
        final_residuals[field] = float(match.group(3))

    # Continuity error
    continuity_matches = list(_RE_CONTINUITY.finditer(text))
    continuity_error = float(continuity_matches[-1].group(1)) if continuity_matches else None

    # Execution time
    exec_matches = list(_RE_EXEC_TIME.finditer(text))
    execution_time_s = float(exec_matches[-1].group(1)) if exec_matches else None

    # Convergence / divergence
    diverged = bool(_RE_DIVERGE.search(text))
    ended_clean = bool(_RE_END.search(text))
    converged = ended_clean and not diverged

    # Likely issue
    likely_issue = None
    if not converged:
        if diverged:
            likely_issue = "Simulation diverged — check mesh quality, time step, and relaxation factors"
        elif not ended_clean:
            likely_issue = "Simulation did not complete — may have been interrupted"
        if continuity_error is not None and abs(continuity_error) > 1e-3:
            likely_issue = (likely_issue or "") + f"; High continuity error ({continuity_error:.2e})"

    return {
        "converged": converged,
        "diverged": diverged,
        "iterations": iterations,
        "final_residuals": final_residuals,
        "continuity_error": continuity_error,
        "execution_time_s": execution_time_s,
        "likely_issue": likely_issue,
    }


class ParseLogTool(Tool):
    """Parse an OpenFOAM solver log file into structured convergence data."""

    name = "parse_log"
    description = (
        "Parse an OpenFOAM solver log file into structured convergence data: "
        "converged (bool), final residuals per field, continuity error, execution time, "
        "and a human-readable diagnosis of any issues."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "log_path": {
                "type": "string",
                "description": "Path to the solver log file. Use <case_dir>/log.<solver> where case_dir is the path from your system prompt.",
            },
        },
        "required": ["log_path"],
    }
    permission_level = PermissionLevel.AUTO

    def __init__(self, docker_client: Any = None) -> None:
        self._docker = docker_client

    def execute(self, log_path: str, **kwargs: Any) -> ToolResult:
        text = self._read_log(log_path)
        if text is None:
            return ToolResult.fail(
                f"Log file not found: {log_path}. "
                "Check that the solver ran and wrote a log file."
            )
        try:
            result = parse_solver_log(text)
            return ToolResult.ok(data=result, token_hint=80)
        except Exception as exc:
            return ToolResult.fail(f"Failed to parse log: {exc}")

    def _read_log(self, log_path: str) -> str | None:
        """Read log content, preferring container exec over host file read."""
        from foampilot.docker.volume import VolumeManager
        vm = VolumeManager()
        container_path = vm.to_container_path(log_path)

        # Try reading via Docker exec (file lives inside the container)
        if self._docker is not None:
            try:
                from foampilot.docker.client import DockerClient
                client = DockerClient(docker_sdk=self._docker)
                result = client.exec_command(f"cat {container_path}")
                if result.get("exit_code", 1) == 0:
                    return result.get("stdout", "")
            except Exception as exc:
                log.warning("parse_log_docker_read_failed", error=str(exc))

        # Fallback: try reading directly from host filesystem
        host_path = vm.container_to_host(container_path)
        if host_path.exists():
            return host_path.read_text(encoding="utf-8", errors="replace")

        return None
