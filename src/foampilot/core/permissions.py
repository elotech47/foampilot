"""Permission checking and approval system.

Three levels:
- AUTO   : Read-only or safe tools — execute without asking.
- NOTIFY : Show the action but don't block execution.
- APPROVE: Require explicit user confirmation before executing.
"""

from enum import Enum

from foampilot import config


class PermissionLevel(str, Enum):
    AUTO = "AUTO"
    NOTIFY = "NOTIFY"
    APPROVE = "APPROVE"


class PermissionDeniedError(Exception):
    """Raised when a user denies approval for a tool call."""


class PermissionChecker:
    """Evaluates whether a tool call may proceed given the current permission mode."""

    def __init__(self, mode: str | None = None) -> None:
        self._mode = mode or config.PERMISSION_MODE

    def requires_approval(self, level: PermissionLevel) -> bool:
        """Return True if this level requires interactive approval in the current mode."""
        if self._mode == "auto_approve":
            return False
        if self._mode == "strict":
            return level in (PermissionLevel.NOTIFY, PermissionLevel.APPROVE)
        # standard mode
        return level == PermissionLevel.APPROVE

    def should_notify(self, level: PermissionLevel) -> bool:
        """Return True if the UI should display this action even without blocking."""
        if self._mode == "auto_approve":
            return False
        return level in (PermissionLevel.NOTIFY, PermissionLevel.APPROVE)
