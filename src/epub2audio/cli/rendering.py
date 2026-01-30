"""Output rendering for epub2audio CLI."""

from pathlib import Path
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from ..config import Config
    from ..pipeline import BookResult


def render_summary(
    config: "Config",
    run_id: str,
    inputs: Sequence[Path],
    results: Sequence[object],
) -> str:
    """Render the overall run summary."""
    from ..config import config_summary

    lines = [
        "epub2audio",
        f"run id: {run_id}",
        f"inputs: {len(inputs)}",
        f"logs: {config.paths.logs}",
        "",
        config_summary(config),
        "",
        render_results_summary(results),
    ]
    return "\n".join(line for line in lines if line is not None)


def render_results_summary(results: Sequence[object]) -> str:
    """Render the results summary."""
    if not results:
        return "No inputs provided. Nothing processed yet."
    if not all(isinstance(result, BookResult) for result in results):
        return f"Processed {len(results)} item(s)."

    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1

    summary = ["Results"]
    summary.append(
        "  "
        + ", ".join(f"{status}={count}" for status, count in sorted(counts.items()))
    )
    for result in results:
        line = f"  - {result.book_slug}: {result.status}"
        if result.output_path is not None:
            line += f" -> {result.output_path}"
        summary.append(line)
    return "\n".join(summary)
