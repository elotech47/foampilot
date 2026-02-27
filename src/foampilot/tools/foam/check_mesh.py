"""Run checkMesh and return structured quality metrics."""

import re
from pathlib import Path
from typing import Any

import structlog

from foampilot.core.permissions import PermissionLevel
from foampilot.tools.base import Tool, ToolResult

log = structlog.get_logger(__name__)

_RE_CELLS = re.compile(r"cells:\s+(\d+)")
_RE_FACES = re.compile(r"faces:\s+(\d+)")
_RE_POINTS = re.compile(r"points:\s+(\d+)")
_RE_NON_ORTHO = re.compile(r"Max non-orthogonality\s*=\s*([\d.]+)")
_RE_SKEWNESS = re.compile(r"Max skewness\s*=\s*([\d.]+)")
_RE_ASPECT = re.compile(r"Max aspect ratio:\s*([\d.]+)")
_RE_FAILED = re.compile(r"Failed (\d+) mesh checks")
_RE_PASSED = re.compile(r"Mesh OK")
_RE_ISSUE = re.compile(r"\*\*\*(.+)")


def parse_checkmesh_output(output: str) -> dict:
    """Parse checkMesh stdout into structured quality metrics."""

    def _find(pattern, text, group=1, cast=float, default=None):
        m = pattern.search(text)
        return cast(m.group(group)) if m else default

    cells = _find(_RE_CELLS, output, cast=int, default=0)
    faces = _find(_RE_FACES, output, cast=int, default=0)
    points = _find(_RE_POINTS, output, cast=int, default=0)
    max_non_ortho = _find(_RE_NON_ORTHO, output, default=None)
    max_skewness = _find(_RE_SKEWNESS, output, default=None)
    max_aspect = _find(_RE_ASPECT, output, default=None)

    failed_match = _RE_FAILED.search(output)
    failed_checks = int(failed_match.group(1)) if failed_match else 0
    passed = bool(_RE_PASSED.search(output)) and failed_checks == 0

    issues = [m.group(1).strip() for m in _RE_ISSUE.finditer(output)]

    return {
        "cells": cells,
        "faces": faces,
        "points": points,
        "max_non_orthogonality": max_non_ortho,
        "max_skewness": max_skewness,
        "max_aspect_ratio": max_aspect,
        "failed_checks": failed_checks,
        "passed": passed,
        "issues": issues,
    }


class CheckMeshTool(Tool):
    """Run checkMesh in the Docker container and return structured quality metrics."""

    name = "check_mesh"
    description = (
        "Run OpenFOAM's checkMesh utility and return structured mesh quality metrics: "
        "cell count, max non-orthogonality, max skewness, max aspect ratio, pass/fail status."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "case_dir": {
                "type": "string",
                "description": "Absolute path to the case directory",
            },
        },
        "required": ["case_dir"],
    }
    permission_level = PermissionLevel.NOTIFY

    def __init__(self, docker_client=None) -> None:
        self._docker = docker_client

    def execute(self, case_dir: str, **kwargs: Any) -> ToolResult:
        if self._docker is None:
            return self._parse_existing_log(case_dir)

        container_dir = self._to_container_path(case_dir)
        log.info("check_mesh", host_path=case_dir, container_path=container_dir)

        try:
            from foampilot.docker.client import DockerClient
            from foampilot.version.registry import VersionRegistry

            profile = VersionRegistry.get().active()
            client = DockerClient(docker_sdk=self._docker)
            source_cmd = f"source /opt/openfoam{profile.VERSION}/etc/bashrc"
            result = client.exec_command(
                f"bash -c '{source_cmd} && cd {container_dir} && checkMesh 2>&1'",
                timeout=120,
            )
            output = result.get("stdout", "") + result.get("stderr", "")
            metrics = parse_checkmesh_output(output)
            return ToolResult.ok(data=metrics, token_hint=100)
        except Exception as exc:
            return ToolResult.fail(f"checkMesh failed: {exc}")

    def _to_container_path(self, path_str: str) -> str:
        """Translate a host-side case path to the container-side equivalent."""
        from foampilot import config as cfg
        from foampilot.docker.volume import VolumeManager
        vm = VolumeManager()
        if path_str.startswith(vm._container_cases_dir):
            return path_str
        host_path = Path(path_str)
        if not host_path.is_absolute():
            host_path = cfg.PROJECT_ROOT / path_str
        return vm.host_to_container(host_path)

    def _parse_existing_log(self, case_dir: str) -> ToolResult:
        """Try to parse an existing checkMesh log file."""
        for log_name in ("checkMesh.log", "log.checkMesh"):
            log_path = Path(case_dir) / log_name
            if log_path.exists():
                output = log_path.read_text()
                metrics = parse_checkmesh_output(output)
                return ToolResult.ok(data=metrics, token_hint=100)
        return ToolResult.fail("Docker client not available and no checkMesh log found.")
