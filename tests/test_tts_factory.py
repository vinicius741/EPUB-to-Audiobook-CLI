from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from epub2audio.config import load_config
from epub2audio.tts_engine import MlxTtsEngine, TtsModelError
from epub2audio.tts_engine_kokoro_onnx import KokoroOnnxTtsEngine
from epub2audio.tts_factory import backend_diagnostics, build_tts_engine, model_cache_status


def _config(tmp_path: Path):
    return load_config(cwd=tmp_path)


def test_build_tts_engine_kokoro_default(tmp_path: Path) -> None:
    config = _config(tmp_path)
    engine = build_tts_engine(config, tmp_path / "out")
    assert isinstance(engine, KokoroOnnxTtsEngine)


def test_build_tts_engine_mlx(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config = replace(config, tts=replace(config.tts, engine="mlx", model_id="mlx-community/test"))
    engine = build_tts_engine(config, tmp_path / "out")
    assert isinstance(engine, MlxTtsEngine)


def test_build_tts_engine_unsupported(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config = replace(config, tts=replace(config.tts, engine="bad_engine"))
    with pytest.raises(TtsModelError, match="Unsupported TTS engine"):
        build_tts_engine(config, tmp_path / "out")


def test_backend_diagnostics_reports_kokoro_checks(tmp_path: Path) -> None:
    config = _config(tmp_path)
    checks = backend_diagnostics(config)
    names = {check.name for check in checks}
    assert "TTS backend" in names
    assert "ONNX providers" in names


def test_model_cache_status_reports_missing_required_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hub = tmp_path / "hub"
    model_root = hub / "models--onnx-community--Kokoro-82M-v1.0-ONNX"
    snapshot = model_root / "snapshots" / "hash123"
    snapshot.mkdir(parents=True)
    (snapshot / "model_q8f16.onnx").write_text("x")

    monkeypatch.setenv("HF_HUB_CACHE", str(hub))
    status = model_cache_status(
        "onnx-community/Kokoro-82M-v1.0-ONNX",
        required_files=("model_q8f16.onnx", "voices-v1.0.bin"),
    )

    assert status.path == model_root
    assert status.missing_files == ("voices-v1.0.bin",)
