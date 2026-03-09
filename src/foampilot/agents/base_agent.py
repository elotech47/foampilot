"""Shared base class for all FoamPilot agents."""

from __future__ import annotations

from typing import Any


class BaseAgent:
    """Common constructor shared by all pipeline agents.

    Provides ``docker_client``, ``event_callback``, and ``approval_callback``
    as instance attributes so every subclass has a consistent interface and
    the orchestrator can safely pass ``**docker_kwargs`` to any agent without
    a crash.
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
