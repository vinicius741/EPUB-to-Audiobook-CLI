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
class Config:
    paths: PathsConfig
    logging: LoggingConfig
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
    return Config(paths=paths, logging=logging, source=source)


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
        f"  console level: {config.logging.console_level}"
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
