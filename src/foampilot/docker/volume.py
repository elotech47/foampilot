"""Case directory volume mounting and path translation."""

from __future__ import annotations

from pathlib import Path

import structlog

from foampilot import config

log = structlog.get_logger(__name__)


class VolumeManager:
    """Manages the bind-mounted case directory shared between host and container.

    The cases directory is mounted at the same path in both the agent and OpenFOAM containers.
    """

    def __init__(
        self,
        host_cases_dir: Path | None = None,
        container_cases_dir: str | None = None,
    ) -> None:
        self._host_cases_dir = host_cases_dir or config.CASES_DIR
        self._container_cases_dir = container_cases_dir or "/home/openfoam/cases"

    def host_to_container(self, host_path: Path) -> str:
        """Translate a host path to the equivalent container path.

        Args:
            host_path: Absolute path on the host.

        Returns:
            Equivalent path inside the container.
        """
        try:
            rel = host_path.relative_to(self._host_cases_dir)
            return f"{self._container_cases_dir}/{rel}"
        except ValueError:
            # Path is not under cases_dir — use as-is
            return str(host_path)

    def container_to_host(self, container_path: str) -> Path:
        """Translate a container path to the equivalent host path."""
        if container_path.startswith(self._container_cases_dir):
            rel = container_path[len(self._container_cases_dir):].lstrip("/")
            return self._host_cases_dir / rel
        return Path(container_path)

    def ensure_writable(self, path: Path) -> None:
        """Ensure a case directory exists and is writable."""
        path.mkdir(parents=True, exist_ok=True)
        test_file = path / ".foampilot_write_test"
        try:
            test_file.write_text("ok")
            test_file.unlink()
        except OSError as exc:
            raise OSError(f"Case directory is not writable: {path}: {exc}") from exc
