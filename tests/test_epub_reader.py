"""Tests for epub_reader module."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from epub2audio.epub_reader import (
    EbooklibEpubReader,
    _build_toc_maps,
    _extract_metadata,
    _extract_title_and_text,
    _first_metadata,
    _get_cover_item,
    _get_item_href,
    _is_non_linear,
    _media_type_to_extension,
    _normalize_href,
    _normalize_title,
    _resolve_title,
    _toc_entry,
    _walk_toc,
)


# ============================================================================
# Fixtures
# ============================================================================


@dataclass
class MockEpubItem:
    """Mock ebooklib item for testing."""

    file_name: str = "chapter1.xhtml"
    media_type: str = "application/xhtml+xml"
    content: bytes = b"<html><body><p>Test content</p></body></html>"
    item_type: str = "ITEM_DOCUMENT"

    def get_type(self) -> str:
        return self.item_type

    def get_name(self) -> str:
        return self.file_name

    def get_content(self) -> bytes:
        return self.content


@dataclass
class MockTocItem:
    """Mock TOC item for testing."""

    title: str | None = "Chapter 1"
    href: str | None = "chapter1.xhtml"


@dataclass
class MockEpubBook:
    """Mock ebooklib EPUB book for testing."""

    title: str = "Test Book"
    author: str | None = "Test Author"
    language: str | None = "en"
    toc: list = ()
    spine: list[tuple[str, bool | str | None]] = ()
    cover: str | None = None
    # Cached items that will be created in __post_init__
    _items: dict[str, MockEpubItem] | None = None

    def __post_init__(self) -> None:
        """Create and cache mock items."""
        if self._items is None:
            self._items = {
                "item1": MockEpubItem(
                    file_name="chapter1.xhtml",
                    content=b"<html><head><title>Chapter One</title></head><body><p>Content of chapter one.</p></body></html>",
                ),
                "item2": MockEpubItem(
                    file_name="chapter2.xhtml",
                    content=b"<html><body><h1>Chapter Two</h1><p>Content of chapter two.</p></body></html>",
                ),
                "non_linear": MockEpubItem(
                    file_name="bonus.xhtml",
                    content=b"<html><body><p>Bonus content.</p></body></html>",
                ),
            }

    def get_metadata(self, namespace: str, name: str) -> list:
        """Get metadata in ebooklib format."""
        if name == "title" and self.title:
            return [(self.title, {})]
        if name == "creator" and self.author:
            return [(self.author, {})]
        if name == "language" and self.language:
            return [(self.language, {})]
        return []

    def get_item_with_id(self, item_id: str) -> MockEpubItem | None:
        """Get item by ID from cached items."""
        return self._items.get(item_id) if self._items else None

    def get_cover_uri(self) -> str | None:
        return self.cover

    def get_items_of_type(self, item_type: int) -> list:
        """Get items of a specific type (e.g., ITEM_COVER)."""
        return []

    def get_item_by_id(self, item_id: str) -> object | None:
        """Get item by ID (for cover lookup in EPUB 2)."""
        return None


# ============================================================================
# Tests for _first_metadata
# ============================================================================


def test_first_metadata_returns_value_when_present() -> None:
    book = MockEpubBook(title="My Title")
    result = _first_metadata(book, "title")
    assert result == "My Title"


def test_first_metadata_returns_none_when_missing() -> None:
    book = MockEpubBook(title=None)
    result = _first_metadata(book, "title")
    assert result is None


def test_first_metadata_strips_whitespace() -> None:
    book = MockEpubBook(title="  My Title  ")
    result = _first_metadata(book, "title")
    assert result == "My Title"


def test_first_metadata_returns_none_for_empty_string() -> None:
    book = MockEpubBook(title="   ")
    result = _first_metadata(book, "title")
    assert result is None


def test_first_metadata_returns_none_for_none_value() -> None:
    book = MockEpubBook()
    book.get_metadata = MagicMock(return_value=[(None, {})])
    result = _first_metadata(book, "title")
    assert result is None


# ============================================================================
# Tests for _extract_metadata
# ============================================================================


def test_extract_metadata_with_all_fields() -> None:
    book = MockEpubBook(title="Book Title", author="Author Name", language="en")
    metadata = _extract_metadata(book, fallback_title="Fallback")
    assert metadata.title == "Book Title"
    assert metadata.author == "Author Name"
    assert metadata.language == "en"


def test_extract_metadata_with_partial_fields() -> None:
    book = MockEpubBook(title="Book Title", author=None, language=None)
    metadata = _extract_metadata(book, fallback_title="Fallback")
    assert metadata.title == "Book Title"
    assert metadata.author is None
    assert metadata.language is None


def test_extract_metadata_uses_fallback_title() -> None:
    book = MockEpubBook(title=None)
    metadata = _extract_metadata(book, fallback_title="fallback_title")
    assert metadata.title == "fallback_title"


# ============================================================================
# Tests for _normalize_title
# ============================================================================


def test_normalize_title_with_valid_title() -> None:
    assert _normalize_title("Chapter One") == "Chapter One"


def test_normalize_title_strips_whitespace() -> None:
    assert _normalize_title("  Chapter One  ") == "Chapter One"


def test_normalize_title_returns_none_for_none() -> None:
    assert _normalize_title(None) is None


def test_normalize_title_returns_none_for_empty_string() -> None:
    assert _normalize_title("") is None
    assert _normalize_title("   ") is None


# ============================================================================
# Tests for _normalize_href
# ============================================================================


def test_normalize_href_basic() -> None:
    assert _normalize_href("chapter1.xhtml") == "chapter1.xhtml"


def test_normalize_href_removes_fragment() -> None:
    assert _normalize_href("chapter1.xhtml#anchor") == "chapter1.xhtml"


def test_normalize_href_unquotes_url() -> None:
    assert _normalize_href("chapter%201.xhtml") == "chapter 1.xhtml"


def test_normalize_href_normalizes_windows_paths() -> None:
    assert _normalize_href("OEBPS\\chapter1.xhtml") == "OEBPS/chapter1.xhtml"


def test_normalize_href_removes_leading_dot_slash() -> None:
    assert _normalize_href("./chapter1.xhtml") == "chapter1.xhtml"
    assert _normalize_href("././chapter1.xhtml") == "chapter1.xhtml"


def test_normalize_href_removes_leading_slash() -> None:
    assert _normalize_href("/chapter1.xhtml") == "chapter1.xhtml"


def test_normalize_href_handles_empty() -> None:
    assert _normalize_href("") == ""
    assert _normalize_href(None) == ""


def test_normalize_href_complex_path() -> None:
    assert _normalize_href("./OEBPS/../Text/chapter.xhtml") == "Text/chapter.xhtml"


# ============================================================================
# Tests for _toc_entry
# ============================================================================


def test_toc_entry_with_valid_item() -> None:
    item = MockTocItem(title="Chapter 1", href="ch1.xhtml")
    result = _toc_entry(item)
    assert result == ("Chapter 1", "ch1.xhtml")


def test_toc_entry_with_none_title() -> None:
    item = MockTocItem(title=None, href="ch1.xhtml")
    result = _toc_entry(item)
    assert result == (None, "ch1.xhtml")


def test_toc_entry_with_none_href() -> None:
    item = MockTocItem(title="Chapter 1", href=None)
    result = _toc_entry(item)
    assert result == ("Chapter 1", None)


def test_toc_entry_with_both_none() -> None:
    item = MockTocItem(title=None, href=None)
    result = _toc_entry(item)
    assert result is None


def test_toc_entry_with_object_without_attributes() -> None:
    result = _toc_entry(object())
    assert result is None


# ============================================================================
# Tests for _walk_toc
# ============================================================================


def test_walk_toc_flat_list() -> None:
    items = [
        MockTocItem(title="Chapter 1", href="ch1.xhtml"),
        MockTocItem(title="Chapter 2", href="ch2.xhtml"),
    ]
    result = list(_walk_toc(items))
    assert result == [("Chapter 1", "ch1.xhtml"), ("Chapter 2", "ch2.xhtml")]


def test_walk_toc_nested_tuple() -> None:
    section = MockTocItem(title="Part 1", href="part1.xhtml")
    children = [
        MockTocItem(title="Chapter 1", href="ch1.xhtml"),
        MockTocItem(title="Chapter 2", href="ch2.xhtml"),
    ]
    items = [(section, children)]
    result = list(_walk_toc(items))
    assert len(result) == 3
    assert ("Part 1", "part1.xhtml") in result
    assert ("Chapter 1", "ch1.xhtml") in result
    assert ("Chapter 2", "ch2.xhtml") in result


def test_walk_toc_deeply_nested() -> None:
    inner = [MockTocItem(title="Inner", href="inner.xhtml")]
    middle = [(MockTocItem(title="Middle", href="mid.xhtml"), inner)]
    items = [(MockTocItem(title="Outer", href="outer.xhtml"), middle)]
    result = list(_walk_toc(items))
    assert len(result) == 3
    assert ("Outer", "outer.xhtml") in result
    assert ("Middle", "mid.xhtml") in result
    assert ("Inner", "inner.xhtml") in result


def test_walk_toc_with_none_items() -> None:
    result = list(_walk_toc(None))
    assert result == []


def test_walk_toc_with_empty_list() -> None:
    result = list(_walk_toc([]))
    assert result == []


def test_walk_toc_skips_invalid_entries() -> None:
    items = [
        MockTocItem(title="Valid", href="valid.xhtml"),
        object(),  # Invalid - no title/href
        MockTocItem(title="Also Valid", href="also.xhtml"),
    ]
    result = list(_walk_toc(items))
    assert result == [("Valid", "valid.xhtml"), ("Also Valid", "also.xhtml")]


# ============================================================================
# Tests for _build_toc_maps
# ============================================================================


def test_build_toc_maps_basic() -> None:
    toc = [
        MockTocItem(title="Chapter 1", href="ch1.xhtml"),
        MockTocItem(title="Chapter 2", href="ch2.xhtml"),
    ]
    toc_map, basename_map = _build_toc_maps(toc)
    assert toc_map == {"ch1.xhtml": "Chapter 1", "ch2.xhtml": "Chapter 2"}
    assert basename_map == {"ch1.xhtml": "Chapter 1", "ch2.xhtml": "Chapter 2"}


def test_build_toc_maps_with_path() -> None:
    toc = [MockTocItem(title="Chapter 1", href="OEBPS/ch1.xhtml")]
    toc_map, basename_map = _build_toc_maps(toc)
    assert toc_map == {"OEBPS/ch1.xhtml": "Chapter 1"}
    assert basename_map == {"ch1.xhtml": "Chapter 1"}


def test_build_toc_maps_handles_duplicate_basenames() -> None:
    toc = [
        MockTocItem(title="Chapter 1", href="dir1/chapter.xhtml"),
        MockTocItem(title="Chapter 2", href="dir2/chapter.xhtml"),
    ]
    toc_map, basename_map = _build_toc_maps(toc)
    # Full paths should still work
    assert toc_map == {
        "dir1/chapter.xhtml": "Chapter 1",
        "dir2/chapter.xhtml": "Chapter 2",
    }
    # Basename map should be empty due to duplicates
    assert basename_map == {}


def test_build_toc_maps_skips_empty_titles() -> None:
    toc = [
        MockTocItem(title=None, href="ch1.xhtml"),
        MockTocItem(title="Chapter 2", href="ch2.xhtml"),
    ]
    toc_map, basename_map = _build_toc_maps(toc)
    assert toc_map == {"ch2.xhtml": "Chapter 2"}
    assert basename_map == {"ch2.xhtml": "Chapter 2"}


def test_build_toc_maps_uses_first_title_for_duplicate_hrefs() -> None:
    toc = [
        MockTocItem(title="First Title", href="ch1.xhtml"),
        MockTocItem(title="Second Title", href="ch1.xhtml"),
    ]
    toc_map, basename_map = _build_toc_maps(toc)
    assert toc_map == {"ch1.xhtml": "First Title"}


# ============================================================================
# Tests for _is_non_linear
# ============================================================================


def test_is_non_linear_with_none() -> None:
    assert _is_non_linear(None) is False


def test_is_non_linear_with_string_no() -> None:
    assert _is_non_linear("no") is True
    assert _is_non_linear("NO") is True
    assert _is_non_linear("  No  ") is True


def test_is_non_linear_with_string_yes() -> None:
    assert _is_non_linear("yes") is False


def test_is_non_linear_with_boolean() -> None:
    assert _is_non_linear(False) is True
    assert _is_non_linear(True) is False


# ============================================================================
# Tests for _get_item_href
# ============================================================================


def test_get_item_href_with_get_name_method() -> None:
    item = MockEpubItem(file_name="chapter.xhtml")
    result = _get_item_href(item)
    assert result == "chapter.xhtml"


def test_get_item_href_fallback_to_file_name_attribute() -> None:
    item = MagicMock(spec=[])  # No get_name method
    item.file_name = "chapter.xhtml"
    result = _get_item_href(item)
    assert result == "chapter.xhtml"


def test_get_item_href_fallback_to_href_attribute() -> None:
    item = MagicMock(spec=[])  # No get_name or file_name
    item.href = "chapter.xhtml"
    result = _get_item_href(item)
    assert result == "chapter.xhtml"


def test_get_item_href_returns_empty_on_error() -> None:
    item = MagicMock()
    item.get_name.side_effect = AttributeError("Test error")
    result = _get_item_href(item)
    assert result == ""


def test_get_item_href_returns_empty_when_no_attributes() -> None:
    item = object()
    result = _get_item_href(item)
    assert result == ""


# ============================================================================
# Tests for _resolve_title
# ============================================================================


def test_resolve_title_from_toc_map() -> None:
    toc_map = {"chapter.xhtml": "Chapter One"}
    toc_basename_map = {}
    result = _resolve_title(
        href="chapter.xhtml",
        toc_map=toc_map,
        toc_basename_map=toc_basename_map,
        html_title=None,
        index=0,
    )
    assert result == "Chapter One"


def test_resolve_title_from_basename_map() -> None:
    toc_map = {}
    toc_basename_map = {"chapter.xhtml": "Chapter From Basename"}
    result = _resolve_title(
        href="OEBPS/chapter.xhtml",
        toc_map=toc_map,
        toc_basename_map=toc_basename_map,
        html_title=None,
        index=0,
    )
    assert result == "Chapter From Basename"


def test_resolve_title_from_html_title() -> None:
    toc_map = {}
    toc_basename_map = {}
    result = _resolve_title(
        href="unknown.xhtml",
        toc_map=toc_map,
        toc_basename_map=toc_basename_map,
        html_title="HTML Title",
        index=0,
    )
    assert result == "HTML Title"


def test_resolve_title_from_filename_stem() -> None:
    toc_map = {}
    toc_basename_map = {}
    result = _resolve_title(
        href="my_chapter-file.xhtml",
        toc_map=toc_map,
        toc_basename_map=toc_basename_map,
        html_title=None,
        index=0,
    )
    assert result == "my chapter file"


def test_resolve_title_fallback_to_section() -> None:
    toc_map = {}
    toc_basename_map = {}
    result = _resolve_title(
        href="",
        toc_map=toc_map,
        toc_basename_map=toc_basename_map,
        html_title=None,
        index=4,
    )
    assert result == "Section 5"


def test_resolve_title_prefer_toc_over_html() -> None:
    toc_map = {"chapter.xhtml": "TOC Title"}
    toc_basename_map = {}
    result = _resolve_title(
        href="chapter.xhtml",
        toc_map=toc_map,
        toc_basename_map=toc_basename_map,
        html_title="HTML Title",
        index=0,
    )
    assert result == "TOC Title"


# ============================================================================
# Tests for _extract_title_and_text
# ============================================================================


@patch("epub2audio.epub_reader.BeautifulSoup")
def test_extract_title_and_text_basic(mock_bs: MagicMock) -> None:
    from bs4 import Tag

    # Mock the HTML structure
    mock_title_tag = MagicMock()
    mock_title_tag.string = "  Chapter Title  "
    mock_soup = MagicMock()
    mock_soup.title = mock_title_tag
    mock_soup.body = MagicMock()
    mock_soup.body.get_text.return_value = "Line 1\n\nLine 2\n\n"
    mock_bs.return_value = mock_soup

    title, text = _extract_title_and_text(b"<html></html>")
    assert title == "Chapter Title"
    assert text == "Line 1\nLine 2"


@patch("epub2audio.epub_reader.BeautifulSoup")
def test_extract_title_and_text_removes_script_tags(mock_bs: MagicMock) -> None:
    mock_soup = MagicMock()
    mock_soup.title = None
    mock_soup.body = MagicMock()
    mock_soup.body.get_text.return_value = "content"
    mock_soup.return_value = mock_soup
    # Call to soup() should remove tags
    mock_soup.__call__ = MagicMock(return_value=mock_soup)

    _extract_title_and_text(b"<html><script>alert('test')</script></html>")
    # Verify soup was called with the content
    mock_bs.assert_called_once()


@patch("epub2audio.epub_reader.BeautifulSoup")
def test_extract_title_and_text_no_body(mock_bs: MagicMock) -> None:
    mock_soup = MagicMock()
    mock_soup.title = None
    mock_soup.body = None
    mock_soup.get_text.return_value = "direct text"
    mock_bs.return_value = mock_soup

    title, text = _extract_title_and_text(b"<p>direct text</p>")
    assert title is None
    assert text == "direct text"


@patch("epub2audio.epub_reader.BeautifulSoup")
def test_extract_title_and_text_none_title_string(mock_bs: MagicMock) -> None:
    mock_title_tag = MagicMock()
    mock_title_tag.string = None
    mock_soup = MagicMock()
    mock_soup.title = mock_title_tag
    mock_soup.body = MagicMock()
    mock_soup.body.get_text.return_value = "content"
    mock_bs.return_value = mock_soup

    title, text = _extract_title_and_text(b"<html></html>")
    assert title is None
    assert text == "content"


# ============================================================================
# Tests for EbooklibEpubReader.read()
# ============================================================================


@patch("epub2audio.epub_reader.ITEM_DOCUMENT", 1)  # Mock ITEM_DOCUMENT constant
@patch("epub2audio.epub_reader.epub")
@patch("epub2audio.epub_reader.BeautifulSoup")
def test_read_basic_epub(mock_bs: MagicMock, mock_epub: MagicMock) -> None:
    """Test reading a basic EPUB file."""
    # Setup mock book
    mock_book = MockEpubBook(
        title="Test Book",
        author="Test Author",
        language="en",
        spine=[("item1", True), ("item2", True)],
    )
    mock_epub.read_epub.return_value = mock_book

    # Mock BeautifulSoup
    mock_soup_instance = MagicMock()
    mock_soup_instance.title = None
    mock_soup_instance.body = MagicMock()
    mock_soup_instance.body.get_text.return_value = "Test content"
    mock_bs.return_value = mock_soup_instance

    # Update MockEpubItem to return the mocked ITEM_DOCUMENT type
    for item_id in ["item1", "item2"]:
        if item := mock_book.get_item_with_id(item_id):
            item.item_type = 1

    reader = EbooklibEpubReader()
    result = reader.read(Path("test.epub"))

    assert result.metadata.title == "Test Book"
    assert result.metadata.author == "Test Author"
    assert result.metadata.language == "en"
    assert len(result.chapters) == 2


@patch("epub2audio.epub_reader.ITEM_DOCUMENT", 1)  # Mock ITEM_DOCUMENT constant
@patch("epub2audio.epub_reader.epub")
@patch("epub2audio.epub_reader.BeautifulSoup")
def test_read_skips_non_linear_items(mock_bs: MagicMock, mock_epub: MagicMock) -> None:
    """Test that non-linear spine items are skipped when skip_non_linear=True."""
    mock_book = MockEpubBook(
        title="Test Book",
        spine=[
            ("item1", True),
            ("non_linear", "no"),  # Non-linear
            ("item2", True),
        ],
    )
    mock_epub.read_epub.return_value = mock_book

    mock_soup_instance = MagicMock()
    mock_soup_instance.title = None
    mock_soup_instance.body = MagicMock()
    mock_soup_instance.body.get_text.return_value = "Content"
    mock_bs.return_value = mock_soup_instance

    for item_id in ["item1", "non_linear", "item2"]:
        if item := mock_book.get_item_with_id(item_id):
            item.item_type = 1

    reader = EbooklibEpubReader(skip_non_linear=True)
    result = reader.read(Path("test.epub"))

    assert len(result.chapters) == 2


@patch("epub2audio.epub_reader.ITEM_DOCUMENT", 1)  # Mock ITEM_DOCUMENT constant
@patch("epub2audio.epub_reader.epub")
@patch("epub2audio.epub_reader.BeautifulSoup")
def test_read_includes_non_linear_when_disabled(
    mock_bs: MagicMock, mock_epub: MagicMock
) -> None:
    """Test that non-linear items are included when skip_non_linear=False."""
    mock_book = MockEpubBook(
        title="Test Book",
        spine=[
            ("item1", True),
            ("non_linear", "no"),
            ("item2", True),
        ],
    )
    mock_epub.read_epub.return_value = mock_book

    mock_soup_instance = MagicMock()
    mock_soup_instance.title = None
    mock_soup_instance.body = MagicMock()
    mock_soup_instance.body.get_text.return_value = "Content"
    mock_bs.return_value = mock_soup_instance

    for item_id in ["item1", "non_linear", "item2"]:
        if item := mock_book.get_item_with_id(item_id):
            item.item_type = 1

    reader = EbooklibEpubReader(skip_non_linear=False)
    result = reader.read(Path("test.epub"))

    assert len(result.chapters) == 3


@patch("epub2audio.epub_reader.ITEM_DOCUMENT", 1)  # Mock ITEM_DOCUMENT constant
@patch("epub2audio.epub_reader.epub")
@patch("epub2audio.epub_reader.BeautifulSoup")
def test_read_skips_empty_documents(mock_bs: MagicMock, mock_epub: MagicMock) -> None:
    """Test that documents with no text content are skipped."""
    mock_book = MockEpubBook(
        title="Test Book",
        spine=[("item1", True), ("item2", True)],
    )
    mock_epub.read_epub.return_value = mock_book

    mock_soup_instance = MagicMock()
    mock_soup_instance.title = None
    mock_soup_instance.body = MagicMock()
    # Second item has empty content
    mock_soup_instance.body.get_text.side_effect = ["Content", "   "]
    mock_bs.return_value = mock_soup_instance

    for item_id in ["item1", "item2"]:
        if item := mock_book.get_item_with_id(item_id):
            item.item_type = 1

    reader = EbooklibEpubReader()
    result = reader.read(Path("test.epub"))

    assert len(result.chapters) == 1


@patch("epub2audio.epub_reader.epub")
def test_read_raises_error_when_dependencies_missing(mock_epub: MagicMock) -> None:
    """Test that a helpful error is raised when dependencies are not installed."""
    with patch("epub2audio.epub_reader.epub", None):
        reader = EbooklibEpubReader()
        with pytest.raises(RuntimeError, match="Missing EPUB reader dependencies"):
            reader.read(Path("test.epub"))


# ============================================================================
# Tests for TOC-based chapter titles
# ============================================================================


@patch("epub2audio.epub_reader.ITEM_DOCUMENT", 1)  # Mock ITEM_DOCUMENT constant
@patch("epub2audio.epub_reader.epub")
@patch("epub2audio.epub_reader.BeautifulSoup")
def test_read_uses_toc_titles(mock_bs: MagicMock, mock_epub: MagicMock) -> None:
    """Test that chapter titles from TOC are used."""
    mock_book = MockEpubBook(
        title="Test Book",
        toc=[
            MockTocItem(title="First Chapter", href="chapter1.xhtml"),
            MockTocItem(title="Second Chapter", href="chapter2.xhtml"),
        ],
        spine=[("item1", True), ("item2", True)],
    )
    mock_epub.read_epub.return_value = mock_book

    mock_soup_instance = MagicMock()
    mock_soup_instance.title = None
    mock_soup_instance.body = MagicMock()
    mock_soup_instance.body.get_text.return_value = "Content"
    mock_bs.return_value = mock_soup_instance

    for item_id in ["item1", "item2"]:
        if item := mock_book.get_item_with_id(item_id):
            item.item_type = 1

    reader = EbooklibEpubReader()
    result = reader.read(Path("test.epub"))

    assert result.chapters[0].title == "First Chapter"
    assert result.chapters[1].title == "Second Chapter"


@patch("epub2audio.epub_reader.ITEM_DOCUMENT", 1)  # Mock ITEM_DOCUMENT constant
@patch("epub2audio.epub_reader.epub")
@patch("epub2audio.epub_reader.BeautifulSoup")
def test_read_falls_back_to_html_title(mock_bs: MagicMock, mock_epub: MagicMock) -> None:
    """Test falling back to HTML <title> when TOC doesn't have the chapter."""
    # TOC only has a different chapter, not the ones in spine
    mock_book = MockEpubBook(
        title="Test Book",
        toc=[MockTocItem(title="Preface", href="preface.xhtml")],  # Not in spine
        spine=[("item1", True), ("item2", True)],
    )
    mock_epub.read_epub.return_value = mock_book

    # For second chapter, we want to have an HTML title
    mock_soup_with_title = MagicMock()
    mock_title = MagicMock()
    mock_title.string = "HTML Chapter Title"
    mock_soup_with_title.title = mock_title
    mock_soup_with_title.body = MagicMock()
    mock_soup_with_title.body.get_text.return_value = "Content"

    call_count = [0]

    def soup_side_effect(content, parser):
        call_count[0] += 1
        if call_count[0] == 2:
            return mock_soup_with_title
        return MagicMock(title=None, body=MagicMock(get_text=MagicMock(return_value="Content")))

    mock_bs.side_effect = soup_side_effect

    for item_id in ["item1", "item2"]:
        if item := mock_book.get_item_with_id(item_id):
            item.item_type = 1

    reader = EbooklibEpubReader()
    result = reader.read(Path("test.epub"))

    # First chapter falls back to filename-derived title (from "chapter1.xhtml")
    assert "chapter" in result.chapters[0].title.lower() or "section" in result.chapters[0].title.lower()
    # Second chapter uses HTML title
    assert result.chapters[1].title == "HTML Chapter Title"


# ============================================================================
# Tests for _media_type_to_extension
# ============================================================================


def test_media_type_to_extension_jpeg() -> None:
    assert _media_type_to_extension("image/jpeg") == ".jpg"
    assert _media_type_to_extension("image/jpg") == ".jpg"


def test_media_type_to_extension_png() -> None:
    assert _media_type_to_extension("image/png") == ".png"


def test_media_type_to_extension_gif() -> None:
    assert _media_type_to_extension("image/gif") == ".gif"


def test_media_type_to_extension_webp() -> None:
    assert _media_type_to_extension("image/webp") == ".webp"


def test_media_type_to_extension_unknown() -> None:
    assert _media_type_to_extension("image/unknown") == ".jpg"
    assert _media_type_to_extension("") == ".jpg"


def test_media_type_to_extension_case_insensitive() -> None:
    assert _media_type_to_extension("IMAGE/JPEG") == ".jpg"
    assert _media_type_to_extension("Image/Png") == ".png"


# ============================================================================
# Tests for _get_cover_item
# ============================================================================


def test_get_cover_item_epub3_style() -> None:
    """Test finding cover via EPUB 3 style properties="cover-image"."""
    book = MockEpubBook()

    @dataclass
    class MockCoverItem:
        media_type: str = "image/jpeg"
        content: bytes = b"fake cover content"

        def get_content(self) -> bytes:
            return self.content

    cover_item = MockCoverItem()

    # Track all calls to get_items_of_type
    calls = []

    def mock_get_items_of_type(item_type):
        calls.append(item_type)
        # Return cover_item for any type (we're just testing the cover logic)
        return [cover_item]

    book.get_items_of_type = mock_get_items_of_type

    result = _get_cover_item(book)
    # Verify get_items_of_type was called
    assert len(calls) > 0
    assert result is cover_item


def test_get_cover_item_epub2_style() -> None:
    """Test finding cover via EPUB 2 style <meta name="cover">."""
    book = MockEpubBook()

    @dataclass
    class MockCoverItem:
        media_type: str = "image/jpeg"
        content: bytes = b"fake cover content"

        def get_content(self) -> bytes:
            return self.content

    cover_item = MockCoverItem()

    def mock_get_metadata(namespace, name):
        if namespace == "OPF" and name == "meta":
            return [("cover", "my-cover-id"), ("other", "value")]
        return []

    def mock_get_item_by_id(item_id):
        if item_id == "my-cover-id":
            return cover_item
        return None

    book.get_metadata = mock_get_metadata
    book.get_item_by_id = mock_get_item_by_id

    result = _get_cover_item(book)
    assert result is cover_item


def test_get_cover_item_no_cover() -> None:
    """Test when no cover is present."""
    book = MockEpubBook()

    def mock_get_items_of_type(item_type):
        return []

    def mock_get_metadata(namespace, name):
        return []

    book.get_items_of_type = mock_get_items_of_type
    book.get_metadata = mock_get_metadata

    result = _get_cover_item(book)
    assert result is None


# ============================================================================
# Tests for _extract_metadata (updated for cover_image)
# ============================================================================


@patch("epub2audio.epub_reader._get_cover_item")
def test_extract_metadata_cover_none_when_no_cover(mock_get_cover: MagicMock) -> None:
    """Test that cover_image is None when no cover is present."""
    mock_get_cover.return_value = None
    book = MockEpubBook(title="Book Title", author="Author Name", language="en")

    metadata = _extract_metadata(book, fallback_title="Fallback")

    assert metadata.title == "Book Title"
    assert metadata.author == "Author Name"
    assert metadata.language == "en"
    assert metadata.cover_image is None


@patch("epub2audio.epub_reader._get_cover_item")
@patch("epub2audio.epub_reader.tempfile.NamedTemporaryFile")
def test_extract_metadata_cover_extracted_when_present(
    mock_tmp_file: MagicMock, mock_get_cover: MagicMock
) -> None:
    """Test that cover_image is extracted when cover is present."""
    from pathlib import Path

    @dataclass
    class MockCoverItem:
        media_type: str = "image/jpeg"
        content: bytes = b"fake cover content"

        def get_content(self) -> bytes:
            return self.content

    cover_item = MockCoverItem()
    mock_get_cover.return_value = cover_item

    # Mock temporary file
    mock_file = MagicMock()
    mock_file.name = "/tmp/epub_cover_abc123.jpg"
    mock_tmp_file.return_value.__enter__ = MagicMock(return_value=mock_file)
    mock_tmp_file.return_value.__exit__ = MagicMock(return_value=False)

    book = MockEpubBook(title="Book Title", author="Author Name", language="en")

    metadata = _extract_metadata(book, fallback_title="Fallback")

    assert metadata.title == "Book Title"
    assert metadata.cover_image == Path("/tmp/epub_cover_abc123.jpg")
    mock_file.write.assert_called_once_with(b"fake cover content")
