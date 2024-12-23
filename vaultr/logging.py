"""Logging setup: route everything, including uvicorn's own records, through loguru."""

from __future__ import annotations

import inspect
import logging
import sys

from loguru import logger

_INTERCEPTED = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi")


class InterceptHandler(logging.Handler):
    """Forwards standard library log records to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Walk back to the caller outside of the logging machinery so the emitted
        # record points at the real source line.
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    """Install the loguru sink and redirect the standard library loggers into it."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=level.upper(),
        serialize=json_logs,
        backtrace=False,
        diagnose=False,  # never render local variables, they may hold passphrases
    )

    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in _INTERCEPTED:
        logging.getLogger(name).handlers = [InterceptHandler()]
        logging.getLogger(name).propagate = False
