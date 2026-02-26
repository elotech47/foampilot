"""Unit tests for the checkMesh output parser."""

from pathlib import Path

import pytest
from foampilot.tools.foam.check_mesh import CheckMeshTool, parse_checkmesh_output

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_logs"


def test_parse_mesh_error_log():
    text = (FIXTURES / "mesh_error.log").read_text()
    result = parse_checkmesh_output(text)
    assert result["passed"] is False
    assert result["failed_checks"] > 0
    assert len(result["issues"]) > 0


def test_parse_mesh_error_cells():
    text = (FIXTURES / "mesh_error.log").read_text()
    result = parse_checkmesh_output(text)
    assert result["cells"] == 2000


def test_parse_mesh_error_non_ortho():
    text = (FIXTURES / "mesh_error.log").read_text()
    result = parse_checkmesh_output(text)
    # The log has "Max aspect ratio: 523.4"
    assert result["max_aspect_ratio"] is not None
    assert result["max_aspect_ratio"] > 100


def test_parse_mesh_good():
    good_log = """
Mesh stats
    cells:            10000
    faces:            20000
    points:           11000

Checking geometry...
    Max non-orthogonality = 35.2
    Max skewness = 0.5
    Max aspect ratio: 4.2
Mesh OK.
    """
    result = parse_checkmesh_output(good_log)
    assert result["passed"] is True
    assert result["cells"] == 10000
    assert abs(result["max_non_orthogonality"] - 35.2) < 0.01
    assert abs(result["max_skewness"] - 0.5) < 0.01
    assert abs(result["max_aspect_ratio"] - 4.2) < 0.01


def test_check_mesh_tool_no_docker_no_log(tmp_path):
    tool = CheckMeshTool(docker_client=None)
    result = tool.execute(case_dir=str(tmp_path))
    assert not result.success


def test_check_mesh_tool_no_docker_with_log(tmp_path):
    log_content = (FIXTURES / "mesh_error.log").read_text()
    (tmp_path / "checkMesh.log").write_text(log_content)
    tool = CheckMeshTool(docker_client=None)
    result = tool.execute(case_dir=str(tmp_path))
    assert result.success
    assert not result.data["passed"]
