"""Kokoro ONNX TTS engine implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
import inspect
import logging
from pathlib import Path
import re
from typing import Mapping
import wave

from .audio_cache import chunk_cache_key
from .interfaces import AudioChunk, TtsEngine
from .onnx_provider import resolve_onnx_provider_chain
from .tts_engine import TtsInputError, TtsModelError, TtsSizeError, TtsTransientError
from .utils import ensure_dir

_LOGGER = logging.getLogger(__name__)


@dataclass
class KokoroOnnxTtsEngine(TtsEngine):
    model_id: str
    output_dir: Path
    sample_rate: int = 24000
    channels: int = 1
    voice: str | None = "af_heart"
    lang_code: str | None = None
    speed: float = 1.0
    max_input_chars: int | None = None
    max_input_tokens: int = 510
    execution_provider: str = "auto"
    onnx_model_file: str = "model_q8f16.onnx"
    onnx_voices_file: str = "voices-v1.0.bin"

    _kokoro: object | None = field(default=None, init=False, repr=False)
    _provider_chain: tuple[str, ...] = field(default=tuple(), init=False, repr=False)
    _model_path: Path | None = field(default=None, init=False, repr=False)
    _voices_path: Path | None = field(default=None, init=False, repr=False)

    def ensure_loaded(self) -> None:
        if self._kokoro is not None:
            return

        try:
            from huggingface_hub import hf_hub_download  # type: ignore
        except ImportError as exc:
            raise TtsModelError(
                "huggingface_hub is required for Kokoro ONNX. Install with `pip install -e '.[tts-kokoro]'`."
            ) from exc

        try:
            from kokoro_onnx import Kokoro  # type: ignore
        except ImportError as exc:
            raise TtsModelError(
                "kokoro-onnx is not installed. Install with `pip install -e '.[tts-kokoro]'`."
            ) from exc

        providers = resolve_onnx_provider_chain(self.execution_provider)
        self._provider_chain = tuple(providers)
        try:
            self._model_path = Path(
                hf_hub_download(
                    repo_id=self.model_id,
                    filename=self.onnx_model_file,
                )
            )
            self._voices_path = Path(
                hf_hub_download(
                    repo_id=self.model_id,
                    filename=self.onnx_voices_file,
                )
            )
        except Exception as exc:  # pragma: no cover - depends on network/cache state
            raise TtsModelError(
                f"Failed to download Kokoro model assets from Hugging Face: {exc}"
            ) from exc

        try:
            self._kokoro = _build_kokoro_runtime(
                Kokoro,
                model_path=self._model_path,
                voices_path=self._voices_path,
                providers=providers,
            )
            _LOGGER.info(
                "Loaded Kokoro ONNX model %s (%s).",
                self.model_id,
                ", ".join(self._provider_chain) if self._provider_chain else "provider unknown",
            )
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise TtsModelError(f"Failed to initialize kokoro-onnx runtime: {exc}") from exc

    def runtime_info(self) -> dict[str, object]:
        return {
            "engine": "kokoro_onnx",
            "requested_execution_provider": self.execution_provider,
            "resolved_providers": list(self._provider_chain),
            "model_id": self.model_id,
            "model_path": str(self._model_path) if self._model_path is not None else None,
            "voices_path": str(self._voices_path) if self._voices_path is not None else None,
            "onnx_model_file": self.onnx_model_file,
            "onnx_voices_file": self.onnx_voices_file,
        }

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        config: Mapping[str, object] | None = None,
    ) -> AudioChunk:
        text = text or ""
        if not _is_speakable_text(text):
            raise TtsInputError("Input text is empty or contains no speakable content.")

        if self.max_input_chars is not None and len(text) > self.max_input_chars:
            raise TtsSizeError(f"Input length {len(text)} exceeds max {self.max_input_chars} chars.")

        estimated_tokens = _estimate_tokens(text)
        if estimated_tokens > self.max_input_tokens:
            raise TtsSizeError(
                f"Estimated token count {estimated_tokens} exceeds max {self.max_input_tokens} tokens."
            )

        cfg = config or {}
        resolved_voice = _coerce_optional_str(cfg.get("voice")) or voice or self.voice or "af_heart"
        resolved_lang = _coerce_optional_str(cfg.get("lang_code")) or self.lang_code or "en-us"
        resolved_speed = _coerce_float(cfg.get("speed"), self.speed)
        sample_rate = _coerce_int(cfg.get("sample_rate"), self.sample_rate)
        channels = _coerce_int(cfg.get("channels"), self.channels)

        ensure_dir(self.output_dir)
        output_path = cfg.get("output_path")
        if output_path is None:
            chunk_id = chunk_cache_key(
                text,
                model_id=f"kokoro_onnx:{self.model_id}:{self.onnx_model_file}",
                voice=resolved_voice,
                lang_code=resolved_lang,
                ref_audio_id=None,
                ref_text=None,
                speed=resolved_speed,
                sample_rate=sample_rate,
                channels=channels,
            )
            output_path = self.output_dir / f"{chunk_id}.wav"
        else:
            output_path = Path(str(output_path))

        if output_path.exists() and output_path.stat().st_size > 0:
            return AudioChunk(index=0, path=output_path, duration_ms=_wav_duration_ms(output_path))

        self.ensure_loaded()
        if self._kokoro is None:  # pragma: no cover - defensive
            raise TtsModelError("Kokoro runtime did not initialize.")

        try:
            audio, rate, detected_channels = _generate_audio(
                self._kokoro,
                text,
                voice=resolved_voice,
                lang_code=resolved_lang,
                speed=resolved_speed,
                sample_rate=sample_rate,
            )
        except TtsSizeError:
            raise
        except TtsModelError:
            raise
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise TtsTransientError(f"Kokoro synthesis failed: {exc}") from exc

        if not audio:
            raise TtsTransientError("Kokoro synthesis returned empty audio.")

        if detected_channels and detected_channels != channels:
            _LOGGER.warning(
                "Detected %d channel(s) from Kokoro output; overriding configured %d.",
                detected_channels,
                channels,
            )
            channels = detected_channels

        _write_wav(output_path, audio, sample_rate=rate or sample_rate, channels=channels)
        return AudioChunk(index=0, path=output_path, duration_ms=_wav_duration_ms(output_path))


def _build_kokoro_runtime(
    kokoro_cls: object,
    *,
    model_path: Path,
    voices_path: Path,
    providers: list[str],
) -> object:
    constructor = kokoro_cls
    params = _accepted_kwargs(constructor)
    kwargs: dict[str, object] = {}

    _set_first_present(params, kwargs, ("model_path", "model", "onnx_path"), str(model_path))
    _set_first_present(params, kwargs, ("voices_path", "voices", "voice_path"), str(voices_path))
    if "providers" in params:
        kwargs["providers"] = providers
    elif "provider" in params and providers:
        kwargs["provider"] = providers[0]

    try:
        return constructor(**kwargs)  # type: ignore[misc]
    except TypeError:
        # Compatibility path for runtimes requiring positional args.
        if providers:
            try:
                return constructor(str(model_path), str(voices_path), providers)  # type: ignore[misc]
            except TypeError:
                pass
        return constructor(str(model_path), str(voices_path))  # type: ignore[misc]


def _generate_audio(
    runtime: object,
    text: str,
    *,
    voice: str,
    lang_code: str,
    speed: float,
    sample_rate: int,
) -> tuple[list[float], int, int]:
    create = getattr(runtime, "create", None)
    if callable(create):
        result = _call_with_supported_kwargs(
            create,
            text=text,
            voice=voice,
            lang_code=lang_code,
            speed=speed,
            sample_rate=sample_rate,
        )
        return _extract_audio_result(result, fallback_rate=sample_rate)

    synthesize = getattr(runtime, "synthesize", None)
    if callable(synthesize):
        result = _call_with_supported_kwargs(
            synthesize,
            text=text,
            voice=voice,
            lang_code=lang_code,
            speed=speed,
            sample_rate=sample_rate,
        )
        return _extract_audio_result(result, fallback_rate=sample_rate)

    if callable(runtime):
        result = runtime(text)
        return _extract_audio_result(result, fallback_rate=sample_rate)

    raise TtsModelError("kokoro-onnx runtime does not expose create() or synthesize().")


def _call_with_supported_kwargs(func: object, **kwargs: object) -> object:
    accepted = _accepted_kwargs(func)
    payload: dict[str, object] = {}
    text = kwargs["text"]

    if "voice" in accepted and kwargs.get("voice") is not None:
        payload["voice"] = kwargs["voice"]
    if "speed" in accepted and kwargs.get("speed") is not None:
        payload["speed"] = kwargs["speed"]
    if "sample_rate" in accepted and kwargs.get("sample_rate") is not None:
        payload["sample_rate"] = kwargs["sample_rate"]

    lang_code = kwargs.get("lang_code")
    for key in ("lang", "lang_code", "language"):
        if key in accepted and lang_code is not None:
            payload[key] = lang_code
            break

    return func(text, **payload)  # type: ignore[misc]


def _extract_audio_result(result: object, *, fallback_rate: int) -> tuple[list[float], int, int]:
    audio = result
    sample_rate = fallback_rate

    if isinstance(result, tuple):
        if len(result) >= 2:
            audio = result[0]
            maybe_rate = result[1]
            if isinstance(maybe_rate, (int, float)):
                sample_rate = int(maybe_rate)
        elif len(result) == 1:
            audio = result[0]
    elif isinstance(result, dict):
        if "audio" in result:
            audio = result["audio"]
        elif "samples" in result:
            audio = result["samples"]
        elif "waveform" in result:
            audio = result["waveform"]

        maybe_rate = result.get("sample_rate") or result.get("sampling_rate") or result.get("rate")
        if isinstance(maybe_rate, (int, float)):
            sample_rate = int(maybe_rate)

    return _normalize_audio_list(_to_list(audio), sample_rate=fallback_rate if sample_rate <= 0 else sample_rate)


def _normalize_audio_list(audio_list: list[object], *, sample_rate: int) -> tuple[list[float], int, int]:
    if not audio_list:
        return [], sample_rate, 0

    if isinstance(audio_list[0], (int, float)):
        return [float(value) for value in audio_list], sample_rate, 1

    if isinstance(audio_list[0], list):
        first = audio_list[0]
        if first and all(isinstance(item, (int, float)) for item in first):
            channels_first = all(isinstance(item, list) and len(item) == len(first) for item in audio_list)
            if channels_first:
                channels = len(audio_list)
                samples = len(first)
                interleaved: list[float] = []
                for idx in range(samples):
                    for ch in range(channels):
                        interleaved.append(float(audio_list[ch][idx]))
                return interleaved, sample_rate, channels

            channels = len(first)
            interleaved = []
            for frame in audio_list:
                if not isinstance(frame, list):
                    continue
                for value in frame:
                    interleaved.append(float(value))
            return interleaved, sample_rate, channels

    flattened: list[float] = []
    for value in audio_list:
        try:
            flattened.append(float(value))
        except (TypeError, ValueError):
            continue
    return flattened, sample_rate, 1


def _accepted_kwargs(func: object) -> set[str]:
    try:
        return set(inspect.signature(func).parameters)
    except (TypeError, ValueError):
        return set()


def _set_first_present(params: set[str], payload: dict[str, object], keys: tuple[str, ...], value: object) -> None:
    for key in keys:
        if key in params:
            payload[key] = value
            return


def _to_list(audio: object) -> list[object]:
    if hasattr(audio, "tolist"):
        return audio.tolist()  # type: ignore[return-value]
    try:
        return list(audio)  # type: ignore[arg-type]
    except TypeError:
        return [audio]


def _is_speakable_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.fullmatch(r"[\W_]+", stripped):
        return False
    return True


def _estimate_tokens(text: str) -> int:
    # Conservative heuristic used for pre-split protection. Real tokenization
    # may vary by model implementation.
    return len(re.findall(r"\w+|[^\w\s]", text))


def _coerce_optional_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned or cleaned.lower() in {"none", "null"}:
            return None
        return cleaned
    return str(value)


def _coerce_float(value: object, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: object, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _write_wav(path: Path, samples: list[float], sample_rate: int, channels: int) -> None:
    pcm = _float_to_pcm16(samples)
    ensure_dir(path.parent)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(max(1, channels))
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm)


def _float_to_pcm16(samples: list[float]) -> bytes:
    import array

    pcm = array.array("h")
    for value in samples:
        if isinstance(value, int):
            clipped = max(-32768, min(32767, value))
        else:
            clipped = int(max(-1.0, min(1.0, float(value))) * 32767)
        pcm.append(clipped)
    return pcm.tobytes()


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
