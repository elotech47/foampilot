"""Unit tests for the solver log parser."""

from pathlib import Path

import pytest
from foampilot.tools.foam.parse_log import ParseLogTool, parse_solver_log

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_logs"


def test_parse_converged_log():
    text = (FIXTURES / "converged_simpleFoam.log").read_text()
    result = parse_solver_log(text)
    assert result["converged"] is True
    assert result["diverged"] is False
    assert result["iterations"] == 2  # Two time steps


def test_parse_converged_residuals():
    text = (FIXTURES / "converged_simpleFoam.log").read_text()
    result = parse_solver_log(text)
    # Should have final residuals from last time step
    assert "Ux" in result["final_residuals"] or "p" in result["final_residuals"]


def test_parse_diverged_log():
    text = (FIXTURES / "diverged_simpleFoam.log").read_text()
    result = parse_solver_log(text)
    assert result["converged"] is False
    assert result["diverged"] is True
    assert result["likely_issue"] is not None


def test_parse_execution_time():
    text = (FIXTURES / "converged_simpleFoam.log").read_text()
    result = parse_solver_log(text)
    assert result["execution_time_s"] is not None
    assert result["execution_time_s"] > 0


def test_parse_log_tool_file_not_found():
    tool = ParseLogTool()
    result = tool.execute(log_path="/nonexistent/file.log")
    assert not result.success
    assert "not found" in result.error


def test_parse_log_tool_success():
    tool = ParseLogTool()
    result = tool.execute(log_path=str(FIXTURES / "converged_simpleFoam.log"))
    assert result.success
    assert "converged" in result.data
    assert result.data["converged"] is True
