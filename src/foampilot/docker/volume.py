"""Case directory volume mounting and path translation."""

from __future__ import annotations

import re
from pathlib import Path

import structlog

from foampilot import config

log = structlog.get_logger(__name__)

_RE_CASE_SEGMENT = re.compile(r"(?:^|/)cases/(case_[a-f0-9]+(?:/.*)?)$")


class VolumeManager:
    """Manages the bind-mounted case directory shared between host and container.

    The cases directory is mounted at the same path in both the agent and OpenFOAM containers.
    """

    def __init__(
        self,
        host_cases_dir: Path | None = None,
        container_cases_dir: str | None = None,
    ) -> None:
        self._host_cases_dir = (host_cases_dir or config.CASES_DIR).resolve()
        self._container_cases_dir = container_cases_dir or config.CONTAINER_CASES_DIR

    def to_container_path(self, path_str: str) -> str:
        """Convert any path (host absolute, relative, or already container) to
        the container-side equivalent.  This is the single entry point that all
        tools should use.

        Handles:
          - Already a container path  →  returned as-is
          - Host absolute path        →  resolved and translated
          - Relative path             →  resolved against PROJECT_ROOT, then translated
        """
        if path_str.startswith(self._container_cases_dir):
            return path_str

        host_path = Path(path_str)
        if not host_path.is_absolute():
            host_path = config.PROJECT_ROOT / path_str
        return self.host_to_container(host_path)

    def host_to_container(self, host_path: Path) -> str:
        """Translate a host path to the equivalent container path.

        Uses Path.relative_to with resolved paths first, then falls back to a
        string-based extraction of ``cases/case_<id>`` so that symlinks, mount
        oddities, or alternative representations never silently return the
        host path into the Docker container.
        """
        resolved = host_path.resolve()
        try:
            rel = resolved.relative_to(self._host_cases_dir)
            return f"{self._container_cases_dir}/{rel}"
        except ValueError:
            pass

        m = _RE_CASE_SEGMENT.search(str(resolved))
        if m:
            log.warning(
                "host_to_container_fallback",
                host_path=str(host_path),
                extracted=m.group(1),
            )
            return f"{self._container_cases_dir}/{m.group(1)}"

        log.error(
            "host_to_container_failed",
            host_path=str(host_path),
            cases_dir=str(self._host_cases_dir),
            hint="Path is not under the cases directory and does not match case_<id> pattern",
        )
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
