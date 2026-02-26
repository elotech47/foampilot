"""OpenFOAM Foundation v13 version profile.

v13 uses modular solvers (incompressibleFluid, fluid, etc.) — NOT traditional solver names.
"""

from foampilot.version.profiles.base import VersionProfile


class FoundationV13(VersionProfile):
    """Profile for OpenFOAM Foundation version 13."""

    VERSION = "13"
    DISTRIBUTION = "foundation"
    DOCKER_IMAGE = "openfoam/openfoam13-paraview510"

    USES_MODULAR_SOLVERS = True

    SOLVERS = {
        # Modular solver — physics type → solver binary (all use 'foamRun')
        "incompressible_steady_turbulent": "incompressibleFluid",
        "incompressible_transient_turbulent": "incompressibleFluid",
        "incompressible_laminar": "incompressibleFluid",
        "compressible_steady": "fluid",
        "compressible_transient": "fluid",
        "multiphase_vof": "multiphaseVoF",
        "heat_transfer_buoyant": "buoyantFluid",
        "combustion": "multicomponentFluid",
    }

    TURBULENCE_MODELS = [
        "kEpsilon",
        "kOmegaSST",
        "kOmega",
        "realizableKE",
        "SpalartAllmaras",
        "Smagorinsky",
        "WALE",
        "laminar",
    ]

    UNSUPPORTED_FEATURES = [
        "simpleFoam_binary",
        "pimpleFoam_binary",
        "icoFoam_binary",
    ]

    TUTORIAL_BASE_PATH = "/opt/openfoam13/tutorials"
    TUTORIAL_STRUCTURE = "by_physics"

    QUIRKS = [
        "v13 uses 'foamRun -solver incompressibleFluid' not 'simpleFoam'",
        "v13 solver is specified in controlDict as 'solver incompressibleFluid'",
        "v13 supports #eval directive in dictionary files",
        "v13 uses 'RANS' not 'RAS' in turbulenceProperties simulationType",
    ]
