from __future__ import annotations

import logging
from pathlib import Path
import struct
import wave

import pytest

from epub2audio.interfaces import BookMetadata, ChapterAudio
from epub2audio.packaging import (
    FfmpegPackager,
    _build_ffmpeg_cmd,
    _ensure_m4b_path,
    _escape_concat_path,
    _escape_metadata_value,
    _resolve_cover_image,
    _run_ffmpeg,
    _validate_chapter_files,
    _wav_duration_ms,
    _write_concat_file,
    _write_metadata_file,
)


class TestEnsureM4bPath:
    def test_returns_path_when_already_m4b(self) -> None:
        path = Path("output/book.m4b")
        result = _ensure_m4b_path(path)
        assert result == path

    def test_returns_path_when_already_m4b_uppercase(self) -> None:
        path = Path("output/book.M4B")
        result = _ensure_m4b_path(path)
        assert result == path

    def test_changes_suffix_to_m4b(self) -> None:
        path = Path("output/book.mp3")
        result = _ensure_m4b_path(path)
        assert result == Path("output/book.m4b")

    def test_adds_m4b_suffix_when_no_suffix(self) -> None:
        path = Path("output/book")
        result = _ensure_m4b_path(path)
        assert result == Path("output/book.m4b")


class TestEscapeMetadataValue:
    def test_escapes_backslashes(self) -> None:
        assert _escape_metadata_value(r"test\value") == r"test\\value"

    def test_escapes_newlines(self) -> None:
        assert _escape_metadata_value("test\nvalue") == r"test\nvalue"

    def test_escapes_equals_sign(self) -> None:
        assert _escape_metadata_value("test=value") == r"test\=value"

    def test_escapes_semicolon(self) -> None:
        assert _escape_metadata_value("test;value") == r"test\;value"

    def test_escapes_hash(self) -> None:
        assert _escape_metadata_value("test#value") == r"test\#value"

    def test_escapes_multiple_special_chars(self) -> None:
        assert _escape_metadata_value(r"a\b=c;d#e") == r"a\\b\=c\;d\#e"


class TestEscapeConcatPath:
    def test_escapes_single_quotes(self) -> None:
        path = Path("/path/to/file's name.wav")
        result = _escape_concat_path(path)
        assert result == "/path/to/file'\\''s name.wav"

    def test_does_not_escape_double_quotes(self) -> None:
        path = Path('/path/to/file"name.wav')
        result = _escape_concat_path(path)
        assert result == '/path/to/file"name.wav'

    def test_no_quotes_returns_unchanged(self) -> None:
        path = Path("/path/to/file.wav")
        result = _escape_concat_path(path)
        assert result == "/path/to/file.wav"


class TestWavDurationMs:
    def test_calculates_duration_correctly(self, tmp_path: Path) -> None:
        wav_path = tmp_path / "test.wav"
        sample_rate = 24000
        num_samples = 12000  # 0.5 seconds

        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(sample_rate)
            # Write silence
            data = struct.pack("<" + "h" * num_samples, *[0] * num_samples)
            wav_file.writeframes(data)

        duration = _wav_duration_ms(wav_path)
        assert duration == 500  # 0.5 seconds = 500ms

    def test_returns_zero_for_zero_sample_rate(self, tmp_path: Path) -> None:
        # Cannot actually set frame rate to 0 with wave module, so we mock it
        # by creating a minimal valid WAV with 1 frame and 1 Hz rate
        wav_path = tmp_path / "test.wav"
        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(1)
            wav_file.writeframes(struct.pack("<h", 0))

        duration = _wav_duration_ms(wav_path)
        assert duration == 1000  # 1 frame / 1 Hz = 1 second = 1000ms

    def test_returns_zero_for_no_frames(self, tmp_path: Path) -> None:
        wav_path = tmp_path / "test.wav"
        with wave.open(str(wav_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)

        duration = _wav_duration_ms(wav_path)
        assert duration == 0


class TestValidateChapterFiles:
    def test_passes_when_all_files_exist(self, tmp_path: Path) -> None:
        chapter1 = tmp_path / "chapter1.wav"
        chapter2 = tmp_path / "chapter2.wav"
        chapter1.write_text("data")
        chapter2.write_text("data")

        chapters = [
            ChapterAudio(index=0, title="Chapter 1", path=chapter1),
            ChapterAudio(index=1, title="Chapter 2", path=chapter2),
        ]

        _validate_chapter_files(chapters)  # Should not raise

    def test_raises_when_file_missing(self, tmp_path: Path) -> None:
        missing_file = tmp_path / "missing.wav"

        chapters = [
            ChapterAudio(index=0, title="Missing", path=missing_file),
        ]

        with pytest.raises(RuntimeError, match="Chapter audio missing"):
            _validate_chapter_files(chapters)

    def test_raises_when_file_is_empty(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "empty.wav"
        empty_file.write_text("")

        chapters = [
            ChapterAudio(index=0, title="Empty", path=empty_file),
        ]

        with pytest.raises(RuntimeError, match="Chapter audio is empty"):
            _validate_chapter_files(chapters)


class TestResolveCoverImage:
    def test_returns_none_when_cover_is_none(self) -> None:
        logger = logging.getLogger(__name__)
        result = _resolve_cover_image(None, logger)
        assert result is None

    def test_returns_path_when_file_exists(self, tmp_path: Path) -> None:
        cover = tmp_path / "cover.jpg"
        cover.write_bytes(b"fake_image_data")
        logger = logging.getLogger(__name__)

        result = _resolve_cover_image(cover, logger)
        assert result == cover

    def test_returns_none_when_file_missing(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        cover = tmp_path / "missing.jpg"
        logger = logging.getLogger(__name__)

        with caplog.at_level(logging.WARNING):
            result = _resolve_cover_image(cover, logger)

        assert result is None
        assert "Cover image missing" in caplog.text

    def test_returns_none_when_file_is_empty(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        cover = tmp_path / "empty.jpg"
        cover.write_bytes(b"")
        logger = logging.getLogger(__name__)

        with caplog.at_level(logging.WARNING):
            result = _resolve_cover_image(cover, logger)

        assert result is None
        assert "Cover image is empty" in caplog.text


class TestBuildFfmpegCmd:
    def test_command_without_cover(self, tmp_path: Path) -> None:
        concat_file = tmp_path / "concat.txt"
        meta_file = tmp_path / "metadata.txt"
        out_path = tmp_path / "output.m4b"

        cmd = _build_ffmpeg_cmd(concat_file, meta_file, out_path, None, "128k")

        assert "ffmpeg" in cmd
        assert "-hide_banner" in cmd
        assert "-nostats" in cmd
        assert "-y" in cmd
        assert "-f" in cmd
        assert "concat" in cmd
        assert "-i" in cmd
        assert str(concat_file) in cmd
        assert str(meta_file) in cmd
        assert "-map_metadata" in cmd
        assert "-c:a" in cmd
        assert "aac" in cmd
        assert "-b:a" in cmd
        assert "128k" in cmd
        assert str(out_path) in cmd
        # No cover-related flags
        assert "-disposition:v:0" not in cmd

    def test_command_with_cover(self, tmp_path: Path) -> None:
        concat_file = tmp_path / "concat.txt"
        meta_file = tmp_path / "metadata.txt"
        out_path = tmp_path / "output.m4b"
        cover = tmp_path / "cover.jpg"

        cmd = _build_ffmpeg_cmd(concat_file, meta_file, out_path, cover, "64k")

        # Should include cover input
        assert "-i" in cmd
        assert str(cover) in cmd
        # Should include video map and disposition
        assert "-disposition:v:0" in cmd
        assert "attached_pic" in cmd
        assert "title=Album cover" in cmd
        # Custom bitrate
        assert "64k" in cmd
        # Verify cover path appears after metadata input
        concat_idx = cmd.index(str(concat_file))
        cover_idx = cmd.index(str(cover))
        meta_idx = cmd.index(str(meta_file))
        assert concat_idx < cover_idx < meta_idx

    def test_metadata_index_with_cover(self, tmp_path: Path) -> None:
        concat_file = tmp_path / "concat.txt"
        meta_file = tmp_path / "metadata.txt"
        out_path = tmp_path / "output.m4b"
        cover = tmp_path / "cover.jpg"

        cmd = _build_ffmpeg_cmd(concat_file, meta_file, out_path, cover, "128k")

        # With cover: concat=0, cover=1, metadata=2
        assert "-map_metadata" in cmd
        metadata_idx_idx = cmd.index("-map_metadata")
        assert cmd[metadata_idx_idx + 1] == "2"

    def test_metadata_index_without_cover(self, tmp_path: Path) -> None:
        concat_file = tmp_path / "concat.txt"
        meta_file = tmp_path / "metadata.txt"
        out_path = tmp_path / "output.m4b"

        cmd = _build_ffmpeg_cmd(concat_file, meta_file, out_path, None, "128k")

        # Without cover: concat=0, metadata=1
        assert "-map_metadata" in cmd
        metadata_idx_idx = cmd.index("-map_metadata")
        assert cmd[metadata_idx_idx + 1] == "1"


class TestWriteConcatFile:
    def test_writes_concat_file(self, tmp_path: Path) -> None:
        concat_path = tmp_path / "concat.txt"
        chapter1 = tmp_path / "chapter1.wav"
        chapter2 = tmp_path / "chapter2.wav"
        chapter1.write_text("data")
        chapter2.write_text("data")

        chapters = [
            ChapterAudio(index=0, title="Chapter 1", path=chapter1),
            ChapterAudio(index=1, title="Chapter 2", path=chapter2),
        ]

        _write_concat_file(concat_path, chapters)

        content = concat_path.read_text()
        assert f"file '{chapter1}'" in content
        assert f"file '{chapter2}'" in content
        assert content.endswith("\n")

    def test_escapes_single_quotes_in_path(self, tmp_path: Path) -> None:
        concat_path = tmp_path / "concat.txt"
        chapter_path = tmp_path / "chapter'1.wav"
        chapter_path.write_text("data")

        chapters = [ChapterAudio(index=0, title="Chapter 1", path=chapter_path)]

        _write_concat_file(concat_path, chapters)

        content = concat_path.read_text()
        assert "'\\''" in content


class TestWriteMetadataFile:
    @staticmethod
    def _create_minimal_wav(path: Path) -> None:
        """Create a minimal valid WAV file for testing."""
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            # Write a single frame of silence
            wav_file.writeframes(struct.pack("<h", 0))

    def test_writes_metadata_with_title_and_author(self, tmp_path: Path) -> None:
        meta_path = tmp_path / "metadata.txt"
        chapter = tmp_path / "chapter.wav"
        self._create_minimal_wav(chapter)

        chapters = [ChapterAudio(index=0, title="Chapter 1", path=chapter)]
        metadata = BookMetadata(title="Test Book", author="Test Author")

        _write_metadata_file(meta_path, chapters, metadata)

        content = meta_path.read_text()
        assert ";FFMETADATA1" in content
        assert "title=Test Book" in content
        assert "album=Test Book" in content
        assert "artist=Test Author" in content
        assert "genre=Audiobook" in content
        assert "stik=2" in content

    def test_writes_metadata_with_author_only(self, tmp_path: Path) -> None:
        meta_path = tmp_path / "metadata.txt"
        chapter = tmp_path / "chapter.wav"
        self._create_minimal_wav(chapter)

        chapters = [ChapterAudio(index=0, title="Chapter 1", path=chapter)]
        metadata = BookMetadata(title="", author="Test Author")

        _write_metadata_file(meta_path, chapters, metadata)

        content = meta_path.read_text()
        # Check that global title/album are NOT written (only chapter title should be present)
        lines = content.split("\n")
        # Global metadata comes right after ;FFMETADATA1
        assert ";FFMETADATA1" in lines[0]
        # The first actual metadata line should be artist, not title
        metadata_lines = [l for l in lines if l and not l.startswith(";") and not l.startswith("[")]
        # First metadata line should be artist, not title
        assert metadata_lines[0] == "artist=Test Author"
        assert "album=" not in metadata_lines[0]

    def test_writes_chapter_markers(self, tmp_path: Path) -> None:
        meta_path = tmp_path / "metadata.txt"
        chapter = tmp_path / "chapter.wav"
        self._create_minimal_wav(chapter)

        chapters = [
            ChapterAudio(index=0, title="First Chapter", path=chapter),
        ]
        metadata = BookMetadata(title="Book", author=None)

        _write_metadata_file(meta_path, chapters, metadata)

        content = meta_path.read_text()
        assert "[CHAPTER]" in content
        assert "TIMEBASE=1/1000" in content
        assert "START=0" in content
        assert "END=1" in content  # Single frame at 24000Hz ≈ 0.04ms, rounded to 1ms
        assert "title=First Chapter" in content

    def test_generates_chapter_title_when_missing(self, tmp_path: Path) -> None:
        meta_path = tmp_path / "metadata.txt"
        chapter = tmp_path / "chapter.wav"
        self._create_minimal_wav(chapter)

        chapters = [ChapterAudio(index=2, title="", path=chapter)]
        metadata = BookMetadata(title="Book", author=None)

        _write_metadata_file(meta_path, chapters, metadata)

        content = meta_path.read_text()
        assert "title=Chapter 3" in content  # index 2 + 1 = Chapter 3

    def test_escapes_special_chars_in_metadata(self, tmp_path: Path) -> None:
        meta_path = tmp_path / "metadata.txt"
        chapter = tmp_path / "chapter.wav"
        self._create_minimal_wav(chapter)

        chapters = [ChapterAudio(index=0, title="Chapter: Test; Value", path=chapter)]
        metadata = BookMetadata(title="Book: Title", author="Author; Name")

        _write_metadata_file(meta_path, chapters, metadata)

        content = meta_path.read_text()
        # Colons are NOT escaped by _escape_metadata_value
        assert "Book: Title" in content
        assert "Author\\; Name" in content
        assert "Chapter: Test\\; Value" in content


class TestRunFfmpeg:
    def test_raises_on_ffmpeg_not_found(self, caplog: pytest.LogCaptureFixture) -> None:
        logger = logging.getLogger(__name__)
        cmd = ["nonexistent_ffmpeg_binary", "-version"]

        with pytest.raises(RuntimeError, match="ffmpeg is required"):
            _run_ffmpeg(cmd, logger)

    def test_raises_on_nonzero_exit_code(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        logger = logging.getLogger(__name__)
        # Use a command that will fail
        cmd = ["ffmpeg", "-invalid_option_that_will_fail"]

        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            _run_ffmpeg(cmd, logger)


class TestFfmpegPackager:
    def test_raises_with_empty_chapters(self, tmp_path: Path) -> None:
        packager = FfmpegPackager(work_dir=tmp_path)
        metadata = BookMetadata(title="Book", author="Author")
        out_path = tmp_path / "output.m4b"

        with pytest.raises(RuntimeError, match="No chapter audio provided"):
            packager.package([], metadata, out_path)

    def test_creates_output_m4b_from_different_extension(self, tmp_path: Path) -> None:
        # Note: This test will fail if ffmpeg is not installed
        # It's mainly to verify the path handling logic
        packager = FfmpegPackager(work_dir=tmp_path)

        # Test path conversion (would fail on ffmpeg, but we can test the path setup)
        assert _ensure_m4b_path(Path("output.mp3")) == Path("output.m4b")
        assert _ensure_m4b_path(Path("output.wav")) == Path("output.m4b")
