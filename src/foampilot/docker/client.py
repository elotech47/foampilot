"""Docker API client for executing commands in the OpenFOAM container.

Provides exec_command(), stream_command(), and file transfer methods.
"""

from __future__ import annotations

import tarfile
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

import structlog

from foampilot import config

log = structlog.get_logger(__name__)

# Candidate socket paths in priority order.
# Docker Desktop on macOS does not create /var/run/docker.sock by default.
_DOCKER_SOCKET_CANDIDATES = [
    "/var/run/docker.sock",
    # Docker Desktop for Mac (4.x+)
    str(Path.home() / ".docker" / "run" / "docker.sock"),
    # Older Docker Desktop for Mac
    str(Path.home() / "Library" / "Containers" / "com.docker.docker" / "Data" / "docker.sock"),
]


def _connect_docker():
    """Return a docker.DockerClient, trying several socket paths on macOS.

    Tries DOCKER_HOST / docker.from_env() first (respects the env var),
    then falls back through known macOS Docker Desktop socket locations.

    Raises:
        RuntimeError: If no working Docker connection can be found.
    """
    import docker

    # First try the standard environment-based resolution
    try:
        client = docker.from_env()
        log.debug("docker_connected", method="from_env")
        return client
    except Exception:
        pass

    # Fall back to known macOS socket paths
    for socket_path in _DOCKER_SOCKET_CANDIDATES:
        if Path(socket_path).exists():
            try:
                client = docker.DockerClient(base_url=f"unix://{socket_path}")
                client.ping()
                log.info("docker_connected", method="socket_fallback", socket=socket_path)
                return client
            except Exception:
                continue

    raise RuntimeError(
        "Docker not available. Tried: DOCKER_HOST env var and socket paths: "
        + ", ".join(_DOCKER_SOCKET_CANDIDATES)
    )


class ExecResult:
    """Result of a docker exec command."""

    def __init__(self, stdout: str, stderr: str, exit_code: int) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.exit_code = exit_code

    def to_dict(self) -> dict:
        return {
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
        }


class DockerClient:
    """Wrapper around the Docker SDK for executing OpenFOAM commands.

    Args:
        docker_sdk: An initialized docker.DockerClient instance.
            If None, a new one is created from the environment.
        container_name: Name of the OpenFOAM container.
    """

    def __init__(
        self,
        docker_sdk: Any | None = None,
        container_name: str | None = None,
    ) -> None:
        if docker_sdk is None:
            docker_sdk = _connect_docker()
        self._sdk = docker_sdk
        self._container_name = container_name or config.OPENFOAM_CONTAINER

    def _get_container(self):
        """Get the OpenFOAM container object."""
        return self._sdk.containers.get(self._container_name)

    def exec_command(
        self,
        cmd: str,
        case_dir: str | None = None,
        timeout: int = 3600,
    ) -> dict:
        """Run a command in the OpenFOAM container.

        Args:
            cmd: The command string to execute.
            case_dir: If provided, cd to this directory first.
            timeout: Timeout in seconds.

        Returns:
            Dict with keys: stdout, stderr, exit_code.
        """
        container = self._get_container()

        if case_dir and "cd" not in cmd:
            full_cmd = f"bash -c 'cd {case_dir} && {cmd}'"
        else:
            full_cmd = cmd

        log.info("docker_exec", container=self._container_name, cmd=cmd[:100])

        result = container.exec_run(
            full_cmd,
            demux=True,
            workdir=case_dir,
        )

        stdout = ""
        stderr = ""
        if result.output:
            if result.output[0]:
                stdout = result.output[0].decode("utf-8", errors="replace")
            if result.output[1]:
                stderr = result.output[1].decode("utf-8", errors="replace")

        log.info(
            "docker_exec_done",
            exit_code=result.exit_code,
            stdout_len=len(stdout),
            stderr_len=len(stderr),
        )

        return ExecResult(stdout=stdout, stderr=stderr, exit_code=result.exit_code).to_dict()

    def stream_command(
        self, cmd: str, case_dir: str | None = None
    ) -> Iterator[str]:
        """Stream stdout from a long-running command line by line.

        Args:
            cmd: The command string.
            case_dir: Working directory inside the container.

        Yields:
            Lines of output from stdout.
        """
        container = self._get_container()

        if case_dir:
            full_cmd = f"bash -c 'cd {case_dir} && {cmd}'"
        else:
            full_cmd = cmd

        _, stream = container.exec_run(full_cmd, stream=True, demux=False)
        for chunk in stream:
            if chunk:
                text = chunk.decode("utf-8", errors="replace")
                for line in text.splitlines():
                    yield line

    def copy_to_container(self, local_path: Path, container_path: str) -> None:
        """Copy a file from the host into the container.

        Args:
            local_path: Path to the file on the host.
            container_path: Destination path inside the container.
        """
        container = self._get_container()

        # Create a tar archive in memory
        buf = BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            tar.add(str(local_path), arcname=local_path.name)
        buf.seek(0)

        dest_dir = str(Path(container_path).parent)
        container.put_archive(dest_dir, buf.getvalue())
        log.info("copied_to_container", local=str(local_path), container=container_path)

    def copy_from_container(self, container_path: str, local_path: Path) -> None:
        """Copy a file from the container to the host.

        Args:
            container_path: Path inside the container.
            local_path: Destination on the host.
        """
        container = self._get_container()
        stream, _ = container.get_archive(container_path)

        buf = BytesIO()
        for chunk in stream:
            buf.write(chunk)
        buf.seek(0)

        with tarfile.open(fileobj=buf) as tar:
            members = tar.getmembers()
            if members:
                f = tar.extractfile(members[0])
                if f:
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                    local_path.write_bytes(f.read())
        log.info("copied_from_container", container=container_path, local=str(local_path))
