"""Structured multi-panel terminal UI for FoamPilot.

Layout (fixed, stable, no flicker):

╭──────────────────────────────────────────────────────────────╮
│  FoamPilot  ·  Session: abc123  ·  Phase: MESHING  ·  8fps  │  ← header
╰──────────────────────────────────────────────────────────────╯
╭──────────────────────────────────╮ ╭────────────────────────╮
│  Process Log                     │ │  Tokens & Cost         │
│                                  │ │                        │
│  18:48:05  Request: ...          │ │  Input tokens   1,411  │
│  18:48:06  ── CONSULTING ──      │ │  Output tokens    691  │
│  18:48:17  ✓ search_tutorials    │ │  Est. cost      $0.01  │
│  18:48:19  ↻ copy_tutorial       │ │                        │
│  ...                             │ │  Turns              8  │
╰──────────────────────────────────╯ ╰────────────────────────╯
╭──────────────────────────────────────────────────────────────╮
│  Model Reasoning                                             │
│  I need to run blockMesh to generate the mesh...            │
╰──────────────────────────────────────────────────────────────╯

Design rules:
- Rich Live is opened ONCE per request and closed ONCE.
- stdout/stderr are redirected away from the terminal during Live.
- _UIState.refresh() is rate-limited to 125ms (8 fps).
- agent_done accumulates tokens; turns uses max(), not +=.
- Approval pauses Live cleanly via live.stop()/live.start().
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Any

import structlog

from foampilot import config

log = structlog.get_logger(__name__)

# ── Rich imports ──────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box
    RICH = True
except ImportError:
    RICH = False


# ── UI State ──────────────────────────────────────────────────────────────────

class _UIState:
    """All mutable state for the live display. Thread-safe enough for single-threaded use."""

    MAX_LOG = 60        # lines kept in the process log buffer
    MAX_REASONING = 800 # chars shown in the reasoning panel
    REFRESH_INTERVAL = 0.125  # seconds between redraws (8 fps)

    def __init__(self) -> None:
        self.live: Any = None
        self._last_refresh: float = 0.0
        self.reset()

    def reset(self) -> None:
        self.session_id: str = ""
        self.phase: str = "IDLE"
        self.log_lines: list[str] = []
        self.reasoning: str = ""
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cost_usd: float = 0.0
        self.context_pct: float = 0.0
        self.turns: int = 0

    def add_log(self, markup: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_lines.append(f"[dim]{ts}[/dim]  {markup}")
        if len(self.log_lines) > self.MAX_LOG:
            self.log_lines = self.log_lines[-self.MAX_LOG:]

    def refresh(self, force: bool = False) -> None:
        """Push a new render to the Live display, rate-limited."""
        if self.live is None:
            return
        now = time.monotonic()
        if not force and (now - self._last_refresh) < self.REFRESH_INTERVAL:
            return
        try:
            self.live.update(self._render())
            self._last_refresh = now
        except Exception:
            pass  # never crash the agent over a UI error

    def _render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="reasoning", size=7),
        )
        layout["body"].split_row(
            Layout(name="log", ratio=3),
            Layout(name="sidebar", ratio=2),
        )

        # ── Header ─────────────────────────────────────────────────────────
        phase_colors = {
            "idle": "white", "consulting": "cyan", "setup": "blue",
            "meshing": "yellow", "running": "green", "analyzing": "magenta",
            "complete": "bold green", "error": "bold red",
        }
        phase_color = phase_colors.get(self.phase.lower(), "white")
        sid = self.session_id or "—"
        layout["header"].update(Panel(
            f"[bold cyan]FoamPilot[/bold cyan]  ·  "
            f"[dim]Session:[/dim] [yellow]{sid}[/yellow]  ·  "
            f"[dim]Phase:[/dim] [{phase_color}]{self.phase.upper()}[/{phase_color}]",
            style="on grey11",
            border_style="bright_cyan",
            padding=(0, 2),
        ))

        # ── Process log ─────────────────────────────────────────────────────
        # Show only the last N lines that fit in the panel (approx 22 lines)
        visible = self.log_lines[-22:]
        log_text = "\n".join(visible) if visible else "[dim]Waiting…[/dim]"
        layout["log"].update(Panel(
            log_text,
            title="[bold]Process Log[/bold]",
            border_style="blue",
            padding=(0, 1),
        ))

        # ── Sidebar ─────────────────────────────────────────────────────────
        tbl = Table.grid(padding=(0, 2))
        tbl.add_column(style="dim", justify="right", min_width=14)
        tbl.add_column(justify="left")
        tbl.add_row("Input tokens",  f"[green]{self.input_tokens:,}[/green]")
        tbl.add_row("Output tokens", f"[green]{self.output_tokens:,}[/green]")
        tbl.add_row("Est. cost",     f"[yellow]${self.cost_usd:.4f}[/yellow]")
        tbl.add_row("",              "")
        tbl.add_row("Turns",         f"[white]{self.turns}[/white]")
        tbl.add_row("Context",       f"[yellow]{self.context_pct:.0f}%[/yellow]")

        layout["sidebar"].update(Panel(
            tbl,
            title="[bold]Tokens & Cost[/bold]",
            border_style="cyan",
            padding=(1, 2),
        ))

        # ── Reasoning ───────────────────────────────────────────────────────
        text = self.reasoning
        if len(text) > self.MAX_REASONING:
            text = "…" + text[-self.MAX_REASONING:]
        layout["reasoning"].update(Panel(
            text or "[dim]Waiting for model response…[/dim]",
            title="[bold]Model Reasoning[/bold]",
            border_style="magenta",
            padding=(0, 1),
        ))

        return layout



# ── Main terminal class ───────────────────────────────────────────────────────

class TerminalUI:
    """Structured, flicker-free multi-panel terminal for FoamPilot."""

    def __init__(self, verbose: bool = False) -> None:
        self._state = _UIState()
        # Use stderr=False so Rich writes to stdout only, not stderr
        self._console = Console(stderr=False, highlight=False) if RICH else None
        self._verbose = verbose

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self, initial_request: str | None = None) -> None:
        """Launch the REPL or process a single request."""
        self._print_welcome()

        if initial_request:
            self._handle_request(initial_request)
            return

        while True:
            try:
                user_input = self._prompt()
            except (EOFError, KeyboardInterrupt):
                self._write("\nGoodbye!")
                break

            stripped = user_input.strip()
            if not stripped:
                continue
            if stripped.lower() in ("/quit", "/exit", "exit", "quit"):
                self._write("Goodbye!")
                break

            self._handle_request(stripped)

    # ── Request handler ───────────────────────────────────────────────────────

    def _handle_request(self, request: str) -> None:
        self._state.reset()
        self._state.add_log(f"[bold]Request:[/bold] {request[:120]}")

        if RICH:
            self._run_with_live(request)
        else:
            self._run_plain(request)

    def _run_with_live(self, request: str) -> None:
        from foampilot.agents.clarify_agent import ClarifyAgent
        from foampilot.core.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            event_callback=self._on_event,
            approval_callback=self._on_approval_required,
        )
        self._state.session_id = orchestrator._session_id

        # ── Phase 0: Clarification (before Live opens, plain console I/O) ────
        confirmed_params: dict | None = None
        try:
            clarify = ClarifyAgent()
            result = clarify.run(request, console=self._console)
            if result.cancelled:
                self._write("[yellow]Request cancelled.[/yellow]")
                return
            request = result.refined_request
            confirmed_params = result.confirmed_params
        except Exception as exc:
            log.warning("clarify_skipped", error=str(exc))
            # Continue without clarification

        # ── Main pipeline inside Live ─────────────────────────────────────────
        # Open Live once — keep it open for the full request
        with Live(
            self._state._render(),
            console=self._console,
            refresh_per_second=8,   # We drive refreshes manually; must be > 0
            screen=False,
            transient=False,
        ) as live:
            self._state.live = live
            self._state.refresh(force=True)

            try:
                final_state = orchestrator.run(request, confirmed_params=confirmed_params)
                self._state.phase = final_state.phase.value
                self._state.add_log(
                    f"[bold green]✓[/bold green] Complete  —  "
                    f"[dim]{final_state.case_dir or '—'}[/dim]"
                )
            except Exception as exc:
                self._state.phase = "error"
                self._state.add_log(f"[bold red]✗[/bold red] Error: {str(exc)[:100]}")
                log.exception("session_error", error=str(exc))
            finally:
                self._state.refresh(force=True)
                self._state.live = None

        # After Live closes, print the summary to clean stdout
        self._print_session_summary()

    def _run_plain(self, request: str) -> None:
        from foampilot.core.orchestrator import Orchestrator
        orchestrator = Orchestrator(
            event_callback=self._on_event_plain,
            approval_callback=self._on_approval_required,
        )
        try:
            orchestrator.run(request)
        except Exception as exc:
            print(f"Error: {exc}")

    # ── Event callback ────────────────────────────────────────────────────────

    def _on_event(self, event: dict) -> None:
        """Translate agent events into UI state mutations, then refresh."""
        t = event.get("type", "")
        d = event.get("data", {})

        if t == "session_start":
            self._state.session_id = d.get("session_id", self._state.session_id)

        elif t == "phase_start":
            phase = d.get("phase", "")
            self._state.phase = phase
            self._state.add_log(
                f"[bold yellow]──  Phase: {phase.upper()}  ──[/bold yellow]"
            )

        elif t == "tool_call":
            tool = d.get("tool", "?")
            inp = d.get("input", {})
            summary = _summarise_input(tool, inp)
            line = f"[blue]↻[/blue] [bold]{tool}[/bold]"
            if summary:
                line += f"  [dim]{summary}[/dim]"
            self._state.add_log(line)

        elif t == "tool_result":
            tool = d.get("tool", "?")
            ok = d.get("success", False)
            icon = "[green]✓[/green]" if ok else "[red]✗[/red]"
            detail = _summarise_result(tool, d.get("data", {}), ok)
            line = f"{icon} [bold]{tool}[/bold]"
            if detail:
                line += f"  [dim]{detail}[/dim]"
            self._state.add_log(line)

        elif t == "tool_error":
            err = str(d.get("error", ""))[:80]
            self._state.add_log(f"[red]✗[/red] [dim]{err}[/dim]")

        elif t == "llm_response":
            text = d.get("text", "").strip()
            if text:
                self._state.reasoning = text

        elif t == "compaction":
            self._state.add_log("[dim]◈ Context compacted[/dim]")

        elif t == "agent_done":
            # Accumulate across subagent phases
            self._state.turns = max(self._state.turns, d.get("turns", 0))
            self._state.input_tokens  += d.get("total_input_tokens", 0)
            self._state.output_tokens += d.get("total_output_tokens", 0)
            self._state.cost_usd      += d.get("total_cost_usd", 0.0)
            self._state.context_pct    = max(
                self._state.context_pct,
                d.get("context_utilization_pct", 0.0),
            )

        elif t == "approval_required":
            self._state.add_log(
                f"[yellow]⚠[/yellow] Approval required: [bold]{d.get('tool')}[/bold]"
            )

        elif t in ("session_complete", "session_error"):
            if t == "session_error":
                self._state.add_log(
                    f"[red]Session error:[/red] {str(d.get('error',''))[:80]}"
                )

        self._state.refresh()

    def _on_event_plain(self, event: dict) -> None:
        t = event.get("type", "")
        d = event.get("data", {})
        ts = datetime.now().strftime("%H:%M:%S")
        if t == "phase_start":
            print(f"{ts}  ── {d.get('phase','').upper()} ──")
        elif t == "tool_call":
            print(f"{ts}  ↻ {d.get('tool')}  {str(d.get('input',''))[:60]}")
        elif t == "tool_result":
            icon = "✓" if d.get("success") else "✗"
            print(f"{ts}  {icon} {d.get('tool')}")
        elif t == "agent_done":
            cost = d.get("total_cost_usd", 0)
            print(f"{ts}  Done: {d.get('turns')} turns, ${cost:.4f}")

    # ── Approval callback ─────────────────────────────────────────────────────

    def _on_approval_required(self, tool_name: str, tool_input: dict) -> bool:
        """Pause Live, ask inline, resume. Never use Prompt.ask inside Live."""
        if self._state.live is not None:
            self._state.live.stop()

        self._console.print()
        self._console.rule("[yellow]⚠  Approval Required[/yellow]")
        self._console.print(f"  [bold]Tool:[/bold] {tool_name}")
        for k, v in list(tool_input.items())[:5]:
            self._console.print(f"  [dim]{k}:[/dim] {str(v)[:100]}")
        self._console.rule()

        try:
            answer = input("  Proceed? [y/N]: ").strip().lower()
            approved = answer == "y"
        except (EOFError, KeyboardInterrupt):
            approved = False

        if self._state.live is not None:
            self._state.live.start(refresh=True)

        icon = "[green]✓[/green]" if approved else "[red]✗[/red]"
        self._state.add_log(
            f"{icon} {'Approved' if approved else 'Denied'}: [bold]{tool_name}[/bold]"
        )
        self._state.refresh(force=True)
        return approved

    # ── Post-run summary ──────────────────────────────────────────────────────

    def _print_session_summary(self) -> None:
        if not RICH or self._console is None:
            return
        s = self._state
        tbl = Table(title="      Session Summary      ", box=box.ROUNDED, show_header=False)
        tbl.add_column(style="dim", justify="right")
        tbl.add_column()
        tbl.add_row("Session",       s.session_id or "—")
        tbl.add_row("Phase",         s.phase)
        tbl.add_row("Turns",         str(s.turns))
        tbl.add_row("Input tokens",  f"{s.input_tokens:,}")
        tbl.add_row("Output tokens", f"{s.output_tokens:,}")
        tbl.add_row("Est. cost",     f"${s.cost_usd:.4f}")
        self._console.print(tbl)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _print_welcome(self) -> None:
        if RICH and self._console:
            self._console.print(Panel(
                "[bold cyan]FoamPilot[/bold cyan]  —  AI-powered OpenFOAM simulation agent\n"
                "[dim]Type your simulation request, or[/dim] [bold]/exit[/bold] [dim]to quit.[/dim]",
                border_style="cyan",
                padding=(0, 2),
            ))
        else:
            print("=" * 60)
            print("FoamPilot — AI-powered OpenFOAM simulation agent")
            print("Type /exit to quit.")
            print("=" * 60)

    def _prompt(self) -> str:
        if RICH and self._console:
            # Use plain input() to avoid Rich Prompt going through Live
            sys.stdout.write("\nfoampilot: ")
            sys.stdout.flush()
            return input()
        return input("\nfoampilot> ")

    def _write(self, msg: str) -> None:
        if RICH and self._console:
            self._console.print(msg)
        else:
            print(msg)


# ── Tool summary helpers (module-level, pure functions) ───────────────────────

def _summarise_input(tool: str, inp: dict) -> str:
    """Return a brief human-readable summary of a tool's input dict."""
    if not inp:
        return ""
    if tool == "search_tutorials":
        solver = inp.get("solver", "")
        tags   = inp.get("physics_tags", [])
        return f"solver={solver} physics={tags}"
    if tool == "copy_tutorial":
        p = str(inp.get("tutorial_path", ""))
        return p[-60:] if p else ""
    if tool in ("edit_foam_dict",):
        path = str(inp.get("path", "")).split("/")[-1]
        key  = inp.get("key_path", "")
        val  = inp.get("new_value", "")
        return f"{path}  {key}={val}"
    if tool == "read_foam_file":
        return str(inp.get("path", "")).split("/")[-1]
    if tool == "run_foam_cmd":
        return str(inp.get("command", ""))[:60]
    if tool in ("str_replace", "write_foam_file", "write_file"):
        return str(inp.get("path", "")).split("/")[-1]
    if tool == "check_mesh":
        return str(inp.get("case_dir", ""))[-40:]
    if tool == "read_file":
        return str(inp.get("path", "")).split("/")[-1]
    # Generic: first key=value
    first_k = next(iter(inp), None)
    if first_k:
        return f"{first_k}={str(inp[first_k])[:40]}"
    return ""


def _summarise_result(tool: str, data: Any, success: bool) -> str:
    """Return a brief human-readable summary of a tool's result."""
    if not success:
        if isinstance(data, str):
            return data[:80]
        return "failed"
    if not isinstance(data, dict):
        return "ok"
    if tool == "search_tutorials":
        n = len(data.get("results", []))
        return f"{n} results"
    if tool == "copy_tutorial":
        n = data.get("files_copied", "?")
        return f"{n} files copied"
    if tool == "check_mesh":
        cells  = data.get("cells", "?")
        passed = data.get("passed", False)
        return f"{'OK' if passed else 'FAIL'}  cells={cells}"
    if tool == "run_foam_cmd":
        ec = data.get("exit_code", "?")
        t  = data.get("execution_time_s")
        ts = f"  {t:.1f}s" if t else ""
        return f"exit={ec}{ts}"
    if tool == "edit_foam_dict":
        return f"{data.get('old_value')} → {data.get('new_value')}"
    if tool == "str_replace":
        n = data.get("replacements_made", 0)
        return f"{n} replacement{'s' if n != 1 else ''}"
    return "ok"
