"""Failure-case tests for resilience testing.

This module tests how the pipeline handles various failure scenarios:
- Bad/malformed EPUB files
- TTS synthesis failures
- Missing dependencies
- File system errors
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from epub2audio.epub_reader import EbooklibEpubReader
from epub2audio.tts_engine import (
    TtsError,
    TtsInputError,
    TtsModelError,
    TtsSizeError,
    TtsTransientError,
    MlxTtsEngine,
)
from epub2audio.tts_pipeline import TtsSynthesisSettings, synthesize_text
from epub2audio.error_log import ErrorCategory, ErrorSeverity, ErrorLog, ErrorLogStore
from epub2audio.interfaces import AudioChunk


# ============================================================================
# Fixtures
# ============================================================================


@dataclass
class MockEpubItem:
    """Mock ebooklib item for testing."""

    file_name: str = "chapter1.xhtml"
    media_type: str = "application/xhtml+xml"
    content: bytes = b"<html><body><p>Test content</p></body></html>"

    def get_type(self) -> str:
        return 9  # ITEM_DOCUMENT


@dataclass
class MockEpubBook:
    """Mock ebooklib EPUB book for testing."""

    title: str | None = "Test Book"
    author: str | None = "Test Author"
    language: str | None = "en"
    toc: list = ()
    spine: list[tuple[str, bool | str | None]] = ()
    cover: str | None = None

    def get_metadata(self, namespace: str, name: str) -> list:
        """Get metadata in ebooklib format."""
        if name == "title" and self.title:
            return [(self.title, {})]
        if name == "creator" and self.author:
            return [(self.author, {})]
        if name == "language" and self.language:
            return [(self.language, {})]
        return []

    def get_item_with_id(self, item_id: str) -> MockEpubItem | None:
        """Get item by ID."""
        return MockEpubItem()

    def get_cover_uri(self) -> str | None:
        return self.cover

    def get_items_of_type(self, item_type: int) -> list:
        return []

    def get_item_by_id(self, item_id: str) -> object | None:
        return None


# ============================================================================
# Bad EPUB Tests
# ============================================================================


class TestBadEpubHandling:
    """Test handling of malformed or invalid EPUB files."""

    @patch("epub2audio.epub_reader.epub")
    def test_epub_file_not_found(self, mock_epub: MagicMock) -> None:
        """Test reading a non-existent EPUB file."""
        mock_epub.read_epub.side_effect = FileNotFoundError("No such file")
        reader = EbooklibEpubReader()

        with pytest.raises(FileNotFoundError):
            reader.read(Path("/nonexistent/path.epub"))

    @patch("epub2audio.epub_reader.epub")
    def test_epub_corrupted_file(self, mock_epub: MagicMock) -> None:
        """Test reading a corrupted EPUB file."""
        # Simulate a corrupted EPUB that raises an exception during parsing
        mock_epub.read_epub.side_effect = Exception("Invalid EPUB format")
        reader = EbooklibEpubReader()

        with pytest.raises(Exception, match="Invalid EPUB format"):
            reader.read(Path("corrupted.epub"))

    @patch("epub2audio.epub_reader.ITEM_DOCUMENT", 1)
    @patch("epub2audio.epub_reader.epub")
    @patch("epub2audio.epub_reader.BeautifulSoup")
    def test_epub_empty_spine(self, mock_bs: MagicMock, mock_epub: MagicMock) -> None:
        """Test handling of EPUB with empty spine."""
        mock_book = MockEpubBook(title="Empty Spine Book", spine=[])
        mock_epub.read_epub.return_value = mock_book

        mock_soup = MagicMock()
        mock_soup.title = None
        mock_soup.body = MagicMock()
        mock_soup.body.get_text.return_value = "Content"
        mock_bs.return_value = mock_soup

        reader = EbooklibEpubReader()
        result = reader.read(Path("empty_spine.epub"))

        # Should succeed but with no chapters
        assert result.metadata.title == "Empty Spine Book"
        assert len(result.chapters) == 0

    @patch("epub2audio.epub_reader.ITEM_DOCUMENT", 1)
    @patch("epub2audio.epub_reader.epub")
    @patch("epub2audio.epub_reader.BeautifulSoup")
    def test_epub_no_metadata(self, mock_bs: MagicMock, mock_epub: MagicMock) -> None:
        """Test handling of EPUB with no metadata."""
        mock_book = MockEpubBook(title=None, author=None, language=None, spine=[("item1", True)])
        mock_epub.read_epub.return_value = mock_book

        mock_soup = MagicMock()
        mock_soup.title = None
        mock_soup.body = MagicMock()
        mock_soup.body.get_text.return_value = "Content"
        mock_bs.return_value = mock_soup

        reader = EbooklibEpubReader()
        result = reader.read(Path("no_metadata.epub"))

        # Should use fallback title
        assert result.metadata.title == "no_metadata"
        assert result.metadata.author is None

    @patch("epub2audio.epub_reader.ITEM_DOCUMENT", 1)
    @patch("epub2audio.epub_reader.epub")
    @patch("epub2audio.epub_reader.BeautifulSoup")
    def test_epub_unreadable_content(self, mock_bs: MagicMock, mock_epub: MagicMock) -> None:
        """Test handling of EPUB with unreadable chapter content."""
        mock_book = MockEpubBook(title="Bad Content Book", spine=[("item1", True)])

        # Mock item that returns None content - get_content raises OSError
        mock_item = MagicMock()
        mock_item.get_name.return_value = "chapter1.xhtml"
        mock_item.get_content.side_effect = OSError("Permission denied")
        mock_book.get_item_with_id = lambda item_id: mock_item

        mock_epub.read_epub.return_value = mock_book

        # Mock BeautifulSoup to handle None content gracefully
        mock_soup = MagicMock()
        mock_soup.title = None
        mock_soup.body = MagicMock()
        # When content extraction fails, empty text is returned
        mock_soup.body.get_text.return_value = ""
        mock_bs.return_value = mock_soup

        reader = EbooklibEpubReader()

        # Should handle the error gracefully by skipping the empty chapter
        result = reader.read(Path("bad_content.epub"))
        assert len(result.chapters) == 0

    @patch("epub2audio.epub_reader.ITEM_DOCUMENT", 1)
    @patch("epub2audio.epub_reader.epub")
    @patch("epub2audio.epub_reader.BeautifulSoup")
    def test_epub_malformed_html(self, mock_bs: MagicMock, mock_epub: MagicMock) -> None:
        """Test handling of EPUB with malformed HTML content."""
        mock_book = MockEpubBook(title="Malformed HTML Book", spine=[("item1", True)])
        mock_epub.read_epub.return_value = mock_book

        # Mock BeautifulSoup to handle malformed HTML gracefully
        mock_soup = MagicMock()
        mock_soup.title = None
        mock_soup.body = MagicMock()
        # Even with malformed HTML, BeautifulSoup should return something
        mock_soup.body.get_text.return_value = ""
        mock_bs.return_value = mock_soup

        reader = EbooklibEpubReader()
        result = reader.read(Path("malformed_html.epub"))

        # Should skip empty chapters
        assert len(result.chapters) == 0

    @patch("epub2audio.epub_reader.ITEM_DOCUMENT", 1)
    @patch("epub2audio.epub_reader.epub")
    @patch("epub2audio.epub_reader.BeautifulSoup")
    def test_epub_missing_spine_items(self, mock_bs: MagicMock, mock_epub: MagicMock) -> None:
        """Test handling of EPUB where spine references non-existent items."""
        mock_book = MockEpubBook(title="Missing Items Book", spine=[("nonexistent", True)])
        # get_item_with_id returns None for missing items
        mock_book.get_item_with_id = lambda item_id: None
        mock_epub.read_epub.return_value = mock_book

        mock_soup = MagicMock()
        mock_soup.title = None
        mock_soup.body = MagicMock()
        mock_soup.body.get_text.return_value = "Content"
        mock_bs.return_value = mock_soup

        reader = EbooklibEpubReader()
        result = reader.read(Path("missing_items.epub"))

        # Should handle gracefully - may skip or error depending on implementation
        assert result.metadata.title == "Missing Items Book"

    @patch("epub2audio.epub_reader.epub")
    def test_epub_missing_dependencies(self, mock_epub: MagicMock) -> None:
        """Test helpful error when ebooklib is not installed."""
        with patch("epub2audio.epub_reader.epub", None):
            reader = EbooklibEpubReader()
            with pytest.raises(RuntimeError, match="Missing EPUB reader dependencies"):
                reader.read(Path("test.epub"))


# ============================================================================
# TTS Failure Tests
# ============================================================================


class TestTtsFailures:
    """Test TTS engine failure scenarios."""

    def test_tts_empty_input(self, tmp_path: Path) -> None:
        """Test TTS with empty input string."""
        engine = MlxTtsEngine(
            model_id="test",
            output_dir=tmp_path,
        )

        with pytest.raises(TtsInputError, match="empty or contains no speakable content"):
            engine.synthesize("")

    def test_tts_whitespace_only_input(self, tmp_path: Path) -> None:
        """Test TTS with whitespace-only input."""
        engine = MlxTtsEngine(
            model_id="test",
            output_dir=tmp_path,
        )

        with pytest.raises(TtsInputError, match="empty or contains no speakable content"):
            engine.synthesize("   \n\t  ")

    def test_tts_punctuation_only_input(self, tmp_path: Path) -> None:
        """Test TTS with punctuation-only input (non-speech)."""
        engine = MlxTtsEngine(
            model_id="test",
            output_dir=tmp_path,
        )

        with pytest.raises(TtsInputError, match="empty or contains no speakable content"):
            engine.synthesize("!!!")

    def test_tts_input_exceeds_max_chars(self, tmp_path: Path) -> None:
        """Test TTS with input exceeding max character limit."""
        engine = MlxTtsEngine(
            model_id="test",
            output_dir=tmp_path,
            max_input_chars=100,
        )

        long_text = "word " * 100  # 500 characters

        with pytest.raises(TtsSizeError, match="exceeds max"):
            engine.synthesize(long_text)

    def test_tts_model_load_failure_mlx_missing(self, tmp_path: Path) -> None:
        """Test model load failure when MLX is not installed."""
        # Since mlx_audio is a runtime dependency and may not be installed,
        # we use pytest.skip to document this test scenario.
        # When mlx_audio is not installed, MlxTtsEngine.ensure_loaded() should
        # raise TtsModelError with message "mlx-audio is not installed".
        pytest.skip("mlx_audio runtime dependency testing - use 'epub2audio doctor' for validation")

    def test_tts_model_load_failure_generic(self, tmp_path: Path) -> None:
        """Test model load failure with generic exception during TextToSpeech instantiation."""
        # Since mlx_audio is a runtime dependency and may not be installed,
        # we use pytest.skip to document this test scenario.
        # When TextToSpeech.from_pretrained() fails, MlxTtsEngine.ensure_loaded()
        # should raise TtsModelError with message "Failed to load MLX Audio TextToSpeech model".
        pytest.skip("mlx_audio runtime dependency testing - use 'epub2audio doctor' for validation")


class TestTtsPipelineFailures:
    """Test TTS pipeline handling of various failure scenarios."""

    def test_pipeline_handles_input_error(self, tmp_path: Path) -> None:
        """Test pipeline skips chunks with TtsInputError."""
        calls: list[str] = []

        class FailingEngine:
            def synthesize(self, text: str, voice: str | None = None, config: dict | None = None) -> AudioChunk:
                calls.append(text)
                raise TtsInputError("Not speakable")

        settings = TtsSynthesisSettings(
            model_id="test",
            max_chars=200,
            min_chars=10,
            hard_max_chars=None,
            max_retries=1,
            backoff_base=0.0,
            backoff_jitter=0.0,
            sample_rate=24000,
            channels=1,
            speed=1.0,
            lang_code=None,
        )

        chunks = synthesize_text("!!!", FailingEngine(), settings, sleep_fn=lambda _: None)

        # Should return empty list for non-speakable input
        assert chunks == []
        assert len(calls) == 1  # Tried once

    def test_pipeline_handles_size_error_with_split(self, tmp_path: Path) -> None:
        """Test pipeline splits text when it exceeds max_chars."""
        calls: list[str] = []

        class SizeLimitEngine:
            def __init__(self):
                self.fail_on_first_call = True

            def synthesize(self, text: str, voice: str | None = None, config: dict | None = None) -> AudioChunk:
                calls.append(text)
                # First call with long text fails with size error
                if self.fail_on_first_call:
                    self.fail_on_first_call = False
                    raise TtsSizeError(f"Input too long")
                # Subsequent calls with shorter text succeed
                chunk_file = tmp_path / f"chunk_{len(calls)}.wav"
                chunk_file.write_bytes(b"fake wav")
                return AudioChunk(index=0, path=chunk_file)

        settings = TtsSynthesisSettings(
            model_id="test",
            max_chars=50,
            min_chars=10,
            hard_max_chars=100,
            max_retries=1,
            backoff_base=0.0,
            backoff_jitter=0.0,
            sample_rate=24000,
            channels=1,
            speed=1.0,
            lang_code=None,
        )

        # Text that will be split
        text = "This is a long text. This is another sentence."
        chunks = synthesize_text(text, SizeLimitEngine(), settings, sleep_fn=lambda _: None)

        # Should have split the text and succeeded
        assert len(chunks) >= 1
        assert len(calls) >= 2  # At least the original call + split chunks

    def test_pipeline_handles_transient_error_with_retry(self, tmp_path: Path) -> None:
        """Test pipeline retries on TtsTransientError."""
        attempts = {"count": 0}

        class TransientFailureEngine:
            def synthesize(self, text: str, voice: str | None = None, config: dict | None = None) -> AudioChunk:
                attempts["count"] += 1
                if attempts["count"] < 3:
                    raise TtsTransientError("Temporary failure")
                (tmp_path / "success.wav").write_bytes(b"fake wav")
                return AudioChunk(index=0, path=tmp_path / "success.wav")

        settings = TtsSynthesisSettings(
            model_id="test",
            max_chars=200,
            min_chars=10,
            hard_max_chars=None,
            max_retries=5,
            backoff_base=0.0,
            backoff_jitter=0.0,
            sample_rate=24000,
            channels=1,
            speed=1.0,
            lang_code=None,
        )

        chunks = synthesize_text("Hello world", TransientFailureEngine(), settings, sleep_fn=lambda _: None)

        # Should have retried and succeeded
        assert attempts["count"] == 3
        assert len(chunks) == 1

    def test_pipeline_gives_up_after_max_retries(self, tmp_path: Path) -> None:
        """Test pipeline gives up after max retries."""
        settings = TtsSynthesisSettings(
            model_id="test",
            max_chars=200,
            min_chars=10,
            hard_max_chars=None,
            max_retries=2,
            backoff_base=0.0,
            backoff_jitter=0.0,
            sample_rate=24000,
            channels=1,
            speed=1.0,
            lang_code=None,
        )

        class AlwaysFailingEngine:
            def synthesize(self, text: str, voice: str | None = None, config: dict | None = None) -> AudioChunk:
                raise TtsTransientError("Always fails")

        # Should raise after max retries
        with pytest.raises(TtsTransientError, match="Always fails"):
            synthesize_text("Hello", AlwaysFailingEngine(), settings, sleep_fn=lambda _: None)

    def test_pipeline_propagates_unexpected_errors(self, tmp_path: Path) -> None:
        """Test pipeline propagates unexpected (non-TTS) errors."""
        settings = TtsSynthesisSettings(
            model_id="test",
            max_chars=200,
            min_chars=10,
            hard_max_chars=None,
            max_retries=3,
            backoff_base=0.0,
            backoff_jitter=0.0,
            sample_rate=24000,
            channels=1,
            speed=1.0,
            lang_code=None,
        )

        class UnexpectedErrorEngine:
            def synthesize(self, text: str, voice: str | None = None, config: dict | None = None) -> AudioChunk:
                raise ValueError("Unexpected error")

        # Unexpected errors should not be retried and should propagate
        with pytest.raises(ValueError, match="Unexpected error"):
            synthesize_text("Hello", UnexpectedErrorEngine(), settings, sleep_fn=lambda _: None)


# ============================================================================
# Error Log Tests
# ============================================================================


class TestErrorLogResilience:
    """Test error logging system resilience."""

    def test_error_log_handles_all_categories(self, tmp_path: Path) -> None:
        """Test that all error categories can be logged."""
        store = ErrorLogStore(tmp_path)
        log = store.get_logger("test-book", "test-id", "run-123")

        # Test logging each category
        for category in ErrorCategory:
            log.add_error(
                category=category,
                severity=ErrorSeverity.ERROR,
                message=f"Test {category.value}",
            )

        assert len(log.errors) == len(ErrorCategory)

    def test_error_log_handles_exception_details(self, tmp_path: Path) -> None:
        """Test error logging with full exception details."""
        store = ErrorLogStore(tmp_path)
        log = store.get_logger("test-book", "test-id", "run-123")

        try:
            raise ValueError("Test exception with details")
        except ValueError as exc:
            entry = log.add_error(
                category=ErrorCategory.UNKNOWN,
                severity=ErrorSeverity.ERROR,
                message="An error occurred",
                step="test_step",
                chapter_index=5,
                details={"context": "test context"},
                exc=exc,
            )

        assert entry.exception_type == "ValueError"
        assert entry.exception_message == "Test exception with details"
        assert entry.step == "test_step"
        assert entry.chapter_index == 5
        assert entry.details == {"context": "test context"}
        assert entry.stack_trace is not None

    def test_error_log_load_corrupted_file(self, tmp_path: Path) -> None:
        """Test loading from corrupted error log returns None."""
        store = ErrorLogStore(tmp_path)

        # Create a corrupted JSON file
        corrupted_path = tmp_path / "test-book.json"
        corrupted_path.write_text("invalid json {{{")

        result = store.load("test-book")
        assert result is None

    def test_error_log_load_missing_file(self, tmp_path: Path) -> None:
        """Test loading from missing error log returns None."""
        store = ErrorLogStore(tmp_path)
        result = store.load("nonexistent-book")
        assert result is None

    def test_error_log_different_run_id(self, tmp_path: Path) -> None:
        """Test that different run IDs create new logs."""
        store = ErrorLogStore(tmp_path)

        # Create first log
        log1 = store.get_logger("test-book", "test-id", "run-123")
        log1.add_error(ErrorCategory.UNKNOWN, ErrorSeverity.ERROR, "First error")
        store.save(log1)

        # Get logger with different run ID
        log2 = store.get_logger("test-book", "test-id", "run-456")

        # Should be a new log, not the old one
        assert len(log2.errors) == 0
        assert log2.run_id == "run-456"


# ============================================================================
# File System Error Tests
# ============================================================================


class TestFileSystemErrors:
    """Test handling of file system errors."""

    @pytest.mark.skip(reason="File system permission tests are platform-dependent and difficult to test reliably")
    def test_output_dir_creation_permission_denied(self, tmp_path: Path) -> None:
        """Test handling when output directory cannot be created."""
        # This is difficult to test reliably without mocking
        # The actual behavior depends on OS and permissions
        pass

    @patch("epub2audio.tts_engine.wave.open")
    def test_wav_write_failure(self, mock_wave_open: MagicMock, tmp_path: Path) -> None:
        """Test handling of WAV file write failure."""
        mock_wave_open.side_effect = OSError("Disk full")

        engine = MlxTtsEngine(
            model_id="test",
            output_dir=tmp_path,
        )
        engine._model = MagicMock()
        engine._model.generate = MagicMock(return_value=iter([]))

        # The actual error handling depends on implementation
        # This test documents the expected behavior
        with pytest.raises((OSError, TtsTransientError)):
            with patch("epub2audio.tts_engine._generate_with_model", return_value=([], 1)):
                engine.synthesize("test")


# ============================================================================
# Integration Tests
# ============================================================================


class TestFailureResilienceIntegration:
    """Integration tests for overall failure resilience."""

    @pytest.mark.skip(reason="Requires full pipeline setup - placeholder for future implementation")
    def test_pipeline_continues_after_single_chapter_failure(self, tmp_path: Path) -> None:
        """Test that pipeline continues processing after one chapter fails."""
        # This would be an integration test with the full pipeline
        # For now, it's a placeholder documenting the expected behavior
        pass

    def test_error_log_created_on_failure(self, tmp_path: Path) -> None:
        """Test that error log is created when failures occur."""
        store = ErrorLogStore(tmp_path)
        log = store.get_logger("failing-book", "book-id", "run-1")

        log.add_error(
            category=ErrorCategory.EPUB_PARSING,
            severity=ErrorSeverity.ERROR,
            message="Failed to parse EPUB",
        )

        store.save(log)

        # Verify the log was saved
        loaded = store.load("failing-book")
        assert loaded is not None
        assert len(loaded.errors) == 1
        assert loaded.errors[0].category == ErrorCategory.EPUB_PARSING
