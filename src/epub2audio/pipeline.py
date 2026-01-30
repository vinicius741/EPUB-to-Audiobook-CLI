"""Pipeline orchestration for EPUB -> chapter audio (Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Iterable, Sequence

from .audio_cache import AudioCacheLayout
from .audio_processing import FfmpegAudioProcessor, LoudnessConfig
from .config import Config
from .epub_reader import EbooklibEpubReader
from .interfaces import AudioChunk, Chapter, EpubBook
from .logging_setup import LoggingContext
from .text_cleaner import BasicTextCleaner
from .text_segmenter import BasicTextSegmenter
from .tts_engine import MlxTtsEngine, TtsError, TtsModelError
from .tts_pipeline import TtsSynthesisSettings, synthesize_text
from .utils import ensure_dir, slugify



@dataclass(frozen=True)
class BookResult:
    source: Path
    book_slug: str
    status: str
    message: str


@dataclass(frozen=True)
class ChapterResult:
    chapter_index: int
    status: str  # "ok", "empty", "failed"
    output_paths: tuple[Path, ...]


def run_pipeline(
    log_ctx: LoggingContext,
    inputs: Sequence[Path],
    config: Config,
) -> list[BookResult]:
    results: list[BookResult] = []
    reader = EbooklibEpubReader()
    cleaner = BasicTextCleaner()
    segmenter = BasicTextSegmenter(
        max_chars=config.tts.max_chars,
        min_chars=config.tts.min_chars,
        hard_max_chars=config.tts.hard_max_chars,
    )
    engine = _build_engine(config)
    settings = _build_settings(config)
    cache = AudioCacheLayout(config.paths.cache)
    output_format = _resolve_output_format(config, log_ctx.logger)
    audio_processor = FfmpegAudioProcessor(
        work_dir=ensure_dir(config.paths.cache / "work"),
        sample_rate=config.tts.sample_rate,
        channels=config.tts.channels,
        loudness=LoudnessConfig(
            target_lufs=config.audio.target_lufs,
            lra=config.audio.lra,
            true_peak=config.audio.true_peak,
        ),
    )

    sources = _expand_inputs(inputs)
    for source in sources:
        book_slug = slugify(source.stem if source.suffix else source.name)
        book_logger = log_ctx.get_book_logger(book_slug)
        if not source.exists():
            message = f"Input not found: {source}"
            book_logger.warning(message)
            results.append(BookResult(source=source, book_slug=book_slug, status="missing", message=message))
            continue

        try:
            book = reader.read(source)
        except Exception as exc:
            message = f"Failed to read EPUB: {exc}"
            book_logger.error(message)
            results.append(BookResult(source=source, book_slug=book_slug, status="failed", message=message))
            continue

        book_slug = slugify(book.metadata.title or book_slug)
        book_logger = log_ctx.get_book_logger(book_slug)
        book_logger.info("Processing %s with %d chapter(s)", book.metadata.title, len(book.chapters))

        try:
            chapter_results = _process_book(
                book,
                book_slug,
                cache,
                cleaner,
                segmenter,
                engine,
                settings,
                audio_processor,
                config,
                output_format,
                book_logger,
            )
        except Exception as exc:
            message = f"Failed during audio pipeline: {exc}"
            book_logger.error(message)
            results.append(BookResult(source=source, book_slug=book_slug, status="failed", message=message))
            continue

        ok_count = sum(1 for r in chapter_results if r.status == "ok")
        empty_count = sum(1 for r in chapter_results if r.status == "empty")
        failed_count = sum(1 for r in chapter_results if r.status == "failed")
        message = f"Generated {ok_count} chapter(s), {empty_count} empty, {failed_count} failed."
        results.append(BookResult(source=source, book_slug=book_slug, status="ok", message=message))

    return results


def resolve_inputs(inputs: Iterable[Path]) -> list[Path]:
    resolved: list[Path] = []
    for path in inputs:
        expanded = path.expanduser()
        try:
            resolved.append(expanded.resolve())
        except FileNotFoundError:
            resolved.append(expanded)
    return resolved


def _expand_inputs(inputs: Sequence[Path]) -> list[Path]:
    expanded: list[Path] = []
    for path in inputs:
        if path.is_dir():
            expanded.extend(sorted(path.glob("*.epub")))
        else:
            expanded.append(path)
    return expanded


def _build_engine(config: Config) -> MlxTtsEngine:
    if config.tts.engine != "mlx":
        raise TtsModelError(f"Unsupported TTS engine '{config.tts.engine}'.")
    output_dir = ensure_dir(config.paths.cache / "tts")
    return MlxTtsEngine(
        model_id=config.tts.model_id,
        output_dir=output_dir,
        sample_rate=config.tts.sample_rate,
        channels=config.tts.channels,
        voice=config.tts.voice,
        lang_code=config.tts.lang_code,
        speed=config.tts.speed,
        max_input_chars=config.tts.max_chars,
    )


def _build_settings(config: Config) -> TtsSynthesisSettings:
    return TtsSynthesisSettings(
        model_id=config.tts.model_id,
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
    )


def _resolve_output_format(config: Config, logger: logging.Logger) -> str:
    fmt = config.tts.output_format.lower()
    if fmt != "wav":
        logger.warning("Only WAV output is supported; using wav instead of %s.", fmt)
        return "wav"
    return fmt


def _process_book(
    book: EpubBook,
    book_slug: str,
    cache: AudioCacheLayout,
    cleaner: BasicTextCleaner,
    segmenter: BasicTextSegmenter,
    engine: MlxTtsEngine,
    settings: TtsSynthesisSettings,
    audio_processor: FfmpegAudioProcessor,
    config: Config,
    output_format: str,
    logger: logging.Logger,
) -> list[ChapterResult]:
    cache.ensure_chapter_dir(book_slug)
    chapter_results: list[ChapterResult] = []
    for chapter in book.chapters:
        chapter_results.append(
            _process_chapter(
                chapter,
                book_slug,
                cache,
                cleaner,
                segmenter,
                engine,
                settings,
                audio_processor,
                config,
                output_format,
                logger,
            )
        )
    return chapter_results


def _process_chapter(
    chapter: Chapter,
    book_slug: str,
    cache: AudioCacheLayout,
    cleaner: BasicTextCleaner,
    segmenter: BasicTextSegmenter,
    engine: MlxTtsEngine,
    settings: TtsSynthesisSettings,
    audio_processor: FfmpegAudioProcessor,
    config: Config,
    output_format: str,
    logger: logging.Logger,
) -> ChapterResult:
    cleaned = cleaner.clean(chapter.text)
    if not cleaned:
        logger.warning("Chapter %d is empty after cleaning; skipping.", chapter.index)
        return ChapterResult(chapter_index=chapter.index, status="empty", output_paths=())

    stitched_path = cache.chapter_path(book_slug, chapter.index, "stitched")
    normalized_path = stitched_path.with_name(f"{stitched_path.stem}.normalized.wav")
    if config.audio.normalize and normalized_path.exists() and normalized_path.stat().st_size > 0:
        return ChapterResult(chapter_index=chapter.index, status="ok", output_paths=(normalized_path,))
    if not config.audio.normalize and stitched_path.exists() and stitched_path.stat().st_size > 0:
        return ChapterResult(chapter_index=chapter.index, status="ok", output_paths=(stitched_path,))

    try:
        chunks = synthesize_text(
            cleaned,
            engine,
            settings,
            segmenter=segmenter,
            voice=config.tts.voice,
            cache=cache,
            output_format=output_format,
            logger=logger,
        )
    except TtsError as exc:
        logger.error("TTS failed for chapter %d: %s", chapter.index, exc)
        return ChapterResult(chapter_index=chapter.index, status="failed", output_paths=())

    if not chunks:
        logger.warning("No audio chunks generated for chapter %d.", chapter.index)
        return ChapterResult(chapter_index=chapter.index, status="empty", output_paths=())

    processed_chunks: Sequence[AudioChunk] = chunks
    if config.audio.silence_ms > 0:
        processed_chunks = audio_processor.insert_silence(chunks, config.audio.silence_ms)

    audio_processor.stitch(processed_chunks, stitched_path)

    if not config.audio.normalize:
        return ChapterResult(chapter_index=chapter.index, status="ok", output_paths=(stitched_path,))

    normalized = audio_processor.normalize([AudioChunk(index=0, path=stitched_path)])
    return ChapterResult(chapter_index=chapter.index, status="ok", output_paths=(normalized[0].path,))
