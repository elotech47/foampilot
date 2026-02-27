"""CLI entry point: `foampilot` command."""

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="foampilot",
        description="AI agent for OpenFOAM CFD simulations",
    )
    subparsers = parser.add_subparsers(dest="command")

    # Run a simulation interactively
    run_parser = subparsers.add_parser("run", help="Run a simulation from a natural language request")
    run_parser.add_argument("request", nargs="?", help="Simulation request (omit for interactive mode)")
    run_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show DEBUG-level logs on the terminal (default: INFO only)",
    )

    # Evaluate benchmarks
    eval_parser = subparsers.add_parser("eval", help="Run benchmark evaluation")
    eval_parser.add_argument("--case", help="Specific benchmark case to run")
    eval_parser.add_argument("--suite", choices=["tier1", "tier2", "tier3"], help="Benchmark tier")
    eval_parser.add_argument("--verbose", "-v", action="store_true", help="Show DEBUG logs")

    # Build tutorial index
    index_parser = subparsers.add_parser("index", help="Build the tutorial index")
    index_parser.add_argument("--version", default="11", help="OpenFOAM version")
    index_parser.add_argument("--tutorials-path", help="Path to OpenFOAM tutorials directory")
    index_parser.add_argument("--verbose", "-v", action="store_true", help="Show DEBUG logs")

    args = parser.parse_args()

    # Configure logging before any foampilot imports use structlog
    verbose = getattr(args, "verbose", False)
    from foampilot.logging_setup import configure_logging
    configure_logging(verbose=verbose)

    if args.command == "run" or args.command is None:
        _run_terminal(getattr(args, "request", None), verbose=verbose)
    elif args.command == "eval":
        _run_eval(args)
    elif args.command == "index":
        _run_index(args)
    else:
        parser.print_help()
        sys.exit(1)


def _run_terminal(initial_request: str | None, verbose: bool = False) -> None:
    """Launch the terminal REPL."""
    from foampilot.ui.terminal import TerminalUI
    ui = TerminalUI(verbose=verbose)
    ui.run(initial_request)


def _run_eval(args: argparse.Namespace) -> None:
    """Run benchmark evaluation."""
    from pathlib import Path
    project_root = Path(__file__).parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from benchmarks.runner import BenchmarkRunner
    runner = BenchmarkRunner()
    if args.case:
        runner.run_case(args.case)
    elif args.suite:
        runner.run_suite(args.suite)
    else:
        runner.run_all()


def _run_index(args: argparse.Namespace) -> None:
    """Build the tutorial index."""
    from foampilot.index.builder import IndexBuilder
    builder = IndexBuilder(version=args.version)
    tutorials_path = args.tutorials_path
    builder.build(tutorials_path=tutorials_path)


if __name__ == "__main__":
    main()
