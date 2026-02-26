"""Unit tests for the tutorial index builder."""

import json
from pathlib import Path

import pytest
from foampilot.index.builder import IndexBuilder, TutorialEntry

TUTORIALS_PATH = Path(__file__).parent.parent.parent / "OpenFOAM-11" / "tutorials"


@pytest.fixture
def builder(tmp_path):
    return IndexBuilder(version="11", output_dir=tmp_path)


@pytest.mark.skipif(
    not TUTORIALS_PATH.exists(),
    reason="OpenFOAM-11 tutorials directory not found",
)
def test_builder_finds_cases(builder):
    entries = builder.build(tutorials_path=TUTORIALS_PATH, generate_embeddings=False)
    assert len(entries) > 0


@pytest.mark.skipif(
    not TUTORIALS_PATH.exists(),
    reason="OpenFOAM-11 tutorials directory not found",
)
def test_builder_finds_cavity(builder):
    entries = builder.build(tutorials_path=TUTORIALS_PATH, generate_embeddings=False)
    paths = [e.path for e in entries]
    assert any("cavity" in p for p in paths)


@pytest.mark.skipif(
    not TUTORIALS_PATH.exists(),
    reason="OpenFOAM-11 tutorials directory not found",
)
def test_builder_writes_json(builder, tmp_path):
    builder.build(tutorials_path=TUTORIALS_PATH, generate_embeddings=False)
    index_file = tmp_path / "tutorial_index_v11.json"
    assert index_file.exists()
    data = json.loads(index_file.read_text())
    assert isinstance(data, list)
    assert len(data) > 0


@pytest.mark.skipif(
    not TUTORIALS_PATH.exists(),
    reason="OpenFOAM-11 tutorials directory not found",
)
def test_entry_has_required_fields(builder):
    entries = builder.build(tutorials_path=TUTORIALS_PATH, generate_embeddings=False)
    entry = entries[0]
    assert entry.path
    assert entry.solver
    assert entry.version == "11"
    assert isinstance(entry.files, list)
    assert isinstance(entry.physics_tags, list)
    assert entry.mesh_type in ("blockMesh", "snappyHexMesh", "external")


@pytest.mark.skipif(
    not TUTORIALS_PATH.exists(),
    reason="OpenFOAM-11 tutorials directory not found",
)
def test_entry_physics_tags_nonempty(builder):
    entries = builder.build(tutorials_path=TUTORIALS_PATH, generate_embeddings=False)
    # At least some entries should have physics tags
    with_tags = [e for e in entries if e.physics_tags]
    assert len(with_tags) > 0


def test_builder_raises_on_missing_path(builder):
    with pytest.raises(FileNotFoundError):
        builder.build(tutorials_path="/nonexistent/path")
