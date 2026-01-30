"""Quiet progress display for epub2audio CLI.

This module provides a calm, readable progress display that prints
to stderr without timestamps or verbose logging. It's designed to
be non-intrusive while still providing clear feedback about progress.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..pipeline import BookResult


def _format_duration(seconds: float) -> str:
    """Format seconds as MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def _truncate_title(title: str, max_len: int = 40) -> str:
    """Truncate a title to fit within max_len characters."""
    if len(title) <= max_len:
        return title
    return title[: max_len - 3] + "..."


@dataclass
class BookProgress:
    """Progress tracking for a single book."""

    book_slug: str
    title: str
    total_chapters: int
    completed_chapters: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None

    @property
    def is_complete(self) -> bool:
        return self.end_time is not None

    @property
    def duration(self) -> timedelta:
        if self.end_time is None:
            return datetime.now() - self.start_time
        return self.end_time - self.start_time

    def mark_complete(self) -> None:
        if self.end_time is None:
            self.end_time = datetime.now()


@dataclass
class ProgressDisplay:
    """Quiet progress display for the CLI.

    This displays calm, minimal progress information to stderr.
    It separates UI messages from logged output.

    Example output:
        Processing: The Great Gatsby
          [Chapter 1/10] Chapter One
          [Chapter 2/10] Chapter Two
          ...
        Completed: The Great Gatsby (00:45)

        Processing: Moby Dick
          [Chapter 1/40] Chapter 1
          ...
        Completed: Moby Dick (02:30)
    """

    _current_book: BookProgress | None = None
    _book_start_time: datetime | None = None

    def print(self, message: str) -> None:
        """Print a message to stderr (for UI output)."""
        print(message, file=sys.stderr)

    def print_processing(self, book_slug: str, title: str, total_chapters: int) -> None:
        """Print that we're starting to process a book."""
        truncated_title = _truncate_title(title)
        self.print(f"Processing: {truncated_title}")

        self._current_book = BookProgress(
            book_slug=book_slug,
            title=title,
            total_chapters=total_chapters,
        )

    def print_chapter_progress(self, chapter_index: int, chapter_title: str, total_chapters: int) -> None:
        """Print chapter progress (indented)."""
        truncated_title = _truncate_title(chapter_title, 30)
        self.print(f"  [Chapter {chapter_index}/{total_chapters}] {truncated_title}")

        if self._current_book:
            self._current_book.completed_chapters = chapter_index

    def print_book_complete(self, book_slug: str, title: str) -> None:
        """Print that a book is complete with duration."""
        if self._current_book:
            self._current_book.mark_complete()
            duration_seconds = self._current_book.duration.total_seconds()
            duration_str = _format_duration(duration_seconds)
            truncated_title = _truncate_title(title)
            self.print(f"Completed: {truncated_title} ({duration_str})")
        else:
            self.print(f"Completed: {title}")

        self.print("")  # Blank line between books
        self._current_book = None

    def print_book_skipped(self, book_slug: str, title: str, output_path: Path) -> None:
        """Print that a book was skipped (already processed)."""
        truncated_title = _truncate_title(title)
        self.print(f"Skipped: {truncated_title} (already exists)")
        self.print("")  # Blank line between books
        self._current_book = None

    def print_book_failed(self, book_slug: str, title: str, message: str) -> None:
        """Print that a book failed."""
        truncated_title = _truncate_title(title)
        self.print(f"Failed: {truncated_title}")
        self.print(f"  Error: {message}")
        self.print("")  # Blank line between books
        self._current_book = None

    def print_book_missing(self, source: Path) -> None:
        """Print that a book file was not found."""
        self.print(f"Missing: {source}")
        self.print("")  # Blank line between books

    def print_summary(self, results: list[BookResult]) -> None:
        """Print the final summary of results."""
        if not results:
            self.print("No books processed.")
            return

        counts: dict[str, int] = {}
        for result in results:
            counts[result.status] = counts.get(result.status, 0) + 1

        self.print("Summary:")
        for status in ["ok", "skipped", "failed", "missing"]:
            if count := counts.get(status):
                self.print(f"  {status}: {count}")

        self.print("")

        # List results
        for result in results:
            line = f"  - {result.book_slug}: {result.status}"
            if result.output_path is not None:
                line += f" -> {result.output_path}"
            self.print(line)
