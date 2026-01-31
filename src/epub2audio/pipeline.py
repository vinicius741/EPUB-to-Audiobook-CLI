"""Pipeline orchestration for EPUB -> chapter audio (Phase 3)."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, wait
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import threading
import time
from typing import TYPE_CHECKING, Iterable, Sequence

from .audio_cache import AudioCacheLayout
from .audio_processing import FfmpegAudioProcessor, LoudnessConfig
from .config import Config
from .epub_reader import EbooklibEpubReader
from .error_log import ErrorCategory, ErrorEntry, ErrorLogStore, ErrorSeverity
from .interfaces import AudioChunk, Chapter, ChapterAudio, EpubBook, PipelineState
from .logging_setup import LoggingContext
from .packaging import FfmpegPackager
from .text_cleaner import BasicTextCleaner
from .text_segmenter import BasicTextSegmenter
from .tts_engine import MlxTtsEngine, TtsError, TtsModelError
from .tts_pipeline import TtsSynthesisSettings, synthesize_text
from .state_store import JsonStateStore
from .utils import ensure_dir, slugify

if TYPE_CHECKING:
    from .cli.progress import ProgressDisplay


@dataclass
class _LocalErrorLog:
    entries: list[ErrorEntry]

    def __init__(self) -> None:
        self.entries = []

    def add_error(
        self,
        category: ErrorCategory,
        severity: ErrorSeverity,
        message: str,
        *,
        step: str | None = None,
        chapter_index: int | None = None,
        details: dict | None = None,
        exc: BaseException | None = None,
    ) -> ErrorEntry:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        exception_type = type(exc).__name__ if exc is not None else None
        exception_message = str(exc) if exc is not None else None
        stack_trace = None
        if exc is not None and exc.__traceback__ is not None:
            stack_trace = "".join(
                __import__("traceback").format_exception(type(exc), exc, exc.__traceback__)
            ).strip()
        entry = ErrorEntry(
            category=category,
            severity=severity,
            message=message,
            timestamp=timestamp,
            step=step,
            chapter_index=chapter_index,
            details=details,
            exception_type=exception_type,
            exception_message=exception_message,
            stack_trace=stack_trace,
        )
        self.entries.append(entry)
        return entry


def _process_chapter_in_subprocess(
    chapter: Chapter,
    book_slug: str,
    config: Config,
    output_format: str,
) -> tuple[ChapterResult, list[ErrorEntry]]:
    logger = logging.getLogger(f"epub2audio.book.{book_slug}")
    pid = os.getpid()
    logger.info("Process %s starting chapter %d (%s).", pid, chapter.index, chapter.title)
    cache = AudioCacheLayout(config.paths.cache)
    cleaner = BasicTextCleaner()
    segmenter = BasicTextSegmenter(
        max_chars=config.tts.max_chars,
        min_chars=config.tts.min_chars,
        hard_max_chars=config.tts.hard_max_chars,
    )
    engine = _build_engine(config)
    settings = _build_settings(config)
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
    local_error_log = _LocalErrorLog()
    result = _process_chapter(
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
        local_error_log,
    )
    logger.info("Process %s completed chapter %d (%s): %s.", pid, chapter.index, chapter.title, result.status)
    return result, local_error_log.entries



@dataclass(frozen=True)
class BookResult:
    source: Path
    book_slug: str
    status: str
    message: str
    output_path: Path | None = None


@dataclass(frozen=True)
class ChapterResult:
    chapter_index: int
    status: str  # "ok", "empty", "failed"
    output_paths: tuple[Path, ...]


def run_pipeline(
    log_ctx: LoggingContext,
    inputs: Sequence[Path],
    config: Config,
    progress: "ProgressDisplay | None" = None,
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
    packager = FfmpegPackager(work_dir=ensure_dir(config.paths.cache / "packaging"))
    state_store = JsonStateStore(ensure_dir(config.paths.cache / "state"))

    sources = _expand_inputs(inputs)
    for source in sources:
        book_slug = slugify(source.stem if source.suffix else source.name)
        book_logger = log_ctx.get_book_logger(book_slug)
        error_log = log_ctx.error_log_store.get_logger(book_slug, book_slug, log_ctx.run_id)

        if not source.exists():
            message = f"Input not found: {source}"
            book_logger.warning(message)
            error_log.add_error(
                ErrorCategory.FILE_IO,
                ErrorSeverity.ERROR,
                message,
                step="input_validation",
                details={"source_path": str(source)},
            )
            log_ctx.error_log_store.save(error_log)
            results.append(BookResult(source=source, book_slug=book_slug, status="missing", message=message))
            if progress:
                progress.print_book_missing(source)
            continue

        try:
            book = reader.read(source)
        except Exception as exc:
            message = f"Failed to read EPUB: {exc}"
            book_logger.error(message)
            error_log.add_error(
                ErrorCategory.EPUB_PARSING,
                ErrorSeverity.ERROR,
                message,
                step="epub_read",
                details={"source_path": str(source)},
                exc=exc,
            )
            log_ctx.error_log_store.save(error_log)
            results.append(BookResult(source=source, book_slug=book_slug, status="failed", message=message))
            if progress:
                progress.print_book_failed(book_slug, source.name, message)
            continue

        book_slug = slugify(book.metadata.title or book_slug)
        book_logger = log_ctx.get_book_logger(book_slug)
        error_log = log_ctx.error_log_store.get_logger(book_slug, book_slug, log_ctx.run_id)
        book_logger.info("Processing %s with %d chapter(s)", book.metadata.title, len(book.chapters))
        state = _load_or_init_state(state_store, book_slug, source, book_logger)
        out_path = _resolve_output_path(config.paths.out, book_slug)

        if state.steps.get("packaged"):
            if out_path.exists():
                message = f"Already packaged: {out_path}"
                state = _state_with(
                    state,
                    artifacts={"output_m4b": str(out_path)},
                )
                _save_state(state_store, state, book_logger)
                results.append(
                    BookResult(
                        source=source,
                        book_slug=book_slug,
                        status="skipped",
                        message=message,
                        output_path=out_path,
                    )
                )
                if progress:
                    progress.print_book_skipped(book_slug, book.metadata.title or book_slug, out_path)
                _cleanup_cover_image(book.metadata.cover_image, book_logger)
                continue
            book_logger.info("State marked packaged but output missing; reprocessing.")
            state = _state_with(state, steps={"packaged": False})
            _save_state(state_store, state, book_logger)

        # Signal that we're starting to process this book
        if progress:
            progress.print_processing(book_slug, book.metadata.title or book_slug, len(book.chapters))

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
                error_log,
                progress,
            )
        except Exception as exc:
            message = f"Failed during audio pipeline: {exc}"
            book_logger.error(message)
            error_log.add_error(
                ErrorCategory.TTS_SYNTHESIS,
                ErrorSeverity.ERROR,
                message,
                step="audio_pipeline",
                details={"chapter_count": len(book.chapters)},
                exc=exc,
            )
            log_ctx.error_log_store.save(error_log)
            error_log_path = log_ctx.error_log_store._path_for(book_slug)
            state = _state_with(state, artifacts={"last_error": message, "error_log": str(error_log_path)})
            _save_state(state_store, state, book_logger)
            results.append(BookResult(source=source, book_slug=book_slug, status="failed", message=message))
            if progress:
                progress.print_book_failed(book_slug, book.metadata.title or book_slug, message)
            continue

        ok_count = sum(1 for r in chapter_results if r.status == "ok")
        empty_count = sum(1 for r in chapter_results if r.status == "empty")
        failed_count = sum(1 for r in chapter_results if r.status == "failed")
        message = f"Generated {ok_count} chapter(s), {empty_count} empty, {failed_count} failed."
        chapters_ok = failed_count == 0
        state = _state_with(
            state,
            steps={"chapters": chapters_ok},
            artifacts={"chapter_dir": str(cache.chapter_dir / book_slug)},
        )
        _save_state(state_store, state, book_logger)

        chapter_audio = _collect_chapter_audio(book, chapter_results, book_logger)
        if not chapter_audio:
            results.append(BookResult(source=source, book_slug=book_slug, status="ok", message=message))
            if progress:
                progress.print_book_complete(book_slug, book.metadata.title or book_slug)
            _cleanup_cover_image(book.metadata.cover_image, book_logger)
            continue

        out_path = _resolve_output_path(config.paths.out, book_slug)
        try:
            _validate_output_path(out_path, config.paths.out, book_slug)
            packaged = packager.package(
                chapter_audio,
                book.metadata,
                out_path,
                cover_image=book.metadata.cover_image,
            )
        except Exception as exc:
            fail_message = f"{message} Packaging failed: {exc}"
            error_log.add_error(
                ErrorCategory.PACKAGING,
                ErrorSeverity.ERROR,
                fail_message,
                step="packaging",
                details={"output_path": str(out_path)},
                exc=exc,
            )
            log_ctx.error_log_store.save(error_log)
            error_log_path = log_ctx.error_log_store._path_for(book_slug)
            results.append(BookResult(source=source, book_slug=book_slug, status="failed", message=fail_message))
            state = _state_with(state, artifacts={"last_error": fail_message, "error_log": str(error_log_path)})
            _save_state(state_store, state, book_logger)
            if progress:
                progress.print_book_failed(book_slug, book.metadata.title or book_slug, fail_message)
            _cleanup_cover_image(book.metadata.cover_image, book_logger)
            continue

        final_message = f"{message} Packaged: {packaged}"
        state = _state_with(
            state,
            steps={"packaged": True},
            artifacts={"output_m4b": str(packaged), "last_error": ""},
        )
        _save_state(state_store, state, book_logger)
        log_ctx.error_log_store.save(error_log)
        results.append(
            BookResult(source=source, book_slug=book_slug, status="ok", message=final_message, output_path=packaged)
        )
        if progress:
            progress.print_book_complete(book_slug, book.metadata.title or book_slug)
        _cleanup_cover_image(book.metadata.cover_image, book_logger)

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


def _resolve_chapter_workers(config: Config, total_chapters: int, logger: logging.Logger) -> int:
    if total_chapters <= 1:
        return 1

    configured = config.tts.chapter_workers
    if configured is not None:
        workers = max(1, int(configured))
        if (
            config.tts.engine == "mlx"
            and config.tts.chapter_parallelism == "thread"
            and workers > 1
            and not config.tts.unsafe_mlx_parallelism
        ):
            logger.warning("MLX engine is not thread-safe; forcing chapter workers to 1.")
            return 1
        workers = min(workers, total_chapters)
        logger.info("Using %d chapter worker(s) (configured).", workers)
        return workers

    cpu_count = os.cpu_count() or 1
    if config.tts.engine == "mlx" and config.tts.chapter_parallelism == "thread":
        if not config.tts.unsafe_mlx_parallelism:
            logger.info("Using 1 chapter worker (auto; MLX engine).")
            return 1
        cap = 2
        workers = max(1, cpu_count - 1)
        workers = min(workers, cap, total_chapters)
        logger.warning("Using %d chapter worker(s) (auto; unsafe MLX parallelism).", workers)
        return workers

    if config.tts.engine == "mlx" and config.tts.chapter_parallelism == "process":
        cap = 3
        workers = max(1, cpu_count - 1)
        workers = min(workers, cap, total_chapters)
        logger.warning("Using %d chapter worker(s) (auto; MLX process parallelism).", workers)
        return workers
    cap = 4
    workers = max(1, cpu_count - 1)
    workers = min(workers, cap, total_chapters)
    logger.info("Using %d chapter worker(s) (auto; cpu=%s, cap=%d).", workers, cpu_count, cap)
    return workers


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
    error_log,
    progress: "ProgressDisplay | None" = None,
) -> list[ChapterResult]:
    cache.ensure_chapter_dir(book_slug)
    chapter_results: list[ChapterResult] = []
    total_chapters = len(book.chapters)
    workers = _resolve_chapter_workers(config, total_chapters, logger)
    if workers <= 1:
        for chapter in book.chapters:
            # Emit chapter progress
            if progress:
                progress.print_chapter_progress(
                    chapter.index,
                    chapter.title,
                    total_chapters,
                )
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
                    error_log,
                )
            )
        return chapter_results

    use_processes = config.tts.chapter_parallelism == "process"
    thread_state = threading.local()

    def _worker(chapter: Chapter) -> ChapterResult:
        worker_engine = getattr(thread_state, "engine", None)
        if worker_engine is None:
            worker_engine = _build_engine(config)
            thread_state.engine = worker_engine
        return _process_chapter(
            chapter,
            book_slug,
            cache,
            cleaner,
            segmenter,
            worker_engine,
            settings,
            audio_processor,
            config,
            output_format,
            logger,
            error_log,
        )

    heartbeat_seconds = 30.0
    executor_cls = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
    with executor_cls(max_workers=workers) as executor:
        futures: dict[object, Chapter] = {}
        for chapter in book.chapters:
            if progress:
                progress.print_chapter_progress(
                    chapter.index,
                    chapter.title,
                    total_chapters,
                )
            if use_processes:
                future = executor.submit(_process_chapter_in_subprocess, chapter, book_slug, config, output_format)
            else:
                future = executor.submit(_worker, chapter)
            futures[future] = chapter

        pending = set(futures.keys())
        last_heartbeat = time.monotonic()
        completed = 0
        while pending:
            done, pending = wait(pending, timeout=heartbeat_seconds)
            if not done:
                now = time.monotonic()
                if now - last_heartbeat >= heartbeat_seconds:
                    if progress:
                        progress.print(
                            f"  ...still working ({completed}/{total_chapters} chapters complete)"
                        )
                    last_heartbeat = now
                continue

            for future in done:
                chapter = futures[future]
                try:
                    if use_processes:
                        result, entries = future.result()
                        if entries:
                            error_log.errors.extend(entries)
                    else:
                        result = future.result()
                except Exception as exc:  # pragma: no cover - defensive guard
                    message = f"Unhandled error in chapter {chapter.index}: {exc}"
                    logger.error(message)
                    error_log.add_error(
                        ErrorCategory.UNKNOWN,
                        ErrorSeverity.ERROR,
                        message,
                        step="chapter_worker",
                        chapter_index=chapter.index,
                        details={"chapter_title": chapter.title},
                        exc=exc,
                    )
                    result = ChapterResult(chapter_index=chapter.index, status="failed", output_paths=())
                chapter_results.append(result)
                completed += 1
                if progress:
                    progress.print_chapter_complete(
                        chapter.index,
                        chapter.title,
                        total_chapters,
                        result.status,
                    )

    chapter_results.sort(key=lambda result: result.chapter_index)
    return chapter_results


def _collect_chapter_audio(
    book: EpubBook,
    chapter_results: Sequence[ChapterResult],
    logger: logging.Logger,
) -> list[ChapterAudio]:
    by_index: dict[int, Path] = {}
    for result in chapter_results:
        if result.status != "ok" or not result.output_paths:
            continue
        path = result.output_paths[0]
        by_index[result.chapter_index] = path

    if not by_index:
        logger.warning("No chapter audio available for packaging.")
        return []

    chapters: list[ChapterAudio] = []
    for chapter in book.chapters:
        path = by_index.get(chapter.index)
        if path is None:
            logger.warning("Missing audio for chapter %d (%s); skipping.", chapter.index, chapter.title)
            continue
        chapters.append(ChapterAudio(index=chapter.index, title=chapter.title, path=path))

    if not chapters:
        logger.warning("All chapter audio missing; skipping packaging.")
    return chapters


def _resolve_output_path(out_root: Path, book_slug: str) -> Path:
    return out_root / book_slug / f"{book_slug}.m4b"


def _validate_output_path(out_path: Path, out_root: Path, book_slug: str) -> None:
    expected_parent = out_root / book_slug
    expected_name = f"{book_slug}.m4b"
    if out_path.parent != expected_parent:
        raise RuntimeError(f"Output directory must be {expected_parent} (got {out_path.parent}).")
    if out_path.name != expected_name:
        raise RuntimeError(f"Output filename must be {expected_name} (got {out_path.name}).")


def _cleanup_cover_image(cover_image: Path | None, logger: logging.Logger) -> None:
    if cover_image is None:
        return
    if not cover_image.exists():
        return
    if not cover_image.is_file():
        return
    if not cover_image.name.startswith("epub_cover_"):
        return
    try:
        cover_image.unlink()
    except OSError as exc:  # pragma: no cover - best-effort cleanup
        logger.debug("Failed to delete temp cover image %s: %s", cover_image, exc)


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
    error_log,
) -> ChapterResult:
    stitched_path = cache.chapter_path(book_slug, chapter.index, "stitched")
    normalized_path = stitched_path.with_name(f"{stitched_path.stem}.normalized.wav")
    if config.audio.normalize and normalized_path.exists() and normalized_path.stat().st_size > 0:
        return ChapterResult(chapter_index=chapter.index, status="ok", output_paths=(normalized_path,))
    if not config.audio.normalize and stitched_path.exists() and stitched_path.stat().st_size > 0:
        return ChapterResult(chapter_index=chapter.index, status="ok", output_paths=(stitched_path,))

    cleaned = cleaner.clean(chapter.text)
    if not cleaned:
        message = f"Chapter {chapter.index} is empty after cleaning; skipping."
        logger.warning(message)
        error_log.add_error(
            ErrorCategory.TEXT_CLEANING,
            ErrorSeverity.WARNING,
            message,
            step="text_cleaning",
            chapter_index=chapter.index,
            details={"chapter_title": chapter.title},
        )
        return ChapterResult(chapter_index=chapter.index, status="empty", output_paths=())

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
        message = f"TTS failed for chapter {chapter.index}: {exc}"
        logger.error(message)
        error_log.add_error(
            ErrorCategory.TTS_SYNTHESIS,
            ErrorSeverity.ERROR,
            message,
            step="tts_synthesis",
            chapter_index=chapter.index,
            details={"chapter_title": chapter.title},
            exc=exc,
        )
        return ChapterResult(chapter_index=chapter.index, status="failed", output_paths=())

    if not chunks:
        message = f"No audio chunks generated for chapter {chapter.index}."
        logger.warning(message)
        error_log.add_error(
            ErrorCategory.TTS_SYNTHESIS,
            ErrorSeverity.WARNING,
            message,
            step="tts_synthesis",
            chapter_index=chapter.index,
            details={"chapter_title": chapter.title},
        )
        return ChapterResult(chapter_index=chapter.index, status="empty", output_paths=())

    processed_chunks: Sequence[AudioChunk] = chunks
    if config.audio.silence_ms > 0:
        try:
            processed_chunks = audio_processor.insert_silence(chunks, config.audio.silence_ms)
        except Exception as exc:
            message = f"Failed to insert silence for chapter {chapter.index}: {exc}"
            error_log.add_error(
                ErrorCategory.AUDIO_SILENCE,
                ErrorSeverity.ERROR,
                message,
                step="silence_insertion",
                chapter_index=chapter.index,
                details={"silence_ms": config.audio.silence_ms},
                exc=exc,
            )
            return ChapterResult(chapter_index=chapter.index, status="failed", output_paths=())

    try:
        audio_processor.stitch(processed_chunks, stitched_path)
    except Exception as exc:
        message = f"Failed to stitch audio for chapter {chapter.index}: {exc}"
        error_log.add_error(
            ErrorCategory.AUDIO_STITCHING,
            ErrorSeverity.ERROR,
            message,
            step="audio_stitching",
            chapter_index=chapter.index,
            details={"stitched_path": str(stitched_path)},
            exc=exc,
        )
        return ChapterResult(chapter_index=chapter.index, status="failed", output_paths=())

    if not config.audio.normalize:
        return ChapterResult(chapter_index=chapter.index, status="ok", output_paths=(stitched_path,))

    try:
        normalized = audio_processor.normalize([AudioChunk(index=0, path=stitched_path)])
    except Exception as exc:
        message = f"Failed to normalize audio for chapter {chapter.index}: {exc}"
        error_log.add_error(
            ErrorCategory.AUDIO_NORMALIZATION,
            ErrorSeverity.ERROR,
            message,
            step="audio_normalization",
            chapter_index=chapter.index,
            details={"stitched_path": str(stitched_path)},
            exc=exc,
        )
        return ChapterResult(chapter_index=chapter.index, status="failed", output_paths=())
    return ChapterResult(chapter_index=chapter.index, status="ok", output_paths=(normalized[0].path,))


def _load_or_init_state(
    store: JsonStateStore,
    book_id: str,
    source: Path,
    logger: logging.Logger,
) -> PipelineState:
    try:
        state = store.load(book_id)
    except Exception as exc:
        logger.warning("State load failed; starting fresh: %s", exc)
        state = None
    if state is None:
        state = PipelineState(
            book_id=book_id,
            steps={"chapters": False, "packaged": False},
            artifacts={"source_path": str(source)},
        )
        _save_state(store, state, logger)
        return state
    artifacts = dict(state.artifacts or {})
    artifacts.setdefault("source_path", str(source))
    steps = dict(state.steps)
    steps.setdefault("chapters", False)
    steps.setdefault("packaged", False)
    return PipelineState(book_id=state.book_id, steps=steps, artifacts=artifacts)


def _state_with(
    state: PipelineState,
    *,
    steps: dict[str, bool] | None = None,
    artifacts: dict[str, str] | None = None,
) -> PipelineState:
    new_steps = dict(state.steps)
    if steps:
        new_steps.update(steps)
    new_artifacts = dict(state.artifacts or {})
    if artifacts:
        new_artifacts.update(artifacts)
    return PipelineState(book_id=state.book_id, steps=new_steps, artifacts=new_artifacts)


def _save_state(store: JsonStateStore, state: PipelineState, logger: logging.Logger) -> None:
    try:
        store.save(state)
    except Exception as exc:
        logger.warning("State save failed: %s", exc)
