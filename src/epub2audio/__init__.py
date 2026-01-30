"""EPUB to Audiobook CLI package."""

from .epub_reader import EbooklibEpubReader
from .interfaces import (
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

__all__ = [
    "__version__",
    "AudioChunk",
    "AudioProcessor",
    "BookMetadata",
    "Chapter",
    "EbooklibEpubReader",
    "EpubBook",
    "EpubReader",
    "Packager",
    "PipelineState",
    "Segment",
    "StateStore",
    "TextCleaner",
    "TextSegmenter",
    "TtsEngine",
]
__version__ = "0.1.0"
