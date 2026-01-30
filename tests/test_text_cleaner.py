"""Tests for text_cleaner module."""

import pytest

from epub2audio.text_cleaner import BasicTextCleaner

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def cleaner() -> BasicTextCleaner:
    """Return a BasicTextCleaner with default settings."""
    return BasicTextCleaner()


@pytest.fixture
def cleaner_no_citations() -> BasicTextCleaner:
    """Return a BasicTextCleaner with citation removal enabled."""
    return BasicTextCleaner(remove_citations=True)


@pytest.fixture
def cleaner_no_paragraphs() -> BasicTextCleaner:
    """Return a BasicTextCleaner that does not preserve paragraph breaks."""
    return BasicTextCleaner(preserve_paragraph_breaks=False)


# =============================================================================
# Tests for Unicode Normalization
# =============================================================================


class TestUnicodeNormalization:
    """Tests for Unicode NFC normalization."""

    def test_nfc_normalization(self, cleaner: BasicTextCleaner) -> None:
        """NFC normalization composes combined characters."""
        # e + combining acute accent = e with acute accent
        text = "e\u0301"  # e + combining acute accent
        result = cleaner.clean(text)
        assert result == "\u00e9"  # e with acute accent as single char

    def test_nfc_disabled(self) -> None:
        """Unicode normalization can be disabled."""
        cleaner = BasicTextCleaner(normalize_unicode=False)
        text = "e\u0301"  # e + combining acute accent
        result = cleaner.clean(text)
        # Without normalization, combining characters remain separate
        assert result == "e\u0301"


# =============================================================================
# Tests for Whitespace Normalization
# =============================================================================


class TestWhitespaceNormalization:
    """Tests for whitespace collapsing and normalization."""

    def test_collapse_multiple_spaces(self, cleaner: BasicTextCleaner) -> None:
        """Multiple spaces collapse to single space."""
        text = "Hello    World"
        result = cleaner.clean(text)
        assert result == "Hello World"

    def test_collapse_tabs_to_spaces(self, cleaner: BasicTextCleaner) -> None:
        """Tabs are treated as whitespace and collapsed."""
        text = "Hello\t\tWorld"
        result = cleaner.clean(text)
        assert result == "Hello World"

    def test_collapse_mixed_whitespace(self, cleaner: BasicTextCleaner) -> None:
        """Mixed spaces and tabs collapse to single space."""
        text = "Hello \t \t  World"
        result = cleaner.clean(text)
        assert result == "Hello World"

    def test_strip_leading_whitespace(self, cleaner: BasicTextCleaner) -> None:
        """Leading whitespace is stripped."""
        text = "   Hello World"
        result = cleaner.clean(text)
        assert result == "Hello World"

    def test_strip_trailing_whitespace(self, cleaner: BasicTextCleaner) -> None:
        """Trailing whitespace is stripped."""
        text = "Hello World   "
        result = cleaner.clean(text)
        assert result == "Hello World"

    def test_strip_both_ends(self, cleaner: BasicTextCleaner) -> None:
        """Leading and trailing whitespace are both stripped."""
        text = "   Hello World   "
        result = cleaner.clean(text)
        assert result == "Hello World"


# =============================================================================
# Tests for Paragraph Preservation
# =============================================================================


class TestParagraphPreservation:
    """Tests for paragraph break preservation."""

    def test_single_newline_preserved(self, cleaner: BasicTextCleaner) -> None:
        """Single newlines within a paragraph are preserved."""
        text = "Hello\nWorld"
        result = cleaner.clean(text)
        assert result == "Hello\nWorld"

    def test_double_newline_becomes_single(self, cleaner: BasicTextCleaner) -> None:
        """Double newlines (paragraph break) become single newline."""
        text = "Hello\n\nWorld"
        result = cleaner.clean(text)
        assert result == "Hello\n\nWorld"

    def test_triple_newline_becomes_single(self, cleaner: BasicTextCleaner) -> None:
        """Triple newlines become single paragraph break."""
        text = "Hello\n\n\nWorld"
        result = cleaner.clean(text)
        assert result == "Hello\n\nWorld"

    def test_many_newlines_collapse(self, cleaner: BasicTextCleaner) -> None:
        """Many consecutive newlines collapse to single paragraph break."""
        text = "Hello\n\n\n\n\nWorld"
        result = cleaner.clean(text)
        assert result == "Hello\n\nWorld"

    def test_newlines_with_spaces(self, cleaner: BasicTextCleaner) -> None:
        """Newlines with intermediate spaces still collapse."""
        text = "Hello\n \nWorld"
        result = cleaner.clean(text)
        assert result == "Hello\n\nWorld"

    def test_multiple_paragraphs(self, cleaner: BasicTextCleaner) -> None:
        """Multiple paragraphs are preserved."""
        text = "First\n\nSecond\n\nThird"
        result = cleaner.clean(text)
        assert result == "First\n\nSecond\n\nThird"

    def test_no_paragraph_preservation(self, cleaner_no_paragraphs: BasicTextCleaner) -> None:
        """With preserve_paragraph_breaks=False, newlines become spaces."""
        text = "Hello\n\nWorld"
        result = cleaner_no_paragraphs.clean(text)
        assert result == "Hello World"


# =============================================================================
# Tests for Control Character Removal
# =============================================================================


class TestControlCharacterRemoval:
    """Tests for control character removal."""

    def test_null_byte_removed(self, cleaner: BasicTextCleaner) -> None:
        """Null bytes are replaced with space."""
        text = "Hello\x00World"
        result = cleaner.clean(text)
        assert result == "Hello World"

    def test_carriage_return_removed(self, cleaner: BasicTextCleaner) -> None:
        """Carriage returns are replaced with space."""
        text = "Hello\rWorld"
        result = cleaner.clean(text)
        assert result == "Hello World"

    def test_bell_removed(self, cleaner: BasicTextCleaner) -> None:
        """Bell character is replaced with space."""
        text = "Hello\x07World"
        result = cleaner.clean(text)
        assert result == "Hello World"

    def test_tab_preserved(self, cleaner: BasicTextCleaner) -> None:
        """Tabs are preserved (treated as whitespace, collapsed)."""
        text = "Hello\tWorld"
        result = cleaner.clean(text)
        assert result == "Hello World"

    def test_newline_preserved(self, cleaner: BasicTextCleaner) -> None:
        """Newlines are preserved for paragraph handling."""
        text = "Hello\nWorld"
        result = cleaner.clean(text)
        assert "\n" in result


# =============================================================================
# Tests for Citation Removal
# =============================================================================


class TestCitationRemoval:
    """Tests for optional citation pattern removal."""

    def test_citations_removed(self, cleaner_no_citations: BasicTextCleaner) -> None:
        """Numeric citations like [1] are removed."""
        text = "Hello World [1]"
        result = cleaner_no_citations.clean(text)
        assert result == "Hello World"

    def test_multi_digit_citations_removed(self, cleaner_no_citations: BasicTextCleaner) -> None:
        """Multi-digit citations like [123] are removed."""
        text = "Hello World [123]"
        result = cleaner_no_citations.clean(text)
        assert result == "Hello World"

    def test_citation_with_text_removed(self, cleaner_no_citations: BasicTextCleaner) -> None:
        """Citations with text like [Chapter 5] are removed."""
        text = "Hello World [Chapter 5]"
        result = cleaner_no_citations.clean(text)
        assert result == "Hello World"

    def test_citation_with_spaces_removed(self, cleaner_no_citations: BasicTextCleaner) -> None:
        """Citations with spaces like [ Note 42 ] are removed."""
        text = "Hello World [ Note 42 ]"
        result = cleaner_no_citations.clean(text)
        assert result == "Hello World"

    def test_multiple_citations_removed(self, cleaner_no_citations: BasicTextCleaner) -> None:
        """Multiple citations in a single line are removed."""
        text = "Hello [1] World [2]"
        result = cleaner_no_citations.clean(text)
        assert result == "Hello World"

    def test_citations_not_removed_by_default(self, cleaner: BasicTextCleaner) -> None:
        """Citations are NOT removed by default."""
        text = "Hello World [1]"
        result = cleaner.clean(text)
        assert result == "Hello World [1]"

    def test_bracket_without_digit_not_removed(self, cleaner_no_citations: BasicTextCleaner) -> None:
        """Brackets without digits are not citations."""
        text = "Hello [abc] World"
        result = cleaner_no_citations.clean(text)
        assert result == "Hello [abc] World"


# =============================================================================
# Tests for Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and special inputs."""

    def test_empty_string(self, cleaner: BasicTextCleaner) -> None:
        """Empty string returns empty string."""
        result = cleaner.clean("")
        assert result == ""

    def test_whitespace_only(self, cleaner: BasicTextCleaner) -> None:
        """Whitespace-only string returns empty string."""
        result = cleaner.clean("   \n\t   ")
        assert result == ""

    def test_newlines_only(self, cleaner: BasicTextCleaner) -> None:
        """Newline-only string returns empty string."""
        result = cleaner.clean("\n\n\n")
        assert result == ""

    def test_already_clean_text(self, cleaner: BasicTextCleaner) -> None:
        """Already clean text is unchanged."""
        text = "Hello World"
        result = cleaner.clean(text)
        assert result == text

    def test_unicode_content(self, cleaner: BasicTextCleaner) -> None:
        """Non-ASCII characters are preserved."""
        text = "Hello 世界 🌍"
        result = cleaner.clean(text)
        assert result == "Hello 世界 🌍"

    def test_preserve_quotes(self, cleaner: BasicTextCleaner) -> None:
        """Quotes are preserved."""
        text = '"Hello World," she said.'
        result = cleaner.clean(text)
        assert result == '"Hello World," she said.'


# =============================================================================
# Tests for Configuration
# =============================================================================


class TestConfiguration:
    """Tests for cleaner configuration options."""

    def test_all_options_enabled(self) -> None:
        """All options enabled works correctly."""
        cleaner = BasicTextCleaner(
            normalize_unicode=True,
            remove_citations=True,
            preserve_paragraph_breaks=True,
        )
        text = "  Hello\n\n  World [1]e\u0301  "
        result = cleaner.clean(text)
        # After citation removal, space remains before "World"
        assert result == "Hello\n\n World \u00e9"

    def test_all_options_disabled(self) -> None:
        """All options disabled works correctly."""
        cleaner = BasicTextCleaner(
            normalize_unicode=False,
            remove_citations=False,
            preserve_paragraph_breaks=False,
        )
        text = "  Hello\n\n  World [1]e\u0301  "
        result = cleaner.clean(text)
        # Newlines become spaces, whitespace collapsed, stripped
        assert result == "Hello World [1]e\u0301"
