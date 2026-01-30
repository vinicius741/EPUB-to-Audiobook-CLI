"""Text segmentation into TTS-safe chunks."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

from .interfaces import Segment

_LOGGER = logging.getLogger(__name__)

_PARAGRAPH_SPLIT_RE = re.compile(r"\n{2,}")
_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_END_RE = re.compile(r"([.!?]+[\"')\]]*)")
_TERMINAL_PUNCT_RE = re.compile(r"[.!?;:]+[\"')\]]*$")


@dataclass(frozen=True)
class BasicTextSegmenter:
    """Segment text into bounded chunks that end with punctuation.

    The segmenter prefers sentence boundaries, but will split long sentences
    on word boundaries when needed. Paragraph breaks are treated as soft
    boundaries: a paragraph can end a chunk if the chunk already meets the
    minimum length.
    """

    max_chars: int = 1000
    min_chars: int = 200
    hard_max_chars: int | None = None
    ensure_terminal_punctuation: bool = True

    def __post_init__(self) -> None:
        if self.max_chars <= 0:
            raise ValueError("max_chars must be positive")
        if self.min_chars < 0:
            raise ValueError("min_chars cannot be negative")
        if self.min_chars > self.max_chars:
            raise ValueError("min_chars cannot exceed max_chars")
        if self.ensure_terminal_punctuation and self.max_chars < 2:
            raise ValueError("max_chars must be at least 2 when ensure_terminal_punctuation is True")

    @property
    def _hard_max(self) -> int:
        if self.hard_max_chars is None:
            return int(self.max_chars * 1.25)
        return max(self.max_chars, self.hard_max_chars)

    @property
    def _max_limit(self) -> int:
        if not self.ensure_terminal_punctuation:
            return self.max_chars
        return max(1, self.max_chars - 1)

    @property
    def _hard_limit(self) -> int:
        if not self.ensure_terminal_punctuation:
            return self._hard_max
        return max(1, self._hard_max - 1)

    def segment(self, text: str) -> Iterable[Segment]:
        if not text:
            return []

        paragraphs = self._split_paragraphs(text)
        segments: list[Segment] = []
        current = ""
        index = 0

        def flush() -> None:
            nonlocal current, index
            chunk = current.strip()
            if not chunk:
                current = ""
                return
            if self.ensure_terminal_punctuation:
                chunk = _ensure_terminal_punctuation(chunk)
            segments.append(Segment(index=index, text=chunk))
            index += 1
            current = ""

        def append_piece(piece: str) -> None:
            nonlocal current
            piece = piece.strip()
            if not piece:
                return
            if not current:
                current = piece
                return

            candidate = f"{current} {piece}"
            if len(candidate) <= self._max_limit:
                current = candidate
                return

            if len(current) < self.min_chars and len(candidate) <= self._hard_limit:
                current = candidate
                return

            flush()
            current = piece

        for paragraph in paragraphs:
            sentences = _split_sentences(paragraph)
            for sentence in sentences:
                if len(sentence) > self._hard_limit:
                    for piece in self._split_long_sentence(sentence):
                        append_piece(piece)
                    continue
                append_piece(sentence)

            if current and len(current) >= self.min_chars:
                flush()

        if current:
            flush()

        _LOGGER.debug("Segmented text into %d chunk(s)", len(segments))
        return segments

    def _split_long_sentence(self, sentence: str) -> list[str]:
        words = sentence.split()
        if not words:
            return []

        pieces: list[str] = []
        current = ""
        for word in words:
            if not current:
                current = word
                continue

            candidate = f"{current} {word}"
            if len(candidate) <= self._hard_limit:
                current = candidate
                continue

            pieces.append(current)
            current = word

            if len(word) > self._hard_limit:
                pieces.extend(self._split_long_word(word))
                current = ""

        if current:
            pieces.append(current)

        return pieces

    def _split_long_word(self, word: str) -> list[str]:
        size = self._hard_limit
        return [word[i : i + size] for i in range(0, len(word), size)]

    @staticmethod
    def _split_paragraphs(text: str) -> list[str]:
        paragraphs = _PARAGRAPH_SPLIT_RE.split(text)
        cleaned: list[str] = []
        for paragraph in paragraphs:
            paragraph = _WHITESPACE_RE.sub(" ", paragraph.strip())
            if paragraph:
                cleaned.append(paragraph)
        return cleaned


def _split_sentences(text: str) -> list[str]:
    parts = _SENTENCE_END_RE.split(text)
    sentences: list[str] = []
    buffer = ""
    for part in parts:
        if not part:
            continue
        if _SENTENCE_END_RE.fullmatch(part):
            buffer += part
            sentence = buffer.strip()
            if sentence:
                sentences.append(sentence)
            buffer = ""
        else:
            buffer += part

    if buffer.strip():
        sentences.append(buffer.strip())
    return sentences


def _ensure_terminal_punctuation(text: str) -> str:
    if _TERMINAL_PUNCT_RE.search(text):
        return text
    return f"{text}."
