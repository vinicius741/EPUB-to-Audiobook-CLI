"""Module interfaces and data contracts for the pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class BookMetadata:
    title: str
    author: str | None = None
    language: str | None = None
    cover_image: Path | None = None


@dataclass(frozen=True)
class Chapter:
    index: int
    title: str
    text: str


@dataclass(frozen=True)
class Segment:
    index: int
    text: str


@dataclass(frozen=True)
class AudioChunk:
    index: int
    path: Path
    duration_ms: int | None = None


@dataclass(frozen=True)
class ChapterAudio:
    index: int
    title: str
    path: Path


@dataclass(frozen=True)
class EpubBook:
    metadata: BookMetadata
    chapters: Sequence[Chapter]


@dataclass(frozen=True)
class PipelineState:
    book_id: str
    steps: Mapping[str, bool]
    artifacts: Mapping[str, str] | None = None


@runtime_checkable
class EpubReader(Protocol):
    def read(self, path: Path) -> EpubBook:  # pragma: no cover - interface
        ...


@runtime_checkable
class TextCleaner(Protocol):
    def clean(self, text: str) -> str:  # pragma: no cover - interface
        ...


@runtime_checkable
class TextSegmenter(Protocol):
    def segment(self, text: str) -> Iterable[Segment]:  # pragma: no cover - interface
        ...


@runtime_checkable
class TtsEngine(Protocol):
    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        config: Mapping[str, object] | None = None,
    ) -> AudioChunk:  # pragma: no cover - interface
        ...


@runtime_checkable
class AudioProcessor(Protocol):
    def insert_silence(
        self, chunks: Sequence[AudioChunk], silence_ms: int
    ) -> Sequence[AudioChunk]:  # pragma: no cover - interface
        ...

    def normalize(self, chunks: Sequence[AudioChunk]) -> Sequence[AudioChunk]:  # pragma: no cover
        ...

    def stitch(self, chunks: Sequence[AudioChunk], out_path: Path) -> Path:  # pragma: no cover
        ...


@runtime_checkable
class Packager(Protocol):
    def package(
        self,
        chapters: Sequence[ChapterAudio],
        metadata: BookMetadata,
        out_path: Path,
        cover_image: Path | None = None,
    ) -> Path:  # pragma: no cover - interface
        ...


@runtime_checkable
class StateStore(Protocol):
    def load(self, book_id: str) -> PipelineState | None:  # pragma: no cover - interface
        ...

    def save(self, state: PipelineState) -> None:  # pragma: no cover - interface
        ...
