"""Structured multi-panel terminal UI for FoamPilot.

Layout:
┌──────────────────────────────────────────────────────────────┐
│  FoamPilot  ·  Session: abc123  ·  Phase: MESHING           │  ← header
├───────────────────────────────────────┬──────────────────────┤
│  Process Log                          │  Tokens & Cost       │
│                                       │  ─────────────────   │
│  ✓ 13:45  ── CONSULTING ──            │  Input     12,345    │
│  ✓ 13:45  search_tutorials (3 found)  │  Output     2,341    │
│  ✓ 13:46  ── SETUP ──                 │  Cost       $0.023   │
│  ✓ 13:46  copy_tutorial               │  Context      12%    │
│  ↻ 13:47  run_foam_cmd (running…)     │  ─────────────────   │
│                                       │  Model               │
│                                       │  sonnet-4-6          │
│                                       │  Turns: 8            │
├───────────────────────────────────────┴──────────────────────┤
│  Model Reasoning                                             │  ← reasoning
│  I need to run blockMesh to generate the mesh. The          │
│  blockMeshDict has been set up with 20x20x1 cells…          │
└──────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Any

import structlog

from foampilot import config

log = structlog.get_logger(__name__)

# ── Try Rich imports ─────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table
    from rich.text import Text
    from rich import box
    RICH = True
except ImportError:
    RICH = False


# ── Shared UI state ──────────────────────────────────────────────────────────

class _UIState:
    """Shared mutable state read by the render loop and written by event callbacks."""

    MAX_LOG = 80   # max lines kept in the process log
    MAX_REASONING = 1200  # chars shown in the reasoning panel

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.session_id: str = ""
        self.phase: str = "idle"
        self.log_lines: list[str] = []   # Rich markup strings
        self.reasoning: str = ""          # Latest LLM text
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.cost_usd: float = 0.0
        self.context_pct: float = 0.0
        self.turns: int = 0
        self.live: Any = None            # Rich Live instance, set during run

    def add_log(self, markup: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_lines.append(f"[dim]{ts}[/]  {markup}")
        if len(self.log_lines) > self.MAX_LOG:
            self.log_lines = self.log_lines[-self.MAX_LOG:]

    def refresh(self) -> None:
        if self.live is not None:
            try:
                self.live.update(self._render())
            except Exception:
                pass

    # ── Layout renderer ───────────────────────────────────────────────────────

    def _render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="reasoning", size=8),
        )
        layout["body"].split_row(
            Layout(name="log", ratio=3),
            Layout(name="sidebar", ratio=2),
        )

        # Header
        phase_color = {
            "consulting": "cyan", "setup": "blue", "meshing": "yellow",
            "running": "green", "analyzing": "magenta", "complete": "bold green",
            "error": "bold red",
        }.get(self.phase.lower(), "white")

        layout["header"].update(Panel(
            f"[bold cyan]FoamPilot[/]  ·  "
            f"Session: [yellow]{self.session_id or '—'}[/]  ·  "
            f"Phase: [{phase_color}]{self.phase.upper()}[/]",
            style="on grey11",
            border_style="cyan",
        ))

        # Process log
        visible = self.log_lines[-28:]  # fit in panel
        log_text = "\n".join(visible) if visible else "[dim]Waiting for activity…[/]"
        layout["log"].update(Panel(
            log_text,
            title="[bold]Process Log[/]",
            border_style="blue",
            padding=(0, 1),
        ))

        # Sidebar: usage table
        tbl = Table.grid(padding=(0, 2))
        tbl.add_column(style="dim", justify="right")
        tbl.add_column(justify="left")
        tbl.add_row("Input tokens",  f"[green]{self.input_tokens:,}[/]")
        tbl.add_row("Output tokens", f"[green]{self.output_tokens:,}[/]")
        tbl.add_row("Est. cost",     f"[yellow]${self.cost_usd:.4f}[/]")
        tbl.add_row("Context used",  f"[yellow]{self.context_pct:.0f}%[/]")
        tbl.add_row("", "")
        model_short = config.MODEL.replace("claude-", "").split("-2")[0]
        tbl.add_row("Model",  f"[cyan]{model_short}[/]")
        tbl.add_row("Turns",  f"[white]{self.turns}[/]")

        layout["sidebar"].update(Panel(
            tbl,
            title="[bold]Tokens & Cost[/]",
            border_style="cyan",
            padding=(1, 1),
        ))

        # Reasoning
        text = self.reasoning
        if len(text) > self.MAX_REASONING:
            text = "…" + text[-self.MAX_REASONING:]
        layout["reasoning"].update(Panel(
            text or "[dim]Waiting for model response…[/]",
            title="[bold]Model Reasoning[/]",
            border_style="magenta",
            padding=(0, 1),
        ))

        return layout


# ── Main terminal class ───────────────────────────────────────────────────────

class TerminalUI:
    """Structured multi-panel terminal for FoamPilot."""

    def __init__(self, verbose: bool = False) -> None:
        self._state = _UIState()
        self._console = Console() if RICH else None
        self._verbose = verbose

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self, initial_request: str | None = None) -> None:
        """Launch the REPL or process a single request."""
        self._print_header()

        if initial_request:
            self._handle_request(initial_request)
            return

        while True:
            try:
                user_input = self._prompt()
            except (EOFError, KeyboardInterrupt):
                self._plain("\nGoodbye!")
                break

            stripped = user_input.strip()
            if not stripped:
                continue
            if stripped.lower() in ("/quit", "/exit", "exit", "quit"):
                self._plain("Goodbye!")
                break

            self._handle_request(stripped)

    # ── Request handler ───────────────────────────────────────────────────────

    def _handle_request(self, request: str) -> None:
        from foampilot.core.orchestrator import Orchestrator

        self._state.reset()
        self._state.add_log(f"[bold]Request:[/] {request[:100]}")

        if RICH:
            self._run_with_live(request)
        else:
            self._run_plain(request)

    def _run_with_live(self, request: str) -> None:
        """Run the orchestrator inside a Rich Live context."""
        from foampilot.core.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            event_callback=self._on_event,
            approval_callback=self._on_approval_required,
        )

        # Capture the session ID
        self._state.session_id = orchestrator._session_id

        with Live(
            self._state._render(),
            console=self._console,
            refresh_per_second=4,
            screen=False,
        ) as live:
            self._state.live = live
            self._state.refresh()

            try:
                final_state = orchestrator.run(request)
                self._state.phase = final_state.phase.value
                self._state.add_log(
                    f"[bold green]✓[/] Session complete  —  "
                    f"Case: [cyan]{final_state.case_dir or '—'}[/]"
                )
            except Exception as exc:
                self._state.add_log(f"[bold red]✗[/] Error: {exc}")
            finally:
                self._state.live = None
                self._state.refresh()

        self._print_session_summary()

    def _run_plain(self, request: str) -> None:
        """Fallback plain-text run (no Rich)."""
        from foampilot.core.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            event_callback=self._on_event_plain,
            approval_callback=self._on_approval_required,
        )
        try:
            orchestrator.run(request)
        except Exception as exc:
            print(f"Error: {exc}")

    # ── Event callbacks ───────────────────────────────────────────────────────

    def _on_event(self, event: dict) -> None:
        """Route agent events into the UI state and refresh the display."""
        t = event.get("type", "")
        d = event.get("data", {})

        if t == "phase_start":
            phase = d.get("phase", "")
            self._state.phase = phase
            self._state.add_log(f"[bold yellow]──  Phase: {phase.upper()}  ──[/]")

        elif t == "tool_call":
            tool = d.get("tool", "?")
            inp = d.get("input", {})
            # Show a brief, human-readable summary of the input
            summary = self._summarise_input(tool, inp)
            self._state.add_log(f"[blue]↻[/] [bold]{tool}[/]  [dim]{summary}[/]")

        elif t == "tool_result":
            tool = d.get("tool", "?")
            ok = d.get("success", False)
            icon = "[green]✓[/]" if ok else "[red]✗[/]"
            detail = self._summarise_result(tool, d.get("data", {}), ok)
            self._state.add_log(f"{icon} [bold]{tool}[/]  [dim]{detail}[/]")

        elif t == "tool_error":
            self._state.add_log(f"[red]✗[/] Tool error: {str(d.get('error',''))[:80]}")

        elif t == "llm_response":
            self._state.turns = d.get("turn", self._state.turns)
            text = d.get("text", "")
            if text:
                self._state.reasoning = text

        elif t == "compaction":
            self._state.add_log("[dim]◈ Context compacted[/]")

        elif t == "agent_done":
            self._state.turns = d.get("turns", self._state.turns)
            self._state.input_tokens += d.get("total_input_tokens", 0)
            self._state.output_tokens += d.get("total_output_tokens", 0)
            self._state.cost_usd += d.get("total_cost_usd", 0.0)
            self._state.context_pct = d.get("context_utilization_pct", 0.0)

        elif t == "approval_required":
            # Approval is handled by the callback; just log it
            self._state.add_log(
                f"[yellow]⚠[/] Approval required: [bold]{d.get('tool')}[/]"
            )

        self._state.refresh()

    def _on_event_plain(self, event: dict) -> None:
        t = event.get("type", "")
        d = event.get("data", {})
        if t == "phase_start":
            print(f"\n── Phase: {d.get('phase','').upper()} ──")
        elif t == "tool_call":
            print(f"  → {d.get('tool')}  {str(d.get('input',''))[:60]}")
        elif t == "tool_result":
            icon = "✓" if d.get("success") else "✗"
            print(f"  {icon} {d.get('tool')}")
        elif t == "agent_done":
            cost = d.get("total_cost_usd", 0)
            print(f"  [Done: {d.get('turns')} turns, ${cost:.4f}]")

    # ── Approval callback ─────────────────────────────────────────────────────

    def _on_approval_required(self, tool_name: str, tool_input: dict) -> bool:
        """Pause the Live display and ask the user for approval."""
        # Temporarily suspend Live so we can safely use input()
        if self._state.live is not None:
            self._state.live.stop()

        if RICH:
            self._console.print(
                Panel(
                    f"[bold yellow]Tool:[/] {tool_name}\n"
                    f"[dim]{self._format_approval_input(tool_input)}[/]",
                    title="[bold yellow]⚠ Approval Required[/]",
                    border_style="yellow",
                )
            )
            try:
                ans = Prompt.ask("  Proceed?", choices=["y", "n"], default="n")
                approved = ans.lower() == "y"
            except (EOFError, KeyboardInterrupt):
                approved = False
        else:
            print(f"\n⚠ Approval required: {tool_name}\n  {str(tool_input)[:120]}")
            try:
                approved = input("  Proceed? [y/N]: ").strip().lower() == "y"
            except (EOFError, KeyboardInterrupt):
                approved = False

        if self._state.live is not None:
            self._state.live.start()

        if approved:
            self._state.add_log(f"[green]✓[/] Approved: [bold]{tool_name}[/]")
        else:
            self._state.add_log(f"[red]✗[/] Denied: [bold]{tool_name}[/]")

        return approved

    # ── Post-run summary ──────────────────────────────────────────────────────

    def _print_session_summary(self) -> None:
        if not RICH:
            return
        s = self._state
        tbl = Table(title="Session Summary", box=box.ROUNDED, show_header=False)
        tbl.add_column(style="dim", justify="right")
        tbl.add_column()
        tbl.add_row("Session", s.session_id)
        tbl.add_row("Phase",   s.phase)
        tbl.add_row("Turns",   str(s.turns))
        tbl.add_row("Input tokens",  f"{s.input_tokens:,}")
        tbl.add_row("Output tokens", f"{s.output_tokens:,}")
        tbl.add_row("Est. cost",     f"${s.cost_usd:.4f}")
        self._console.print(tbl)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _summarise_input(self, tool: str, inp: dict) -> str:
        """Create a short human-readable summary of a tool's input."""
        if not inp:
            return ""
        if tool == "search_tutorials":
            return f"solver={inp.get('solver','?')} physics={inp.get('physics_tags','')}"
        if tool == "copy_tutorial":
            return str(inp.get("tutorial_path", ""))[-50:]
        if tool in ("edit_foam_dict", "read_foam_file"):
            return str(inp.get("file_path", ""))[-50:]
        if tool == "run_foam_cmd":
            return str(inp.get("command", ""))[:60]
        if tool == "check_mesh":
            p = str(inp.get("case_dir", ""))
            return p[-40:] if p else ""
        # Generic fallback — show first key=value pair
        first_k = next(iter(inp), None)
        if first_k:
            return f"{first_k}={str(inp[first_k])[:40]}"
        return ""

    def _summarise_result(self, tool: str, data: Any, success: bool) -> str:
        """Create a short human-readable summary of a tool's result."""
        if not success:
            if isinstance(data, str):
                return data[:80]
            return "failed"
        if isinstance(data, dict):
            if tool == "search_tutorials":
                return f"{len(data.get('results', []))} results"
            if tool == "check_mesh":
                cells = data.get("cells", "?")
                passed = data.get("passed", False)
                return f"{'OK' if passed else 'FAIL'}  cells={cells}"
            if tool == "run_foam_cmd":
                ec = data.get("exit_code", "?")
                t = data.get("execution_time_s")
                ts = f"  {t:.1f}s" if t else ""
                return f"exit={ec}{ts}"
        return "ok"

    def _format_approval_input(self, inp: dict) -> str:
        """Format tool input for the approval dialog."""
        lines = []
        for k, v in inp.items():
            lines.append(f"  {k}: {str(v)[:100]}")
        return "\n".join(lines[:6])

    # ── Print helpers ─────────────────────────────────────────────────────────

    def _print_header(self) -> None:
        if RICH:
            self._console.print(Panel(
                "[bold cyan]FoamPilot[/]  —  AI-powered OpenFOAM simulation agent\n"
                "[dim]Type your simulation request, or[/] [bold]/exit[/] [dim]to quit.[/]",
                border_style="cyan",
                padding=(0, 2),
            ))
        else:
            print("=" * 60)
            print("FoamPilot — AI-powered OpenFOAM simulation agent")
            print("Type /exit to quit.")
            print("=" * 60)

    def _prompt(self) -> str:
        if RICH:
            return Prompt.ask("\n[bold cyan]foampilot[/]")
        return input("\nfoampilot> ")

    def _plain(self, msg: str) -> None:
        if RICH:
            self._console.print(msg)
        else:
            print(msg)
