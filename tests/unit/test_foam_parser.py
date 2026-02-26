"""Unit tests for the OpenFOAM dictionary parser — the most critical parser."""

from pathlib import Path

import pytest
from foampilot.index.parser import FoamFileParser, parse_foam_string

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_dicts"

parser = FoamFileParser()


# ── Basic parsing ──────────────────────────────────────────────────────────────


def test_parse_controlDict_application():
    foam = parse_foam_string(
        (FIXTURES / "controlDict").read_text(), source="controlDict"
    )
    assert foam.data["application"] == "simpleFoam"


def test_parse_controlDict_endTime():
    foam = parse_foam_string(
        (FIXTURES / "controlDict").read_text(), source="controlDict"
    )
    assert foam.data["endTime"] == 500


def test_parse_controlDict_writeCompression():
    foam = parse_foam_string(
        (FIXTURES / "controlDict").read_text(), source="controlDict"
    )
    # "off" → False
    assert foam.data["writeCompression"] is False


def test_parse_controlDict_runTimeModifiable():
    foam = parse_foam_string(
        (FIXTURES / "controlDict").read_text(), source="controlDict"
    )
    assert foam.data["runTimeModifiable"] is True


def test_parse_foamfile_header():
    foam = parse_foam_string(
        (FIXTURES / "controlDict").read_text(), source="controlDict"
    )
    assert foam.foam_file["object"] == "controlDict"
    assert foam.foam_file["class"] == "dictionary"


# ── Nested dicts ───────────────────────────────────────────────────────────────


def test_parse_fvSchemes_ddtSchemes():
    foam = parse_foam_string(
        (FIXTURES / "fvSchemes").read_text(), source="fvSchemes"
    )
    assert foam.data["ddtSchemes"]["default"] == "steadyState"


def test_parse_fvSchemes_divSchemes():
    foam = parse_foam_string(
        (FIXTURES / "fvSchemes").read_text(), source="fvSchemes"
    )
    div = foam.data["divSchemes"]
    assert "default" in div
    assert div["default"] == "none"


def test_parse_fvSolution_solver_p():
    foam = parse_foam_string(
        (FIXTURES / "fvSolution").read_text(), source="fvSolution"
    )
    p_solver = foam.data["solvers"]["p"]
    assert p_solver["solver"] == "GAMG"
    assert p_solver["smoother"] == "GaussSeidel"
    assert abs(p_solver["tolerance"] - 1e-06) < 1e-10
    assert abs(p_solver["relTol"] - 0.1) < 1e-10


def test_parse_fvSolution_simple_block():
    foam = parse_foam_string(
        (FIXTURES / "fvSolution").read_text(), source="fvSolution"
    )
    simple = foam.data["SIMPLE"]
    assert simple["nNonOrthogonalCorrectors"] == 0
    assert simple["consistent"] is True


def test_parse_fvSolution_relaxation():
    foam = parse_foam_string(
        (FIXTURES / "fvSolution").read_text(), source="fvSolution"
    )
    relax = foam.data["relaxationFactors"]["equations"]
    assert abs(relax["U"] - 0.9) < 1e-10
    assert abs(relax["k"] - 0.7) < 1e-10


# ── FoamDict.get dot notation ─────────────────────────────────────────────────


def test_foam_dict_get_simple():
    foam = parse_foam_string(
        (FIXTURES / "controlDict").read_text(), source="controlDict"
    )
    assert foam.get("application") == "simpleFoam"


def test_foam_dict_get_nested():
    foam = parse_foam_string(
        (FIXTURES / "fvSolution").read_text(), source="fvSolution"
    )
    assert foam.get("solvers.p.solver") == "GAMG"


def test_foam_dict_get_default_on_missing():
    foam = parse_foam_string(
        (FIXTURES / "controlDict").read_text(), source="controlDict"
    )
    assert foam.get("nonexistent.key", "fallback") == "fallback"


def test_foam_dict_set():
    foam = parse_foam_string(
        (FIXTURES / "controlDict").read_text(), source="controlDict"
    )
    foam.set("endTime", 1000)
    assert foam.data["endTime"] == 1000


def test_foam_dict_set_nested():
    foam = parse_foam_string(
        (FIXTURES / "fvSolution").read_text(), source="fvSolution"
    )
    foam.set("solvers.p.relTol", 0.05)
    assert abs(foam.get("solvers.p.relTol") - 0.05) < 1e-10


# ── Vector / dimensional values ────────────────────────────────────────────────


def test_parse_uniform_vector():
    text = """
FoamFile { class volVectorField; object U; }
dimensions [0 1 -1 0 0 0 0];
internalField uniform (0 0 0);
boundaryField
{
    inlet { type fixedValue; value uniform (1 0 0); }
    walls { type noSlip; }
}
"""
    foam = parse_foam_string(text, source="U")
    assert foam.data["internalField"] == "uniform [0, 0, 0]" or \
        "uniform" in str(foam.data["internalField"])
    # Boundary field is parsed as nested dict
    assert foam.data["boundaryField"]["walls"]["type"] == "noSlip"
    assert foam.data["boundaryField"]["inlet"]["type"] == "fixedValue"


# ── Comment stripping ──────────────────────────────────────────────────────────


def test_comments_are_stripped():
    text = """
// This is a comment
FoamFile { object test; /* block comment */ class dictionary; }
key /* inline block */ value;
"""
    foam = parse_foam_string(text, source="test")
    assert foam.data.get("key") == "value"


# ── Booleans and numbers ──────────────────────────────────────────────────────


def test_coerce_bool_on():
    foam = parse_foam_string("FoamFile{object x;} runTimeModifiable on;")
    assert foam.data["runTimeModifiable"] is True


def test_coerce_bool_off():
    foam = parse_foam_string("FoamFile{object x;} writeCompression off;")
    assert foam.data["writeCompression"] is False


def test_coerce_int():
    foam = parse_foam_string("FoamFile{object x;} nCorrectors 3;")
    assert foam.data["nCorrectors"] == 3


def test_coerce_float():
    foam = parse_foam_string("FoamFile{object x;} tolerance 1e-06;")
    assert abs(foam.data["tolerance"] - 1e-6) < 1e-12


# ── Quoted keys (regex patterns) ──────────────────────────────────────────────


def test_quoted_regex_key():
    foam = parse_foam_string(
        (FIXTURES / "fvSolution").read_text(), source="fvSolution"
    )
    # The key "(U|k|epsilon)" should be parsed without the outer quotes
    solvers = foam.data["solvers"]
    assert "(U|k|epsilon)" in solvers
