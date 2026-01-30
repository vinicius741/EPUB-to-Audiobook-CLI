"""EPUB to Audiobook CLI package."""

from .epub_reader import EbooklibEpubReader
from .text_cleaner import BasicTextCleaner
from .text_segmenter import BasicTextSegmenter
from .tts_engine import MlxTtsEngine, TtsError
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
    "BasicTextCleaner",
    "BasicTextSegmenter",
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
    "MlxTtsEngine",
    "TtsError",
]
__version__ = "0.1.0"
