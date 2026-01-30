"""TTS engine implementations and error taxonomy."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import hashlib
import logging
import re
import wave
from typing import Iterable, Mapping

from .interfaces import AudioChunk, TtsEngine
from .utils import ensure_dir

_LOGGER = logging.getLogger(__name__)


class TtsError(RuntimeError):
    """Base class for TTS failures."""


class TtsInputError(TtsError):
    """Raised when input text is empty or non-speech."""


class TtsSizeError(TtsError):
    """Raised when input text exceeds model constraints."""


class TtsTransientError(TtsError):
    """Raised for transient runtime failures worth retrying."""


class TtsModelError(TtsError):
    """Raised when the model cannot be loaded or initialized."""


@dataclass
class MlxTtsEngine(TtsEngine):
    model_id: str
    output_dir: Path
    sample_rate: int = 24000
    channels: int = 1
    voice: str | None = None
    lang_code: str | None = None
    speed: float = 1.0
    max_input_chars: int | None = None

    _model: object | None = field(default=None, init=False, repr=False)
    _tts: object | None = field(default=None, init=False, repr=False)

    def ensure_loaded(self) -> None:
        if self._model is not None or self._tts is not None:
            return

        try:
            from mlx_audio.tts.utils import load_model  # type: ignore
        except ImportError:
            load_model = None

        if load_model is not None:
            try:
                self._model = load_model(self.model_id)
                _LOGGER.info("Loaded MLX Audio model %s", self.model_id)
                return
            except Exception as exc:  # pragma: no cover - runtime dependency
                raise TtsModelError(f"Failed to load MLX Audio model: {exc}") from exc

        try:
            from mlx_audio.tts import TextToSpeech  # type: ignore
        except ImportError as exc:
            raise TtsModelError(
                "mlx-audio is not installed. Install with `pip install mlx mlx-audio huggingface_hub`."
            ) from exc

        try:
            self._tts = TextToSpeech.from_pretrained(self.model_id)
            _LOGGER.info("Loaded MLX Audio TextToSpeech model %s", self.model_id)
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise TtsModelError(f"Failed to load MLX Audio TextToSpeech model: {exc}") from exc

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

        cfg = config or {}
        resolved_voice = _coerce_optional_str(cfg.get("voice")) or voice or self.voice
        resolved_lang = _coerce_optional_str(cfg.get("lang_code")) or self.lang_code
        resolved_speed = _coerce_float(cfg.get("speed"), self.speed)
        sample_rate = _coerce_int(cfg.get("sample_rate"), self.sample_rate)
        channels = _coerce_int(cfg.get("channels"), self.channels)

        ensure_dir(self.output_dir)
        output_path = cfg.get("output_path")
        if output_path is None:
            chunk_id = _chunk_id(
                text,
                model_id=self.model_id,
                voice=resolved_voice,
                lang_code=resolved_lang,
                speed=resolved_speed,
                sample_rate=sample_rate,
                channels=channels,
            )
            output_path = self.output_dir / f"{chunk_id}.wav"
        else:
            output_path = Path(str(output_path))

        if output_path.exists() and output_path.stat().st_size > 0:
            duration_ms = _wav_duration_ms(output_path)
            return AudioChunk(index=0, path=output_path, duration_ms=duration_ms)

        self.ensure_loaded()

        try:
            if self._model is not None:
                audio, detected_channels = _generate_with_model(
                    self._model,
                    text,
                    voice=resolved_voice,
                    lang_code=resolved_lang,
                    speed=resolved_speed,
                )
            elif self._tts is not None:
                audio, detected_channels = _generate_with_tts(
                    self._tts,
                    text,
                    voice=resolved_voice,
                    lang_code=resolved_lang,
                    speed=resolved_speed,
                )
            else:  # pragma: no cover - defensive
                raise TtsModelError("No MLX Audio model loaded.")
        except TtsError:
            raise
        except Exception as exc:  # pragma: no cover - runtime dependency
            raise TtsTransientError(f"TTS synthesis failed: {exc}") from exc

        if not audio:
            raise TtsTransientError("TTS synthesis returned empty audio.")

        if detected_channels and detected_channels != channels:
            _LOGGER.warning(
                "Detected %d channel(s) from model output; overriding configured %d.",
                detected_channels,
                channels,
            )
            channels = detected_channels

        _write_wav(output_path, audio, sample_rate=sample_rate, channels=channels)
        duration_ms = _wav_duration_ms(output_path)
        return AudioChunk(index=0, path=output_path, duration_ms=duration_ms)

def _generate_with_model(model: object, text: str, **kwargs: object) -> tuple[list[float], int]:
    try:
        import mlx.core as mx  # type: ignore
    except ImportError as exc:  # pragma: no cover - runtime dependency
        raise TtsModelError("mlx is not installed. Install with `pip install mlx`. ") from exc

    generate = getattr(model, "generate", None)
    if generate is None:
        raise TtsModelError("Loaded model does not expose generate().")

    accepted = _accepted_kwargs(generate)
    filtered = {key: value for key, value in kwargs.items() if key in accepted and value is not None}
    results: Iterable[object] = generate(text, **filtered)

    segments: list[object] = []
    for result in results:
        audio = getattr(result, "audio", result)
        segments.append(audio)

    if not segments:
        return [], 0

    if len(segments) == 1:
        combined = segments[0]
    else:
        combined = mx.concatenate([mx.array(seg) for seg in segments])

    audio_list = _to_list(combined)
    return _normalize_audio_list(audio_list)


def _generate_with_tts(tts: object, text: str, **kwargs: object) -> tuple[list[float], int]:
    synth = getattr(tts, "synthesize", None)
    if synth is None:
        raise TtsModelError("Loaded TextToSpeech model does not expose synthesize().")

    accepted = _accepted_kwargs(synth)
    filtered = {key: value for key, value in kwargs.items() if key in accepted and value is not None}
    audio = synth(text, **filtered)
    if isinstance(audio, tuple) and len(audio) == 2:
        audio = audio[0]
    audio_list = _to_list(audio)
    return _normalize_audio_list(audio_list)


def _accepted_kwargs(func: object) -> set[str]:
    try:
        import inspect

        return set(inspect.signature(func).parameters)
    except (ValueError, TypeError):
        return set()


def _to_list(audio: object) -> list[object]:
    if hasattr(audio, "tolist"):
        return audio.tolist()  # type: ignore[return-value]
    try:
        return list(audio)  # type: ignore[arg-type]
    except TypeError:
        return [audio]


def _normalize_audio_list(audio_list: list[object]) -> tuple[list[float], int]:
    if not audio_list:
        return [], 0

    if isinstance(audio_list[0], (int, float)):
        return [float(value) for value in audio_list], 1

    if isinstance(audio_list[0], list):
        # Try channels-first then samples-first shapes
        if audio_list and all(isinstance(item, list) for item in audio_list):
            first = audio_list[0]
            if first and all(isinstance(item, (int, float)) for item in first):
                channels_first = all(len(item) == len(first) for item in audio_list)
                if channels_first:
                    channels = len(audio_list)
                    samples = len(first)
                    interleaved: list[float] = []
                    for idx in range(samples):
                        for ch in range(channels):
                            interleaved.append(float(audio_list[ch][idx]))
                    return interleaved, channels

                # Treat as samples-first
                channels = len(first)
                interleaved = []
                for frame in audio_list:
                    for value in frame:
                        interleaved.append(float(value))
                return interleaved, channels

    # Fallback: flatten anything else
    flattened: list[float] = []
    for value in audio_list:
        try:
            flattened.append(float(value))
        except (TypeError, ValueError):
            continue
    return flattened, 1


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
        if isinstance(value, (int,)):
            clipped = max(-32768, min(32767, value))
        else:
            clipped = int(max(-1.0, min(1.0, float(value))) * 32767)
        pcm.append(clipped)
    return pcm.tobytes()


def _chunk_id(
    text: str,
    *,
    model_id: str,
    voice: str | None,
    lang_code: str | None,
    speed: float,
    sample_rate: int,
    channels: int,
) -> str:
    payload = "|".join(
        [
            model_id,
            voice or "",
            lang_code or "",
            f"{speed:.3f}",
            str(sample_rate),
            str(channels),
            text,
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"tts_{digest[:16]}"


def _is_speakable_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.fullmatch(r"[\W_]+", stripped):
        return False
    return True


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
