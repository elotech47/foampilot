"""Generate version-specific prompt sections from the active VersionProfile."""

from foampilot.version.registry import VersionRegistry


def get_version_context() -> str:
    """Return a version-specific prompt section for injection into any agent system prompt."""
    return VersionRegistry.get().active().prompt_context()
