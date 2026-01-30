from __future__ import annotations

from pathlib import Path

from epub2audio.interfaces import AudioChunk, TtsEngine
from epub2audio.tts_engine import TtsInputError, TtsTransientError
from epub2audio.tts_pipeline import TtsSynthesisSettings, synthesize_text


def test_synthesize_text_splits_long_text(tmp_path: Path) -> None:
    calls: list[str] = []

    class DummyEngine(TtsEngine):
        def synthesize(self, text: str, voice: str | None = None, config: dict | None = None) -> AudioChunk:
            calls.append(text)
            return AudioChunk(index=0, path=tmp_path / f"{len(calls)}.wav")

    settings = TtsSynthesisSettings(
        max_chars=50,
        min_chars=10,
        hard_max_chars=60,
        max_retries=1,
        backoff_base=0.0,
        backoff_jitter=0.0,
        sample_rate=24000,
        channels=1,
        speed=1.0,
        lang_code=None,
    )

    text = "Sentence one. Sentence two. Sentence three. Sentence four."
    chunks = synthesize_text(text, DummyEngine(), settings, sleep_fn=lambda _: None)

    assert len(chunks) >= 2
    assert len(calls) >= 2


def test_transient_retry(tmp_path: Path) -> None:
    attempts = {"count": 0}

    class DummyEngine(TtsEngine):
        def synthesize(self, text: str, voice: str | None = None, config: dict | None = None) -> AudioChunk:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise TtsTransientError("temporary")
            return AudioChunk(index=0, path=tmp_path / "ok.wav")

    settings = TtsSynthesisSettings(
        max_chars=200,
        min_chars=10,
        hard_max_chars=None,
        max_retries=3,
        backoff_base=0.0,
        backoff_jitter=0.0,
        sample_rate=24000,
        channels=1,
        speed=1.0,
        lang_code=None,
    )

    chunks = synthesize_text("Hello world.", DummyEngine(), settings, sleep_fn=lambda _: None)
    assert len(chunks) == 1
    assert attempts["count"] == 3


def test_invalid_input_skips(tmp_path: Path) -> None:
    calls: list[str] = []

    class DummyEngine(TtsEngine):
        def synthesize(self, text: str, voice: str | None = None, config: dict | None = None) -> AudioChunk:
            calls.append(text)
            raise TtsInputError("empty")

    settings = TtsSynthesisSettings(
        max_chars=200,
        min_chars=10,
        hard_max_chars=None,
        max_retries=1,
        backoff_base=0.0,
        backoff_jitter=0.0,
        sample_rate=24000,
        channels=1,
        speed=1.0,
        lang_code=None,
    )

    chunks = synthesize_text("!!!", DummyEngine(), settings, sleep_fn=lambda _: None)
    assert chunks == []
    assert calls
