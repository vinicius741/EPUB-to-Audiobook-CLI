"""Configuration loading and defaults."""

from __future__ import annotations

from dataclasses import dataclass
import copy
from pathlib import Path
from typing import Any, Mapping

_TOML = None
try:  # pragma: no cover - module availability depends on Python version
    import tomllib as _TOML
except ModuleNotFoundError:  # pragma: no cover - fallback for older Python
    try:
        import tomli as _TOML
    except ModuleNotFoundError:
        _TOML = None


DEFAULT_CONFIG: dict[str, Any] = {
    "paths": {
        "epubs": "epubs",
        "out": "out",
        "cache": "cache",
        "logs": "logs",
    },
    "logging": {
        "level": "INFO",
        "console_level": "INFO",
    },
    "tts": {
        "engine": "mlx",
        "model_id": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit",
        "voice": None,
        "lang_code": None,
        "speed": 1.0,
        "sample_rate": 24000,
        "channels": 1,
        "max_chars": 1000,
        "min_chars": 200,
        "hard_max_chars": 1250,
        "max_retries": 2,
        "backoff_base": 0.5,
        "backoff_jitter": 0.1,
        "output_format": "wav",
    },
    "audio": {
        "silence_ms": 250,
        "normalize": True,
        "target_lufs": -23.0,
        "lra": 7.0,
        "true_peak": -1.0,
    },
}


@dataclass(frozen=True)
class PathsConfig:
    epubs: Path
    out: Path
    cache: Path
    logs: Path


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    console_level: str


@dataclass(frozen=True)
class TtsConfig:
    engine: str
    model_id: str
    voice: str | None
    lang_code: str | None
    speed: float
    sample_rate: int
    channels: int
    max_chars: int
    min_chars: int
    hard_max_chars: int | None
    max_retries: int
    backoff_base: float
    backoff_jitter: float
    output_format: str


@dataclass(frozen=True)
class AudioConfig:
    silence_ms: int
    normalize: bool
    target_lufs: float
    lra: float
    true_peak: float


@dataclass(frozen=True)
class Config:
    paths: PathsConfig
    logging: LoggingConfig
    tts: TtsConfig
    audio: AudioConfig
    source: Path | None = None


def load_config(config_path: Path | None = None, *, cwd: Path | None = None) -> Config:
    cwd = cwd or Path.cwd()
    source: Path | None = None
    raw: Mapping[str, Any] = {}

    if config_path is None:
        candidate = cwd / "config.toml"
        if candidate.exists():
            source = candidate
            raw = _read_toml(candidate)
    else:
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        source = config_path
        raw = _read_toml(config_path)

    merged = _deep_merge(_clone_defaults(DEFAULT_CONFIG), raw)
    base_dir = source.parent if source is not None else cwd

    paths = PathsConfig(
        epubs=_resolve_path(base_dir, merged["paths"]["epubs"]),
        out=_resolve_path(base_dir, merged["paths"]["out"]),
        cache=_resolve_path(base_dir, merged["paths"]["cache"]),
        logs=_resolve_path(base_dir, merged["paths"]["logs"]),
    )
    logging = LoggingConfig(
        level=str(merged["logging"]["level"]).upper(),
        console_level=str(merged["logging"]["console_level"]).upper(),
    )
    tts_raw = merged.get("tts", {})
    tts = TtsConfig(
        engine=str(tts_raw.get("engine", "mlx")),
        model_id=str(tts_raw.get("model_id", DEFAULT_CONFIG["tts"]["model_id"])),
        voice=_optional_str(tts_raw.get("voice")),
        lang_code=_optional_str(tts_raw.get("lang_code")),
        speed=float(tts_raw.get("speed", 1.0)),
        sample_rate=int(tts_raw.get("sample_rate", 24000)),
        channels=int(tts_raw.get("channels", 1)),
        max_chars=int(tts_raw.get("max_chars", 1000)),
        min_chars=int(tts_raw.get("min_chars", 200)),
        hard_max_chars=_optional_int(tts_raw.get("hard_max_chars")),
        max_retries=int(tts_raw.get("max_retries", 2)),
        backoff_base=float(tts_raw.get("backoff_base", 0.5)),
        backoff_jitter=float(tts_raw.get("backoff_jitter", 0.1)),
        output_format=str(tts_raw.get("output_format", "wav")).lower(),
    )
    audio_raw = merged.get("audio", {})
    audio = AudioConfig(
        silence_ms=int(audio_raw.get("silence_ms", 250)),
        normalize=bool(audio_raw.get("normalize", True)),
        target_lufs=float(audio_raw.get("target_lufs", -23.0)),
        lra=float(audio_raw.get("lra", 7.0)),
        true_peak=float(audio_raw.get("true_peak", -1.0)),
    )
    return Config(paths=paths, logging=logging, tts=tts, audio=audio, source=source)


def config_summary(config: Config) -> str:
    source = str(config.source) if config.source is not None else "defaults"
    return (
        "Config\n"
        f"  source: {source}\n"
        f"  epubs: {config.paths.epubs}\n"
        f"  out: {config.paths.out}\n"
        f"  cache: {config.paths.cache}\n"
        f"  logs: {config.paths.logs}\n"
        f"  log level: {config.logging.level}\n"
        f"  console level: {config.logging.console_level}\n"
        "TTS\n"
        f"  engine: {config.tts.engine}\n"
        f"  model: {config.tts.model_id}\n"
        f"  voice: {config.tts.voice or 'default'}\n"
        f"  lang_code: {config.tts.lang_code or 'default'}\n"
        f"  speed: {config.tts.speed}\n"
        f"  sample_rate: {config.tts.sample_rate}\n"
        f"  channels: {config.tts.channels}\n"
        f"  max_chars: {config.tts.max_chars}\n"
        f"  min_chars: {config.tts.min_chars}\n"
        f"  hard_max_chars: {config.tts.hard_max_chars or 'auto'}\n"
        f"  max_retries: {config.tts.max_retries}\n"
        f"  output_format: {config.tts.output_format}\n"
        "Audio\n"
        f"  silence_ms: {config.audio.silence_ms}\n"
        f"  normalize: {config.audio.normalize}\n"
        f"  target_lufs: {config.audio.target_lufs}\n"
        f"  lra: {config.audio.lra}\n"
        f"  true_peak: {config.audio.true_peak}"
    )


def _read_toml(path: Path) -> Mapping[str, Any]:
    if _TOML is None:  # pragma: no cover - defensive guard
        raise RuntimeError("TOML parser unavailable. Install tomli or use Python 3.11+.")
    with path.open("rb") as handle:
        return _TOML.load(handle)


def _resolve_path(base_dir: Path, value: Any) -> Path:
    path = value if isinstance(value, Path) else Path(str(value))
    return path if path.is_absolute() else base_dir / path


def _clone_defaults(defaults: Mapping[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(defaults)


def _deep_merge(base: Mapping[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned or cleaned.lower() in {"none", "null"}:
            return None
        return cleaned
    return str(value)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
