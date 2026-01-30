"""Packaging chapter audio into M4B with metadata and cover art."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import subprocess
import wave
from typing import Sequence

from .interfaces import BookMetadata, ChapterAudio, Packager
from .utils import ensure_dir

_LOGGER = logging.getLogger(__name__)


@dataclass
class FfmpegPackager(Packager):
    work_dir: Path
    audio_bitrate: str = "128k"
    logger: logging.Logger | None = None

    def package(
        self,
        chapters: Sequence[ChapterAudio],
        metadata: BookMetadata,
        out_path: Path,
        cover_image: Path | None = None,
    ) -> Path:
        logger = self.logger or _LOGGER
        if not chapters:
            raise RuntimeError("No chapter audio provided for packaging.")

        ordered = sorted(chapters, key=lambda chapter: chapter.index)
        _validate_chapter_files(ordered)

        out_path = _ensure_m4b_path(out_path)
        ensure_dir(out_path.parent)
        ensure_dir(self.work_dir)

        concat_file = self.work_dir / f"{out_path.stem}_concat.txt"
        meta_file = self.work_dir / f"{out_path.stem}_metadata.txt"
        _write_concat_file(concat_file, ordered)
        _write_metadata_file(meta_file, ordered, metadata)

        resolved_cover = _resolve_cover_image(cover_image, logger)
        cmd = _build_ffmpeg_cmd(concat_file, meta_file, out_path, resolved_cover, self.audio_bitrate)
        _run_ffmpeg(cmd, logger)
        return out_path


def _ensure_m4b_path(out_path: Path) -> Path:
    if out_path.suffix.lower() != ".m4b":
        return out_path.with_suffix(".m4b")
    return out_path


def _validate_chapter_files(chapters: Sequence[ChapterAudio]) -> None:
    for chapter in chapters:
        if not chapter.path.exists():
            raise RuntimeError(f"Chapter audio missing: {chapter.path}")
        if chapter.path.stat().st_size <= 0:
            raise RuntimeError(f"Chapter audio is empty: {chapter.path}")


def _resolve_cover_image(cover_image: Path | None, logger: logging.Logger) -> Path | None:
    if cover_image is None:
        return None
    if not cover_image.exists():
        logger.warning("Cover image missing: %s (skipping cover embed).", cover_image)
        return None
    if cover_image.stat().st_size <= 0:
        logger.warning("Cover image is empty: %s (skipping cover embed).", cover_image)
        return None
    return cover_image


def _build_ffmpeg_cmd(
    concat_file: Path,
    meta_file: Path,
    out_path: Path,
    cover_image: Path | None,
    audio_bitrate: str,
) -> list[str]:
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),
    ]
    if cover_image is not None:
        cmd.extend(["-i", str(cover_image)])
    cmd.extend(["-f", "ffmetadata", "-i", str(meta_file)])

    metadata_index = "2" if cover_image is not None else "1"
    cmd.extend(["-map", "0:a"])
    if cover_image is not None:
        cmd.extend(["-map", "1:v"])
    cmd.extend(["-map_metadata", metadata_index])
    cmd.extend(["-c:a", "aac", "-b:a", audio_bitrate])
    if cover_image is not None:
        cmd.extend(
            [
                "-disposition:v:0",
                "attached_pic",
                "-metadata:s:v",
                "title=Album cover",
                "-metadata:s:v",
                "comment=Cover (front)",
            ]
        )
    cmd.append(str(out_path))
    return cmd


def _write_concat_file(path: Path, chapters: Sequence[ChapterAudio]) -> None:
    lines = []
    for chapter in chapters:
        escaped = _escape_concat_path(chapter.path)
        lines.append(f"file '{escaped}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_metadata_file(path: Path, chapters: Sequence[ChapterAudio], metadata: BookMetadata) -> None:
    lines = [";FFMETADATA1"]
    if metadata.title:
        lines.append(f"title={_escape_metadata_value(metadata.title)}")
        lines.append(f"album={_escape_metadata_value(metadata.title)}")
    if metadata.author:
        lines.append(f"artist={_escape_metadata_value(metadata.author)}")
    lines.append("genre=Audiobook")
    lines.append("stik=2")

    start_ms = 0
    for chapter in chapters:
        duration_ms = _wav_duration_ms(chapter.path)
        if duration_ms <= 0:
            duration_ms = 1
        end_ms = start_ms + duration_ms
        title = chapter.title or f"Chapter {chapter.index + 1}"
        lines.extend(
            [
                "",
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={_escape_metadata_value(title)}",
            ]
        )
        start_ms = end_ms

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as handle:
        frames = handle.getnframes()
        rate = handle.getframerate()
    if rate <= 0:
        return 0
    return int(round((frames / rate) * 1000))


def _escape_metadata_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace("\n", "\\n")
    escaped = escaped.replace("=", "\\=")
    escaped = escaped.replace(";", "\\;")
    escaped = escaped.replace("#", "\\#")
    return escaped


def _escape_concat_path(path: Path) -> str:
    raw = str(path)
    return raw.replace("'", "'\\''")


def _run_ffmpeg(cmd: list[str], logger: logging.Logger) -> None:
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg is required for M4B packaging but was not found in PATH.") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        logger.error("ffmpeg failed during packaging: %s", stderr)
        raise RuntimeError("ffmpeg failed during M4B packaging.")
