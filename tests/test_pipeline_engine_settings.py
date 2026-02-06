from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from epub2audio.config import load_config
from epub2audio.pipeline import _build_settings


def test_build_settings_model_id_includes_engine_prefix(tmp_path: Path) -> None:
    config = load_config(cwd=tmp_path)
    default_settings = _build_settings(config)
    assert default_settings.model_id == "kokoro_onnx:onnx-community/Kokoro-82M-v1.0-ONNX"

    mlx_config = replace(
        config,
        tts=replace(
            config.tts,
            engine="mlx",
            model_id="mlx-community/example-model",
        ),
    )
    mlx_settings = _build_settings(mlx_config)
    assert mlx_settings.model_id == "mlx:mlx-community/example-model"
