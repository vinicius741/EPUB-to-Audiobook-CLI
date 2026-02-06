"""TTS engine factory and backend diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .config import Config
from .interfaces import TtsEngine
from .onnx_provider import get_available_onnx_providers, render_onnx_provider_resolution
from .tts_engine import MlxTtsEngine, TtsModelError
from .tts_engine_kokoro_onnx import KokoroOnnxTtsEngine


@dataclass(frozen=True)
class BackendDiagnostic:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class ModelCacheStatus:
    path: Path | None
    missing_files: tuple[str, ...]


def build_tts_engine(config: Config, output_dir: Path) -> TtsEngine:
    engine = (config.tts.engine or "").strip().lower()
    ref_audio_id = _ref_audio_cache_id(config.tts.ref_audio)

    if engine == "mlx":
        return MlxTtsEngine(
            model_id=config.tts.model_id,
            output_dir=output_dir,
            sample_rate=config.tts.sample_rate,
            channels=config.tts.channels,
            voice=config.tts.voice,
            lang_code=config.tts.lang_code,
            ref_audio=config.tts.ref_audio,
            ref_text=config.tts.ref_text,
            ref_audio_id=ref_audio_id,
            speed=config.tts.speed,
            max_input_chars=config.tts.max_chars,
        )

    if engine in {"kokoro", "kokoro_onnx", "onnx"}:
        return KokoroOnnxTtsEngine(
            model_id=config.tts.model_id,
            output_dir=output_dir,
            sample_rate=config.tts.sample_rate,
            channels=config.tts.channels,
            voice=config.tts.voice,
            lang_code=config.tts.lang_code,
            speed=config.tts.speed,
            max_input_chars=config.tts.max_chars,
            max_input_tokens=config.tts.max_input_tokens,
            execution_provider=config.tts.execution_provider,
            onnx_model_file=config.tts.onnx_model_file,
            onnx_voices_file=config.tts.onnx_voices_file,
        )

    raise TtsModelError(f"Unsupported TTS engine '{config.tts.engine}'.")


def backend_diagnostics(config: Config) -> list[BackendDiagnostic]:
    engine = (config.tts.engine or "").strip().lower()
    checks: list[BackendDiagnostic] = []

    if engine == "mlx":
        try:
            import mlx_audio  # type: ignore  # noqa: F401

            checks.append(BackendDiagnostic("TTS backend", "OK", "mlx-audio is available."))
        except ImportError:
            checks.append(
                BackendDiagnostic(
                    "TTS backend",
                    "FAIL",
                    "mlx-audio missing. Install with `pip install -e '.[tts-mlx]'`.",
                )
            )
        return checks

    if engine in {"kokoro", "kokoro_onnx", "onnx"}:
        try:
            import kokoro_onnx  # type: ignore  # noqa: F401

            checks.append(BackendDiagnostic("TTS backend", "OK", "kokoro-onnx is available."))
        except ImportError:
            checks.append(
                BackendDiagnostic(
                    "TTS backend",
                    "FAIL",
                    "kokoro-onnx missing. Install with `pip install -e '.[tts-kokoro]'`.",
                )
            )

        try:
            providers = get_available_onnx_providers()
            detail = ", ".join(providers) if providers else "none"
            checks.append(BackendDiagnostic("ONNX providers", "OK", f"Available providers: {detail}."))
            checks.append(
                BackendDiagnostic(
                    "Execution provider",
                    "OK",
                    render_onnx_provider_resolution(config.tts.execution_provider, available=providers),
                )
            )
        except Exception:
            checks.append(
                BackendDiagnostic(
                    "ONNX providers",
                    "FAIL",
                    "onnxruntime missing. Install with `pip install -e '.[tts-kokoro]'`.",
                )
            )
        return checks

    checks.append(BackendDiagnostic("TTS backend", "FAIL", f"Unsupported TTS engine '{config.tts.engine}'."))
    return checks


def _ref_audio_cache_id(ref_audio: Path | None) -> str | None:
    if ref_audio is None:
        return None
    try:
        stat = ref_audio.stat()
        return f"{ref_audio}:{stat.st_mtime_ns}:{stat.st_size}"
    except OSError:
        return str(ref_audio)


def model_cache_status(model_id: str, *, required_files: tuple[str, ...] = ()) -> ModelCacheStatus:
    model_dir = model_id.replace("/", "--")
    candidates: list[Path] = []

    for key in ("HUGGINGFACE_HUB_CACHE", "HF_HUB_CACHE", "HF_HOME"):
        value = os.environ.get(key)
        if not value:
            continue
        path = Path(value)
        if key == "HF_HOME":
            candidates.append(path / "hub")
        else:
            candidates.append(path)

    if not candidates:
        candidates.append(Path.home() / ".cache" / "huggingface" / "hub")

    for root in candidates:
        if not root.exists():
            continue
        direct = root / f"models--{model_dir}"
        if direct.exists():
            missing: list[str] = []
            snapshot_root = direct / "snapshots"
            if required_files:
                if not snapshot_root.exists():
                    missing.extend(required_files)
                else:
                    latest_snapshot = _latest_snapshot(snapshot_root)
                    if latest_snapshot is None:
                        missing.extend(required_files)
                    else:
                        for filename in required_files:
                            if not (latest_snapshot / filename).exists():
                                missing.append(filename)
            return ModelCacheStatus(path=direct, missing_files=tuple(missing))
    return ModelCacheStatus(path=None, missing_files=tuple(required_files))


def _latest_snapshot(snapshot_root: Path) -> Path | None:
    snapshots = [path for path in snapshot_root.iterdir() if path.is_dir()]
    if not snapshots:
        return None
    return sorted(snapshots, key=lambda path: path.stat().st_mtime_ns, reverse=True)[0]
