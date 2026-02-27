"""Unit tests for the tutorial index searcher."""

import json
from pathlib import Path

import pytest
from foampilot.index.builder import TutorialEntry
from foampilot.index.searcher import TutorialSearcher


def _make_entries() -> list[dict]:
    return [
        {
            "path": "incompressibleFluid/cavity",
            "solver": "icoFoam",
            "version": "11",
            "files": ["system/controlDict", "0/U", "0/p"],
            "boundary_patches": {"movingWall": "fixedValue", "fixedWalls": "noSlip"},
            "physics_tags": ["incompressible", "laminar", "transient"],
            "turbulence_model": None,
            "has_heat_transfer": False,
            "has_multiphase": False,
            "mesh_type": "blockMesh",
            "description": "incompressibleFluid/cavity — icoFoam (incompressible, laminar, transient, blockMesh)",
            "embedding": None,
        },
        {
            "path": "incompressibleFluid/pitzDaily",
            "solver": "simpleFoam",
            "version": "11",
            "files": ["system/controlDict", "0/U", "0/p", "0/k"],
            "boundary_patches": {"inlet": "fixedValue", "outlet": "zeroGradient"},
            "physics_tags": ["incompressible", "turbulent", "steady"],
            "turbulence_model": "kEpsilon",
            "has_heat_transfer": False,
            "has_multiphase": False,
            "mesh_type": "blockMesh",
            "description": "incompressibleFluid/pitzDaily — simpleFoam (incompressible, turbulent, steady, kEpsilon, blockMesh)",
            "embedding": None,
        },
        {
            "path": "compressibleVoF/sphereDrop",
            "solver": "interFoam",
            "version": "11",
            "files": ["system/controlDict", "0/alpha.water"],
            "boundary_patches": {"atmosphere": "inletOutlet"},
            "physics_tags": ["multiphase", "transient"],
            "turbulence_model": None,
            "has_heat_transfer": False,
            "has_multiphase": True,
            "mesh_type": "blockMesh",
            "description": "compressibleVoF/sphereDrop — interFoam (multiphase, transient, blockMesh)",
            "embedding": None,
        },
    ]


@pytest.fixture
def searcher(tmp_path) -> TutorialSearcher:
    """Create a searcher backed by a fake index file."""
    index_file = tmp_path / "tutorial_index_v11.json"
    index_file.write_text(json.dumps(_make_entries()))
    return TutorialSearcher(index_dir=tmp_path, version="11")


def test_search_by_solver(searcher):
    results = searcher.search(solver="simpleFoam")
    assert len(results) == 1
    assert results[0].entry.solver == "simpleFoam"


def test_search_by_solver_no_match(searcher):
    # When an exact solver match fails, the searcher falls back to relaxed search
    # and returns results from the whole index rather than an empty list.
    results = searcher.search(solver="rhoPimpleFoam")
    assert len(results) > 0  # fallback returns best-effort candidates


def test_search_by_physics_tags(searcher):
    results = searcher.search(physics_tags=["incompressible", "turbulent"])
    assert len(results) == 1
    assert results[0].entry.path == "incompressibleFluid/pitzDaily"


def test_search_top_n(searcher):
    results = searcher.search(top_n=2)
    assert len(results) <= 2


def test_search_returns_all_if_no_filter(searcher):
    results = searcher.search(top_n=100)
    assert len(results) == 3


def test_search_by_keyword(searcher):
    results = searcher.search(keywords=["cavity"])
    assert any("cavity" in r.entry.path for r in results)


def test_search_requires_mesh_type(searcher):
    # When no snappyHexMesh cases exist, the searcher falls back to all cases.
    results = searcher.search(require_mesh_type="snappyHexMesh")
    assert len(results) > 0  # fallback: returns best-effort candidates


def test_search_by_mesh_type_block(searcher):
    results = searcher.search(require_mesh_type="blockMesh")
    assert len(results) == 3


def test_search_result_has_score(searcher):
    results = searcher.search(solver="simpleFoam")
    assert results[0].score > 0


def test_search_result_has_reasons(searcher):
    results = searcher.search(solver="simpleFoam", physics_tags=["incompressible"])
    assert len(results[0].match_reasons) > 0


def test_search_empty_index(tmp_path):
    index_file = tmp_path / "tutorial_index_v11.json"
    index_file.write_text("[]")
    searcher = TutorialSearcher(index_dir=tmp_path, version="11")
    results = searcher.search(solver="simpleFoam")
    assert results == []


def test_search_missing_index(tmp_path):
    searcher = TutorialSearcher(index_dir=tmp_path, version="11")
    results = searcher.search(solver="simpleFoam")
    assert results == []
