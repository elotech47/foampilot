"""Pre-flight clarification agent.

Runs a conversational loop with the user before any pipeline phase begins.
Identifies ambiguities, states assumptions, and gets explicit confirmation.
Uses the Anthropic API directly (no tool loop) for a tight chat experience.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any

import structlog
from anthropic import Anthropic

from foampilot import config

log = structlog.get_logger(__name__)

MAX_CLARIFY_TURNS = 5

CLARIFY_SYSTEM_PROMPT = """\
You are FoamPilot's pre-flight assistant. Given a simulation request:
1. Identify what is ambiguous or missing (geometry dims, Re number, fluid properties, solver, turbulence model, end time, mesh resolution).
2. State the assumptions you will make if the user doesn't specify.
3. Ask ONE question per turn — the single most important unknown first.
4. Once everything is clear, output a JSON block tagged ```confirm``` with the finalised parameters.
Do not start setting up files. Only clarify.
"""


@dataclass
class ClarifyResult:
    confirmed: bool           # True = user approved, proceed
    refined_request: str      # Possibly reworded request after clarification
    confirmed_params: dict    # Key params the user explicitly agreed to
    cancelled: bool = False   # True = user abandoned the request


class ClarifyAgent:
    """Conversational pre-flight agent that clarifies the user's simulation request.

    Runs a plain-text chat loop (not inside Rich Live) until the user confirms
    or cancels. Automatically proceeds after MAX_CLARIFY_TURNS turns.
    """

    def __init__(self) -> None:
        self._client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    def run(self, user_request: str, console: Any) -> ClarifyResult:
        """Run the clarification chat loop.

        Args:
            user_request: The raw simulation request from the user.
            console: A Rich Console instance for printing (outside Live).

        Returns:
            ClarifyResult with confirmation status and refined parameters.
        """
        # Import here to avoid circular import at module level
        try:
            from rich.panel import Panel
            from rich.rule import Rule
            console.print(Panel(
                "[bold cyan]FoamPilot Pre-flight[/bold cyan]  —  "
                "Let me clarify your request before we begin.\n"
                "[dim]Type your answers, or[/dim] [bold]go[/bold] [dim]to proceed / [/dim]"
                "[bold]cancel[/bold] [dim]to abort.[/dim]",
                border_style="cyan",
                padding=(0, 2),
            ))
        except Exception:
            print("\n=== FoamPilot Pre-flight ===")
            print("Type 'go' to proceed, 'cancel' to abort.\n")

        messages: list[dict] = [{"role": "user", "content": user_request}]
        params: dict = {}
        turns = 0

        while turns < MAX_CLARIFY_TURNS:
            # Call the LLM
            try:
                response = self._client.messages.create(
                    model=config.MODEL,
                    max_tokens=1024,
                    system=CLARIFY_SYSTEM_PROMPT,
                    messages=messages,
                )
            except Exception as exc:
                log.warning("clarify_llm_error", error=str(exc))
                # Skip clarification on API error — proceed with original request
                return ClarifyResult(
                    confirmed=True,
                    refined_request=user_request,
                    confirmed_params={},
                )

            assistant_text = response.content[0].text
            messages.append({"role": "assistant", "content": assistant_text})
            turns += 1

            # Check for confirm block
            has_confirm = "```confirm" in assistant_text
            if has_confirm:
                params = self._extract_confirm(assistant_text)
                # Strip the confirm block from displayed text
                display_text = re.sub(r"```confirm[\s\S]*?```", "", assistant_text).strip()
            else:
                display_text = assistant_text

            # Print the assistant response
            self._print_agent(display_text, console)

            if has_confirm:
                self._print_params(params, console)
                self._print_hint("[dim]Type [bold]go[/bold] to proceed or [bold]cancel[/bold] to abort.[/dim]", console)

            # Check if we've hit the turn limit
            if turns >= MAX_CLARIFY_TURNS and not has_confirm:
                self._print_hint(
                    f"[dim]Maximum clarification turns reached — proceeding with stated assumptions.[/dim]",
                    console,
                )
                return ClarifyResult(
                    confirmed=True,
                    refined_request=self._refine(messages, user_request),
                    confirmed_params=params,
                )

            # Get user input — restore real stdout in case we're inside StreamGuard
            saved_out, saved_err = sys.stdout, sys.stderr
            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                user_input = "cancel"
            finally:
                sys.stdout = saved_out
                sys.stderr = saved_err

            if not user_input:
                continue

            lower = user_input.lower()

            if lower in ("cancel", "exit", "quit", "abort"):
                return ClarifyResult(
                    confirmed=False,
                    refined_request=user_request,
                    confirmed_params={},
                    cancelled=True,
                )

            if lower in ("go", "ok", "proceed", "yes", "confirm"):
                return ClarifyResult(
                    confirmed=True,
                    refined_request=self._refine(messages, user_request),
                    confirmed_params=params,
                )

            messages.append({"role": "user", "content": user_input})

        # Fallback — auto-proceed after turn limit
        return ClarifyResult(
            confirmed=True,
            refined_request=self._refine(messages, user_request),
            confirmed_params=params,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _extract_confirm(self, text: str) -> dict:
        """Extract the JSON object from a ```confirm ... ``` block."""
        match = re.search(r"```confirm\s*([\s\S]+?)\s*```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return {}

    def _refine(self, messages: list[dict], original: str) -> str:
        """Produce a refined request string from the conversation history.

        Asks the LLM to summarise the agreed parameters into a single concise
        request string. Falls back to the original on any error.
        """
        summary_messages = messages + [{
            "role": "user",
            "content": (
                "Summarise the agreed simulation parameters into a single concise "
                "request sentence (no JSON, no lists — just one sentence describing "
                "the full simulation setup)."
            ),
        }]
        try:
            resp = self._client.messages.create(
                model=config.MODEL,
                max_tokens=256,
                system=CLARIFY_SYSTEM_PROMPT,
                messages=summary_messages,
            )
            refined = resp.content[0].text.strip()
            return refined if refined else original
        except Exception:
            return original

    def _print_agent(self, text: str, console: Any) -> None:
        """Print the agent's response to the console with Markdown rendering."""
        try:
            from rich.markdown import Markdown
            console.print("\n[cyan]FoamPilot:[/cyan]")
            console.print(Markdown(text))
            console.print()
        except Exception:
            print(f"\nFoamPilot: {text}\n")

    def _print_params(self, params: dict, console: Any) -> None:
        """Print the confirmed parameters table."""
        if not params:
            return
        try:
            from rich.table import Table
            tbl = Table.grid(padding=(0, 2))
            tbl.add_column(style="dim", justify="right")
            tbl.add_column()
            for k, v in params.items():
                tbl.add_row(str(k), str(v))
            console.print(tbl)
        except Exception:
            for k, v in params.items():
                print(f"  {k}: {v}")

    def _print_hint(self, markup: str, console: Any) -> None:
        try:
            console.print(markup)
        except Exception:
            import re as _re
            print(_re.sub(r"\[.*?\]", "", markup))
