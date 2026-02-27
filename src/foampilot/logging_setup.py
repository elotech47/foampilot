"""Configure structlog with dual-sink logging.

- Console (stderr): INFO level by default, DEBUG when verbose=True.
- File (logs/foampilot.log): DEBUG level always, rotating 10 MB × 3.

Call configure_logging() once at process startup before any structlog usage.
"""

import logging
import logging.handlers
import sys
from pathlib import Path

import structlog


def configure_logging(
    verbose: bool = False,
    log_dir: Path | None = None,
) -> None:
    """Set up structlog + stdlib for dual-sink logging.

    Args:
        verbose: If True, show DEBUG messages on the terminal too.
        log_dir: Directory for the log file (default: <cwd>/logs).
    """
    log_dir = log_dir or (Path.cwd() / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "foampilot.log"

    # Processors applied before the stdlib bridge
    shared_processors: list = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%dT%H:%M:%S", utc=False),
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # ── Console handler (INFO by default, DEBUG with --verbose) ───────────────
    console_level = logging.DEBUG if verbose else logging.INFO
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()),
            foreign_pre_chain=shared_processors,
        )
    )

    # ── File handler (DEBUG always, rotating) ────────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
        )
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    # Remove any default handlers (e.g., from previous configure calls)
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)
