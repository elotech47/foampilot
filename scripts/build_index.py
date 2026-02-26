#!/usr/bin/env python3
"""Standalone script to build the FoamPilot tutorial index.

Usage:
    python scripts/build_index.py --version 11
    python scripts/build_index.py --version 11 --tutorials-path /path/to/tutorials
    python scripts/build_index.py --version 11 --embeddings
    python scripts/build_index.py --version 11 --verbose        # show DEBUG logs
"""

import argparse
import logging
import sys
from pathlib import Path

# Add src/ to path so we can import foampilot without installing
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def _configure_logging(verbose: bool = False) -> None:
    """Configure structlog for human-readable console output.

    INFO level by default; DEBUG level when --verbose is passed.
    """
    import structlog

    level = logging.DEBUG if verbose else logging.INFO

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="%H:%M:%S", utc=False),
            structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the FoamPilot tutorial index",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic index build (no embeddings)
  python scripts/build_index.py --version 11 --tutorials-path OpenFOAM-11/tutorials

  # Include semantic embeddings (~90 MB model download on first run)
  python scripts/build_index.py --version 11 --tutorials-path OpenFOAM-11/tutorials --embeddings

  # Show all debug-level logging for every extraction step
  python scripts/build_index.py --version 11 --tutorials-path OpenFOAM-11/tutorials --verbose
        """,
    )
    parser.add_argument(
        "--version",
        default="11",
        help="OpenFOAM version to index (default: 11)",
    )
    parser.add_argument(
        "--tutorials-path",
        help="Path to OpenFOAM tutorials directory "
             "(default: /opt/openfoam{version}/tutorials)",
    )
    parser.add_argument(
        "--embeddings",
        action="store_true",
        help="Also generate semantic embeddings (requires sentence-transformers). "
             "Downloads ~90 MB model on first run.",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for the index files "
             "(default: src/foampilot/index/data/)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG-level logging (shows every extraction sub-step)",
    )
    args = parser.parse_args()

    _configure_logging(verbose=args.verbose)

    import structlog
    script_log = structlog.get_logger("build_index")

    script_log.info(
        "build_index_script_start",
        version=args.version,
        tutorials_path=args.tutorials_path or f"/opt/openfoam{args.version}/tutorials",
        embeddings=args.embeddings,
        verbose=args.verbose,
    )

    from foampilot.index.builder import IndexBuilder

    output_dir = Path(args.output_dir) if args.output_dir else None
    builder = IndexBuilder(version=args.version, output_dir=output_dir)

    try:
        entries = builder.build(
            tutorials_path=args.tutorials_path,
            generate_embeddings=args.embeddings,
        )
    except FileNotFoundError as exc:
        script_log.error("build_failed", error=str(exc))
        sys.exit(1)
    except Exception as exc:
        script_log.error("build_failed_unexpected", error=str(exc), exc_info=True)
        sys.exit(1)

    # ── Final summary ─────────────────────────────────────────────────────────
    print()  # blank line before summary
    print("=" * 60)
    print(f"  FoamPilot Index Build Complete")
    print("=" * 60)
    print(f"  Version:   OpenFOAM v{args.version}")
    print(f"  Cases:     {len(entries)} tutorial cases indexed")

    if entries:
        # Solver breakdown
        solvers: dict[str, int] = {}
        mesh_types: dict[str, int] = {}
        physics: dict[str, int] = {}
        has_turb = sum(1 for e in entries if e.turbulence_model)
        has_emb = sum(1 for e in entries if e.embedding is not None)

        for e in entries:
            solvers[e.solver] = solvers.get(e.solver, 0) + 1
            mesh_types[e.mesh_type] = mesh_types.get(e.mesh_type, 0) + 1
            for tag in e.physics_tags:
                physics[tag] = physics.get(tag, 0) + 1

        print()
        print("  Solvers (top 10):")
        for solver, count in sorted(solvers.items(), key=lambda x: -x[1])[:10]:
            print(f"    {solver:<35} {count}")

        print()
        print("  Mesh types:")
        for mtype, count in sorted(mesh_types.items(), key=lambda x: -x[1]):
            print(f"    {mtype:<35} {count}")

        print()
        print("  Physics tags:")
        for tag, count in sorted(physics.items(), key=lambda x: -x[1]):
            print(f"    {tag:<35} {count}")

        print()
        print(f"  With turbulence model:  {has_turb}")
        print(f"  With embeddings:        {has_emb}")

    output_dir_resolved = (
        Path(args.output_dir) if args.output_dir
        else Path(__file__).parent.parent / "src" / "foampilot" / "index" / "data"
    )
    index_file = output_dir_resolved / f"tutorial_index_v{args.version}.json"
    print()
    print(f"  Index file: {index_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
