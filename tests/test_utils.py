from __future__ import annotations

from epub2audio.utils import slugify


def test_slugify_basic() -> None:
    assert slugify("Hello World") == "hello-world"
    assert slugify("MiXeD  Case") == "mixed-case"


def test_slugify_fallback() -> None:
    assert slugify("   !!!   ") == "book"
    assert slugify("") == "book"


def test_slugify_preserves_words() -> None:
    assert slugify("Already-Slug") == "already-slug"
