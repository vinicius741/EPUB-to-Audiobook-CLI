from __future__ import annotations

import json
from pathlib import Path

import pytest
from epub2audio.interfaces import PipelineState
from epub2audio.state_store import JsonStateStore


def test_path_for_sanitizes_book_id(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path)
    # Using a book_id that would be risky if not sanitized or different
    book_id = "../unsafe/book id" 
    
    # Internal method access to verify logic
    path = store._path_for(book_id)
    
    # Should be sanitized to "unsafe-book-id" or similar
    assert path.name == "unsafe-book-id.json"
    assert path.parent == tmp_path


def test_load_returns_none_for_missing_file(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path)
    state = store.load("missing-book")
    assert state is None


def test_load_handles_malformed_json(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path)
    # Create a malformed file manually
    path = store._path_for("malformed")
    path.write_text("{ not valid json }", encoding="utf-8")
    
    with pytest.raises(RuntimeError, match="Failed to read state file"):
        store.load("malformed")


def test_save_and_load_preserves_none_artifacts(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path)
    book_id = "test-book"
    
    state = PipelineState(
        book_id=book_id,
        steps={"step1": True},
        artifacts={"key1": "value1", "key2": None}
    )
    
    store.save(state)
    
    loaded = store.load(book_id)
    assert loaded is not None
    assert loaded.book_id == book_id
    assert loaded.steps == {"step1": True}
    assert loaded.artifacts == {"key1": "value1", "key2": None}


def test_save_is_atomic(tmp_path: Path) -> None:
    store = JsonStateStore(tmp_path)
    book_id = "atomic-book"
    state = PipelineState(book_id=book_id, steps={}, artifacts={})
    
    store.save(state)
    path = store._path_for(book_id)
    assert path.exists()
    
    # Verify no temp file exists
    assert not path.with_suffix(".json.tmp").exists()
