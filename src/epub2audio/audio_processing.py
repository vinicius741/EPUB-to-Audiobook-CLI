"""Audio post-processing: silence insertion, normalization, and stitching."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import re
import subprocess
import wave
from typing import Sequence

from .interfaces import AudioChunk, AudioProcessor
from .utils import ensure_dir

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class LoudnessConfig:
    target_lufs: float = -23.0
    lra: float = 7.0
    true_peak: float = -1.0


@dataclass
class FfmpegAudioProcessor(AudioProcessor):
    work_dir: Path
    sample_rate: int
    channels: int
    loudness: LoudnessConfig = field(default_factory=LoudnessConfig)
    logger: logging.Logger | None = None

    def insert_silence(self, chunks: Sequence[AudioChunk], silence_ms: int) -> Sequence[AudioChunk]:
        if silence_ms <= 0 or len(chunks) <= 1:
            return list(chunks)

        silence_chunk = self._silence_chunk(silence_ms)
        output: list[AudioChunk] = []
        for idx, chunk in enumerate(chunks):
            output.append(chunk)
            if idx < len(chunks) - 1:
                output.append(silence_chunk)
        return output

    def normalize(self, chunks: Sequence[AudioChunk]) -> Sequence[AudioChunk]:
        if not chunks:
            return []
        logger = self.logger or _LOGGER
        normalized: list[AudioChunk] = []
        for chunk in chunks:
            out_path = chunk.path.with_name(f"{chunk.path.stem}.normalized.wav")
            if out_path.exists() and out_path.stat().st_size > 0:
                normalized.append(AudioChunk(index=chunk.index, path=out_path, duration_ms=chunk.duration_ms))
                continue
            ensure_dir(out_path.parent)
            self._normalize_wav(chunk.path, out_path, logger)
            normalized.append(AudioChunk(index=chunk.index, path=out_path, duration_ms=chunk.duration_ms))
        return normalized

    def stitch(self, chunks: Sequence[AudioChunk], out_path: Path) -> Path:
        if out_path.exists() and out_path.stat().st_size > 0:
            return out_path
        ensure_dir(out_path.parent)
        if not chunks:
            raise RuntimeError("No chunks provided for stitching.")

        with wave.open(str(out_path), "wb") as output:
            output.setnchannels(self.channels)
            output.setsampwidth(2)
            output.setframerate(self.sample_rate)
            for chunk in chunks:
                self._append_chunk(output, chunk.path)
        return out_path

    def _append_chunk(self, output: wave.Wave_write, path: Path) -> None:
        with wave.open(str(path), "rb") as handle:
            if handle.getnchannels() != self.channels:
                raise RuntimeError(f"Channel mismatch for {path}: expected {self.channels}")
            if handle.getframerate() != self.sample_rate:
                raise RuntimeError(f"Sample rate mismatch for {path}: expected {self.sample_rate}")
            if handle.getsampwidth() != 2:
                raise RuntimeError(f"Sample width mismatch for {path}: expected 16-bit PCM")
            frames = handle.readframes(handle.getnframes())
            output.writeframes(frames)

    def _silence_chunk(self, silence_ms: int) -> AudioChunk:
        silence_dir = ensure_dir(self.work_dir / "silence")
        filename = f"silence_{self.sample_rate}hz_{self.channels}ch_{silence_ms}ms.wav"
        path = silence_dir / filename
        if not path.exists() or path.stat().st_size == 0:
            self._write_silence(path, silence_ms)
        return AudioChunk(index=0, path=path, duration_ms=silence_ms)

    def _write_silence(self, path: Path, silence_ms: int) -> None:
        frames = int(self.sample_rate * (silence_ms / 1000.0))
        frame_count = frames * self.channels
        silence_bytes = b"\x00\x00" * frame_count
        ensure_dir(path.parent)
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(self.channels)
            handle.setsampwidth(2)
            handle.setframerate(self.sample_rate)
            handle.writeframes(silence_bytes)

    def _normalize_wav(self, input_path: Path, output_path: Path, logger: logging.Logger) -> None:
        loud = self.loudness
        analysis = self._loudnorm_analysis(input_path, loud, logger)
        if not _analysis_is_finite(analysis):
            logger.warning("Skipping loudness normalization for %s (non-finite analysis). Running format-conversion-only pass.", input_path)
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-nostats",
                "-y",
                "-i",
                str(input_path),
                "-ar",
                str(self.sample_rate),
                "-ac",
                str(self.channels),
                "-c:a",
                "pcm_s16le",
                str(output_path),
            ]
            self._run_ffmpeg(cmd, logger)
            return

        filter_args = (
            f"loudnorm=I={loud.target_lufs}:LRA={loud.lra}:TP={loud.true_peak}"
            f":measured_I={analysis['input_i']}"
            f":measured_LRA={analysis['input_lra']}"
            f":measured_TP={analysis['input_tp']}"
            f":measured_thresh={analysis['input_thresh']}"
            f":offset={analysis['target_offset']}"
            f":linear=true"
        )
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-y",
            "-i",
            str(input_path),
            "-af",
            filter_args,
            "-ar",
            str(self.sample_rate),
            "-ac",
            str(self.channels),
            "-c:a",
            "pcm_s16le",
            str(output_path),
        ]
        self._run_ffmpeg(cmd, logger)

    def _loudnorm_analysis(self, input_path: Path, loud: LoudnessConfig, logger: logging.Logger) -> dict[str, str]:
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(input_path),
            "-af",
            f"loudnorm=I={loud.target_lufs}:LRA={loud.lra}:TP={loud.true_peak}:print_format=json",
            "-f",
            "null",
            "-",
        ]
        result = self._run_ffmpeg(cmd, logger, capture_output=True)
        return _extract_loudnorm_json(result.stderr)

    def _run_ffmpeg(
        self,
        cmd: list[str],
        logger: logging.Logger,
        *,
        capture_output: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                cmd,
                check=False,
                capture_output=capture_output,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError("ffmpeg is required for audio processing but was not found in PATH.") from exc

        if result.returncode != 0:
            stderr = result.stderr or ""
            logger.error("ffmpeg failed: %s", stderr.strip())
            raise RuntimeError("ffmpeg failed during audio processing.")
        return result


_LOUDNORM_JSON_RE = re.compile(r"\{[\s\S]*?\}")


def _extract_loudnorm_json(stderr: str) -> dict[str, str]:
    match = _LOUDNORM_JSON_RE.search(stderr)
    if not match:
        raise RuntimeError("Failed to parse loudnorm analysis output.")
    payload = json.loads(match.group(0))
    required = {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}
    if not required.issubset(payload):
        raise RuntimeError("loudnorm analysis output missing required fields.")
    return {key: str(payload[key]) for key in required}


def _analysis_is_finite(analysis: dict[str, str]) -> bool:
    for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset"):
        value = analysis.get(key, "")
        if not _is_finite_number(value):
            return False
    return True


def _is_finite_number(value: str) -> bool:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return parsed == parsed and parsed not in (float("inf"), float("-inf"))
