"""Command-line interface for epub2audio."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from .config import Config, LoggingConfig, config_summary, load_config
from .logging_setup import initialize_logging
from .pipeline import resolve_inputs, run_pipeline
from .utils import generate_run_id


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config, cwd=Path.cwd())
    except (FileNotFoundError, RuntimeError) as exc:
        print(str(exc))
        return 2

    if args.log_level:
        config = _override_log_level(config, args.log_level)

    run_id = generate_run_id()
    log_ctx = initialize_logging(config, run_id)
    logger = log_ctx.logger

    inputs = resolve_inputs(args.inputs)
    logger.info("Starting stub run")
    if not inputs:
        logger.info("No inputs provided")
        print(_render_summary(config, run_id, inputs, results=[]))
        return 0

    results = run_pipeline(log_ctx, inputs)
    print(_render_summary(config, run_id, inputs, results))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="epub2audio",
        description="EPUB to Audiobook CLI (Phase 0 stub)",
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        type=Path,
        help="EPUB files or folders to process",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to config.toml (optional)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        help="Override log level (e.g. INFO, DEBUG)",
    )
    parser.add_argument("--version", action="version", version="epub2audio 0.1.0")
    return parser


def _override_log_level(config: Config, level: str) -> Config:
    logging_cfg = LoggingConfig(level=level.upper(), console_level=level.upper())
    return replace(config, logging=logging_cfg)


def _render_summary(
    config: Config,
    run_id: str,
    inputs: Sequence[Path],
    results: Sequence[object],
) -> str:
    lines = [
        "epub2audio (stub)",
        f"run id: {run_id}",
        f"inputs: {len(inputs)}",
        f"logs: {config.paths.logs}",
        "",
        config_summary(config),
        "",
        _render_results_summary(results),
    ]
    return "\n".join(line for line in lines if line is not None)


def _render_results_summary(results: Sequence[object]) -> str:
    if not results:
        return "No inputs provided. Nothing processed yet."
    return f"Stubbed {len(results)} item(s). No real processing performed."
