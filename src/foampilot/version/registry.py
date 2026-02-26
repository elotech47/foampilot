"""Version registry — singleton that holds the active OpenFOAM version profile.

All tools and prompts access the version through VersionRegistry.active().
Never import a specific profile directly in tool or agent code.
"""

import structlog

from foampilot.version.profiles.base import VersionProfile

log = structlog.get_logger(__name__)

_PROFILE_MAP: dict[tuple[str, str], type[VersionProfile]] = {}


def _register_profiles() -> None:
    """Lazily import and register all known profiles."""
    global _PROFILE_MAP
    if _PROFILE_MAP:
        return

    from foampilot.version.profiles.foundation_v11 import FoundationV11
    from foampilot.version.profiles.foundation_v13 import FoundationV13

    _PROFILE_MAP = {
        ("foundation", "11"): FoundationV11,
        ("foundation", "13"): FoundationV13,
    }


class VersionRegistry:
    """Singleton registry for the active version profile.

    Usage:
        registry = VersionRegistry.get()
        registry.set_active("foundation", "11")
        profile = registry.active()
        profile.validate_solver("simpleFoam")  # True
    """

    _instance: "VersionRegistry | None" = None
    _active_profile: VersionProfile | None = None

    @classmethod
    def get(cls) -> "VersionRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_active(self, distribution: str, version: str) -> None:
        """Set the active profile by distribution and version number.

        Args:
            distribution: "foundation" or "esi"
            version: e.g. "11", "13"
        """
        _register_profiles()
        key = (distribution.lower(), version)
        profile_cls = _PROFILE_MAP.get(key)
        if profile_cls is None:
            available = list(_PROFILE_MAP.keys())
            raise ValueError(
                f"No profile for ({distribution!r}, {version!r}). "
                f"Available: {available}"
            )
        self._active_profile = profile_cls()
        log.info("version_profile_set", distribution=distribution, version=version)

    def active(self) -> VersionProfile:
        """Return the currently active version profile.

        Raises:
            RuntimeError: If no profile has been set yet.
        """
        if self._active_profile is None:
            # Auto-load from config
            from foampilot import config
            self.set_active(config.OPENFOAM_DISTRIBUTION, config.OPENFOAM_VERSION)
        return self._active_profile

    def available_profiles(self) -> list[tuple[str, str]]:
        """Return list of (distribution, version) tuples for all registered profiles."""
        _register_profiles()
        return list(_PROFILE_MAP.keys())

    def reset(self) -> None:
        """Reset the active profile (useful for testing)."""
        self._active_profile = None
