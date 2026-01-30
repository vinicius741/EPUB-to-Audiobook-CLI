"""Main CLI entrypoint for epub2audio."""

import argparse
import sys
from typing import Sequence

from .parsers import build_run_parser, build_doctor_parser, build_init_parser
from .commands import run_main, run_doctor_cmd, run_init_cmd


def main(argv: Sequence[str] | None = None) -> int:
    """Main entrypoint for the epub2audio CLI.

    Routes to the appropriate command based on the first argument:
    - No args or unknown first arg: run main pipeline
    - 'doctor': run environment checks
    - 'init': initialize project structure
    """
    argv = list(argv) if argv is not None else sys.argv[1:]

    # Check for subcommands first
    if argv and argv[0] == "doctor":
        args = build_doctor_parser().parse_args(argv[1:])
        return run_doctor_cmd(args)

    if argv and argv[0] == "init":
        args = build_init_parser().parse_args(argv[1:])
        return run_init_cmd(args)

    # Default: run main pipeline (handles both empty argv and file paths)
    args = build_run_parser().parse_args(argv)
    return run_main(args)
