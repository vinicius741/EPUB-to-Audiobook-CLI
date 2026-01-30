"""Pipeline stubs for Phase 0 verification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .logging_setup import LoggingContext
from .utils import slugify


@dataclass(frozen=True)
class BookResult:
    source: Path
    book_slug: str
    status: str
    message: str


def run_pipeline(
    log_ctx: LoggingContext,
    inputs: Sequence[Path],
) -> list[BookResult]:
    results: list[BookResult] = []

    for source in inputs:
        book_slug = slugify(source.stem if source.suffix else source.name)
        book_logger = log_ctx.get_book_logger(book_slug)
        if not source.exists():
            message = f"Input not found: {source}"
            book_logger.warning(message)
            results.append(BookResult(source=source, book_slug=book_slug, status="missing", message=message))
            continue

        book_logger.info("Stub pipeline for %s", source)
        results.append(
            BookResult(
                source=source,
                book_slug=book_slug,
                status="stub",
                message="No processing implemented yet.",
            )
        )

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
