"""Integration tests for EPUB -> M4B pipeline."""

from __future__ import annotations

import struct
import subprocess
import wave
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from epub2audio.config import Config, load_config
from epub2audio.interfaces import AudioChunk
from epub2audio.logging_setup import initialize_logging
from epub2audio.pipeline import run_pipeline
from epub2audio.utils import ensure_dir, generate_run_id


# ============================================================================
# Test fixtures
# ============================================================================


@pytest.fixture
def sample_epub(tmp_path: Path) -> Path:
    """Create a minimal valid EPUB file for testing."""
    try:
        from ebooklib import epub
    except ImportError:
        pytest.skip("ebooklib not installed")

    epub_path = tmp_path / "test_book.epub"

    # Create a minimal EPUB
    book = epub.EpubBook()

    # Set metadata
    book.set_identifier("test-id-123")
    book.set_title("Test Audiobook")
    book.set_language("en")
    book.add_author("Test Author")

    # Create chapters
    chapter1 = epub.EpubHtml(
        title="Chapter One",
        file_name="chapter1.xhtml",
        content="<h1>Chapter One</h1><p>This is the first chapter with some sample text for the audiobook.</p>",
    )
    chapter2 = epub.EpubHtml(
        title="Chapter Two",
        file_name="chapter2.xhtml",
        content="<h1>Chapter Two</h1><p>This is the second chapter with more sample text for the audiobook.</p>",
    )

    # Add chapters to the book
    book.add_item(chapter1)
    book.add_item(chapter2)

    # Define the spine (reading order)
    book.spine = ["nav", chapter1, chapter2]

    # Set the table of contents
    book.toc = (chapter1, chapter2)

    # Add navigation files
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    # Write the EPUB
    epub.write_epub(str(epub_path), book, {})

    return epub_path


@pytest.fixture
def sample_epub_with_cover(tmp_path: Path) -> Path:
    """Create an EPUB with a cover image for testing."""
    try:
        from ebooklib import epub
    except ImportError:
        pytest.skip("ebooklib not installed")

    epub_path = tmp_path / "test_book_cover.epub"

    # Create a minimal EPUB with cover
    book = epub.EpubBook()

    # Set metadata
    book.set_identifier("test-id-cover")
    book.set_title("Book With Cover")
    book.set_language("en")
    book.add_author("Cover Author")

    # Create a simple cover image (1x1 red pixel JPEG)
    cover_data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xdb\x00C\x00\x03\x02\x02\x03\x02\x02\x03\x03\x03\x03\x04\x03\x03\x04\x05\x08\x05\x05\x04\x04\x05\n\x07\x07\x06\x08\x0c\n\x0c\x0c\x0b\n\x0b\x0b\r\x0e\x12\x10\r\x0e\x11\x0e\x0b\x0b\x10\x16\x10\x11\x13\x14\x15\x15\x15\x0c\x0f\x17\x18\x16\x14\x18\x12\x14\x15\x14\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!\x06\x13AQa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1R\x15r\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xc4\x00\x1f\x01\x00\x03\x01\x01\x01\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x11\x00\x02\x01\x02\x04\x04\x03\x04\x07\x05\x04\x04\x00\x01\x02w\x00\x01\x02\x03\x11\x04\x05!1\x06\x12AQ\x07q\x13\"2\x81\x08\x14B\x91\xa1\xb1\xc1\t#3R\xf0\x15br\xd1\n\x16\x17\x18\x19\x1a%&'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00T\x9f\xff\xd9"

    cover = epub.EpubItem(
        uid="cover",
        file_name="cover.jpg",
        media_type="image/jpeg",
        content=cover_data,
    )
    book.add_item(cover)

    # Add a single chapter
    chapter = epub.EpubHtml(
        title="Single Chapter",
        file_name="chapter.xhtml",
        content="<h1>Single Chapter</h1><p>Content with cover image.</p>",
    )
    book.add_item(chapter)
    book.spine = ["nav", chapter]
    book.toc = (chapter,)

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(str(epub_path), book, {})

    return epub_path


def _create_minimal_wav(path: Path, sample_rate: int = 24000, channels: int = 1, duration_ms: int = 500) -> None:
    """Create a minimal valid WAV file for testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    num_samples = int(sample_rate * (duration_ms / 1000.0))

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        # Write silence (16-bit samples = 2 bytes per sample)
        silence = b'\x00' * (num_samples * channels * 2)
        wav_file.writeframes(silence)


@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    """Create a test configuration with temporary directories."""
    paths = tmp_path / "paths"
    epubs = paths / "epubs"
    out = paths / "out"
    cache = paths / "cache"
    logs = paths / "logs"
    errors = paths / "errors"

    for d in (epubs, out, cache, logs, errors):
        ensure_dir(d)

    from epub2audio.config import PathsConfig, LoggingConfig, TtsConfig, AudioConfig

    return Config(
        paths=PathsConfig(
            epubs=epubs,
            out=out,
            cache=cache,
            logs=logs,
            errors=errors,
        ),
        logging=LoggingConfig(level="INFO", console_level="WARNING"),
        tts=TtsConfig(
            engine="mlx",
            model_id="test-model",
            voice=None,
            lang_code=None,
            speed=1.0,
            sample_rate=24000,
            channels=1,
            max_chars=1000,
            min_chars=200,
            hard_max_chars=1250,
            max_retries=2,
            backoff_base=0.5,
            backoff_jitter=0.1,
            output_format="wav",
        ),
        audio=AudioConfig(
            silence_ms=250,
            normalize=True,
            target_lufs=-23.0,
            lra=7.0,
            true_peak=-1.0,
        ),
    )


class _MockTtsEngine:
    """Mock TTS engine that creates minimal WAV files."""

    def __init__(self, config: Config, cache_dir: Path):
        self.config = config
        self.cache_dir = cache_dir
        self.counter = 0

    def synthesize(self, text: str, voice: str | None = None, config: dict | None = None) -> AudioChunk:
        self.counter += 1
        chunk_path = (
            self.cache_dir
            / "tts"
            / "chunks"
            / f"chunk_{self.counter:04d}.wav"
        )
        ensure_dir(chunk_path.parent)
        _create_minimal_wav(
            chunk_path,
            sample_rate=self.config.tts.sample_rate,
            channels=self.config.tts.channels,
            duration_ms=500,
        )
        return AudioChunk(index=self.counter, path=chunk_path)


def _mock_build_engine(config: Config):
    """Mock implementation of _build_engine."""
    return _MockTtsEngine(config, config.paths.cache)


# ============================================================================
# Integration tests
# ============================================================================


@pytest.mark.integration
def test_epub_to_m4b_full_pipeline(sample_epub: Path, test_config: Config) -> None:
    """Test the full pipeline from EPUB to M4B output."""
    # Skip if ffmpeg is not available
    if not _ffmpeg_available():
        pytest.skip("ffmpeg not available")

    run_id = generate_run_id()
    log_ctx = initialize_logging(test_config, run_id)

    # Patch _build_engine to return our mock TTS engine
    with patch("epub2audio.pipeline._build_engine", _mock_build_engine):
        results = run_pipeline(log_ctx, [sample_epub], test_config, progress=None)

    # Verify results
    assert len(results) == 1
    result = results[0]
    assert result.status == "ok"
    assert result.book_slug == "test-audiobook"
    assert result.output_path is not None

    # Verify M4B file exists
    m4b_path = result.output_path
    assert m4b_path.exists()
    assert m4b_path.suffix == ".m4b"
    assert m4b_path.stat().st_size > 0

    # Verify the file is in the correct location
    assert m4b_path.parent == test_config.paths.out / "test-audiobook"
    assert m4b_path.name == "test-audiobook.m4b"

    # Verify chapter audio files were created
    chapter_dir = test_config.paths.cache / "chapters" / "test-audiobook"
    assert chapter_dir.exists()
    chapter_files = list(chapter_dir.glob("*.wav"))
    assert len(chapter_files) >= 2  # At least 2 chapters


@pytest.mark.integration
def test_epub_to_m4b_with_cover(sample_epub_with_cover: Path, test_config: Config) -> None:
    """Test the pipeline preserves cover art in the M4B output."""
    # Skip if ffmpeg is not available
    if not _ffmpeg_available():
        pytest.skip("ffmpeg not available")

    run_id = generate_run_id()
    log_ctx = initialize_logging(test_config, run_id)

    with patch("epub2audio.pipeline._build_engine", _mock_build_engine):
        results = run_pipeline(log_ctx, [sample_epub_with_cover], test_config, progress=None)

    assert len(results) == 1
    result = results[0]
    assert result.status == "ok"
    assert result.output_path is not None

    # Verify M4B file exists and has reasonable size (cover art adds size)
    m4b_path = result.output_path
    assert m4b_path.exists()
    assert m4b_path.stat().st_size > 1000  # Should have some content


@pytest.mark.integration
def test_epub_to_m4b_resumability(sample_epub: Path, test_config: Config) -> None:
    """Test that the pipeline can resume from a previous run."""
    # Skip if ffmpeg is not available
    if not _ffmpeg_available():
        pytest.skip("ffmpeg not available")

    # First run
    run_id_1 = generate_run_id()
    log_ctx_1 = initialize_logging(test_config, run_id_1)

    with patch("epub2audio.pipeline._build_engine", _mock_build_engine):
        results_1 = run_pipeline(log_ctx_1, [sample_epub], test_config, progress=None)

    assert len(results_1) == 1
    assert results_1[0].status == "ok"
    m4b_path_1 = results_1[0].output_path
    assert m4b_path_1 is not None
    assert m4b_path_1.exists()

    # Second run - should skip processing since M4B already exists
    run_id_2 = generate_run_id()
    log_ctx_2 = initialize_logging(test_config, run_id_2)

    with patch("epub2audio.pipeline._build_engine", _mock_build_engine):
        results_2 = run_pipeline(log_ctx_2, [sample_epub], test_config, progress=None)

    # Verify the second run skipped synthesis
    assert results_2[0].status == "skipped"


# ============================================================================
# Helper functions
# ============================================================================


def _ffmpeg_available() -> bool:
    """Check if ffmpeg is available in the system."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False
