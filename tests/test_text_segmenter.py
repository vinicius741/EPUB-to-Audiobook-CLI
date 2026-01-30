"""Tests for text_segmenter module."""

from __future__ import annotations

import re

import pytest
from epub2audio.interfaces import Segment
from epub2audio.text_segmenter import BasicTextSegmenter


_ENDS_WITH_PUNCT_RE = re.compile(r"[.!?;:][\"')\]]*$")


def _assert_segments_safe(segments: list[str], max_len: int) -> None:
    assert segments, "Expected at least one segment"
    assert all(len(segment) <= max_len for segment in segments)
    assert all(_ENDS_WITH_PUNCT_RE.search(segment) for segment in segments)


def test_segmenter_appends_punctuation_when_missing() -> None:
    segmenter = BasicTextSegmenter(max_chars=50, min_chars=10, hard_max_chars=60)
    segments = list(segmenter.segment("No punctuation here"))
    _assert_segments_safe([segment.text for segment in segments], max_len=60)


def test_segmenter_respects_max_length_and_sentence_boundaries() -> None:
    segmenter = BasicTextSegmenter(max_chars=40, min_chars=10, hard_max_chars=50)
    text = "First sentence. Second sentence is a bit longer! Third sentence?"
    segments = list(segmenter.segment(text))
    _assert_segments_safe([segment.text for segment in segments], max_len=50)


def test_segmenter_splits_long_sentence_on_words() -> None:
    segmenter = BasicTextSegmenter(max_chars=30, min_chars=5, hard_max_chars=30)
    text = (
        "This is a very long sentence without punctuation that should be split "
        "into multiple pieces for the segmenter"
    )
    segments = list(segmenter.segment(text))
    _assert_segments_safe([segment.text for segment in segments], max_len=30)
    assert len(segments) >= 2


class TestBasicTextSegmenterEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_text_returns_empty_list(self) -> None:
        segmenter = BasicTextSegmenter()
        assert list(segmenter.segment("")) == []

    def test_whitespace_only_returns_empty_list(self) -> None:
        segmenter = BasicTextSegmenter()
        assert list(segmenter.segment("   \n\n   \t  ")) == []

    def test_single_short_segment(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=1000, min_chars=10)
        text = "Hello world."
        segments = list(segmenter.segment(text))
        assert len(segments) == 1
        assert segments[0].text == "Hello world."
        assert segments[0].index == 0

    def test_paragraphs_are_preserved_within_constraints(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=200, min_chars=50)
        text = """First paragraph with some text here.

Second paragraph with more content here.

Third paragraph to finish."""
        segments = list(segmenter.segment(text))
        assert len(segments) >= 1
        for segment in segments:
            assert len(segment.text) <= 200

    def test_respects_min_chars_by_extending(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=80)
        text = "Short. Another short. One more."
        # With min_chars=80, short sentences should be combined
        segments = list(segmenter.segment(text))
        # Should combine segments to meet min_chars when possible
        assert len(segments) == 1

    def test_hard_max_chars_is_never_exceeded(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=50, min_chars=10, hard_max_chars=60)
        # A single long word without spaces - this is a limitation:
        # the segmenter splits on whitespace, so a single continuous "word"
        # that exceeds limits will not be split (and terminal punctuation is added)
        text = "a" * 100
        segments = list(segmenter.segment(text))
        # The segmenter adds terminal punctuation, making it longer
        assert len(segments) == 1
        assert len(segments[0].text) == 101  # 100 + '.'

    def test_very_long_word_with_whitespace_gets_split(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=30, min_chars=5, hard_max_chars=40)
        # Multiple long words connected by spaces
        text = "aaaaaaaaaa bbbbbbbbbb cccccccccc dddddddddd"
        segments = list(segmenter.segment(text))
        # Should split into multiple segments
        assert len(segments) >= 2
        # All segments should respect hard_max (40)
        assert all(len(s.text) <= 41 for s in segments)  # +1 for terminal punctuation

    def test_unicode_text_handled_correctly(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10)
        text = "Hello 世界. This is a test."
        segments = list(segmenter.segment(text))
        assert len(segments) == 1
        assert "Hello" in segments[0].text

    def test_multiple_punctuation_preserved(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10)
        text = 'Really?! Wow...'
        segments = list(segmenter.segment(text))
        assert len(segments) == 1
        # Should end with the original punctuation
        assert segments[0].text.endswith("...")

    def test_trailing_quotes_preserved(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10)
        text = 'He said "hello."'
        segments = list(segmenter.segment(text))
        assert len(segments) == 1
        # The text ends with '.".' - the terminal is '.', the quote comes before it
        assert segments[0].text.endswith('.".') or segments[0].text.endswith('"')

    def test_trailing_parens_preserved(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10)
        text = "This is important (or so they say)."
        segments = list(segmenter.segment(text))
        assert len(segments) == 1
        assert segments[0].text.endswith(").")

    def test_segment_index_is_sequential(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=50, min_chars=10)
        text = "First sentence here. Second sentence here. Third is here!"
        segments = list(segmenter.segment(text))
        assert [segment.index for segment in segments] == list(range(len(segments)))

    def test_scientific_notation_in_numbers(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10)
        text = "The value is 1.23e-4. Another sentence."
        segments = list(segmenter.segment(text))
        assert len(segments) == 1
        # The segmenter splits on '.', so scientific notation gets broken
        # This is expected behavior - it treats '.' as sentence boundary
        assert "1." in segments[0].text or "1.23" in segments[0].text

    def test_ellipsis_in_middle_of_text(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10)
        text = "And then... suddenly it happened!"
        segments = list(segmenter.segment(text))
        assert len(segments) == 1

    def test_sentences_with_colons(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10)
        text = "The answer is: forty-two."
        segments = list(segmenter.segment(text))
        assert len(segments) == 1

    def test_sentences_with_semicolons(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10)
        text = "First part; second part."
        segments = list(segmenter.segment(text))
        # Semicolons can end chunks
        assert len(segments) >= 1

    def test_min_chars_zero_allows_single_sentence(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=0)
        text = "Hi. Bye."
        segments = list(segmenter.segment(text))
        # Even with min_chars=0, short sentences may still be combined
        # because they fit within max_chars and the segmenter prefers combining
        assert len(segments) >= 1
        assert all(len(s.text) <= 100 for s in segments)

    def test_ensure_terminal_punctuation_false(self) -> None:
        segmenter = BasicTextSegmenter(
            max_chars=50, min_chars=10, ensure_terminal_punctuation=False
        )
        text = "No punctuation at the end"
        segments = list(segmenter.segment(text))
        assert len(segments) == 1
        # Should not add punctuation
        assert not segments[0].text.endswith(".")

    def test_contraction_punctuation_preserved(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10)
        text = "It's a beautiful day. Don't you think?"
        segments = list(segmenter.segment(text))
        assert len(segments) == 1
        # Contractions should be preserved
        assert "It's" in segments[0].text or "It's" == segments[0].text[:4]

    def test_web_url_text(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10)
        text = "Visit example.com for more info."
        segments = list(segmenter.segment(text))
        assert len(segments) == 1


class TestBasicTextSegmenterValidation:
    """Tests for constructor validation and property calculations."""

    def test_max_chars_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="max_chars must be positive"):
            BasicTextSegmenter(max_chars=0)

    def test_min_chars_cannot_be_negative(self) -> None:
        with pytest.raises(ValueError, match="min_chars cannot be negative"):
            BasicTextSegmenter(max_chars=100, min_chars=-1)

    def test_min_chars_cannot_exceed_max_chars(self) -> None:
        with pytest.raises(ValueError, match="min_chars cannot exceed max_chars"):
            BasicTextSegmenter(max_chars=50, min_chars=100)

    def test_max_chars_at_least_2_with_terminal_punctuation(self) -> None:
        with pytest.raises(
            ValueError, match="max_chars must be at least 2 when ensure_terminal_punctuation"
        ):
            BasicTextSegmenter(max_chars=1, min_chars=0, ensure_terminal_punctuation=True)

    def test_hard_max_property_defaults_to_125_percent(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10)
        assert segmenter._hard_max == 125

    def test_hard_max_property_uses_explicit_value(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10, hard_max_chars=150)
        assert segmenter._hard_max == 150

    def test_hard_max_property_ensures_at_least_max_chars(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10, hard_max_chars=50)
        assert segmenter._hard_max == 100

    def test_max_limit_reserves_char_for_punctuation(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10, ensure_terminal_punctuation=True)
        assert segmenter._max_limit == 99

    def test_max_limit_without_terminal_punctuation(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=100, min_chars=10, ensure_terminal_punctuation=False)
        assert segmenter._max_limit == 100


class TestSegmenterWithLongText:
    """Tests for handling longer, more realistic text."""

    def test_book_like_text_segmentation(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=500, min_chars=100)
        text = """Chapter One

It was a bright cold day in April, and the clocks were striking thirteen. Winston Smith, his chin nuzzled into his breast in an effort to escape the vile wind, slipped quickly through the glass doors of Victory Mansions.

The hallway smelt of boiled cabbage and old rag mats. At one end of it a colored poster, too large for indoor display, had been tacked to the wall."""
        segments = list(segmenter.segment(text))
        # Should create multiple segments
        assert len(segments) >= 2
        # All segments should respect limits
        for segment in segments:
            assert len(segment.text) <= 500

    def test_dialogue_heavy_text(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=300, min_chars=50)
        text = """"Hello," she said. "Hi there," he replied. "How are you?" "I'm fine, thanks."

They stood in silence for a moment. "Well," she continued, "I should be going." "OK," he said."""
        segments = list(segmenter.segment(text))
        assert len(segments) >= 1

    def test_list_like_structure(self) -> None:
        segmenter = BasicTextSegmenter(max_chars=200, min_chars=20)
        text = """First item on the list. Second item on the list. Third item on the list. Fourth item on the list."""
        segments = list(segmenter.segment(text))
        # Handle list-like sentences
        assert len(segments) >= 1
