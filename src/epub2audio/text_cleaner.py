"""Text cleaning and normalization for EPUB content."""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Final

_LOGGER = logging.getLogger(__name__)

# Control characters to remove (excluding newline \n and tab \t)
_CONTROL_CHARS_PATTERN: Final = re.compile(
    r"[\x00-\x08\x0b\x0c\x0d\x0e-\x1f\x7f-\x9f]"
)

# Citation pattern: [1], [Chapter X], [Note 123], etc.
# Matches brackets containing at least one digit
_CITATION_PATTERN: Final = re.compile(r"\[[^\]]*\d[^\]]*\]")

# Multiple whitespace pattern (spaces, tabs)
_WHITESPACE_PATTERN: Final = re.compile(r"[ \t]+")

# Multiple newlines pattern (2+ newlines with possible spaces/tabs between)
_MULTIPLE_NEWLINE_PATTERN: Final = re.compile(r"\n[ \t]*\n+")


class BasicTextCleaner:
    """Basic text cleaner for EPUB content.

    Conservative defaults:
    - Unicode NFC normalization
    - Collapse multiple whitespace characters
    - Preserve paragraph breaks (double newlines become single newline)
    - Remove control characters (except newlines and tabs)
    - Strip leading/trailing whitespace
    - Optional citation removal
    """

    def __init__(
        self,
        normalize_unicode: bool = True,
        remove_citations: bool = False,
        preserve_paragraph_breaks: bool = True,
    ) -> None:
        """Initialize the text cleaner.

        Args:
            normalize_unicode: Apply Unicode NFC normalization.
            remove_citations: Remove citation patterns like [1], [Chapter X].
            preserve_paragraph_breaks: If True, preserve paragraph breaks.
                                       If False, all newlines become spaces.
        """
        self.normalize_unicode = normalize_unicode
        self.remove_citations = remove_citations
        self.preserve_paragraph_breaks = preserve_paragraph_breaks
        _LOGGER.debug(
            "Initialized BasicTextCleaner: normalize_unicode=%s, remove_citations=%s, preserve_paragraph_breaks=%s",
            normalize_unicode,
            remove_citations,
            preserve_paragraph_breaks,
        )

    def clean(self, text: str) -> str:
        """Clean and normalize text content.

        Args:
            text: Raw text content from EPUB.

        Returns:
            Cleaned and normalized text.
        """
        if not text:
            return ""

        # 1. Unicode normalization
        if self.normalize_unicode:
            text = unicodedata.normalize("NFC", text)

        # 2. Remove control characters (except newline and tab)
        text = _CONTROL_CHARS_PATTERN.sub(" ", text)

        # 3. Remove citations if enabled
        if self.remove_citations:
            text = _CITATION_PATTERN.sub("", text)

        # 4. Normalize whitespace and newlines
        if self.preserve_paragraph_breaks:
            # Collapse multiple newlines to single newline (preserving paragraphs)
            text = _MULTIPLE_NEWLINE_PATTERN.sub("\n\n", text)
        else:
            # Convert all newlines to spaces
            text = text.replace("\n", " ")

        # Collapse multiple spaces/tabs to single space
        text = _WHITESPACE_PATTERN.sub(" ", text)

        # 5. Strip leading/trailing whitespace
        text = text.strip()

        return text
