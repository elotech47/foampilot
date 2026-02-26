"""Abstract base class for OpenFOAM version profiles.

All version-specific knowledge lives in concrete subclasses of VersionProfile.
Class-level attributes are declared here with empty defaults; each concrete
subclass overrides them as plain class variables (NOT via dataclass machinery).
"""

from abc import ABC


class VersionProfile(ABC):
    """Abstract base for a specific OpenFOAM version/distribution combination.

    Subclasses declare all data as class-level attributes — no __init__ needed.
    This keeps profiles simple: just class-variable assignments, no instantiation args.
    """

    # ── Identity ───────────────────────────────────────────────────────────────
    VERSION: str = ""
    DISTRIBUTION: str = ""   # "foundation" | "esi"
    DOCKER_IMAGE: str = ""

    # ── Solver registry ────────────────────────────────────────────────────────
    # Maps physics description → actual solver binary name
    SOLVERS: dict[str, str] = {}

    # Whether this version uses modular solvers (v12+ foundation, ESI)
    USES_MODULAR_SOLVERS: bool = False

    # ── Turbulence ─────────────────────────────────────────────────────────────
    TURBULENCE_MODELS: list[str] = []

    # ── Boundary conditions ────────────────────────────────────────────────────
    # Maps field type → list of available BC types
    BC_TYPES: dict[str, list[str]] = {}

    # ── Numerical schemes ──────────────────────────────────────────────────────
    SCHEMES: dict[str, list[str]] = {}

    # ── Features ───────────────────────────────────────────────────────────────
    UNSUPPORTED_FEATURES: list[str] = []

    # ── Tutorial layout ────────────────────────────────────────────────────────
    TUTORIAL_BASE_PATH: str = ""
    TUTORIAL_STRUCTURE: str = "by_solver"  # "by_solver" | "by_physics"

    # ── Known quirks ───────────────────────────────────────────────────────────
    QUIRKS: list[str] = []

    # ── Utilities ──────────────────────────────────────────────────────────────
    MESH_UTILITIES: list[str] = []
    POST_PROCESSING_UTILITIES: list[str] = []

    def validate_solver(self, solver_name: str) -> bool:
        """Return True if solver_name is a known binary for this version."""
        return solver_name in self.SOLVERS.values()

    def validate_feature(self, feature: str) -> bool:
        """Return True if the feature is supported in this version."""
        return feature not in self.UNSUPPORTED_FEATURES

    def validate_turbulence_model(self, model: str) -> bool:
        """Return True if the turbulence model is available."""
        return model in self.TURBULENCE_MODELS

    def get_solver(self, physics_key: str) -> str | None:
        """Look up the solver binary for a physics description key.

        Args:
            physics_key: e.g. "incompressible_steady_turbulent"

        Returns:
            Solver binary name, or None if not found.
        """
        return self.SOLVERS.get(physics_key)

    def prompt_context(self) -> str:
        """Generate a version-specific prompt context string for injection into LLM prompts."""
        solvers_list = "\n".join(f"  - {k}: {v}" for k, v in self.SOLVERS.items())
        quirks_list = "\n".join(f"  - {q}" for q in self.QUIRKS)
        unsupported = ", ".join(self.UNSUPPORTED_FEATURES) or "none"
        modular = "YES (modular solvers)" if self.USES_MODULAR_SOLVERS else "NO (traditional solver names)"

        return f"""## OpenFOAM Version Context
You are working with OpenFOAM {self.DISTRIBUTION.capitalize()} v{self.VERSION}.
Docker image: {self.DOCKER_IMAGE}
Modular solvers: {modular}
Unsupported features: {unsupported}

Available solvers (physics \u2192 binary):
{solvers_list}

Known quirks \u2014 CRITICAL, do not violate:
{quirks_list}

CRITICAL: Do not use syntax or features from other OpenFOAM versions.
"""
