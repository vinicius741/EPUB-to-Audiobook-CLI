"""Tests for state_store module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from epub2audio.interfaces import PipelineState
from epub2audio.state_store import (
    JsonStateStore,
    _coerce_artifacts,
    _coerce_steps,
    _serialize_state,
)


class TestJsonStateStore:
    """Tests for JsonStateStore class."""

    def test_init_creates_root_directory(self, tmp_path: Path) -> None:
        """Store initialization should create the root directory if it doesn't exist."""
        state_dir = tmp_path / "state"
        store = JsonStateStore(root=state_dir)
        assert state_dir.exists()
        assert state_dir.is_dir()

    def test_path_for_sanitizes_book_id(self, tmp_path: Path) -> None:
        """Path generation should sanitize book_id using slugify."""
        store = JsonStateStore(tmp_path)
        book_id = "../unsafe/book id"
        path = store._path_for(book_id)
        assert path.name == "unsafe-book-id.json"
        assert path.parent == tmp_path

    def test_load_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        """Loading a non-existent state should return None."""
        store = JsonStateStore(tmp_path)
        state = store.load("missing-book")
        assert state is None

    def test_load_handles_malformed_json(self, tmp_path: Path) -> None:
        """Loading malformed JSON should raise RuntimeError."""
        store = JsonStateStore(tmp_path)
        path = store._path_for("malformed")
        path.write_text("{ not valid json }", encoding="utf-8")

        with pytest.raises(RuntimeError, match="Failed to read state file"):
            store.load("malformed")

    def test_save_and_load_preserves_state(self, tmp_path: Path) -> None:
        """Saving and loading should preserve state data."""
        store = JsonStateStore(tmp_path)
        book_id = "test-book"

        state = PipelineState(
            book_id=book_id,
            steps={"step1": True, "step2": False},
            artifacts={"key1": "value1", "key2": "value2"}
        )

        store.save(state)
        loaded = store.load(book_id)

        assert loaded is not None
        assert loaded.book_id == book_id
        assert loaded.steps == {"step1": True, "step2": False}
        assert loaded.artifacts == {"key1": "value1", "key2": "value2"}

    def test_save_and_load_preserves_none_artifacts(self, tmp_path: Path) -> None:
        """Saving and loading should preserve None values in artifacts."""
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
        assert loaded.artifacts == {"key1": "value1", "key2": None}

    def test_save_overwrites_existing_state(self, tmp_path: Path) -> None:
        """Saving should overwrite existing state file."""
        store = JsonStateStore(tmp_path)
        book_id = "test-book"

        state1 = PipelineState(
            book_id=book_id,
            steps={"step1": True},
            artifacts={"key1": "value1"}
        )
        state2 = PipelineState(
            book_id=book_id,
            steps={"step1": True, "step2": True},
            artifacts={"key1": "value1", "key2": "value2"}
        )

        store.save(state1)
        store.save(state2)

        loaded = store.load(book_id)
        assert loaded is not None
        assert loaded.steps == {"step1": True, "step2": True}
        assert "key2" in loaded.artifacts

    def test_save_is_atomic(self, tmp_path: Path) -> None:
        """Save should use atomic write (temp file then rename)."""
        store = JsonStateStore(tmp_path)
        book_id = "atomic-book"
        state = PipelineState(book_id=book_id, steps={}, artifacts={})

        store.save(state)
        path = store._path_for(book_id)
        assert path.exists()

        # Verify no temp file exists after successful save
        assert not path.with_suffix(".json.tmp").exists()

    def test_save_creates_json_file(self, tmp_path: Path) -> None:
        """Saved file should be valid JSON."""
        store = JsonStateStore(tmp_path)
        book_id = "test-book"
        state = PipelineState(
            book_id=book_id,
            steps={"step1": True},
            artifacts={"key1": "value1"}
        )

        store.save(state)
        path = store._path_for(book_id)

        # Should be valid JSON
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["book_id"] == book_id
        assert data["steps"]["step1"] is True

    def test_load_with_empty_steps_and_artifacts(self, tmp_path: Path) -> None:
        """Loading state with empty steps and artifacts should work."""
        store = JsonStateStore(tmp_path)
        book_id = "empty-book"

        # Manually create a minimal state file
        path = store._path_for(book_id)
        minimal_state = {
            "version": 1,
            "book_id": book_id,
            "updated_at": "2024-01-01T00:00:00+00:00",
            "steps": {},
            "artifacts": {}
        }
        path.write_text(json.dumps(minimal_state), encoding="utf-8")

        loaded = store.load(book_id)
        assert loaded is not None
        assert loaded.book_id == book_id
        assert loaded.steps == {}
        assert loaded.artifacts == {}

    def test_load_ignores_unknown_fields(self, tmp_path: Path) -> None:
        """Loading should ignore unknown fields in JSON (forward compatibility)."""
        store = JsonStateStore(tmp_path)
        book_id = "future-book"

        # Create a state file with extra unknown fields
        path = store._path_for(book_id)
        state_with_extra = {
            "version": 1,
            "book_id": book_id,
            "updated_at": "2024-01-01T00:00:00+00:00",
            "steps": {"step1": True},
            "artifacts": {},
            "unknown_field": "should be ignored",
            "future_version_data": {"nested": "value"}
        }
        path.write_text(json.dumps(state_with_extra), encoding="utf-8")

        loaded = store.load(book_id)
        assert loaded is not None
        assert loaded.steps == {"step1": True}


class TestCoerceSteps:
    """Tests for _coerce_steps helper function."""

    def test_coerce_steps_with_valid_dict(self) -> None:
        """Valid dict should be coerced properly."""
        raw = {"step1": True, "step2": False, "step3": 1}
        result = _coerce_steps(raw)
        assert result == {"step1": True, "step2": False, "step3": True}

    def test_coerce_steps_with_non_dict_returns_empty(self) -> None:
        """Non-dict input should return empty dict."""
        assert _coerce_steps(None) == {}
        assert _coerce_steps("not a dict") == {}
        assert _coerce_steps([1, 2, 3]) == {}
        assert _coerce_steps(123) == {}

    def test_coerce_steps_converts_keys_to_strings(self) -> None:
        """Keys should be converted to strings."""
        raw = {1: True, 2.5: False}
        result = _coerce_steps(raw)
        assert result == {"1": True, "2.5": False}

    def test_coerce_steps_converts_values_to_bool(self) -> None:
        """Values should be converted to bool."""
        raw = {"a": 1, "b": 0, "c": "yes", "d": ""}
        result = _coerce_steps(raw)
        assert result == {"a": True, "b": False, "c": True, "d": False}


class TestCoerceArtifacts:
    """Tests for _coerce_artifacts helper function."""

    def test_coerce_artifacts_with_valid_dict(self) -> None:
        """Valid dict should be coerced properly."""
        raw = {"key1": "value1", "key2": None}
        result = _coerce_artifacts(raw)
        assert result == {"key1": "value1", "key2": None}

    def test_coerce_artifacts_with_non_dict_returns_empty(self) -> None:
        """Non-dict input should return empty dict."""
        assert _coerce_artifacts(None) == {}
        assert _coerce_artifacts("not a dict") == {}
        assert _coerce_artifacts([1, 2, 3]) == {}
        assert _coerce_artifacts(123) == {}

    def test_coerce_artifacts_converts_keys_to_strings(self) -> None:
        """Keys should be converted to strings."""
        raw = {1: "value1", 2.5: "value2"}
        result = _coerce_artifacts(raw)
        assert result == {"1": "value1", "2.5": "value2"}

    def test_coerce_artifacts_preserves_none_values(self) -> None:
        """None values should be preserved."""
        raw = {"key1": None, "key2": "value2"}
        result = _coerce_artifacts(raw)
        assert result == {"key1": None, "key2": "value2"}

    def test_coerce_artifacts_converts_values_to_strings_or_none(self) -> None:
        """Values should be converted to strings or None."""
        raw = {"a": 123, "b": 45.6, "c": True, "d": None}
        result = _coerce_artifacts(raw)
        assert result == {"a": "123", "b": "45.6", "c": "True", "d": None}


class TestSerializeState:
    """Tests for _serialize_state helper function."""

    def test_serialize_state_includes_version(self) -> None:
        """Serialized state should include version."""
        state = PipelineState(book_id="test", steps={}, artifacts=None)
        result = _serialize_state(state)
        assert result["version"] == 1

    def test_serialize_state_includes_book_id(self) -> None:
        """Serialized state should include book_id."""
        state = PipelineState(book_id="test-book", steps={}, artifacts=None)
        result = _serialize_state(state)
        assert result["book_id"] == "test-book"

    def test_serialize_state_includes_timestamp(self) -> None:
        """Serialized state should include ISO timestamp."""
        state = PipelineState(book_id="test", steps={}, artifacts=None)
        result = _serialize_state(state)
        assert "updated_at" in result
        # Should be a valid ISO format timestamp
        assert result["updated_at"].startswith("20")

    def test_serialize_state_converts_steps_to_dict(self) -> None:
        """Steps mapping should be converted to dict."""
        state = PipelineState(
            book_id="test",
            steps={"step1": True, "step2": False},
            artifacts=None
        )
        result = _serialize_state(state)
        assert result["steps"] == {"step1": True, "step2": False}

    def test_serialize_state_converts_none_artifacts_to_empty_dict(self) -> None:
        """None artifacts should be serialized as empty dict."""
        state = PipelineState(book_id="test", steps={}, artifacts=None)
        result = _serialize_state(state)
        assert result["artifacts"] == {}

    def test_serialize_state_converts_artifacts_to_dict(self) -> None:
        """Artifacts mapping should be converted to dict."""
        state = PipelineState(
            book_id="test",
            steps={},
            artifacts={"key1": "value1", "key2": None}
        )
        result = _serialize_state(state)
        assert result["artifacts"] == {"key1": "value1", "key2": None}
