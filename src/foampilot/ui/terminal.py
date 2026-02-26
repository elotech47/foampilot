"""Rich/Textual-based terminal REPL for FoamPilot.

Features:
- Interactive REPL with command history
- Real-time display of tool calls and results
- Token usage in status bar
- Inline approval prompts for APPROVE-level tools
- Colored output: tool calls in blue, results in green, errors in red, LLM text in white
"""

from __future__ import annotations

import sys
import threading
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class TerminalUI:
    """Interactive terminal REPL for FoamPilot.

    Uses Rich for formatting when available; falls back to plain text.
    """

    def __init__(self) -> None:
        self._try_import_rich()
        self._events: list[dict] = []

    def _try_import_rich(self) -> None:
        try:
            from rich.console import Console
            from rich.panel import Panel
            from rich.text import Text
            self._console = Console()
            self._rich = True
        except ImportError:
            self._console = None
            self._rich = False

    def run(self, initial_request: str | None = None) -> None:
        """Launch the REPL."""
        self._print_header()

        if initial_request:
            self._handle_request(initial_request)
            return

        while True:
            try:
                user_input = self._prompt()
            except (EOFError, KeyboardInterrupt):
                self._print("\nGoodbye!")
                break

            if not user_input.strip():
                continue
            if user_input.strip().lower() in ("/quit", "/exit", "exit", "quit"):
                self._print("Goodbye!")
                break

            self._handle_request(user_input)

    def _handle_request(self, request: str) -> None:
        """Process a simulation request."""
        from foampilot.core.orchestrator import Orchestrator

        orchestrator = Orchestrator(
            event_callback=self._on_event,
            approval_callback=self._on_approval_required,
        )

        self._print_info(f"Starting simulation pipeline for: {request[:80]}...")
        try:
            final_state = orchestrator.run(request)
            self._print_success(
                f"\nSimulation pipeline complete. Phase: {final_state.phase.value}"
            )
            if final_state.case_dir:
                self._print_info(f"Case directory: {final_state.case_dir}")
        except Exception as exc:
            self._print_error(f"Error: {exc}")

    def _on_event(self, event: dict) -> None:
        """Handle events from the agent loop."""
        event_type = event.get("type", "")
        data = event.get("data", {})

        if event_type == "tool_call":
            self._print_blue(f"  → [{data.get('tool')}] {str(data.get('input', ''))[:80]}")
        elif event_type == "tool_result":
            if data.get("success"):
                self._print_green(f"  ✓ [{data.get('tool')}] OK")
            else:
                self._print_error(f"  ✗ [{data.get('tool')}] FAILED")
        elif event_type == "tool_error":
            self._print_error(f"  ✗ Tool error: {data.get('error', '')[:100]}")
        elif event_type == "llm_response":
            turn = data.get("turn", "?")
            has_tools = data.get("has_tool_calls", False)
            self._print_dim(f"  [Turn {turn}]{'  (calling tools)' if has_tools else ''}")
        elif event_type == "compaction":
            self._print_info("  [Context compacted]")
        elif event_type == "phase_start":
            phase = data.get("phase", "").upper()
            self._print_info(f"\n── Phase: {phase} ──")
        elif event_type == "agent_done":
            turns = data.get("turns", "?")
            cost = data.get("total_cost_usd", 0)
            ctx_pct = data.get("context_utilization_pct", 0)
            self._print_dim(
                f"  [Done: {turns} turns, ${cost:.4f}, ctx {ctx_pct:.0f}%]"
            )

    def _on_approval_required(self, tool_name: str, tool_input: dict) -> bool:
        """Ask the user to approve an APPROVE-level tool call."""
        self._print_warning(
            f"\n⚠  Approval required for: {tool_name}\n"
            f"   Input: {str(tool_input)[:200]}"
        )
        try:
            response = input("  Proceed? [y/N]: ").strip().lower()
            return response in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    def _prompt(self) -> str:
        if self._rich:
            from rich.prompt import Prompt
            return Prompt.ask("[bold cyan]foampilot[/bold cyan]")
        return input("foampilot> ")

    def _print_header(self) -> None:
        header = (
            "FoamPilot — AI-powered OpenFOAM simulation agent\n"
            "Type a simulation request or '/exit' to quit."
        )
        if self._rich:
            from rich.panel import Panel
            self._console.print(Panel(header, style="bold blue"))
        else:
            print("=" * 60)
            print(header)
            print("=" * 60)

    def _print(self, msg: str) -> None:
        if self._rich:
            self._console.print(msg)
        else:
            print(msg)

    def _print_blue(self, msg: str) -> None:
        if self._rich:
            self._console.print(f"[blue]{msg}[/blue]")
        else:
            print(msg)

    def _print_green(self, msg: str) -> None:
        if self._rich:
            self._console.print(f"[green]{msg}[/green]")
        else:
            print(msg)

    def _print_error(self, msg: str) -> None:
        if self._rich:
            self._console.print(f"[red]{msg}[/red]")
        else:
            print(f"ERROR: {msg}", file=sys.stderr)

    def _print_warning(self, msg: str) -> None:
        if self._rich:
            self._console.print(f"[yellow]{msg}[/yellow]")
        else:
            print(f"WARNING: {msg}")

    def _print_info(self, msg: str) -> None:
        if self._rich:
            self._console.print(f"[cyan]{msg}[/cyan]")
        else:
            print(msg)

    def _print_dim(self, msg: str) -> None:
        if self._rich:
            self._console.print(f"[dim]{msg}[/dim]")
        else:
            print(msg)

    def _print_success(self, msg: str) -> None:
        if self._rich:
            self._console.print(f"[bold green]{msg}[/bold green]")
        else:
            print(f"SUCCESS: {msg}")
