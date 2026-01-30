from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from epub2audio.interfaces import (
    AudioChunk,
    AudioProcessor,
    BookMetadata,
    Chapter,
    EpubBook,
    EpubReader,
    Packager,
    PipelineState,
    Segment,
    StateStore,
    TextCleaner,
    TextSegmenter,
    TtsEngine,
)


class DummyReader:
    def read(self, path: Path) -> EpubBook:
        return EpubBook(metadata=BookMetadata(title="x"), chapters=[Chapter(index=0, title="c", text="t")])


class DummyCleaner:
    def clean(self, text: str) -> str:
        return text.strip()


class DummySegmenter:
    def segment(self, text: str) -> Iterable[Segment]:
        return [Segment(index=0, text=text)]


class DummyTts:
    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        config: Mapping[str, str] | None = None,
    ) -> AudioChunk:
        return AudioChunk(index=0, path=Path("audio.wav"))


class DummyAudio:
    def insert_silence(self, chunks: Sequence[AudioChunk], silence_ms: int) -> Sequence[AudioChunk]:
        return chunks

    def normalize(self, chunks: Sequence[AudioChunk]) -> Sequence[AudioChunk]:
        return chunks

    def stitch(self, chunks: Sequence[AudioChunk], out_path: Path) -> Path:
        return out_path


class DummyPackager:
    def package(
        self,
        chapter_audio: Sequence[Path],
        metadata: BookMetadata,
        out_path: Path,
        cover_image: Path | None = None,
    ) -> Path:
        return out_path


class DummyState:
    def load(self, book_id: str) -> PipelineState | None:
        return None

    def save(self, state: PipelineState) -> None:
        return None


def test_protocol_runtime_checks() -> None:
    assert isinstance(DummyReader(), EpubReader)
    assert isinstance(DummyCleaner(), TextCleaner)
    assert isinstance(DummySegmenter(), TextSegmenter)
    assert isinstance(DummyTts(), TtsEngine)
    assert isinstance(DummyAudio(), AudioProcessor)
    assert isinstance(DummyPackager(), Packager)
    assert isinstance(DummyState(), StateStore)
