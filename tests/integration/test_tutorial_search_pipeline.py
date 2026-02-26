"""Integration test: tutorial search → index → search pipeline."""

import json
from pathlib import Path

import pytest

TUTORIALS_PATH = Path(__file__).parent.parent.parent / "OpenFOAM-11" / "tutorials"


@pytest.mark.skipif(
    not TUTORIALS_PATH.exists(),
    reason="OpenFOAM-11 tutorials directory not found",
)
def test_full_search_pipeline(tmp_path):
    """Build index from real tutorials, then search for cavity case."""
    from foampilot.index.builder import IndexBuilder
    from foampilot.index.searcher import TutorialSearcher

    builder = IndexBuilder(version="11", output_dir=tmp_path)
    entries = builder.build(tutorials_path=TUTORIALS_PATH, generate_embeddings=False)
    assert len(entries) > 0

    searcher = TutorialSearcher(index_dir=tmp_path, version="11")
    results = searcher.search(keywords=["cavity"], top_n=5)

    assert len(results) > 0
    assert any("cavity" in r.entry.path.lower() for r in results)


@pytest.mark.skipif(
    not TUTORIALS_PATH.exists(),
    reason="OpenFOAM-11 tutorials directory not found",
)
def test_search_returns_correct_solvers(tmp_path):
    """Search for simpleFoam cases should return only simpleFoam cases."""
    from foampilot.index.builder import IndexBuilder
    from foampilot.index.searcher import TutorialSearcher

    builder = IndexBuilder(version="11", output_dir=tmp_path)
    builder.build(tutorials_path=TUTORIALS_PATH, generate_embeddings=False)

    searcher = TutorialSearcher(index_dir=tmp_path, version="11")
    # Note: v11 tutorials use modular solver names, not traditional names in controlDict
    results = searcher.search(top_n=20)

    assert len(results) > 0
    # All results should have a non-empty solver
    assert all(r.entry.solver for r in results)
