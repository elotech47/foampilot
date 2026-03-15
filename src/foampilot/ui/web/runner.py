"""Background simulation runner – bridges sync Orchestrator to async WebSocket."""

import json
import re
import threading
from pathlib import Path
from typing import Callable


MAX_CLARIFY_TURNS = 6

CLARIFY_SYSTEM_PROMPT = """\
You are FoamPilot's pre-flight assistant. Clarify simulation parameters before any files are created.

For EACH question, output exactly one structured block tagged ```question```:
```question
{
  "context": "1-2 sentences summarising what you already understand (optional)",
  "question": "Single clear question sentence",
  "parameter": "snake_case_param_name",
  "options": ["Option A — short label", "Option B — short label"] or null for free text,
  "default": "value string" or null,
  "hint": "One line: why this parameter matters"
}
```

Rules:
- ONE ```question``` block per response — the most critical unknown first.
- Provide options when choices are enumerable (turbulence models, solver types, yes/no).
- For numeric values (Reynolds number, dimensions) use null options so the user types the value.
- When all parameters are confirmed, output a ```confirm``` block (JSON object) with all finalised values.
- Do NOT write files, do NOT start setup. Only clarify.
"""


class SimulationRunner:
    """Run the foampilot Orchestrator in a daemon thread.

    Accepts a plain callable *emit_fn* that the background thread calls to push
    events to the WebSocket.  All Orchestrator callbacks (event_callback,
    approval_callback) are wired to this runner.
    """

    def __init__(self, emit_fn: Callable[[dict], None], auto_approve: bool = False) -> None:
        self._emit = emit_fn
        self.auto_approve = auto_approve
        self._stopped = False
        # Approval blocking
        self._approval_event = threading.Event()
        self._approval_result: bool = False
        # Clarification blocking
        self._clarify_event = threading.Event()
        self._clarify_reply: str = ""
        # State
        self.is_running: bool = False
        self.session_id: str | None = None
        self.case_dir: str | None = None
        self.current_phase: str = "idle"
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, prompt: str) -> None:
        self.is_running = True
        self._stopped = False
        self.current_phase = "starting"
        self._thread = threading.Thread(
            target=self._run_sync, args=(prompt,), daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stopped = True
        self.is_running = False
        # Unblock any waiting events so the thread can exit cleanly
        self._approval_event.set()
        self._clarify_event.set()

    def resolve_approval(self, approved: bool) -> None:
        self._approval_result = approved
        self._approval_event.set()

    def set_clarify_reply(self, text: str) -> None:
        self._clarify_reply = text
        self._clarify_event.set()

    # ------------------------------------------------------------------
    # Orchestrator callbacks (called from background thread)
    # ------------------------------------------------------------------

    def _on_event(self, event: dict) -> None:
        t = event.get("type", "")
        d = event.get("data", {})

        if t == "session_start":
            self.session_id = d.get("session_id")
            if self.session_id:
                from foampilot import config
                self.case_dir = str(config.CASES_DIR / f"case_{self.session_id}")
        elif t == "phase_start":
            self.current_phase = d.get("phase", "")
            if self.current_phase in ("meshing", "running", "analyzing") and self.case_dir:
                if Path(self.case_dir).exists():
                    self._emit_file_tree()
        elif t == "session_complete":
            self.current_phase = "complete"
            self._emit_file_tree()
        elif t == "session_error":
            self.current_phase = "error"

        self._emit(event)

    def _approval_callback(self, tool_name: str, tool_input: dict) -> bool:
        if self._stopped:
            return False

        if self.auto_approve:
            self._emit({"type": "auto_approved", "data": {"tool": tool_name}})
            return True

        self._emit({
            "type": "approval_required",
            "data": {"tool": tool_name, "input": tool_input},
        })
        self._approval_event.clear()
        timed_out = not self._approval_event.wait(timeout=300)
        if timed_out or self._stopped:
            return False
        return self._approval_result

    # ------------------------------------------------------------------
    # Web clarification loop
    # ------------------------------------------------------------------

    def _web_clarify(self, prompt: str) -> tuple[str, dict | None]:
        """Run a pre-flight clarification loop via WebSocket.

        Returns (refined_request, confirmed_params).
        Returns (prompt, None) if the user cancels.
        """
        try:
            from anthropic import Anthropic
            from foampilot import config
            client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
        except Exception:
            # If we can't import or connect, skip clarification
            return prompt, {}

        messages: list[dict] = [{"role": "user", "content": prompt}]
        params: dict = {}

        for turn in range(MAX_CLARIFY_TURNS):
            if self._stopped:
                return prompt, None

            try:
                response = client.messages.create(
                    model=config.MODEL,
                    max_tokens=1024,
                    system=CLARIFY_SYSTEM_PROMPT,
                    messages=messages,
                )
            except Exception:
                # API error — skip clarification and proceed
                self._emit({"type": "clarification_done", "data": {}})
                return prompt, {}

            assistant_text = response.content[0].text
            messages.append({"role": "assistant", "content": assistant_text})

            # Parse structured blocks
            has_confirm = "```confirm" in assistant_text
            has_question = "```question" in assistant_text

            if has_confirm:
                match = re.search(r"```confirm\s*([\s\S]+?)\s*```", assistant_text)
                if match:
                    try:
                        params = json.loads(match.group(1))
                    except json.JSONDecodeError:
                        pass

            question_data = None
            if has_question:
                match = re.search(r"```question\s*([\s\S]+?)\s*```", assistant_text)
                if match:
                    try:
                        question_data = json.loads(match.group(1))
                    except json.JSONDecodeError:
                        pass

            # Fallback text for agents that don't follow the structured format
            if not has_question and not has_confirm:
                display_text = assistant_text
            else:
                # Strip code blocks from any surrounding prose
                display_text = re.sub(r"```(?:question|confirm)[\s\S]*?```", "", assistant_text).strip()

            # Emit question to UI
            self._emit({
                "type": "clarification_question",
                "data": {
                    "text": display_text,
                    "question_data": question_data,
                    "params": params if has_confirm else None,
                    "turn": turn + 1,
                },
            })

            # Auto-proceed after max turns
            if turn >= MAX_CLARIFY_TURNS - 1:
                break

            # Wait for user reply
            self._clarify_event.clear()
            timed_out = not self._clarify_event.wait(timeout=300)
            if timed_out or self._stopped:
                self._emit({"type": "clarification_done", "data": {}})
                return prompt, None

            reply = self._clarify_reply.strip()
            lower = reply.lower()

            if lower in ("cancel", "exit", "quit", "abort"):
                self._emit({"type": "clarification_done", "data": {}})
                return prompt, None

            # If agent showed a confirm block, any non-cancel reply means proceed
            if has_confirm:
                break

            if lower in ("go", "ok", "proceed", "yes", "confirm", ""):
                break

            messages.append({"role": "user", "content": reply})

        # Produce refined request
        refined = self._refine_request(client, messages, prompt)
        self._emit({"type": "clarification_done", "data": {"refined_request": refined}})
        return refined, params

    def _refine_request(self, client, messages: list[dict], original: str) -> str:
        from foampilot import config
        summary_msgs = messages + [{
            "role": "user",
            "content": (
                "Summarise the agreed simulation parameters into a single concise "
                "request sentence (no JSON, no lists — just one sentence)."
            ),
        }]
        try:
            resp = client.messages.create(
                model=config.MODEL,
                max_tokens=256,
                system=CLARIFY_SYSTEM_PROMPT,
                messages=summary_msgs,
            )
            refined = resp.content[0].text.strip()
            return refined if refined else original
        except Exception:
            return original

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_sync(self, prompt: str) -> None:
        try:
            # Web clarification before orchestrator
            refined_prompt, confirmed_params = self._web_clarify(prompt)
            if confirmed_params is None or self._stopped:
                self._emit({"type": "session_error", "data": {"error": "Session cancelled."}})
                return

            from foampilot.core.orchestrator import Orchestrator
            orch = Orchestrator(
                event_callback=self._on_event,
                approval_callback=self._approval_callback,
            )
            state = orch.run(refined_prompt, confirmed_params=confirmed_params)
            if state.case_dir:
                self.case_dir = state.case_dir
                self._emit_file_tree()
        except ImportError as exc:
            import traceback
            self._emit({
                "type": "session_error",
                "data": {"error": f"Import error — check dependencies are installed: {exc}\n{traceback.format_exc()}"},
            })
        except Exception as exc:
            import traceback
            self._emit({
                "type": "session_error",
                "data": {"error": f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"},
            })
        finally:
            self.is_running = False

    def _emit_file_tree(self) -> None:
        if not self.case_dir:
            return
        p = Path(self.case_dir)
        if not p.exists():
            return
        try:
            tree = build_file_tree(p)
            self._emit({"type": "file_tree", "data": {"tree": tree}})
        except Exception:
            pass


def build_file_tree(node: Path, depth: int = 0) -> dict:
    """Recursively build a JSON-serialisable file tree."""
    if node.is_file():
        return {
            "name": node.name,
            "type": "file",
            "path": str(node),
            "size": node.stat().st_size,
        }
    children: list[dict] = []
    if depth < 8:
        try:
            for child in sorted(
                node.iterdir(),
                key=lambda x: (x.is_file(), x.name.lower()),
            ):
                if not child.name.startswith("."):
                    children.append(build_file_tree(child, depth + 1))
        except PermissionError:
            pass
    return {
        "name": node.name,
        "type": "directory",
        "path": str(node),
        "children": children,
    }
