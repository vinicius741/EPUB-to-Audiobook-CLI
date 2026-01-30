"""Argument parser builders for epub2audio CLI."""

import argparse
from pathlib import Path


def build_run_parser() -> argparse.ArgumentParser:
    """Build argument parser for the main run command."""
    parser = argparse.ArgumentParser(
        prog="epub2audio",
        description="EPUB to Audiobook CLI",
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


def build_doctor_parser() -> argparse.ArgumentParser:
    """Build argument parser for the doctor command."""
    parser = argparse.ArgumentParser(
        prog="epub2audio doctor",
        description="Check TTS environment and model readiness",
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
    parser.add_argument(
        "--text",
        type=str,
        default="Hello world.",
        help="Text to synthesize for smoke/RTF tests",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory to write doctor audio output",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run a basic synthesis smoke test",
    )
    parser.add_argument(
        "--rtf-test",
        action="store_true",
        help="Measure real-time factor for a short synthesis",
    )
    parser.add_argument(
        "--long-text-test",
        action="store_true",
        help="Run a long-text resilience test",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run all verification checks",
    )
    return parser


def build_init_parser() -> argparse.ArgumentParser:
    """Build argument parser for the init command."""
    parser = argparse.ArgumentParser(
        prog="epub2audio init",
        description="Initialize epub2audio project structure",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing config.toml if it exists",
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="Skip creating config.toml file",
    )
    return parser
