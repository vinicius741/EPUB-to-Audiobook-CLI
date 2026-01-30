"""State store for resumable pipeline runs."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from .interfaces import PipelineState, StateStore
from .utils import ensure_dir, slugify


class JsonStateStore(StateStore):
    def __init__(self, root: Path) -> None:
        self.root = ensure_dir(root)

    def load(self, book_id: str) -> PipelineState | None:
        path = self._path_for(book_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Failed to read state file {path}: {exc}") from exc
        steps = _coerce_steps(payload.get("steps"))
        artifacts = _coerce_artifacts(payload.get("artifacts"))
        return PipelineState(book_id=book_id, steps=steps, artifacts=artifacts)

    def save(self, state: PipelineState) -> None:
        path = self._path_for(state.book_id)
        payload = _serialize_state(state)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), "utf-8")
        tmp_path.replace(path)

    def _path_for(self, book_id: str) -> Path:
        return self.root / f"{slugify(book_id)}.json"


def _serialize_state(state: PipelineState) -> Mapping[str, Any]:
    payload = {
        "version": 1,
        "book_id": state.book_id,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "steps": dict(state.steps),
        "artifacts": dict(state.artifacts or {}),
    }
    return payload


def _coerce_steps(raw: object) -> dict[str, bool]:
    if not isinstance(raw, dict):
        return {}
    steps: dict[str, bool] = {}
    for key, value in raw.items():
        steps[str(key)] = bool(value)
    return steps


def _coerce_artifacts(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    artifacts: dict[str, str | None] = {}
    for key, value in raw.items():
        artifacts[str(key)] = value if value is None else str(value)
    return artifacts
