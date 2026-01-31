"""Audio cache layout and deterministic chunk hashing."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .utils import ensure_dir


def chunk_cache_key(
    text: str,
    *,
    model_id: str,
    voice: str | None,
    lang_code: str | None,
    ref_audio_id: str | None,
    ref_text: str | None,
    speed: float,
    sample_rate: int,
    channels: int,
) -> str:
    payload = {
        "v": 1,
        "model_id": model_id,
        "voice": voice or "",
        "lang_code": lang_code or "",
        "ref_audio_id": ref_audio_id or "",
        "ref_text": ref_text or "",
        "speed": round(speed, 4),
        "sample_rate": sample_rate,
        "channels": channels,
        "text": text,
    }
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"tts_{digest}"


@dataclass(frozen=True)
class AudioCacheLayout:
    root: Path

    @property
    def tts_dir(self) -> Path:
        return self.root / "tts"

    @property
    def chunk_dir(self) -> Path:
        return self.tts_dir / "chunks"

    @property
    def chapter_dir(self) -> Path:
        return self.root / "chapters"

    def chunk_path(self, key: str, ext: str = "wav") -> Path:
        prefix = key[:2] if len(key) >= 2 else "00"
        return self.chunk_dir / prefix / f"{key}.{ext}"

    def chapter_path(self, book_slug: str, chapter_index: int, stage: str) -> Path:
        safe_stage = stage.replace(" ", "_")
        return self.chapter_dir / book_slug / f"chapter_{chapter_index:03d}_{safe_stage}.wav"

    def ensure_chunk_dir(self, key: str) -> Path:
        path = self.chunk_path(key).parent
        return ensure_dir(path)

    def ensure_chapter_dir(self, book_slug: str) -> Path:
        path = self.chapter_dir / book_slug
        return ensure_dir(path)
