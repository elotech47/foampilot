"""Unit tests for the Version Registry and v11 profile."""

import pytest
from foampilot.version.registry import VersionRegistry
from foampilot.version.profiles.foundation_v11 import FoundationV11


@pytest.fixture(autouse=True)
def reset_registry():
    """Reset the registry singleton before each test."""
    VersionRegistry.get().reset()
    yield
    VersionRegistry.get().reset()


def test_set_and_get_active():
    registry = VersionRegistry.get()
    registry.set_active("foundation", "11")
    profile = registry.active()
    assert profile.VERSION == "11"
    assert profile.DISTRIBUTION == "foundation"


def test_unknown_version_raises():
    registry = VersionRegistry.get()
    with pytest.raises(ValueError, match="No profile"):
        registry.set_active("foundation", "99")


def test_v11_validate_solver_simplerFoam():
    registry = VersionRegistry.get()
    registry.set_active("foundation", "11")
    profile = registry.active()
    assert profile.validate_solver("simpleFoam") is True


def test_v11_validate_solver_modular_returns_false():
    """incompressibleFluid is a v12+ modular solver — should not validate on v11."""
    registry = VersionRegistry.get()
    registry.set_active("foundation", "11")
    profile = registry.active()
    assert profile.validate_solver("incompressibleFluid") is False


def test_v11_validate_solver_icoFoam():
    registry = VersionRegistry.get()
    registry.set_active("foundation", "11")
    profile = registry.active()
    assert profile.validate_solver("icoFoam") is True


def test_v11_validate_feature_eval_false():
    registry = VersionRegistry.get()
    registry.set_active("foundation", "11")
    profile = registry.active()
    assert profile.validate_feature("eval_directive") is False


def test_v11_validate_feature_supported():
    registry = VersionRegistry.get()
    registry.set_active("foundation", "11")
    profile = registry.active()
    assert profile.validate_feature("kOmegaSST") is True


def test_v11_get_solver_physics_key():
    registry = VersionRegistry.get()
    registry.set_active("foundation", "11")
    profile = registry.active()
    assert profile.get_solver("incompressible_steady_turbulent") == "simpleFoam"
    assert profile.get_solver("multiphase_vof") == "interFoam"
    assert profile.get_solver("nonexistent") is None


def test_v11_turbulence_models():
    registry = VersionRegistry.get()
    registry.set_active("foundation", "11")
    profile = registry.active()
    assert profile.validate_turbulence_model("kOmegaSST") is True
    assert profile.validate_turbulence_model("fakeModel") is False


def test_v11_prompt_context_contains_version():
    registry = VersionRegistry.get()
    registry.set_active("foundation", "11")
    profile = registry.active()
    ctx = profile.prompt_context()
    assert "v11" in ctx
    assert "simpleFoam" in ctx
    assert "CRITICAL" in ctx


def test_v11_uses_traditional_solvers():
    registry = VersionRegistry.get()
    registry.set_active("foundation", "11")
    profile = registry.active()
    assert profile.USES_MODULAR_SOLVERS is False


def test_v13_uses_modular_solvers():
    registry = VersionRegistry.get()
    registry.set_active("foundation", "13")
    profile = registry.active()
    assert profile.USES_MODULAR_SOLVERS is True


def test_available_profiles():
    registry = VersionRegistry.get()
    profiles = registry.available_profiles()
    assert ("foundation", "11") in profiles
    assert ("foundation", "13") in profiles
