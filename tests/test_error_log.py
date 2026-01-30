"""Tests for error_log module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from epub2audio.error_log import (
    ErrorCategory,
    ErrorEntry,
    ErrorLog,
    ErrorLogStore,
    ErrorSeverity,
)


class TestErrorEntry:
    """Tests for ErrorEntry dataclass."""

    def test_to_dict_includes_all_fields(self) -> None:
        """to_dict should include all fields."""
        entry = ErrorEntry(
            category=ErrorCategory.TTS_SYNTHESIS,
            severity=ErrorSeverity.ERROR,
            message="Synthesis failed",
            timestamp="2024-01-01T12:00:00+00:00",
            step="tts",
            chapter_index=5,
            details={"retry_count": 3},
            exception_type="RuntimeError",
            exception_message="Something went wrong",
            stack_trace="line 1\nline 2",
        )
        result = entry.to_dict()
        assert result == {
            "timestamp": "2024-01-01T12:00:00+00:00",
            "category": "tts_synthesis",
            "severity": "error",
            "step": "tts",
            "chapter_index": 5,
            "message": "Synthesis failed",
            "details": {"retry_count": 3},
            "exception_type": "RuntimeError",
            "exception_message": "Something went wrong",
            "stack_trace": "line 1\nline 2",
        }

    def test_to_dict_with_minimal_fields(self) -> None:
        """to_dict should work with only required fields."""
        entry = ErrorEntry(
            category=ErrorCategory.EPUB_PARSING,
            severity=ErrorSeverity.WARNING,
            message="Missing metadata",
            timestamp="2024-01-01T12:00:00+00:00",
        )
        result = entry.to_dict()
        assert result == {
            "timestamp": "2024-01-01T12:00:00+00:00",
            "category": "epub_parsing",
            "severity": "warning",
            "step": None,
            "chapter_index": None,
            "message": "Missing metadata",
            "details": None,
            "exception_type": None,
            "exception_message": None,
            "stack_trace": None,
        }

    def test_entry_is_immutable(self) -> None:
        """ErrorEntry should be frozen/immutable."""
        entry = ErrorEntry(
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.INFO,
            message="test",
            timestamp="2024-01-01T00:00:00+00:00",
        )
        with pytest.raises(Exception):  # FrozenInstanceError from dataclasses
            entry.message = "modified"


class TestErrorLog:
    """Tests for ErrorLog dataclass."""

    def test_add_error_creates_entry(self) -> None:
        """add_error should create and append an ErrorEntry."""
        log = ErrorLog(
            book_slug="test-book",
            book_id="test-book-id",
            run_id="run-123",
        )
        entry = log.add_error(
            category=ErrorCategory.TTS_INPUT,
            severity=ErrorSeverity.ERROR,
            message="Empty text",
            step="segmentation",
            chapter_index=2,
        )
        assert len(log.errors) == 1
        assert log.errors[0] is entry
        assert entry.category == ErrorCategory.TTS_INPUT
        assert entry.severity == ErrorSeverity.ERROR
        assert entry.message == "Empty text"
        assert entry.step == "segmentation"
        assert entry.chapter_index == 2
        assert entry.details is None
        assert entry.exception_type is None

    def test_add_error_with_details(self) -> None:
        """add_error should store details dict."""
        log = ErrorLog(book_slug="b", book_id="id", run_id="r")
        log.add_error(
            category=ErrorCategory.AUDIO_NORMALIZATION,
            severity=ErrorSeverity.WARNING,
            message="High LUFS",
            details={"lufs": -12, "target": -16},
        )
        assert log.errors[0].details == {"lufs": -12, "target": -16}

    def test_add_error_with_exception(self) -> None:
        """add_error should capture exception info."""
        log = ErrorLog(book_slug="b", book_id="id", run_id="r")

        try:
            raise ValueError("test exception")
        except ValueError as e:
            log.add_error(
                category=ErrorCategory.FILE_IO,
                severity=ErrorSeverity.CRITICAL,
                message="Failed to read file",
                exc=e,
            )

        entry = log.errors[0]
        assert entry.exception_type == "ValueError"
        assert entry.exception_message == "test exception"
        assert entry.stack_trace is not None
        assert "ValueError: test exception" in entry.stack_trace

    def test_add_error_without_exception(self) -> None:
        """add_error without exception should have None exception fields."""
        log = ErrorLog(book_slug="b", book_id="id", run_id="r")
        log.add_error(
            category=ErrorCategory.TEXT_CLEANING,
            severity=ErrorSeverity.INFO,
            message="Removed citation",
        )
        entry = log.errors[0]
        assert entry.exception_type is None
        assert entry.exception_message is None
        assert entry.stack_trace is None

    def test_add_error_returns_entry(self) -> None:
        """add_error should return the created entry."""
        log = ErrorLog(book_slug="b", book_id="id", run_id="r")
        entry = log.add_error(
            category=ErrorCategory.PACKAGING,
            severity=ErrorSeverity.ERROR,
            message="FFmpeg failed",
        )
        assert entry.category == ErrorCategory.PACKAGING
        assert entry.message == "FFmpeg failed"

    def test_add_error_generates_timestamp(self) -> None:
        """add_error should generate UTC timestamp in ISO format."""
        log = ErrorLog(book_slug="b", book_id="id", run_id="r")
        entry = log.add_error(
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.INFO,
            message="test",
        )
        # Should be ISO format with Z or +00:00
        assert entry.timestamp.endswith("+00:00") or entry.timestamp.endswith("Z")

    def test_to_dict_includes_metadata(self) -> None:
        """to_dict should include log metadata."""
        log = ErrorLog(
            book_slug="my-book",
            book_id="book-id-123",
            run_id="run-456",
        )
        log.add_error(
            category=ErrorCategory.EPUB_INVALID,
            severity=ErrorSeverity.ERROR,
            message="Corrupted EPUB",
        )

        result = log.to_dict()
        assert result["book_slug"] == "my-book"
        assert result["book_id"] == "book-id-123"
        assert result["run_id"] == "run-456"
        assert result["error_count"] == 1

    def test_to_dict_includes_all_errors(self) -> None:
        """to_dict should serialize all error entries."""
        log = ErrorLog(book_slug="b", book_id="id", run_id="r")
        log.add_error(ErrorCategory.EPUB_PARSING, ErrorSeverity.ERROR, "error1")
        log.add_error(ErrorCategory.TTS_SYNTHESIS, ErrorSeverity.WARNING, "error2")

        result = log.to_dict()
        assert len(result["errors"]) == 2
        assert result["errors"][0]["message"] == "error1"
        assert result["errors"][1]["message"] == "error2"


class TestErrorLogStore:
    """Tests for ErrorLogStore class."""

    def test_init_creates_root_directory(self, tmp_path: Path) -> None:
        """Store initialization should create the root directory."""
        error_dir = tmp_path / "errors"
        store = ErrorLogStore(root=error_dir)
        assert error_dir.exists()
        assert error_dir.is_dir()

    def test_path_for_sanitizes_book_slug(self, tmp_path: Path) -> None:
        """Path generation should sanitize book_slug using slugify."""
        store = ErrorLogStore(tmp_path)
        book_slug = "../unsafe/book slug/../../etc"
        path = store._path_for(book_slug)
        assert path.name == "unsafe-book-slug-etc.json"
        assert path.parent == tmp_path

    def test_load_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        """Loading a non-existent error log should return None."""
        store = ErrorLogStore(tmp_path)
        log = store.load("missing-book")
        assert log is None

    def test_load_handles_corrupted_json(self, tmp_path: Path) -> None:
        """Loading corrupted JSON should return None gracefully."""
        store = ErrorLogStore(tmp_path)
        path = store._path_for("corrupted")
        path.write_text("{ not valid json }", encoding="utf-8")

        log = store.load("corrupted")
        assert log is None

    def test_load_handles_missing_required_fields(self, tmp_path: Path) -> None:
        """Loading JSON with missing required fields should return None."""
        store = ErrorLogStore(tmp_path)
        path = store._path_for("incomplete")
        incomplete_data = {
            "book_slug": "test",
            # Missing book_id and run_id
        }
        path.write_text(json.dumps(incomplete_data), encoding="utf-8")

        log = store.load("incomplete")
        assert log is None

    def test_load_handles_invalid_enum_values(self, tmp_path: Path) -> None:
        """Loading with invalid category/severity should return None."""
        store = ErrorLogStore(tmp_path)
        path = store._path_for("invalid-enum")
        invalid_data = {
            "book_slug": "test",
            "book_id": "id",
            "run_id": "r",
            "errors": [
                {
                    "timestamp": "2024-01-01T00:00:00+00:00",
                    "category": "not_a_real_category",
                    "severity": "error",
                    "message": "test",
                }
            ],
        }
        path.write_text(json.dumps(invalid_data), encoding="utf-8")

        log = store.load("invalid-enum")
        assert log is None

    def test_save_and_load_preserves_log(self, tmp_path: Path) -> None:
        """Saving and loading should preserve log data."""
        store = ErrorLogStore(tmp_path)
        book_slug = "test-book"

        log = ErrorLog(
            book_slug=book_slug,
            book_id="book-id-123",
            run_id="run-456",
        )
        log.add_error(
            category=ErrorCategory.TTS_TRANSIENT,
            severity=ErrorSeverity.ERROR,
            message="Temporary failure",
            step="synthesis",
            chapter_index=3,
            details={"retry": 2},
        )

        store.save(log)
        loaded = store.load(book_slug)

        assert loaded is not None
        assert loaded.book_slug == book_slug
        assert loaded.book_id == "book-id-123"
        assert loaded.run_id == "run-456"
        assert len(loaded.errors) == 1
        assert loaded.errors[0].category == ErrorCategory.TTS_TRANSIENT
        assert loaded.errors[0].severity == ErrorSeverity.ERROR
        assert loaded.errors[0].message == "Temporary failure"
        assert loaded.errors[0].step == "synthesis"
        assert loaded.errors[0].chapter_index == 3
        assert loaded.errors[0].details == {"retry": 2}

    def test_save_creates_json_file(self, tmp_path: Path) -> None:
        """Saved file should be valid JSON."""
        store = ErrorLogStore(tmp_path)
        book_slug = "json-test"
        log = ErrorLog(
            book_slug=book_slug,
            book_id="id",
            run_id="r",
        )
        log.add_error(
            category=ErrorCategory.EPUB_METADATA,
            severity=ErrorSeverity.WARNING,
            message="Missing author",
        )

        store.save(log)
        path = store._path_for(book_slug)

        # Should be valid JSON
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["book_slug"] == book_slug
        assert data["error_count"] == 1
        assert data["errors"][0]["message"] == "Missing author"

    def test_save_is_atomic(self, tmp_path: Path) -> None:
        """Save should use atomic write (temp file then rename)."""
        store = ErrorLogStore(tmp_path)
        book_slug = "atomic-book"
        log = ErrorLog(book_slug=book_slug, book_id="id", run_id="r")

        store.save(log)
        path = store._path_for(book_slug)
        assert path.exists()

        # Verify no temp file exists after successful save
        assert not path.with_suffix(".json.tmp").exists()

    def test_save_overwrites_existing_log(self, tmp_path: Path) -> None:
        """Saving should overwrite existing error log file."""
        store = ErrorLogStore(tmp_path)
        book_slug = "overwrite-test"

        log1 = ErrorLog(book_slug=book_slug, book_id="id", run_id="r1")
        log1.add_error(ErrorCategory.UNKNOWN, ErrorSeverity.INFO, "error1")
        store.save(log1)

        log2 = ErrorLog(book_slug=book_slug, book_id="id", run_id="r2")
        log2.add_error(ErrorCategory.UNKNOWN, ErrorSeverity.ERROR, "error2")
        store.save(log2)

        loaded = store.load(book_slug)
        assert loaded is not None
        assert loaded.run_id == "r2"
        assert len(loaded.errors) == 1
        assert loaded.errors[0].message == "error2"

    def test_get_logger_creates_new_log_when_missing(self, tmp_path: Path) -> None:
        """get_logger should create new log when none exists."""
        store = ErrorLogStore(tmp_path)
        log = store.get_logger(
            book_slug="new-book",
            book_id="book-id",
            run_id="run-1",
        )
        assert log.book_slug == "new-book"
        assert log.book_id == "book-id"
        assert log.run_id == "run-1"
        assert len(log.errors) == 0

    def test_get_logger_loads_existing_same_run(self, tmp_path: Path) -> None:
        """get_logger should load existing log from same run."""
        store = ErrorLogStore(tmp_path)
        book_slug = "same-run-book"

        # Create initial log
        log1 = store.get_logger(
            book_slug=book_slug,
            book_id="id1",
            run_id="run-123",
        )
        log1.add_error(ErrorCategory.TTS_SYNTHESIS, ErrorSeverity.ERROR, "error1")
        store.save(log1)

        # Get logger for same run - should reload
        log2 = store.get_logger(
            book_slug=book_slug,
            book_id="id2",  # Different book_id but same run
            run_id="run-123",
        )
        assert len(log2.errors) == 1
        assert log2.errors[0].message == "error1"
        assert log2.book_id == "id1"  # Should preserve original book_id

    def test_get_logger_creates_new_for_different_run(self, tmp_path: Path) -> None:
        """get_logger should create new log when run_id differs."""
        store = ErrorLogStore(tmp_path)
        book_slug = "multi-run-book"

        # Create log for run-1
        log1 = store.get_logger(
            book_slug=book_slug,
            book_id="id",
            run_id="run-1",
        )
        log1.add_error(ErrorCategory.EPUB_PARSING, ErrorSeverity.ERROR, "old error")
        store.save(log1)

        # Get logger for different run - should create fresh log
        log2 = store.get_logger(
            book_slug=book_slug,
            book_id="id",
            run_id="run-2",
        )
        assert len(log2.errors) == 0
        assert log2.run_id == "run-2"

    def test_save_and_load_with_all_categories(self, tmp_path: Path) -> None:
        """Saving and loading should preserve all error categories."""
        store = ErrorLogStore(tmp_path)
        book_slug = "all-categories"

        log = ErrorLog(book_slug=book_slug, book_id="id", run_id="r")

        # Add one error from each category
        categories = [
            ErrorCategory.EPUB_PARSING,
            ErrorCategory.EPUB_INVALID,
            ErrorCategory.EPUB_METADATA,
            ErrorCategory.TEXT_CLEANING,
            ErrorCategory.TEXT_SEGMENTATION,
            ErrorCategory.TTS_MODEL_LOAD,
            ErrorCategory.TTS_INPUT,
            ErrorCategory.TTS_SIZE,
            ErrorCategory.TTS_TRANSIENT,
            ErrorCategory.TTS_SYNTHESIS,
            ErrorCategory.AUDIO_SILENCE,
            ErrorCategory.AUDIO_NORMALIZATION,
            ErrorCategory.AUDIO_STITCHING,
            ErrorCategory.PACKAGING,
            ErrorCategory.METADATA,
            ErrorCategory.FILE_IO,
            ErrorCategory.DISK_SPACE,
            ErrorCategory.PERMISSION,
            ErrorCategory.UNKNOWN,
        ]

        for cat in categories:
            log.add_error(cat, ErrorSeverity.ERROR, f"{cat.value} error")

        store.save(log)
        loaded = store.load(book_slug)

        assert loaded is not None
        assert len(loaded.errors) == len(categories)
        loaded_categories = {e.category for e in loaded.errors}
        assert loaded_categories == set(categories)

    def test_save_and_load_with_all_severities(self, tmp_path: Path) -> None:
        """Saving and loading should preserve all severity levels."""
        store = ErrorLogStore(tmp_path)
        book_slug = "all-severities"

        log = ErrorLog(book_slug=book_slug, book_id="id", run_id="r")

        severities = [
            ErrorSeverity.INFO,
            ErrorSeverity.WARNING,
            ErrorSeverity.ERROR,
            ErrorSeverity.CRITICAL,
        ]

        for sev in severities:
            log.add_error(ErrorCategory.UNKNOWN, sev, f"{sev.value} message")

        store.save(log)
        loaded = store.load(book_slug)

        assert loaded is not None
        assert len(loaded.errors) == len(severities)
        loaded_severities = {e.severity for e in loaded.errors}
        assert loaded_severities == set(severities)

    def test_save_and_load_with_all_optional_fields(self, tmp_path: Path) -> None:
        """Saving and loading should preserve all optional fields."""
        store = ErrorLogStore(tmp_path)
        book_slug = "full-fields"

        log = ErrorLog(book_slug=book_slug, book_id="id", run_id="r")
        log.add_error(
            category=ErrorCategory.TTS_SYNTHESIS,
            severity=ErrorSeverity.ERROR,
            message="Full error",
            step="tts_pipeline",
            chapter_index=42,
            details={"context": "test context", "extra": [1, 2, 3]},
        )

        store.save(log)
        loaded = store.load(book_slug)

        assert loaded is not None
        entry = loaded.errors[0]
        assert entry.step == "tts_pipeline"
        assert entry.chapter_index == 42
        assert entry.details == {"context": "test context", "extra": [1, 2, 3]}
