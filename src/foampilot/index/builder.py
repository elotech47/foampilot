"""Tutorial index builder.

Scans the OpenFOAM tutorial directory tree and extracts structured metadata
for each case. Produces a JSON index and an optional embeddings file.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import structlog
from tqdm import tqdm

from foampilot.index.parser import FoamFileParser, parse_foam_file

log = structlog.get_logger(__name__)

_parser = FoamFileParser()


@dataclass
class TutorialEntry:
    """Structured metadata for a single OpenFOAM tutorial case."""

    path: str                          # Relative path from tutorials root
    solver: str                        # From controlDict application field
    version: str                       # OpenFOAM version this was indexed from
    files: list[str]                   # All files in the case directory
    boundary_patches: dict[str, str]   # patch_name → BC type (from 0/ files)
    physics_tags: list[str]            # Inferred: incompressible, turbulent, steady, ...
    turbulence_model: str | None       # From turbulenceProperties or constant/
    has_heat_transfer: bool
    has_multiphase: bool
    mesh_type: str                     # "blockMesh" | "snappyHexMesh" | "external"
    description: str                   # Human-readable one-liner
    embedding: list[float] | None = None


class IndexBuilder:
    """Scans an OpenFOAM tutorial directory and builds a searchable index.

    Args:
        version: OpenFOAM version string (e.g., "11").
        output_dir: Directory where index JSON will be written.
    """

    def __init__(self, version: str = "11", output_dir: Path | None = None) -> None:
        self._version = version
        self._output_dir = output_dir or (Path(__file__).parent / "data")

    def build(
        self,
        tutorials_path: str | Path | None = None,
        generate_embeddings: bool = False,
    ) -> list[TutorialEntry]:
        """Build the index from the given tutorials directory.

        Args:
            tutorials_path: Path to the OpenFOAM tutorials directory.
                Defaults to /opt/openfoam{version}/tutorials.
            generate_embeddings: Whether to compute semantic embeddings.

        Returns:
            List of TutorialEntry objects.
        """
        if tutorials_path is None:
            tutorials_path = Path(f"/opt/openfoam{self._version}/tutorials")
        tutorials_path = Path(tutorials_path).resolve()

        log.info(
            "index_build_start",
            tutorials_path=str(tutorials_path),
            version=self._version,
            generate_embeddings=generate_embeddings,
        )

        if not tutorials_path.exists():
            log.error("tutorials_path_not_found", path=str(tutorials_path))
            raise FileNotFoundError(f"Tutorials path not found: {tutorials_path}")

        # ── Stage 1: Discover all case directories ─────────────────────────
        case_dirs = list(self._find_cases(tutorials_path))

        if not case_dirs:
            log.warning("no_cases_found", tutorials_path=str(tutorials_path))
            return []

        # ── Stage 2: Extract metadata from each case ────────────────────────
        entries: list[TutorialEntry] = []
        failed = 0
        skipped = 0

        for case_dir in tqdm(case_dirs, desc="Indexing cases", unit="case"):
            rel_path = str(case_dir.relative_to(tutorials_path))
            try:
                entry = self._extract_entry(case_dir, tutorials_path)
                if entry is not None:
                    entries.append(entry)
                else:
                    skipped += 1
            except Exception as exc:
                failed += 1
                log.warning("case_extraction_failed", case=rel_path, error=str(exc))

        log.info(
            "extraction_complete",
            total=len(case_dirs),
            indexed=len(entries),
            skipped=skipped,
            failed=failed,
        )

        # ── Stage 3: Semantic embeddings (optional) ─────────────────────────
        if generate_embeddings:
            self._add_embeddings(entries)

        # ── Stage 4: Persist to disk ─────────────────────────────────────────
        self._save(entries)

        log.info("index_build_complete", entries=len(entries), output_dir=str(self._output_dir))
        return entries

    # ── Case discovery ─────────────────────────────────────────────────────────

    def _find_cases(self, tutorials_path: Path):
        """Yield directories that look like OpenFOAM cases (have system/controlDict)."""
        for root, dirs, _files in os.walk(tutorials_path):
            root_path = Path(root)
            if (root_path / "system" / "controlDict").exists():
                yield root_path
                dirs.clear()  # Don't recurse into sub-cases

    # ── Per-case metadata extraction ───────────────────────────────────────────

    # OpenFOAM-11 modular runner apps — these delegate to a physics module
    _MODULAR_RUNNERS = frozenset({"foamRun", "foamMultiRun"})

    def _extract_entry(self, case_dir: Path, tutorials_root: Path) -> TutorialEntry | None:
        """Extract metadata from a single case directory."""
        rel_path = str(case_dir.relative_to(tutorials_root))

        control_dict_path = case_dir / "system" / "controlDict"
        try:
            control_dict = parse_foam_file(control_dict_path)
        except Exception as exc:
            log.warning("controlDict_parse_failed", case=rel_path, error=str(exc))
            return None

        application = str(control_dict.data.get("application", "unknown")).strip()

        # OpenFOAM-11 uses foamRun/foamMultiRun as runner with a separate 'solver'
        # key that names the actual physics module (e.g., incompressibleFluid).
        if application in self._MODULAR_RUNNERS:
            physics_module = str(control_dict.data.get("solver", "")).strip()
            solver = physics_module if physics_module else application
            log.debug(
                "v11_modular_solver",
                case=rel_path,
                runner=application,
                physics_module=solver,
            )
        else:
            solver = application

        all_files = []
        for root, _, fnames in os.walk(case_dir):
            for fname in fnames:
                fpath = Path(root) / fname
                all_files.append(str(fpath.relative_to(case_dir)))

        boundary_patches = self._extract_boundary_patches(case_dir)
        physics_tags = self._infer_physics_tags(case_dir, solver, control_dict)
        turbulence_model = self._extract_turbulence_model(case_dir)
        mesh_type = self._detect_mesh_type(case_dir)
        has_heat_transfer = self._has_heat_transfer(case_dir, physics_tags)
        has_multiphase = self._has_multiphase(case_dir, physics_tags)
        description = self._build_description(
            rel_path, solver, physics_tags, turbulence_model, mesh_type
        )

        return TutorialEntry(
            path=rel_path,
            solver=solver,
            version=self._version,
            files=all_files,
            boundary_patches=boundary_patches,
            physics_tags=physics_tags,
            turbulence_model=turbulence_model,
            has_heat_transfer=has_heat_transfer,
            has_multiphase=has_multiphase,
            mesh_type=mesh_type,
            description=description,
        )

    def _extract_boundary_patches(self, case_dir: Path) -> dict[str, str]:
        """Extract patch_name → BC type from any field file in 0/."""
        zero_dir = case_dir / "0"
        patches: dict[str, str] = {}

        if not zero_dir.exists():
            return patches

        for field_file in (f for f in zero_dir.iterdir() if f.is_file()):
            try:
                foam = parse_foam_file(field_file)
                bf = foam.data.get("boundaryField", {})
                if not isinstance(bf, dict):
                    continue
                for patch_name, patch_data in bf.items():
                    if isinstance(patch_data, dict) and "type" in patch_data:
                        patches[patch_name] = patch_data["type"]
                if patches:
                    break
            except Exception:
                continue

        return patches

    # Maps lowercase v11 physics module names → inferred physics tags
    _V11_MODULE_TAGS: dict[str, list[str]] = {
        "incompressiblefluid": ["incompressible"],
        "compressiblefluid": ["compressible"],
        "multicomponentfluid": ["compressible"],
        "incompressiblevof": ["multiphase", "incompressible"],
        "compressiblevof": ["multiphase", "compressible"],
        "multiphaseeuler": ["multiphase"],
        "isothermaldriftflux": ["multiphase", "incompressible"],
        "shallowwater": ["incompressible"],
        "xifluid": ["compressible"],
        "buoyantboussinesqsimplefluid": ["incompressible", "heat_transfer"],
        "buoyantsimplefluid": ["compressible", "heat_transfer"],
        "buoyantsimplefoam": ["compressible", "heat_transfer"],
        "solidfluid": ["heat_transfer"],
        "solidbodymotion": [],
        "reactions": ["compressible"],
        "electrokineticfluid": [],
        "isothermalfilm": ["multiphase"],
    }

    def _infer_physics_tags(
        self, case_dir: Path, solver: str, control_dict,
    ) -> list[str]:
        """Infer physics tags from solver name and case structure."""
        tags: list[str] = []
        solver_lower = solver.lower()

        # Check v11 physics module table first (exact module name match)
        if solver_lower in self._V11_MODULE_TAGS:
            tags.extend(self._V11_MODULE_TAGS[solver_lower])
        else:
            # Classic solver name patterns (v6–v10)
            if any(s in solver_lower for s in ["icofoam", "simplefoam", "pimplefoam", "srf",
                                                "incompressible"]):
                tags.append("incompressible")

            if any(s in solver_lower for s in ["rho", "sonic", "compressible", "central"]):
                tags.append("compressible")

            if any(s in solver_lower for s in ["inter", "multiphase", "vof", "drift"]):
                tags.append("multiphase")

            if any(s in solver_lower for s in ["buoyant", "cht", "heat"]):
                tags.append("heat_transfer")

        fv_schemes_path = case_dir / "system" / "fvSchemes"
        if fv_schemes_path.exists():
            try:
                fv = parse_foam_file(fv_schemes_path)
                ddt = fv.data.get("ddtSchemes", {})
                if isinstance(ddt, dict):
                    default_ddt = str(ddt.get("default", "")).lower()
                    if "steadystate" in default_ddt:
                        tags.append("steady")
                    else:
                        tags.append("transient")
            except Exception:
                pass

        turb_path = case_dir / "constant" / "turbulenceProperties"
        if turb_path.exists():
            try:
                turb = parse_foam_file(turb_path)
                sim_type = str(turb.data.get("simulationType", "")).lower()
                if sim_type in ("ras", "les"):
                    tags.append("turbulent")
                elif sim_type == "laminar":
                    tags.append("laminar")
            except Exception:
                pass

        return list(dict.fromkeys(tags))

    def _extract_turbulence_model(self, case_dir: Path) -> str | None:
        """Extract turbulence model name from constant/turbulenceProperties."""
        turb_path = case_dir / "constant" / "turbulenceProperties"
        if not turb_path.exists():
            return None

        try:
            turb = parse_foam_file(turb_path)
            for section in ("RAS", "LES"):
                if section in turb.data and isinstance(turb.data[section], dict):
                    model = str(turb.data[section].get("turbulenceModel", ""))
                    if model:
                        return model
            return str(turb.data.get("turbulenceModel", "")) or None
        except Exception:
            return None

    def _detect_mesh_type(self, case_dir: Path) -> str:
        """Detect mesh generation method from the case's system directory."""
        system_dir = case_dir / "system"
        if (system_dir / "snappyHexMeshDict").exists():
            return "snappyHexMesh"
        if (system_dir / "blockMeshDict").exists():
            return "blockMesh"
        return "external"

    def _has_heat_transfer(self, case_dir: Path, physics_tags: list[str]) -> bool:
        if "heat_transfer" in physics_tags:
            return True
        thermo_path = case_dir / "constant" / "thermophysicalProperties"
        g_path = case_dir / "constant" / "g"
        return thermo_path.exists() or g_path.exists()

    def _has_multiphase(self, case_dir: Path, physics_tags: list[str]) -> bool:
        if "multiphase" in physics_tags:
            return True
        transport_path = case_dir / "constant" / "transportProperties"
        if transport_path.exists():
            try:
                tp = parse_foam_file(transport_path)
                if "phases" in tp.data:
                    return True
            except Exception:
                pass
        return False

    def _build_description(
        self,
        rel_path: str,
        solver: str,
        physics_tags: list[str],
        turbulence_model: str | None,
        mesh_type: str,
    ) -> str:
        tags_str = ", ".join(physics_tags) if physics_tags else "general"
        turb_str = f", {turbulence_model}" if turbulence_model else ""
        return f"{rel_path} — {solver} ({tags_str}{turb_str}, {mesh_type})"

    # ── Embeddings ─────────────────────────────────────────────────────────────

    def _add_embeddings(self, entries: list[TutorialEntry]) -> None:
        """Compute and attach embeddings to each entry."""
        log.info("generating_embeddings", entry_count=len(entries), model="all-MiniLM-L6-v2")
        from foampilot.index.embeddings import embed_batch

        texts = [e.description for e in entries]
        embeddings = embed_batch(texts)
        if embeddings:
            for entry, emb in zip(entries, embeddings):
                entry.embedding = emb
        else:
            log.error("embeddings_failed", reason="embed_batch returned None")

    # ── Persistence ────────────────────────────────────────────────────────────

    def _save(self, entries: list[TutorialEntry]) -> None:
        """Write the index to disk."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        index_path = self._output_dir / f"tutorial_index_v{self._version}.json"

        index_data = []
        embeddings_data = []
        for entry in entries:
            d = asdict(entry)
            emb = d.pop("embedding", None)
            index_data.append(d)
            embeddings_data.append(emb)

        json_text = json.dumps(index_data, indent=2)
        index_path.write_text(json_text)
        size_kb = len(json_text.encode()) / 1024
        log.info("index_saved", path=str(index_path), entries=len(entries), size_kb=round(size_kb, 1))

        has_embeddings = any(e is not None for e in embeddings_data)
        if has_embeddings:
            import numpy as np
            emb_path = self._output_dir / f"tutorial_embeddings_v{self._version}.npy"
            valid = [e for e in embeddings_data if e is not None]
            np.save(emb_path, np.array(valid, dtype=np.float32))
            log.info("embeddings_saved", path=str(emb_path), count=len(valid))
