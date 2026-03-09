"""Top-level orchestrator that manages the full simulation lifecycle.

Coordinates the sequence: consult → setup → mesh → run → analyze.
Manages state persistence and error recovery.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from foampilot import config
from foampilot.core.state import SimulationPhase, SimulationState, StateManager

log = structlog.get_logger(__name__)


class _CaseLogger:
    """Writes LLM reasoning and tool events to a per-session case.log file.

    Intercepts the existing event_callback stream and appends human-readable
    entries to case_dir/case.log. All other events are forwarded unchanged.
    """

    def __init__(self, case_dir: Path, upstream: Any | None = None) -> None:
        self._path = case_dir / "case.log"
        self._upstream = upstream
        # Ensure the directory and file exist
        case_dir.mkdir(parents=True, exist_ok=True)
        self._path.touch()

    def __call__(self, event: dict) -> None:
        self._write(event)
        if self._upstream:
            self._upstream(event)

    def _write(self, event: dict) -> None:
        t = event.get("type", "")
        d = event.get("data", {})
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        line: str | None = None

        if t == "phase_start":
            line = f"\n{'='*60}\n[{ts}] PHASE: {d.get('phase','').upper()}\n{'='*60}"

        elif t == "llm_response":
            text = d.get("text", "").strip()
            turn = d.get("turn", "?")
            if text:
                line = f"\n[{ts}] LLM Turn {turn}:\n{text}\n"

        elif t == "tool_call":
            tool = d.get("tool", "?")
            inp = d.get("input", {})
            inp_str = json.dumps(inp, indent=2) if isinstance(inp, dict) else str(inp)
            line = f"\n[{ts}] TOOL CALL: {tool}\n{inp_str}"

        elif t == "tool_result":
            tool = d.get("tool", "?")
            ok = d.get("success", False)
            data = d.get("data", {})
            error = d.get("error", "")
            status = "OK" if ok else "FAILED"
            if ok:
                data_str = json.dumps(data, indent=2) if isinstance(data, dict) else str(data)
            else:
                data_str = error or (json.dumps(data, indent=2) if isinstance(data, dict) else str(data))
            line = f"\n[{ts}] TOOL RESULT: {tool} [{status}]\n{data_str[:2000]}"

        elif t == "session_start":
            sid = d.get("session_id", "?")
            req = d.get("request", "")
            line = (
                f"\n{'#'*60}\n"
                f"# FoamPilot Session: {sid}\n"
                f"# Started: {ts}\n"
                f"# Request: {req}\n"
                f"{'#'*60}\n"
            )

        elif t in ("session_complete", "session_error"):
            if t == "session_error":
                line = f"\n[{ts}] SESSION ERROR: {d.get('error','')}\n"
            else:
                line = f"\n[{ts}] SESSION COMPLETE\n"

        if line is not None:
            try:
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except Exception:
                pass  # silently ignore — never crash the agent over a log write


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
        self._docker = self._init_docker()
        # Set by TerminalUI before run() so ClarifyAgent can print to the real console
        self._console_ref: Any = None

    def _init_docker(self):
        """Connect to the Docker daemon, handling macOS socket fallback."""
        try:
            from foampilot.docker.client import _connect_docker
            client = _connect_docker()
            log.info("docker_connected", session=self._session_id)
            return client
        except Exception as exc:
            log.warning(
                "docker_unavailable",
                error=str(exc),
                hint="Docker tools (blockMesh, solvers) will be disabled",
            )
            return None

    def _emit(self, event_type: str, data: dict) -> None:
        if self._event_cb:
            self._event_cb({"type": event_type, "data": data})

    def run(
        self,
        user_request: str,
        confirmed_params: dict | None = None,
    ) -> SimulationState:
        """Execute the full simulation pipeline for a user request.

        Args:
            user_request: Natural language simulation request from the user.
                May be a refined version produced by the ClarifyAgent.
            confirmed_params: Parameters explicitly agreed by the user during
                pre-flight clarification. If provided, the CLARIFYING phase is
                skipped and these params are injected directly into the state.

        Returns:
            Final SimulationState after all phases complete (or fail).
        """
        case_dir = self._cases_dir / f"case_{self._session_id}"
        state_manager = StateManager(case_dir)

        # Attach a per-session case logger (writes to case_dir/case.log)
        case_logger = _CaseLogger(case_dir=case_dir, upstream=self._event_cb)
        self._event_cb = case_logger

        # Try to resume an existing session
        state = state_manager.load()
        if state is None:
            state = SimulationState(
                session_id=self._session_id,
                original_request=user_request,
            )

        self._emit("session_start", {"session_id": self._session_id, "request": user_request})

        try:
            state = self._run_phases(
                state, state_manager, case_dir, user_request, confirmed_params
            )
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
        confirmed_params: dict | None = None,
    ) -> SimulationState:
        """Run each simulation phase in sequence, skipping already-completed ones."""
        # Import agents here to avoid circular imports at module load time
        from foampilot.agents.clarify_agent import ClarifyAgent
        from foampilot.agents.consult_agent import ConsultAgent
        from foampilot.agents.setup_agent import SetupAgent
        from foampilot.agents.mesh_agent import MeshAgent
        from foampilot.agents.run_agent import RunAgent
        from foampilot.agents.analyze_agent import AnalyzeAgent

        agent_kwargs = {
            "event_callback": self._event_cb,
            "approval_callback": self._approval_cb,
        }
        docker_kwargs = {**agent_kwargs, "docker_client": self._docker}

        # Phase 0: Clarify
        if state.phase == SimulationPhase.IDLE:
            state.set_phase(SimulationPhase.CLARIFYING)
            state_manager.save(state)
            self._emit("phase_start", {"phase": "clarifying"})

            if confirmed_params is not None:
                # Clarification was done externally (by TerminalUI before Live opened)
                state.confirmed_params = confirmed_params
                log.info("clarify_skipped_external", params=list(confirmed_params))
            elif self._console_ref is not None:
                # Run clarification inline using the console reference
                try:
                    clarify = ClarifyAgent()
                    result = clarify.run(user_request, console=self._console_ref)
                    if result.cancelled:
                        state.set_phase(SimulationPhase.IDLE)
                        state_manager.save(state)
                        self._emit("session_cancelled", {})
                        return state
                    user_request = result.refined_request
                    state.confirmed_params = result.confirmed_params
                except Exception as exc:
                    log.warning("clarify_failed", error=str(exc), hint="Proceeding without clarification")

            state.set_phase(SimulationPhase.CONSULTING)
            state_manager.save(state)

        # Phase 1: Consult
        if state.phase in (SimulationPhase.CLARIFYING, SimulationPhase.CONSULTING):
            state.set_phase(SimulationPhase.CONSULTING)
            state_manager.save(state)
            self._emit("phase_start", {"phase": "consulting"})

            consult = ConsultAgent(**agent_kwargs)
            consult_request = user_request
            if state.confirmed_params:
                params_json = json.dumps(state.confirmed_params, indent=2)
                consult_request = (
                    f"{user_request}\n\n"
                    f"The user has already confirmed these parameters:\n```json\n{params_json}\n```\n"
                    f"Use them directly — do not re-ask."
                )
            spec = consult.run(consult_request)
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

            mesh = MeshAgent(**docker_kwargs)
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

            run = RunAgent(**docker_kwargs)
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

            analyze = AnalyzeAgent(**docker_kwargs)
            analyze.run(case_dir, state)
            state.set_phase(SimulationPhase.COMPLETE)
            state_manager.save(state)
            self._emit("session_complete", {"session_id": self._session_id})

        return state
