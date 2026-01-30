"""Structured error logging for diagnostics.

This module provides per-book error logging in JSON format for improved
diagnostics and error analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any
import traceback

from .utils import ensure_dir, slugify


class ErrorCategory(Enum):
    """Categories of errors for structured classification."""

    # EPUB parsing errors
    EPUB_PARSING = "epub_parsing"
    EPUB_INVALID = "epub_invalid"
    EPUB_METADATA = "epub_metadata"

    # Text processing errors
    TEXT_CLEANING = "text_cleaning"
    TEXT_SEGMENTATION = "text_segmentation"

    # TTS errors
    TTS_MODEL_LOAD = "tts_model_load"
    TTS_INPUT = "tts_input"
    TTS_SIZE = "tts_size"
    TTS_TRANSIENT = "tts_transient"
    TTS_SYNTHESIS = "tts_synthesis"

    # Audio processing errors
    AUDIO_SILENCE = "audio_silence"
    AUDIO_NORMALIZATION = "audio_normalization"
    AUDIO_STITCHING = "audio_stitching"

    # Packaging errors
    PACKAGING = "packaging"
    METADATA = "metadata"

    # System errors
    FILE_IO = "file_io"
    DISK_SPACE = "disk_space"
    PERMISSION = "permission"
    UNKNOWN = "unknown"


class ErrorSeverity(Enum):
    """Severity levels for errors."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ErrorEntry:
    """A single structured error entry."""

    category: ErrorCategory
    severity: ErrorSeverity
    message: str
    timestamp: str
    step: str | None = None
    chapter_index: int | None = None
    details: dict[str, Any] | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    stack_trace: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "category": self.category.value,
            "severity": self.severity.value,
            "step": self.step,
            "chapter_index": self.chapter_index,
            "message": self.message,
            "details": self.details,
            "exception_type": self.exception_type,
            "exception_message": self.exception_message,
            "stack_trace": self.stack_trace,
        }


@dataclass
class ErrorLog:
    """Structured error log for a single book."""

    book_slug: str
    book_id: str
    run_id: str
    errors: list[ErrorEntry] = field(default_factory=list)

    def add_error(
        self,
        category: ErrorCategory,
        severity: ErrorSeverity,
        message: str,
        *,
        step: str | None = None,
        chapter_index: int | None = None,
        details: dict[str, Any] | None = None,
        exc: BaseException | None = None,
    ) -> ErrorEntry:
        """Add a new error entry to the log."""
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        exception_type = None
        exception_message = None
        stack_trace = None

        if exc is not None:
            exception_type = type(exc).__name__
            exception_message = str(exc)
            stack_trace = traceback.format_exception(type(exc), exc, exc.__traceback__)
            stack_trace = "".join(stack_trace).strip()

        entry = ErrorEntry(
            category=category,
            severity=severity,
            message=message,
            timestamp=timestamp,
            step=step,
            chapter_index=chapter_index,
            details=details,
            exception_type=exception_type,
            exception_message=exception_message,
            stack_trace=stack_trace,
        )
        self.errors.append(entry)
        return entry

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "book_slug": self.book_slug,
            "book_id": self.book_id,
            "run_id": self.run_id,
            "error_count": len(self.errors),
            "errors": [entry.to_dict() for entry in self.errors],
        }


class ErrorLogStore:
    """Persistent storage for structured error logs."""

    def __init__(self, root: Path) -> None:
        self.root = ensure_dir(root)

    def load(self, book_slug: str) -> ErrorLog | None:
        """Load an error log for a book."""
        path = self._path_for(book_slug)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text("utf-8"))
            errors = []
            for error_data in data.get("errors", []):
                errors.append(
                    ErrorEntry(
                        category=ErrorCategory(error_data["category"]),
                        severity=ErrorSeverity(error_data["severity"]),
                        message=error_data["message"],
                        timestamp=error_data["timestamp"],
                        step=error_data.get("step"),
                        chapter_index=error_data.get("chapter_index"),
                        details=error_data.get("details"),
                        exception_type=error_data.get("exception_type"),
                        exception_message=error_data.get("exception_message"),
                        stack_trace=error_data.get("stack_trace"),
                    )
                )
            return ErrorLog(
                book_slug=data["book_slug"],
                book_id=data["book_id"],
                run_id=data["run_id"],
                errors=errors,
            )
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            # Don't fail the whole pipeline if error log is corrupted
            return None

    def save(self, log: ErrorLog) -> None:
        """Save an error log for a book."""
        path = self._path_for(log.book_slug)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(log.to_dict(), indent=2, ensure_ascii=True), "utf-8")
        tmp_path.replace(path)

    def _path_for(self, book_slug: str) -> Path:
        """Get the path to an error log file."""
        safe_slug = slugify(book_slug)
        return self.root / f"{safe_slug}.json"

    def get_logger(
        self,
        book_slug: str,
        book_id: str,
        run_id: str,
    ) -> ErrorLog:
        """Get or create an error log for a book."""
        existing = self.load(book_slug)
        if existing is not None:
            # Only reuse if it's from the same run
            if existing.run_id == run_id:
                return existing
        return ErrorLog(book_slug=book_slug, book_id=book_id, run_id=run_id)
