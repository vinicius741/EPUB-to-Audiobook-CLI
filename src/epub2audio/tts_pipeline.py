"""Chunk synthesis pipeline with retry and split logic."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from pathlib import Path
from typing import Callable

from .audio_cache import AudioCacheLayout, chunk_cache_key
from .interfaces import AudioChunk, Segment, TextSegmenter, TtsEngine
from .text_segmenter import BasicTextSegmenter
from .tts_engine import TtsError, TtsInputError, TtsSizeError, TtsTransientError
from .utils import ensure_dir

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TtsSynthesisSettings:
    model_id: str
    max_chars: int
    min_chars: int
    hard_max_chars: int | None
    max_retries: int
    backoff_base: float
    backoff_jitter: float
    sample_rate: int
    channels: int
    speed: float
    lang_code: str | None
    ref_audio: Path | None
    ref_text: str | None
    ref_audio_id: str | None


def synthesize_text(
    text: str,
    engine: TtsEngine,
    settings: TtsSynthesisSettings,
    *,
    segmenter: TextSegmenter | None = None,
    voice: str | None = None,
    output_dir: Path | None = None,
    cache: AudioCacheLayout | None = None,
    output_format: str = "wav",
    logger: logging.Logger | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> list[AudioChunk]:
    logger = logger or _LOGGER
    if not text:
        return []

    segmenter = segmenter or BasicTextSegmenter(
        max_chars=settings.max_chars,
        min_chars=settings.min_chars,
        hard_max_chars=settings.hard_max_chars,
    )

    if output_dir is not None:
        ensure_dir(output_dir)

    segments = list(segmenter.segment(text))
    audio_chunks: list[AudioChunk] = []
    for segment in segments:
        audio_chunks.extend(
            _synthesize_with_retry(
                segment,
                engine,
                settings,
                voice=voice,
                lang_code=settings.lang_code,
                logger=logger,
                sleep_fn=sleep_fn,
                cache=cache,
                output_dir=output_dir,
                output_format=output_format,
            )
        )
    return audio_chunks


def _synthesize_with_retry(
    segment: Segment,
    engine: TtsEngine,
    settings: TtsSynthesisSettings,
    *,
    voice: str | None,
    lang_code: str | None,
    logger: logging.Logger,
    sleep_fn: Callable[[float], None],
    depth: int = 0,
    cache: AudioCacheLayout | None = None,
    output_dir: Path | None = None,
    output_format: str = "wav",
) -> list[AudioChunk]:
    text = segment.text
    if len(text) > settings.max_chars:
        return _split_and_synthesize(
            text,
            engine,
            settings,
            voice,
            lang_code,
            logger,
            sleep_fn,
            depth,
            cache=cache,
            output_dir=output_dir,
            output_format=output_format,
        )

    attempts = 0
    while True:
        try:
            resolved_voice = voice or getattr(engine, "voice", None)
            resolved_lang = lang_code or getattr(engine, "lang_code", None)
            engine_config = {
                "speed": settings.speed,
                "lang_code": resolved_lang,
                "sample_rate": settings.sample_rate,
                "channels": settings.channels,
                "ref_audio": settings.ref_audio,
                "ref_text": settings.ref_text,
                "ref_audio_id": settings.ref_audio_id,
            }
            output_path = _resolve_output_path(
                text,
                settings,
                resolved_voice,
                resolved_lang,
                cache=cache,
                output_dir=output_dir,
                output_format=output_format,
            )
            if output_path is not None:
                engine_config["output_path"] = output_path
            chunk = engine.synthesize(text, voice=voice, config=engine_config)
            return [chunk]
        except TtsInputError as exc:
            logger.warning("Skipping chunk %d: %s", segment.index, exc)
            return []
        except TtsSizeError:
            return _split_and_synthesize(
                text,
                engine,
                settings,
                voice,
                lang_code,
                logger,
                sleep_fn,
                depth,
                cache=cache,
                output_dir=output_dir,
                output_format=output_format,
            )
        except TtsTransientError as exc:
            if attempts >= settings.max_retries:
                raise
            delay = _backoff_delay(attempts, settings.backoff_base, settings.backoff_jitter)
            logger.warning("Transient TTS error on chunk %d: %s. Retrying in %.2fs", segment.index, exc, delay)
            sleep_fn(delay)
            attempts += 1
        except TtsError:
            raise


def _split_and_synthesize(
    text: str,
    engine: TtsEngine,
    settings: TtsSynthesisSettings,
    voice: str | None,
    lang_code: str | None,
    logger: logging.Logger,
    sleep_fn: Callable[[float], None],
    depth: int,
    *,
    cache: AudioCacheLayout | None,
    output_dir: Path | None,
    output_format: str,
) -> list[AudioChunk]:
    if depth > 8:
        raise TtsSizeError("Maximum split depth exceeded.")

    pieces = _split_text(text, settings)
    if not pieces:
        raise TtsSizeError("Unable to split text for synthesis.")

    chunks: list[AudioChunk] = []
    for idx, piece in enumerate(pieces):
        segment = Segment(index=idx, text=piece)
        chunks.extend(
            _synthesize_with_retry(
                segment,
                engine,
                settings,
                voice=voice,
                lang_code=lang_code,
                logger=logger,
                sleep_fn=sleep_fn,
                depth=depth + 1,
                cache=cache,
                output_dir=output_dir,
                output_format=output_format,
            )
        )
    return chunks


def _split_text(text: str, settings: TtsSynthesisSettings) -> list[str]:
    splitter = BasicTextSegmenter(
        max_chars=settings.max_chars,
        min_chars=settings.min_chars,
        hard_max_chars=settings.hard_max_chars,
    )
    segments = [segment.text for segment in splitter.segment(text)]
    if len(segments) > 1:
        return segments

    return _hard_split(text, settings.max_chars)


def _hard_split(text: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    current = text.strip()
    while current:
        piece = current[:max_chars].strip()
        if piece:
            pieces.append(_ensure_terminal_punctuation(piece))
        current = current[max_chars:].strip()
    return pieces


def _ensure_terminal_punctuation(text: str) -> str:
    if text and text[-1] in ".!?;:)]\"'":
        return text
    return f"{text}."


def _backoff_delay(attempt: int, base: float, jitter: float) -> float:
    delay = base * (2**attempt)
    if jitter <= 0:
        return delay
    return delay + (delay * jitter)


def _resolve_output_path(
    text: str,
    settings: TtsSynthesisSettings,
    resolved_voice: str | None,
    resolved_lang: str | None,
    *,
    cache: AudioCacheLayout | None,
    output_dir: Path | None,
    output_format: str,
) -> Path | None:
    if cache is None and output_dir is None:
        return None
    key = chunk_cache_key(
        text,
        model_id=settings.model_id,
        voice=resolved_voice,
        lang_code=resolved_lang,
        ref_audio_id=settings.ref_audio_id,
        ref_text=settings.ref_text,
        speed=settings.speed,
        sample_rate=settings.sample_rate,
        channels=settings.channels,
    )
    if cache is not None:
        cache.ensure_chunk_dir(key)
        return cache.chunk_path(key, ext=output_format)
    ensure_dir(output_dir)  # type: ignore[arg-type]
    return Path(output_dir) / f"{key}.{output_format}"
