"""Command runners for epub2audio CLI."""

import argparse
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from ..config import Config, LoggingConfig, load_config
from ..config import write_default_config
from ..doctor import DoctorOptions, run_doctor
from ..logging_setup import initialize_logging
from ..pipeline import BookResult, resolve_inputs, run_pipeline
from ..utils import ensure_dir, generate_run_id
from .progress import ProgressDisplay
from .rendering import render_summary


def run_main(args: argparse.Namespace) -> int:
    """Run the main epub2audio pipeline."""
    try:
        config = load_config(args.config, cwd=Path.cwd())
    except (FileNotFoundError, RuntimeError) as exc:
        print(str(exc))
        return 2

    # Apply logging overrides in priority order: --debug > --verbose > --log-level
    if getattr(args, "debug", False):
        config = override_log_level(config, "DEBUG")
    elif getattr(args, "verbose", False):
        config = override_console_level(config, "DEBUG")
    elif args.log_level:
        config = override_log_level(config, args.log_level)

    # Ensure required directories exist
    ensure_dir(config.paths.epubs)
    ensure_dir(config.paths.out)
    ensure_dir(config.paths.cache)

    run_id = generate_run_id()
    log_ctx = initialize_logging(config, run_id)
    logger = log_ctx.logger

    # Default to configured epubs directory if no inputs provided
    input_paths = args.inputs if args.inputs else [config.paths.epubs]
    inputs = resolve_inputs(input_paths)
    progress = ProgressDisplay()

    if not inputs:
        logger.info("No inputs provided")
        progress.print("No inputs found. Place EPUB files in the 'epubs/' folder.")
        return 0

    results = run_pipeline(log_ctx, inputs, config, progress=progress)

    # Print final summary using progress display
    progress.print_summary(results)
    return 0


def run_doctor_cmd(args: argparse.Namespace) -> int:
    """Run the doctor command."""
    try:
        config = load_config(args.config, cwd=Path.cwd())
    except (FileNotFoundError, RuntimeError) as exc:
        print(str(exc))
        return 2

    # Apply logging overrides in priority order: --debug > --verbose > --log-level
    if getattr(args, "debug", False):
        config = override_log_level(config, "DEBUG")
    elif getattr(args, "verbose", False):
        config = override_console_level(config, "DEBUG")
    elif args.log_level:
        config = override_log_level(config, args.log_level)

    options = DoctorOptions(
        smoke_test=args.smoke_test,
        long_text_test=args.long_text_test,
        rtf_test=args.rtf_test,
        verify=args.verify,
        text=args.text,
        output_dir=args.output_dir,
    )
    return run_doctor(config, options)


def run_init_cmd(args: argparse.Namespace) -> int:
    """Initialize epub2audio project structure."""
    cwd = Path.cwd()

    # Define required folders
    folders = {
        "epubs": cwd / "epubs",
        "out": cwd / "out",
        "cache": cwd / "cache",
        "logs": cwd / "logs",
    }

    # Create folders
    created_folders = []
    for name, path in folders.items():
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created_folders.append(name)
        else:
            print(f"  {name}/ already exists")

    if created_folders:
        for name in created_folders:
            print(f"  Created {name}/")
    else:
        print("  All folders already exist")

    # Create config.toml
    config_path = cwd / "config.toml"
    if args.no_config:
        print("  Skipping config.toml creation (--no-config)")
    elif config_path.exists() and not args.force:
        print(f"  config.toml already exists (use --force to overwrite)")
    else:
        write_default_config(config_path)
        if args.force:
            print(f"  Overwrote config.toml")
        else:
            print(f"  Created config.toml")

    print("\nProject initialized. Place EPUB files in the 'epubs/' folder.")
    return 0


def override_log_level(config: Config, level: str) -> Config:
    """Override the logging configuration with a new log level."""
    logging_cfg = LoggingConfig(level=level.upper(), console_level=level.upper())
    return replace(config, logging=logging_cfg)


def override_console_level(config: Config, level: str) -> Config:
    """Override only the console log level (file level remains unchanged)."""
    logging_cfg = LoggingConfig(
        level=config.logging.level,
        console_level=level.upper(),
    )
    return replace(config, logging=logging_cfg)
