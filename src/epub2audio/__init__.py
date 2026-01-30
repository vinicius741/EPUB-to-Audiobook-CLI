"""EPUB to Audiobook CLI package."""

from .epub_reader import EbooklibEpubReader
from .text_cleaner import BasicTextCleaner
from .text_segmenter import BasicTextSegmenter
from .tts_engine import MlxTtsEngine, TtsError
from .interfaces import (
    AudioChunk,
    AudioProcessor,
    BookMetadata,
    ChapterAudio,
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
from .packaging import FfmpegPackager

__all__ = [
    "__version__",
    "AudioChunk",
    "AudioProcessor",
    "BasicTextCleaner",
    "BasicTextSegmenter",
    "BookMetadata",
    "ChapterAudio",
    "Chapter",
    "EbooklibEpubReader",
    "EpubBook",
    "EpubReader",
    "FfmpegPackager",
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
