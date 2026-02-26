"""Run shell commands (with permission gating)."""

import subprocess
import shlex
from typing import Any

import structlog

from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)

_DANGEROUS_PATTERNS = [
    "rm -rf", "sudo", "chmod 777", "> /dev/", "dd if=", "mkfs",
]


class BashTool(Tool):
    """Execute a shell command on the host machine."""

    name = "bash"
    description = (
        "Execute a shell command on the host machine. "
        "Use for file operations, running scripts, and system tasks. "
        "For OpenFOAM commands, prefer run_foam_cmd instead."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default 30)",
                "default": 30,
            },
        },
        "required": ["command"],
    }
    permission_level = PermissionLevel.APPROVE

    def execute(self, command: str, timeout: int = 30, **kwargs: Any) -> ToolResult:
        # Safety check for obviously dangerous patterns
        cmd_lower = command.lower()
        for pattern in _DANGEROUS_PATTERNS:
            if pattern in cmd_lower:
                return ToolResult.fail(
                    f"Command blocked: contains dangerous pattern '{pattern}'. "
                    "Use a more targeted approach."
                )

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stdout = result.stdout.strip()
            stderr = result.stderr.strip()

            log.info("bash_executed", command=command[:80], returncode=result.returncode)

            return ToolResult.ok(
                data={
                    "returncode": result.returncode,
                    "stdout": stdout[-3000:] if len(stdout) > 3000 else stdout,
                    "stderr": stderr[-500:] if len(stderr) > 500 else stderr,
                    "success": result.returncode == 0,
                }
            )
        except subprocess.TimeoutExpired:
            return ToolResult.fail(f"Command timed out after {timeout} seconds")
        except Exception as exc:
            return ToolResult.fail(f"Command failed: {exc}")
