"""Unit tests for the edit_foam_dict tool."""

import shutil
from pathlib import Path

import pytest
from foampilot.tools.foam.edit_foam_dict import EditFoamDictTool

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_dicts"


@pytest.fixture
def tmp_control_dict(tmp_path):
    """Copy the sample controlDict to a temp directory."""
    src = FIXTURES / "controlDict"
    dest = tmp_path / "controlDict"
    shutil.copy(src, dest)
    return dest


@pytest.fixture
def tmp_fv_solution(tmp_path):
    """Copy the sample fvSolution to a temp directory."""
    src = FIXTURES / "fvSolution"
    dest = tmp_path / "fvSolution"
    shutil.copy(src, dest)
    return dest


def test_edit_top_level_key(tmp_control_dict):
    tool = EditFoamDictTool()
    result = tool.execute(
        path=str(tmp_control_dict),
        key_path="endTime",
        new_value=1000,
    )
    assert result.success
    assert result.data["old_value"] == 500
    assert result.data["new_value"] == 1000


def test_edit_top_level_writes_to_disk(tmp_control_dict):
    tool = EditFoamDictTool()
    tool.execute(path=str(tmp_control_dict), key_path="endTime", new_value=1000)

    from foampilot.index.parser import parse_foam_file
    updated = parse_foam_file(tmp_control_dict)
    assert updated.data["endTime"] == 1000


def test_edit_nested_key(tmp_fv_solution):
    tool = EditFoamDictTool()
    result = tool.execute(
        path=str(tmp_fv_solution),
        key_path="SIMPLE.nNonOrthogonalCorrectors",
        new_value=3,
    )
    assert result.success
    assert result.data["new_value"] == 3


def test_edit_file_not_found(tmp_path):
    tool = EditFoamDictTool()
    result = tool.execute(
        path=str(tmp_path / "nonexistent"),
        key_path="endTime",
        new_value=100,
    )
    assert not result.success
    assert "not found" in result.error
