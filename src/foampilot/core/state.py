"""Simulation state management.

Manages foampilot_state.json (machine-readable) and FOAMPILOT.md (human-readable log).
State tracks: current phase, simulation spec, files modified, assumptions, issues.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)


class SimulationPhase(str, Enum):
    IDLE = "idle"
    CONSULTING = "consulting"
    SETUP = "setup"
    MESHING = "meshing"
    RUNNING = "running"
    ANALYZING = "analyzing"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class FileModification:
    path: str
    action: str  # "created" | "edited" | "deleted"
    description: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class SimulationState:
    """Full state of a FoamPilot simulation session."""

    session_id: str
    phase: SimulationPhase = SimulationPhase.IDLE
    original_request: str = ""
    simulation_spec: dict = field(default_factory=dict)
    case_dir: str | None = None
    tutorial_source: str | None = None
    files_modified: list[FileModification] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    mesh_quality: dict = field(default_factory=dict)
    convergence_data: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def record_modification(self, path: str, action: str, description: str) -> None:
        self.files_modified.append(FileModification(path=path, action=action, description=description))
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_assumption(self, assumption: str) -> None:
        if assumption not in self.assumptions:
            self.assumptions.append(assumption)

    def add_issue(self, issue: str) -> None:
        if issue not in self.issues:
            self.issues.append(issue)

    def set_phase(self, phase: SimulationPhase) -> None:
        self.phase = phase
        self.updated_at = datetime.now(timezone.utc).isoformat()
        log.info("phase_transition", phase=phase.value, session=self.session_id)


class StateManager:
    """Persists and loads SimulationState to/from disk."""

    def __init__(self, case_dir: Path) -> None:
        self._case_dir = case_dir
        self._state_file = case_dir / "foampilot_state.json"
        self._md_file = case_dir / "FOAMPILOT.md"

    def save(self, state: SimulationState) -> None:
        """Persist state to JSON and regenerate FOAMPILOT.md."""
        self._case_dir.mkdir(parents=True, exist_ok=True)
        data = asdict(state)
        self._state_file.write_text(json.dumps(data, indent=2))
        self._write_markdown(state)
        log.info("state_saved", path=str(self._state_file))

    def load(self) -> SimulationState | None:
        """Load state from disk. Returns None if no state file exists."""
        if not self._state_file.exists():
            return None
        data = json.loads(self._state_file.read_text())
        # Convert nested dicts back to dataclass instances
        data["phase"] = SimulationPhase(data["phase"])
        mods = [FileModification(**m) for m in data.get("files_modified", [])]
        data["files_modified"] = mods
        return SimulationState(**data)

    def _write_markdown(self, state: SimulationState) -> None:
        lines = [
            "# FoamPilot Session Log",
            "",
            f"**Session ID:** {state.session_id}",
            f"**Phase:** {state.phase.value}",
            f"**Created:** {state.created_at}",
            f"**Updated:** {state.updated_at}",
            "",
            "## Original Request",
            "",
            state.original_request or "_Not yet captured._",
            "",
        ]

        if state.simulation_spec:
            lines += ["## Simulation Specification", "", "```json",
                      json.dumps(state.simulation_spec, indent=2), "```", ""]

        if state.assumptions:
            lines += ["## Assumptions", ""]
            for a in state.assumptions:
                lines.append(f"- {a}")
            lines.append("")

        if state.files_modified:
            lines += ["## Files Modified", ""]
            for m in state.files_modified:
                lines.append(f"- `{m.path}` — **{m.action}**: {m.description}")
            lines.append("")

        if state.issues:
            lines += ["## Issues Encountered", ""]
            for i in state.issues:
                lines.append(f"- {i}")
            lines.append("")

        if state.mesh_quality:
            lines += ["## Mesh Quality", "", "```json",
                      json.dumps(state.mesh_quality, indent=2), "```", ""]

        if state.convergence_data:
            lines += ["## Convergence", "", "```json",
                      json.dumps(state.convergence_data, indent=2), "```", ""]

        self._md_file.write_text("\n".join(lines))
