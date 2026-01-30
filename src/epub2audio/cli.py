"""Command-line interface for epub2audio.

This module provides backward compatibility by re-exporting from the cli package.
The actual CLI implementation has been moved to the cli/ subpackage for better
organization and maintainability.
"""

from .cli import main

__all__ = ["main"]
