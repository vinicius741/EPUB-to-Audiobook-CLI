"""Small utilities shared across modules."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    cleaned = _SLUG_RE.sub("-", value.strip().lower())
    cleaned = cleaned.strip("-")
    return cleaned or "book"


def generate_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
