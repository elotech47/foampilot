"""Global configuration — reads from environment variables with sensible defaults.

All modules import configuration from here. Never read os.environ directly in tool/agent code.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
SRC_ROOT = Path(__file__).parent

def _resolve(env_key: str, default: Path) -> Path:
    """Read a path from env, resolve relative paths against PROJECT_ROOT."""
    raw = os.environ.get(env_key)
    if raw is None:
        return default
    p = Path(raw)
    return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


CASES_DIR = _resolve("FOAMPILOT_CASES_DIR", PROJECT_ROOT / "cases")
INDEX_DIR = _resolve("FOAMPILOT_INDEX_DIR", SRC_ROOT / "index" / "data")
TUTORIALS_DIR = _resolve("FOAMPILOT_TUTORIALS_DIR", PROJECT_ROOT / "OpenFOAM-11" / "tutorials")

# ── Anthropic API ──────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")

# Default model for most tasks
MODEL: str = os.environ.get("FOAMPILOT_MODEL", "claude-sonnet-4-5-20250929")

# Model for complex reasoning tasks (compaction, difficult diagnosis)
MODEL_COMPLEX: str = os.environ.get("FOAMPILOT_MODEL_COMPLEX", "claude-opus-4-5")

# ── Agent Behavior ─────────────────────────────────────────────────────────────
MAX_TURNS: int = int(os.environ.get("FOAMPILOT_MAX_TURNS", "100"))

# Fraction of context window at which compaction is triggered (0.0–1.0)
COMPACTION_THRESHOLD: float = float(
    os.environ.get("FOAMPILOT_COMPACTION_THRESHOLD", "0.70")
)

# "standard" | "auto_approve" | "strict"
PERMISSION_MODE: str = os.environ.get("FOAMPILOT_PERMISSION_MODE", "standard")

# ── OpenFOAM / Docker ──────────────────────────────────────────────────────────
OPENFOAM_VERSION: str = os.environ.get("OPENFOAM_VERSION", "11")
OPENFOAM_DISTRIBUTION: str = os.environ.get("OPENFOAM_DISTRIBUTION", "foundation")
OPENFOAM_CONTAINER: str = os.environ.get("OPENFOAM_CONTAINER", "foampilot-openfoam")

# Path inside the OpenFOAM container where cases are mounted.
# Must match the volume mount in docker-compose.yml (./cases:/home/openfoam/cases).
CONTAINER_CASES_DIR: str = os.environ.get("FOAMPILOT_CONTAINER_CASES_DIR", "/home/openfoam/cases")

# OpenFOAM install prefix inside the container (e.g. /opt/openfoam11).
CONTAINER_FOAM_DIR: str = os.environ.get(
    "FOAMPILOT_CONTAINER_FOAM_DIR", f"/opt/openfoam{OPENFOAM_VERSION}"
)

# ── Context Window Sizes (token counts) ───────────────────────────────────────
# sonnet-4-5 has a 200k token context window
CONTEXT_WINDOW_TOKENS: int = int(os.environ.get("FOAMPILOT_CONTEXT_WINDOW", "200000"))
