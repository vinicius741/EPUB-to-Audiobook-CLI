from __future__ import annotations

from pathlib import Path

import pytest

from epub2audio.config import load_config


def test_load_config_defaults(tmp_path: Path) -> None:
    config = load_config(cwd=tmp_path)
    assert config.source is None
    assert config.paths.epubs == tmp_path / "epubs"
    assert config.paths.out == tmp_path / "out"
    assert config.paths.cache == tmp_path / "cache"
    assert config.paths.logs == tmp_path / "logs"
    assert config.logging.level == "INFO"
    assert config.tts.engine == "mlx"
    assert config.tts.sample_rate == 24000
    assert config.tts.channels == 1


def test_load_config_overrides(tmp_path: Path) -> None:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    config_path = config_dir / "config.toml"
    config_path.write_text(
        """
[paths]
epubs = "input"
[logging]
level = "debug"
console_level = "warning"
[tts]
engine = "mlx"
voice = "narrator"
sample_rate = 44100
channels = 2
""".lstrip()
    )

    config = load_config(config_path, cwd=tmp_path)
    assert config.source == config_path
    assert config.paths.epubs == config_dir / "input"
    assert config.logging.level == "DEBUG"
    assert config.logging.console_level == "WARNING"
    assert config.tts.voice == "narrator"
    assert config.tts.sample_rate == 44100
    assert config.tts.channels == 2


def test_missing_config_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "missing.toml", cwd=tmp_path)
