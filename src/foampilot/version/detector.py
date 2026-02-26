"""Detects the OpenFOAM version installed inside a Docker container.

Falls back to configuration values if detection fails.
"""

import re
import structlog

from foampilot import config

log = structlog.get_logger(__name__)

_BASHRC_PATHS = [
    "/opt/openfoam11/etc/bashrc",
    "/opt/openfoam12/etc/bashrc",
    "/opt/openfoam13/etc/bashrc",
    "/opt/openfoam10/etc/bashrc",
    "/opt/openfoam9/etc/bashrc",
]


class VersionDetector:
    """Detects the OpenFOAM version from inside a running Docker container."""

    def __init__(self, docker_client=None) -> None:
        self._docker = docker_client

    def detect(self) -> tuple[str, str]:
        """Return (distribution, version) for the running OpenFOAM installation.

        Returns:
            Tuple of (distribution, version), e.g. ("foundation", "11").
            Falls back to config values if detection fails.
        """
        if self._docker is not None:
            result = self._detect_from_docker()
            if result:
                return result

        log.warning(
            "version_detection_fallback",
            reason="Docker client unavailable or detection failed",
            fallback_version=config.OPENFOAM_VERSION,
            fallback_distribution=config.OPENFOAM_DISTRIBUTION,
        )
        return config.OPENFOAM_DISTRIBUTION, config.OPENFOAM_VERSION

    def _detect_from_docker(self) -> tuple[str, str] | None:
        """Try to detect version by examining files inside the container."""
        try:
            container = self._docker.containers.get(config.OPENFOAM_CONTAINER)

            # Method 1: Check which bashrc file exists
            for bashrc_path in _BASHRC_PATHS:
                result = container.exec_run(f"test -f {bashrc_path}", demux=True)
                if result.exit_code == 0:
                    version = self._parse_version_from_path(bashrc_path)
                    distribution = self._detect_distribution(container, version)
                    if version:
                        log.info("version_detected", method="bashrc_path", version=version)
                        return distribution, version

            # Method 2: Run foamVersion command
            result = container.exec_run(
                "bash -c 'source /etc/bashrc 2>/dev/null; foamVersion 2>&1 || echo $WM_PROJECT_VERSION'",
                demux=True,
            )
            if result.exit_code == 0 and result.output[0]:
                stdout = result.output[0].decode("utf-8", errors="replace").strip()
                version = self._parse_version_from_output(stdout)
                if version:
                    distribution = "foundation"
                    log.info("version_detected", method="foamVersion", version=version)
                    return distribution, version

        except Exception as exc:
            log.warning("version_detection_failed", error=str(exc))

        return None

    def _parse_version_from_path(self, path: str) -> str | None:
        """Extract version number from a path like /opt/openfoam11/etc/bashrc."""
        match = re.search(r"openfoam(\d+)", path)
        return match.group(1) if match else None

    def _parse_version_from_output(self, output: str) -> str | None:
        """Extract version number from foamVersion or WM_PROJECT_VERSION output."""
        # Handles: "11", "v2406", "2406", "11.0"
        match = re.search(r"\b(\d{1,2})\b", output)
        return match.group(1) if match else None

    def _detect_distribution(self, container, version: str) -> str:
        """Distinguish Foundation from ESI OpenFOAM by inspecting the installation."""
        try:
            result = container.exec_run(
                f"test -d /opt/openfoam{version}",
                demux=True,
            )
            if result.exit_code == 0:
                return "foundation"
            # ESI uses /usr/lib/openfoam/openfoam<version>
            result = container.exec_run(
                f"test -d /usr/lib/openfoam/openfoam{version}",
                demux=True,
            )
            if result.exit_code == 0:
                return "esi"
        except Exception:
            pass
        return "foundation"
