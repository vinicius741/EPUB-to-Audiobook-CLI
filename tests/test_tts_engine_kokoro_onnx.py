from __future__ import annotations

from pathlib import Path

import pytest

from epub2audio.tts_engine import TtsInputError, TtsSizeError
from epub2audio.tts_engine_kokoro_onnx import KokoroOnnxTtsEngine


def test_kokoro_engine_rejects_empty_input(tmp_path: Path) -> None:
    engine = KokoroOnnxTtsEngine(model_id="test", output_dir=tmp_path)
    with pytest.raises(TtsInputError, match="empty or contains no speakable content"):
        engine.synthesize("")


def test_kokoro_engine_enforces_token_limit(tmp_path: Path) -> None:
    engine = KokoroOnnxTtsEngine(model_id="test", output_dir=tmp_path, max_input_tokens=3, max_input_chars=1000)
    with pytest.raises(TtsSizeError, match="Estimated token count"):
        engine.synthesize("One two three four")


def test_kokoro_engine_writes_audio_with_mocked_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = KokoroOnnxTtsEngine(model_id="test", output_dir=tmp_path)
    engine._kokoro = object()  # type: ignore[attr-defined]
    monkeypatch.setattr(engine, "ensure_loaded", lambda: None)
    monkeypatch.setattr(
        "epub2audio.tts_engine_kokoro_onnx._generate_audio",
        lambda *args, **kwargs: ([0.0, 0.2, -0.2, 0.0], 24000, 1),
    )

    out_path = tmp_path / "chunk.wav"
    chunk = engine.synthesize("Hello world.", config={"output_path": out_path})

    assert chunk.path == out_path
    assert out_path.exists()
    assert out_path.stat().st_size > 0
