"""Top-level orchestrator that manages the full simulation lifecycle.

Coordinates the sequence: consult → setup → mesh → run → analyze.
Manages state persistence and error recovery.
"""

import uuid
from pathlib import Path
from typing import Any

import structlog

from foampilot import config
from foampilot.core.state import SimulationPhase, SimulationState, StateManager

log = structlog.get_logger(__name__)


class Orchestrator:
    """Manages a FoamPilot simulation session from start to finish.

    Args:
        cases_dir: Base directory where simulation cases live.
        event_callback: Optional callable for streaming UI events.
        approval_callback: Called when APPROVE-level tool needs user confirmation.
    """

    def __init__(
        self,
        cases_dir: Path | None = None,
        event_callback: Any | None = None,
        approval_callback: Any | None = None,
    ) -> None:
        self._cases_dir = cases_dir or config.CASES_DIR
        self._event_cb = event_callback
        self._approval_cb = approval_callback
        self._session_id = str(uuid.uuid4())[:8]

    def _emit(self, event_type: str, data: dict) -> None:
        if self._event_cb:
            self._event_cb({"type": event_type, "data": data})

    def run(self, user_request: str) -> SimulationState:
        """Execute the full simulation pipeline for a user request.

        Args:
            user_request: Natural language simulation request from the user.

        Returns:
            Final SimulationState after all phases complete (or fail).
        """
        case_dir = self._cases_dir / f"case_{self._session_id}"
        state_manager = StateManager(case_dir)

        # Try to resume an existing session
        state = state_manager.load()
        if state is None:
            state = SimulationState(
                session_id=self._session_id,
                original_request=user_request,
            )

        self._emit("session_start", {"session_id": self._session_id, "request": user_request})

        try:
            state = self._run_phases(state, state_manager, case_dir, user_request)
        except Exception as exc:
            log.error("orchestrator_error", error=str(exc), session=self._session_id)
            state.set_phase(SimulationPhase.ERROR)
            state.add_issue(f"Orchestrator error: {exc}")
            state_manager.save(state)
            self._emit("session_error", {"error": str(exc)})

        return state

    def _run_phases(
        self,
        state: SimulationState,
        state_manager: StateManager,
        case_dir: Path,
        user_request: str,
    ) -> SimulationState:
        """Run each simulation phase in sequence, skipping already-completed ones."""
        # Import agents here to avoid circular imports at module load time
        from foampilot.agents.consult_agent import ConsultAgent
        from foampilot.agents.setup_agent import SetupAgent
        from foampilot.agents.mesh_agent import MeshAgent
        from foampilot.agents.run_agent import RunAgent
        from foampilot.agents.analyze_agent import AnalyzeAgent

        agent_kwargs = {
            "event_callback": self._event_cb,
            "approval_callback": self._approval_cb,
        }

        # Phase 1: Consult
        if state.phase in (SimulationPhase.IDLE,):
            state.set_phase(SimulationPhase.CONSULTING)
            state_manager.save(state)
            self._emit("phase_start", {"phase": "consulting"})

            consult = ConsultAgent(**agent_kwargs)
            spec = consult.run(user_request)
            state.simulation_spec = spec
            state_manager.save(state)

        # Phase 2: Setup
        if state.phase == SimulationPhase.CONSULTING:
            state.set_phase(SimulationPhase.SETUP)
            state_manager.save(state)
            self._emit("phase_start", {"phase": "setup"})

            setup = SetupAgent(**agent_kwargs)
            setup_result = setup.run(state.simulation_spec, case_dir)
            state.case_dir = str(case_dir)
            state.tutorial_source = setup_result.get("tutorial_source")
            for mod in setup_result.get("files_modified", []):
                state.record_modification(mod["path"], mod["action"], mod["description"])
            for assumption in setup_result.get("assumptions", []):
                state.add_assumption(assumption)
            state_manager.save(state)

        # Phase 3: Mesh
        if state.phase == SimulationPhase.SETUP:
            state.set_phase(SimulationPhase.MESHING)
            state_manager.save(state)
            self._emit("phase_start", {"phase": "meshing"})

            mesh = MeshAgent(**agent_kwargs)
            mesh_result = mesh.run(case_dir)
            state.mesh_quality = mesh_result
            if not mesh_result.get("passed", False):
                for issue in mesh_result.get("issues", []):
                    state.add_issue(f"Mesh: {issue}")
            state_manager.save(state)

        # Phase 4: Run
        if state.phase == SimulationPhase.MESHING:
            state.set_phase(SimulationPhase.RUNNING)
            state_manager.save(state)
            self._emit("phase_start", {"phase": "running"})

            run = RunAgent(**agent_kwargs)
            run_result = run.run(case_dir, state.simulation_spec)
            state.convergence_data = run_result
            if not run_result.get("converged", False):
                state.add_issue("Solver did not converge — check residuals")
            state_manager.save(state)

        # Phase 5: Analyze
        if state.phase == SimulationPhase.RUNNING:
            state.set_phase(SimulationPhase.ANALYZING)
            state_manager.save(state)
            self._emit("phase_start", {"phase": "analyzing"})

            analyze = AnalyzeAgent(**agent_kwargs)
            analyze.run(case_dir, state)
            state.set_phase(SimulationPhase.COMPLETE)
            state_manager.save(state)
            self._emit("session_complete", {"session_id": self._session_id})

        return state
