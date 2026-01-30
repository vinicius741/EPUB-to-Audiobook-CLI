"""Tests for text_segmenter module."""

from __future__ import annotations

import re

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
