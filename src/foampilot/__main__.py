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

    # Start the web UI server
    web_parser = subparsers.add_parser("web", help="Launch the FoamPilot web UI")
    web_parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    web_parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    web_parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    web_parser.add_argument("--build", action="store_true", help="Build the frontend before starting")

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
    elif args.command == "web":
        _run_web(args)
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


def _run_web(args: argparse.Namespace) -> None:
    """Launch the FoamPilot web UI server."""
    try:
        import uvicorn
    except ImportError:
        print("ERROR: web dependencies not installed. Run: uv pip install 'foampilot[web]'")
        sys.exit(1)

    frontend_dir = (
        __import__("pathlib").Path(__file__).parent / "ui" / "web" / "frontend"
    )

    if args.build:
        import subprocess
        print("Building frontend...")
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(frontend_dir),
            check=False,
        )
        if result.returncode != 0:
            print("ERROR: Frontend build failed.")
            sys.exit(1)
        print("Frontend built successfully.")

    url = f"http://{args.host}:{args.port}"
    print("Loading FoamPilot (this may take a moment on first run)...")

    from foampilot.ui.web.server import app

    import uvicorn.config
    uv_config = uvicorn.config.Config(
        app, host=args.host, port=args.port, log_level="warning"
    )
    server = uvicorn.Server(uv_config)

    if not args.no_browser:
        import threading
        import webbrowser

        def _open_when_ready():
            while not server.started:
                import time
                time.sleep(0.2)
            print(f"FoamPilot Web UI → {url}")
            webbrowser.open(url)

        threading.Thread(target=_open_when_ready, daemon=True).start()
    else:
        # Still defer the URL message until the server is actually up
        import threading

        def _print_when_ready():
            while not server.started:
                import time
                time.sleep(0.2)
            print(f"FoamPilot Web UI → {url}")

        threading.Thread(target=_print_when_ready, daemon=True).start()

    server.run()


def _run_index(args: argparse.Namespace) -> None:
    """Build the tutorial index."""
    from foampilot.index.builder import IndexBuilder
    builder = IndexBuilder(version=args.version)
    tutorials_path = args.tutorials_path
    builder.build(tutorials_path=tutorials_path)


if __name__ == "__main__":
    main()
