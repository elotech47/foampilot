"""Centralized path resolution for container ↔ host translation.

All tools that accept file paths should call ``resolve_host_path()`` before
touching the filesystem.  The mapping table is built entirely from
``foampilot.config`` — no hard-coded paths outside of config.
"""

from __future__ import annotations

from pathlib import Path

from foampilot import config

# ── Mapping table: (container_prefix, host_directory) ─────────────────────────
# Order matters: more-specific prefixes must come first so that
# /opt/openfoam11/tutorials matches before /opt/openfoam11.
_CONTAINER_TO_HOST: list[tuple[str, Path]] = [
    (f"{config.CONTAINER_FOAM_DIR}/tutorials", config.TUTORIALS_DIR),
    (config.CONTAINER_FOAM_DIR,                config.PROJECT_ROOT / f"OpenFOAM-{config.OPENFOAM_VERSION}"),
    (config.CONTAINER_CASES_DIR,               config.CASES_DIR),
]


def resolve_host_path(path_str: str) -> Path:
    """Translate *any* path the LLM might provide into a host-side ``Path``.

    Resolution order:
      1. Container prefix match  → swap prefix for host equivalent
      2. Already absolute        → return as-is
      3. Relative                → resolve against PROJECT_ROOT
    """
    for container_prefix, host_dir in _CONTAINER_TO_HOST:
        if path_str == container_prefix:
            return host_dir
        if path_str.startswith(container_prefix + "/"):
            suffix = path_str[len(container_prefix) + 1:]
            return host_dir / suffix

    p = Path(path_str)
    if p.is_absolute():
        return p

    return config.PROJECT_ROOT / path_str
