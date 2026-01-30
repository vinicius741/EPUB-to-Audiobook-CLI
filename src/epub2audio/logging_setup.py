"""Logging setup with per-book log files."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .error_log import ErrorLogStore
from .utils import ensure_dir, slugify


@dataclass
class LoggingContext:
    root_dir: Path
    run_id: str
    log_level: int
    console_level: int
    logger: logging.Logger
    formatter: logging.Formatter
    error_log_store: ErrorLogStore

    def get_book_logger(self, book_slug: str) -> logging.Logger:
        safe_slug = slugify(book_slug)
        logger_name = f"epub2audio.book.{safe_slug}"
        logger = logging.getLogger(logger_name)
        logger.setLevel(self.log_level)
        logger.propagate = False

        if not _has_file_handler(logger):
            book_dir = ensure_dir(self.root_dir / safe_slug)
            file_path = book_dir / f"{self.run_id}.log"
            handler = logging.FileHandler(file_path, encoding="utf-8")
            handler.setLevel(self.log_level)
            handler.setFormatter(self.formatter)
            logger.addHandler(handler)
        return logger


def initialize_logging(config: Config, run_id: str) -> LoggingContext:
    root_dir = ensure_dir(config.paths.logs)
    log_level = _parse_log_level(config.logging.level)
    console_level = _parse_log_level(config.logging.console_level)

    logger = logging.getLogger("epub2audio")
    logger.setLevel(log_level)
    logger.propagate = False
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    run_log_path = root_dir / f"run-{run_id}.log"
    file_handler = logging.FileHandler(run_log_path, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Initialize structured error log store
    error_log_dir = ensure_dir(config.paths.errors)
    error_log_store = ErrorLogStore(error_log_dir)

    return LoggingContext(
        root_dir=root_dir,
        run_id=run_id,
        log_level=log_level,
        console_level=console_level,
        logger=logger,
        formatter=formatter,
        error_log_store=error_log_store,
    )


def _parse_log_level(level: str) -> int:
    return getattr(logging, level.upper(), logging.INFO)


def _has_file_handler(logger: logging.Logger) -> bool:
    return any(isinstance(handler, logging.FileHandler) for handler in logger.handlers)
