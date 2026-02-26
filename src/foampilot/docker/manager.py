"""Container lifecycle management."""

from __future__ import annotations

from typing import Any

import structlog

from foampilot import config

log = structlog.get_logger(__name__)


class ContainerManager:
    """Manages the lifecycle of the OpenFOAM Docker container.

    Args:
        docker_sdk: Initialized docker.DockerClient instance.
    """

    def __init__(self, docker_sdk: Any | None = None) -> None:
        if docker_sdk is None:
            try:
                import docker
                docker_sdk = docker.from_env()
            except Exception as exc:
                raise RuntimeError(f"Docker not available: {exc}") from exc
        self._sdk = docker_sdk

    def ensure_running(self) -> str:
        """Ensure the OpenFOAM container is running. Start it if not.

        Returns:
            Container ID.
        """
        try:
            container = self._sdk.containers.get(config.OPENFOAM_CONTAINER)
            if container.status != "running":
                log.info("starting_container", name=config.OPENFOAM_CONTAINER)
                container.start()
            return container.id
        except Exception:
            # Container doesn't exist — try to start from docker-compose
            log.warning("container_not_found", name=config.OPENFOAM_CONTAINER)
            raise RuntimeError(
                f"Container '{config.OPENFOAM_CONTAINER}' not found. "
                "Run 'docker-compose up -d' first."
            )

    def is_running(self) -> bool:
        """Return True if the OpenFOAM container is running."""
        try:
            container = self._sdk.containers.get(config.OPENFOAM_CONTAINER)
            return container.status == "running"
        except Exception:
            return False

    def stop(self) -> None:
        """Stop the OpenFOAM container."""
        try:
            container = self._sdk.containers.get(config.OPENFOAM_CONTAINER)
            container.stop()
            log.info("container_stopped", name=config.OPENFOAM_CONTAINER)
        except Exception as exc:
            log.warning("container_stop_failed", error=str(exc))
