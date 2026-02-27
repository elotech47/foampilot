"""Configure structlog with file-only logging.

The terminal UI is handled exclusively by Rich. No log output goes to
stdout or stderr — everything is routed to the rotating log file.

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
    """Set up structlog + stdlib for file-only logging.

    Args:
        verbose: If True, log at DEBUG level to the file (default: INFO).
        log_dir: Directory for the log file (default: <cwd>/logs).
    """
    log_dir = log_dir or (Path.cwd() / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "foampilot.log"

    file_level = logging.DEBUG if verbose else logging.INFO

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

    # ── File handler only — no console handler ────────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(file_level)
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
        )
    )

    # Root logger: WARNING so stray library output doesn't escape to anywhere
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    root.handlers.clear()
    root.addHandler(file_handler)

    # Raise foampilot's own loggers to file_level so our messages are captured
    logging.getLogger("foampilot").setLevel(file_level)

    # Silence noisy third-party libraries completely
    for noisy in ("httpx", "httpcore", "anthropic", "urllib3", "docker"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
