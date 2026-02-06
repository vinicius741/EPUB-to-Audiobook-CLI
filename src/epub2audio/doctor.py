"""Doctor checks for TTS environment and model health."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import platform
import time
import wave
from typing import Iterable, Sequence

from .config import Config
from .interfaces import TtsEngine
from .logging_setup import initialize_logging
from .text_segmenter import BasicTextSegmenter
from .tts_engine import TtsError, TtsModelError
from .tts_factory import backend_diagnostics, build_tts_engine, model_cache_status
from .tts_pipeline import TtsSynthesisSettings, synthesize_text
from .utils import ensure_dir, generate_run_id

_LOGGER = logging.getLogger(__name__)
_MIGRATION_NOTE_EMITTED: set[Path] = set()


@dataclass(frozen=True)
class DoctorOptions:
    smoke_test: bool
    long_text_test: bool
    rtf_test: bool
    verify: bool
    text: str
    output_dir: Path | None


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


def run_doctor(config: Config, options: DoctorOptions) -> int:
    run_id = generate_run_id()
    log_ctx = initialize_logging(config, run_id)
    logger = log_ctx.logger

    checks: list[DoctorCheck] = []

    checks.extend(_check_environment(config))

    if options.smoke_test or options.verify:
        checks.extend(_run_smoke_test(config, options, logger))

    if options.rtf_test or options.verify:
        checks.extend(_run_rtf_test(config, options, logger))

    if options.long_text_test or options.verify:
        checks.extend(_run_long_text_test(config, options, logger))

    report = _render_report(checks)
    print(report)

    if any(check.status == "FAIL" for check in checks):
        return 1
    return 0


def _check_environment(config: Config) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []

    checks.append(DoctorCheck("Engine", "OK", config.tts.engine))

    checks.extend(
        DoctorCheck(check.name, check.status, check.detail)
        for check in backend_diagnostics(config)
    )

    if config.tts.engine == "mlx":
        metal_status = _check_metal()
        if metal_status is None:
            checks.append(DoctorCheck("Metal", "WARN", "mlx not installed; cannot detect Metal availability."))
        elif metal_status:
            checks.append(DoctorCheck("Metal", "OK", "Metal GPU acceleration is available."))
        else:
            checks.append(DoctorCheck("Metal", "WARN", "Metal GPU acceleration not available."))

    total_ram_gb = _total_ram_gb()
    if total_ram_gb is None:
        checks.append(DoctorCheck("Memory", "WARN", "Unable to determine system RAM."))
    elif total_ram_gb >= 4:
        checks.append(DoctorCheck("Memory", "OK", f"Detected {total_ram_gb:.1f} GB RAM."))
    else:
        checks.append(DoctorCheck("Memory", "WARN", f"Only {total_ram_gb:.1f} GB RAM detected."))

    required_files: tuple[str, ...] = ()
    if config.tts.engine in {"kokoro", "kokoro_onnx", "onnx"}:
        required_files = (config.tts.onnx_model_file, config.tts.onnx_voices_file)
    cache_status = model_cache_status(config.tts.model_id, required_files=required_files)
    if cache_status.path is None:
        checks.append(
            DoctorCheck(
                "Model cache",
                "WARN",
                "Model cache not found; first run will download weights.",
            )
        )
    elif cache_status.missing_files:
        missing = ", ".join(cache_status.missing_files)
        checks.append(
            DoctorCheck(
                "Model cache",
                "WARN",
                f"Model cache present at {cache_status.path}, but missing file(s): {missing}.",
            )
        )
    else:
        checks.append(DoctorCheck("Model cache", "OK", f"Model cache present at {cache_status.path}."))

    checks.append(DoctorCheck("Platform", "OK", f"{platform.platform()}"))
    migration_note = _migration_note(config)
    if migration_note is not None:
        source = config.source
        if source is None or source not in _MIGRATION_NOTE_EMITTED:
            checks.append(DoctorCheck("Migration", "WARN", migration_note))
            if source is not None:
                _MIGRATION_NOTE_EMITTED.add(source)

    return checks


def _run_smoke_test(config: Config, options: DoctorOptions, logger: logging.Logger) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    output_dir = options.output_dir or config.paths.cache / "doctor"
    ensure_dir(output_dir)

    engine = _build_engine(config, output_dir)
    settings = _build_settings(config)

    text = options.text or "Hello world."

    start = time.time()
    try:
        chunks = synthesize_text(
            text,
            engine,
            settings,
            segmenter=BasicTextSegmenter(max_chars=settings.max_chars, min_chars=settings.min_chars),
            logger=logger,
        )
    except TtsModelError as exc:
        checks.append(DoctorCheck("Smoke test", "FAIL", f"Model load failed: {exc}"))
        return checks
    except TtsError as exc:
        checks.append(DoctorCheck("Smoke test", "FAIL", f"Synthesis failed: {exc}"))
        return checks

    elapsed = time.time() - start
    if not chunks:
        checks.append(DoctorCheck("Smoke test", "FAIL", "No audio produced."))
        return checks

    path = chunks[0].path
    if not path.exists() or path.stat().st_size == 0:
        checks.append(DoctorCheck("Smoke test", "FAIL", f"Audio file missing or empty: {path}"))
        return checks

    if _is_valid_wav(path):
        checks.append(DoctorCheck("Smoke test", "OK", f"Audio generated in {elapsed:.2f}s at {path}."))
    else:
        checks.append(DoctorCheck("Smoke test", "WARN", "Audio generated but WAV header invalid."))

    checks.extend(_check_audio_format(path, config))
    checks.extend(_check_audio_physiology(path))
    return checks


def _run_rtf_test(config: Config, options: DoctorOptions, logger: logging.Logger) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    output_dir = options.output_dir or config.paths.cache / "doctor"
    ensure_dir(output_dir)

    engine = _build_engine(config, output_dir)
    settings = _build_settings(config)

    text = options.text or "Hello world."

    start = time.time()
    try:
        chunks = synthesize_text(text, engine, settings, logger=logger)
    except TtsError as exc:
        checks.append(DoctorCheck("RTF", "FAIL", f"Synthesis failed: {exc}"))
        return checks

    elapsed = time.time() - start
    duration = _audio_duration_seconds(chunks)
    if duration is None or duration <= 0:
        checks.append(DoctorCheck("RTF", "WARN", "Unable to compute audio duration."))
        return checks

    rtf = elapsed / duration
    status = "OK" if rtf < 1.0 else "WARN"
    checks.append(DoctorCheck("RTF", status, f"RTF {rtf:.2f} (elapsed {elapsed:.2f}s, audio {duration:.2f}s)."))
    return checks


def _run_long_text_test(config: Config, options: DoctorOptions, logger: logging.Logger) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    output_dir = options.output_dir or config.paths.cache / "doctor"
    ensure_dir(output_dir)

    engine = _build_engine(config, output_dir)
    settings = _build_settings(config)

    long_text = ("This is a long test sentence. " * 80).strip()

    try:
        chunks = synthesize_text(long_text, engine, settings, logger=logger)
    except TtsError as exc:
        checks.append(DoctorCheck("Long text", "FAIL", f"Synthesis failed: {exc}"))
        return checks

    if len(chunks) < 2:
        checks.append(DoctorCheck("Long text", "WARN", "Long text did not split into multiple chunks."))
    else:
        checks.append(DoctorCheck("Long text", "OK", f"Long text split into {len(chunks)} chunk(s)."))
    return checks


def _build_engine(config: Config, output_dir: Path) -> TtsEngine:
    return build_tts_engine(config, output_dir)


def _build_settings(config: Config) -> TtsSynthesisSettings:
    ref_audio_id = _ref_audio_cache_id(config.tts.ref_audio)
    return TtsSynthesisSettings(
        model_id=f"{config.tts.engine}:{config.tts.model_id}",
        max_chars=config.tts.max_chars,
        min_chars=config.tts.min_chars,
        hard_max_chars=config.tts.hard_max_chars,
        max_retries=config.tts.max_retries,
        backoff_base=config.tts.backoff_base,
        backoff_jitter=config.tts.backoff_jitter,
        sample_rate=config.tts.sample_rate,
        channels=config.tts.channels,
        speed=config.tts.speed,
        lang_code=config.tts.lang_code,
        ref_audio=config.tts.ref_audio,
        ref_text=config.tts.ref_text,
        ref_audio_id=ref_audio_id,
    )


def _ref_audio_cache_id(ref_audio: Path | None) -> str | None:
    if ref_audio is None:
        return None
    try:
        stat = ref_audio.stat()
        return f"{ref_audio}:{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        return str(ref_audio)


def _check_metal() -> bool | None:
    try:
        import mlx.core as mx  # type: ignore
    except ImportError:
        return None

    metal = getattr(mx, "metal", None)
    if metal is None or not hasattr(metal, "is_available"):
        return None
    try:
        return bool(metal.is_available())
    except Exception:
        return None


def _total_ram_gb() -> float | None:
    try:
        import psutil  # type: ignore

        return psutil.virtual_memory().total / (1024**3)
    except ImportError:
        pass

    try:
        import os

        page_size = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        return (page_size * pages) / (1024**3)
    except (OSError, ValueError, AttributeError):
        return None


def _migration_note(config: Config) -> str | None:
    if config.source is None or not config.source.exists():
        return None

    try:
        import tomllib  # type: ignore
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore
        except ModuleNotFoundError:
            return None

    try:
        with config.source.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, ValueError):
        return None

    tts = raw.get("tts")
    if not isinstance(tts, dict):
        return "Using new default TTS engine 'kokoro_onnx' because [tts] section is missing."

    missing = [key for key in ("engine", "model_id") if key not in tts]
    if missing:
        joined = ", ".join(missing)
        return f"Using new defaults for missing [tts] key(s): {joined}."
    return None


def _is_valid_wav(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnchannels() > 0
    except wave.Error:
        return False


def _check_audio_format(path: Path, config: Config) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    try:
        with wave.open(str(path), "rb") as handle:
            rate = handle.getframerate()
            channels = handle.getnchannels()
    except wave.Error as exc:
        checks.append(DoctorCheck("Format", "WARN", f"Unable to read WAV header: {exc}"))
        return checks

    if rate == config.tts.sample_rate and channels == config.tts.channels:
        checks.append(DoctorCheck("Format", "OK", f"{rate} Hz, {channels} channel(s)."))
    else:
        checks.append(
            DoctorCheck(
                "Format",
                "WARN",
                f"Expected {config.tts.sample_rate} Hz/{config.tts.channels} ch, got {rate} Hz/{channels} ch.",
            )
        )
    return checks


def _check_audio_physiology(path: Path) -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
            width = handle.getsampwidth()
            channels = handle.getnchannels()
    except wave.Error as exc:
        checks.append(DoctorCheck("Audio quality", "WARN", f"Unable to read audio: {exc}"))
        return checks

    if width != 2:
        checks.append(DoctorCheck("Audio quality", "WARN", "Non-16-bit audio; clipping analysis skipped."))
        return checks

    import array

    pcm = array.array("h")
    pcm.frombytes(frames)
    if not pcm:
        checks.append(DoctorCheck("Audio quality", "WARN", "Empty audio frames."))
        return checks

    max_amp = max(abs(sample) for sample in pcm)
    if max_amp >= 32000:
        checks.append(DoctorCheck("Audio quality", "WARN", "Potential clipping detected."))
    else:
        checks.append(DoctorCheck("Audio quality", "OK", "No clipping detected."))

    return checks


def _audio_duration_seconds(chunks: Iterable) -> float | None:
    total = 0.0
    for chunk in chunks:
        duration_ms = getattr(chunk, "duration_ms", None)
        if duration_ms is None:
            duration_ms = _wav_duration_ms(chunk.path)
        if duration_ms is None:
            return None
        total += duration_ms / 1000.0
    return total


def _wav_duration_ms(path: Path) -> int | None:
    try:
        with wave.open(str(path), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
        if rate <= 0:
            return None
        return int((frames / rate) * 1000)
    except (wave.Error, OSError):
        return None


def _render_report(checks: Sequence[DoctorCheck]) -> str:
    lines = ["epub2audio doctor", ""]
    for check in checks:
        lines.append(f"[{check.status}] {check.name}: {check.detail}")
    return "\n".join(lines)
