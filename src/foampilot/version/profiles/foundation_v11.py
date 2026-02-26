"""OpenFOAM Foundation v11 version profile.

v11 uses traditional solver names (simpleFoam, pimpleFoam, etc.) — NOT modular solvers.
"""

from foampilot.version.profiles.base import VersionProfile


class FoundationV11(VersionProfile):
    """Profile for OpenFOAM Foundation version 11."""

    VERSION = "11"
    DISTRIBUTION = "foundation"
    DOCKER_IMAGE = "openfoam/openfoam11-paraview510"

    USES_MODULAR_SOLVERS = False

    SOLVERS = {
        # Incompressible
        "incompressible_laminar_transient": "icoFoam",
        "incompressible_steady_laminar": "icoFoam",
        "incompressible_steady_turbulent": "simpleFoam",
        "incompressible_transient_turbulent": "pimpleFoam",
        "incompressible_rotating": "SRFSimpleFoam",
        "incompressible_transient_rotating": "SRFPimpleFoam",
        # Compressible
        "compressible_steady": "rhoSimpleFoam",
        "compressible_transient": "rhoPimpleFoam",
        "compressible_transient_central": "rhoCentralFoam",
        "compressible_sonic": "sonicFoam",
        # Multiphase
        "multiphase_vof": "interFoam",
        "multiphase_compressible_vof": "compressibleInterFoam",
        "multiphase_mphase": "multiphaseInterFoam",
        "multiphase_drift_flux": "driftFluxFoam",
        # Heat transfer
        "heat_transfer_buoyant_steady": "buoyantSimpleFoam",
        "heat_transfer_buoyant_transient": "buoyantPimpleFoam",
        "heat_transfer_cht_steady": "chtMultiRegionSimpleFoam",
        "heat_transfer_cht_transient": "chtMultiRegionFoam",
        # Combustion / reactive
        "combustion_steady": "reactingFoam",
        "combustion_transient": "reactingFoam",
        "combustion_premixed": "XiFoam",
        # Lagrangian / particles
        "lagrangian_particles": "lagrangianParcelFoam",
        # Electromagnetics
        "electromagnetics_magnetohydro": "mhdFoam",
        # Porous / Darcy
        "porous_steady": "porousSimpleFoam",
    }

    TURBULENCE_MODELS = [
        "kEpsilon",
        "kOmegaSST",
        "kOmega",
        "realizableKE",
        "RNGkEpsilon",
        "SpalartAllmaras",
        "LRR",
        "SSG",
        "Smagorinsky",
        "WALE",
        "dynamicKEqn",
        "laminar",
    ]

    BC_TYPES = {
        "velocity": [
            "fixedValue",
            "zeroGradient",
            "inletOutlet",
            "pressureInletOutletVelocity",
            "noSlip",
            "slip",
            "movingWallVelocity",
            "rotatingWallVelocity",
            "uniformFixedValue",
            "flowRateInletVelocity",
            "surfaceNormalFixedValue",
            "freestream",
        ],
        "pressure": [
            "fixedValue",
            "zeroGradient",
            "fixedFluxPressure",
            "totalPressure",
            "prghPressure",
            "freestreamPressure",
        ],
        "turbulence_k": [
            "fixedValue",
            "zeroGradient",
            "kqRWallFunction",
            "turbulentIntensityKineticEnergyInlet",
        ],
        "turbulence_epsilon": [
            "fixedValue",
            "zeroGradient",
            "epsilonWallFunction",
            "turbulentMixingLengthDissipationRateInlet",
        ],
        "turbulence_omega": [
            "fixedValue",
            "zeroGradient",
            "omegaWallFunction",
            "turbulentMixingLengthFrequencyInlet",
        ],
        "temperature": [
            "fixedValue",
            "zeroGradient",
            "inletOutlet",
            "fixedGradient",
            "externalWallHeatFluxTemperature",
        ],
        "nut": [
            "nutkWallFunction",
            "nutUWallFunction",
            "nutLowReWallFunction",
            "calculated",
            "zeroGradient",
        ],
    }

    SCHEMES = {
        "ddtSchemes": [
            "steadyState",
            "Euler",
            "backward",
            "CrankNicolson 0.9",
            "localEuler",
        ],
        "gradSchemes": [
            "Gauss linear",
            "leastSquares",
            "Gauss pointLinear",
            "cellMDLimited Gauss linear 1",
            "cellLimited Gauss linear 1",
        ],
        "divSchemes": [
            "Gauss linear",
            "Gauss linearUpwind grad(U)",
            "Gauss upwind",
            "Gauss LUST grad(U)",
            "Gauss limitedLinear 1",
            "Gauss limitedLinearV 1",
            "Gauss vanLeer",
            "Gauss MUSCL",
            "bounded Gauss linearUpwind grad(U)",
            "bounded Gauss upwind",
        ],
        "laplacianSchemes": [
            "Gauss linear corrected",
            "Gauss linear limited corrected 0.5",
            "Gauss linear uncorrected",
        ],
        "interpolationSchemes": [
            "linear",
            "linearUpwind grad(U)",
        ],
        "snGradSchemes": [
            "corrected",
            "limited corrected 0.5",
            "uncorrected",
        ],
    }

    UNSUPPORTED_FEATURES = [
        "overset_mesh",
        "modular_solvers",
        "eval_directive",
        "incompressibleFluid_solver",
        "fluid_solver",
    ]

    TUTORIAL_BASE_PATH = "/opt/openfoam11/tutorials"
    TUTORIAL_STRUCTURE = "by_solver"

    MESH_UTILITIES = [
        "blockMesh",
        "snappyHexMesh",
        "checkMesh",
        "transformPoints",
        "mirrorMesh",
        "mergeMeshes",
        "createPatch",
        "refineMesh",
        "extrudeMesh",
        "surfaceFeatureExtract",
        "decomposePar",
        "reconstructPar",
        "topoSet",
        "setFields",
    ]

    POST_PROCESSING_UTILITIES = [
        "foamToVTK",
        "foamToEnsight",
        "postProcess",
        "probeLocations",
        "sample",
        "wallShearStress",
        "yPlus",
        "forces",
        "forceCoeffs",
        "turbulenceFields",
        "residuals",
    ]

    QUIRKS = [
        "v11 uses 'RAS' not 'RANS' in turbulenceProperties simulationType",
        "v11 uses 'application simpleFoam' not 'solver incompressibleFluid'",
        "v11 blockMesh is run as 'blockMesh' not 'blockMesh -dict system/blockMeshDict'",
        "v11 does not support #eval directive in dictionary files",
        "v11 turbulenceProperties is in constant/ directory",
        "v11 uses 'turbulenceModel' keyword in turbulenceProperties, not 'RASModel'",
        "v11 walls use noSlip BC for velocity, not fixedValue (0 0 0) in newer tutorial style",
        "v11 fvSolution SIMPLE dict uses 'nNonOrthogonalCorrectors', not 'nCorrectors'",
    ]
