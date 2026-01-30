"""EPUB reader implementation using ebooklib for TOC/spine extraction."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import posixpath
import tempfile
from collections.abc import Iterable as IterableABC
from urllib.parse import unquote

from .interfaces import BookMetadata, Chapter, EpubBook, EpubReader

try:  # pragma: no cover - exercised in integration tests once dependencies are installed
    from ebooklib import ITEM_COVER, ITEM_DOCUMENT, epub
except ImportError:  # pragma: no cover - optional dependency until Phase 1 is wired in
    epub = None
    ITEM_COVER = None
    ITEM_DOCUMENT = None

try:  # pragma: no cover - exercised in integration tests once dependencies are installed
    from bs4 import BeautifulSoup
except ImportError:  # pragma: no cover - optional dependency until Phase 1 is wired in
    BeautifulSoup = None

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class EbooklibEpubReader:
    """Read EPUB files and emit ordered chapters based on the spine."""

    skip_non_linear: bool = True

    def read(self, path: Path) -> EpubBook:
        _require_dependencies()

        book = epub.read_epub(str(path))
        toc_map, toc_basename_map = _build_toc_maps(book.toc)
        metadata = _extract_metadata(book, fallback_title=path.stem)
        chapters = _extract_chapters(
            book,
            toc_map=toc_map,
            toc_basename_map=toc_basename_map,
            skip_non_linear=self.skip_non_linear,
        )
        return EpubBook(metadata=metadata, chapters=chapters)


def _require_dependencies() -> None:
    if epub is None or BeautifulSoup is None:
        missing = []
        if epub is None:
            missing.append("ebooklib")
        if BeautifulSoup is None:
            missing.append("beautifulsoup4")
        raise RuntimeError(
            "Missing EPUB reader dependencies: "
            + ", ".join(missing)
            + ". Install with `pip install ebooklib beautifulsoup4`."
        )


def _extract_metadata(book: epub.EpubBook, fallback_title: str) -> BookMetadata:
    title = _first_metadata(book, "title") or fallback_title
    author = _first_metadata(book, "creator")
    language = _first_metadata(book, "language")
    cover_image = _extract_cover_image(book)
    return BookMetadata(title=title, author=author, language=language, cover_image=cover_image)


def _first_metadata(book: epub.EpubBook, name: str) -> str | None:
    values = book.get_metadata("DC", name)
    if not values:
        return None
    value = values[0][0]
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _extract_cover_image(book: epub.EpubBook) -> Path | None:
    """Extract the cover image from the EPUB and return its path.

    Returns None if no cover is found. The cover is extracted to a
    temporary file that should be cleaned up by the caller.
    """
    cover_item = _get_cover_item(book)
    if cover_item is None:
        return None

    try:
        content = cover_item.get_content()
        if not content:
            return None

        # Determine file extension from media type or item name
        media_type = getattr(cover_item, "media_type", "")
        ext = _media_type_to_extension(media_type)

        # Create a temporary file with appropriate extension
        with tempfile.NamedTemporaryFile(
            suffix=ext, delete=False, prefix="epub_cover_"
        ) as tmp_file:
            tmp_file.write(content)
            return Path(tmp_file.name)
    except (OSError, IOError) as e:  # pragma: no cover - defensive
        _LOGGER.warning("Failed to extract cover image: %s", e)
        return None


def _get_cover_item(book: epub.EpubBook) -> object | None:
    """Find the cover item in the EPUB, handling both EPUB 2 and 3 formats."""
    # Try EPUB 3 style: items with properties="cover-image"
    cover_item = next(iter(book.get_items_of_type(ITEM_COVER)), None)
    if cover_item is not None:
        return cover_item

    # Try EPUB 2 style: <meta name="cover" content="item-id" />
    for meta_name, meta_content in book.get_metadata("OPF", "meta"):
        if meta_name == "cover" and meta_content:
            cover_item = book.get_item_by_id(meta_content)
            if cover_item:
                return cover_item

    return None


def _media_type_to_extension(media_type: str) -> str:
    """Convert a media type to a file extension."""
    extensions = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    return extensions.get(media_type.lower(), ".jpg")


def _build_toc_maps(toc: Iterable[object]) -> tuple[dict[str, str], dict[str, str]]:
    toc_map: dict[str, str] = {}
    toc_basename_map: dict[str, str] = {}
    basename_counts: dict[str, int] = {}

    for title, href in _walk_toc(toc):
        normalized_title = _normalize_title(title)
        normalized_href = _normalize_href(href)
        if not normalized_title or not normalized_href:
            continue

        if normalized_href not in toc_map:
            toc_map[normalized_href] = normalized_title

        basename = posixpath.basename(normalized_href)
        if basename:
            basename_counts[basename] = basename_counts.get(basename, 0) + 1
            if basename not in toc_basename_map:
                toc_basename_map[basename] = normalized_title

    for basename, count in basename_counts.items():
        if count > 1:
            toc_basename_map.pop(basename, None)

    return toc_map, toc_basename_map


def _walk_toc(items: Iterable[object]) -> Iterable[tuple[str | None, str | None]]:
    for item in items or []:
        if isinstance(item, tuple) and len(item) == 2:
            section, children = item
            entry = _toc_entry(section)
            if entry:
                yield entry
            if _is_iterable_collection(children):
                yield from _walk_toc(children)
            continue

        entry = _toc_entry(item)
        if entry:
            yield entry
            continue

        if _is_iterable_collection(item):
            yield from _walk_toc(item)


def _toc_entry(item: object) -> tuple[str | None, str | None] | None:
    title = getattr(item, "title", None)
    href = getattr(item, "href", None)
    if title is None and href is None:
        return None
    return title, href


def _is_iterable_collection(value: object) -> bool:
    return isinstance(value, IterableABC) and not isinstance(value, (str, bytes))


def _normalize_title(title: str | None) -> str | None:
    if title is None:
        return None
    cleaned = str(title).strip()
    return cleaned or None


def _normalize_href(href: str | None) -> str:
    if not href:
        return ""
    base = href.split("#", 1)[0]
    if not base:
        return ""
    base = unquote(base)
    base = base.replace("\\", "/")
    base = posixpath.normpath(base)
    while base.startswith("./"):
        base = base[2:]
    if base.startswith("/"):
        base = base[1:]
    return base


def _extract_chapters(
    book: epub.EpubBook,
    toc_map: dict[str, str],
    toc_basename_map: dict[str, str],
    skip_non_linear: bool,
) -> list[Chapter]:
    chapters: list[Chapter] = []
    index = 0

    for item_id, linear in book.spine:
        if skip_non_linear and _is_non_linear(linear):
            continue

        item = book.get_item_with_id(item_id)
        if item is None:
            _LOGGER.debug("Spine item %s not found in manifest", item_id)
            continue

        if item.get_type() != ITEM_DOCUMENT:
            continue

        href = _get_item_href(item)
        html_title, text = _extract_title_and_text(item.get_content())
        title = _resolve_title(
            href=href,
            toc_map=toc_map,
            toc_basename_map=toc_basename_map,
            html_title=html_title,
            index=index,
        )

        cleaned_text = text.strip()
        if not cleaned_text:
            _LOGGER.debug("Skipping empty spine document: %s", href or item_id)
            continue

        chapters.append(Chapter(index=index, title=title, text=cleaned_text))
        index += 1

    return chapters


def _is_non_linear(linear: object) -> bool:
    if linear is None:
        return False
    if isinstance(linear, str):
        return linear.strip().lower() == "no"
    return not bool(linear)


def _get_item_href(item: object) -> str:
    if hasattr(item, "get_name"):
        try:
            return str(item.get_name())
        except (AttributeError, TypeError, OSError):  # pragma: no cover - defensive
            return ""
    return str(getattr(item, "file_name", "")) or str(getattr(item, "href", ""))


def _resolve_title(
    href: str,
    toc_map: dict[str, str],
    toc_basename_map: dict[str, str],
    html_title: str | None,
    index: int,
) -> str:
    normalized_href = _normalize_href(href)
    if normalized_href:
        if normalized_href in toc_map:
            return toc_map[normalized_href]
        basename = posixpath.basename(normalized_href)
        if basename in toc_basename_map:
            return toc_basename_map[basename]

    if html_title:
        return html_title.strip()

    if normalized_href:
        stem = posixpath.splitext(posixpath.basename(normalized_href))[0]
        if stem:
            return stem.replace("_", " ").replace("-", " ").strip()

    return f"Section {index + 1}"


def _extract_title_and_text(content: bytes | str) -> tuple[str | None, str]:
    soup = BeautifulSoup(content, "html.parser")

    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "svg"]):
        tag.decompose()

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip() or None

    root = soup.body if soup.body else soup
    text = root.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return title, "\n".join(lines)
