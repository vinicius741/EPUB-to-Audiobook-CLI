"""Tests for audio_cache module (hash and layout)."""

from __future__ import annotations

from pathlib import Path

import pytest
from epub2audio.audio_cache import AudioCacheLayout, chunk_cache_key


class TestChunkCacheKey:
    """Tests for chunk_cache_key deterministic hash function."""

    def test_same_input_produces_same_hash(self) -> None:
        """Identical inputs should produce identical cache keys."""
        params = {
            "text": "Hello world",
            "model_id": "mlx-community/Qwen3-TTS-12Hz-1.7B-4bit",
            "voice": "default",
            "lang_code": "en",
            "ref_audio_id": None,
            "ref_text": None,
            "speed": 1.0,
            "sample_rate": 24000,
            "channels": 1,
        }
        key1 = chunk_cache_key(**params)
        key2 = chunk_cache_key(**params)
        assert key1 == key2

    def test_different_text_produces_different_hash(self) -> None:
        """Different text should produce different cache keys."""
        base_params = {
            "model_id": "test-model",
            "voice": "default",
            "lang_code": "en",
            "ref_audio_id": None,
            "ref_text": None,
            "speed": 1.0,
            "sample_rate": 24000,
            "channels": 1,
        }
        key1 = chunk_cache_key(text="First text", **base_params)
        key2 = chunk_cache_key(text="Second text", **base_params)
        assert key1 != key2

    def test_different_model_id_produces_different_hash(self) -> None:
        """Different model IDs should produce different cache keys."""
        base_params = {
            "text": "Test text",
            "voice": "default",
            "lang_code": "en",
            "ref_audio_id": None,
            "ref_text": None,
            "speed": 1.0,
            "sample_rate": 24000,
            "channels": 1,
        }
        key1 = chunk_cache_key(model_id="model-a", **base_params)
        key2 = chunk_cache_key(model_id="model-b", **base_params)
        assert key1 != key2

    def test_different_voice_produces_different_hash(self) -> None:
        """Different voices should produce different cache keys."""
        base_params = {
            "text": "Test text",
            "model_id": "test-model",
            "lang_code": "en",
            "ref_audio_id": None,
            "ref_text": None,
            "speed": 1.0,
            "sample_rate": 24000,
            "channels": 1,
        }
        key1 = chunk_cache_key(voice="voice1", **base_params)
        key2 = chunk_cache_key(voice="voice2", **base_params)
        assert key1 != key2

    def test_none_voice_treated_same_as_empty_string(self) -> None:
        """None voice should be treated the same as empty string."""
        base_params = {
            "text": "Test text",
            "model_id": "test-model",
            "lang_code": "en",
            "ref_audio_id": None,
            "ref_text": None,
            "speed": 1.0,
            "sample_rate": 24000,
            "channels": 1,
        }
        key1 = chunk_cache_key(voice=None, **base_params)
        key2 = chunk_cache_key(voice="", **base_params)
        assert key1 == key2

    def test_none_lang_code_treated_same_as_empty_string(self) -> None:
        """None lang_code should be treated the same as empty string."""
        base_params = {
            "text": "Test text",
            "model_id": "test-model",
            "voice": "default",
            "ref_audio_id": None,
            "ref_text": None,
            "speed": 1.0,
            "sample_rate": 24000,
            "channels": 1,
        }
        key1 = chunk_cache_key(lang_code=None, **base_params)
        key2 = chunk_cache_key(lang_code="", **base_params)
        assert key1 == key2

    def test_different_speed_produces_different_hash(self) -> None:
        """Different speeds should produce different cache keys."""
        base_params = {
            "text": "Test text",
            "model_id": "test-model",
            "voice": "default",
            "lang_code": "en",
            "ref_audio_id": None,
            "ref_text": None,
            "sample_rate": 24000,
            "channels": 1,
        }
        key1 = chunk_cache_key(speed=1.0, **base_params)
        key2 = chunk_cache_key(speed=1.5, **base_params)
        assert key1 != key2

    def test_speed_rounded_to_four_decimal_places(self) -> None:
        """Speed should be rounded to 4 decimal places for hashing."""
        base_params = {
            "text": "Test text",
            "model_id": "test-model",
            "voice": "default",
            "lang_code": "en",
            "ref_audio_id": None,
            "ref_text": None,
            "sample_rate": 24000,
            "channels": 1,
        }
        key1 = chunk_cache_key(speed=1.00001, **base_params)
        key2 = chunk_cache_key(speed=1.0, **base_params)
        assert key1 == key2

    def test_different_sample_rate_produces_different_hash(self) -> None:
        """Different sample rates should produce different cache keys."""
        base_params = {
            "text": "Test text",
            "model_id": "test-model",
            "voice": "default",
            "lang_code": "en",
            "ref_audio_id": None,
            "ref_text": None,
            "speed": 1.0,
            "channels": 1,
        }
        key1 = chunk_cache_key(sample_rate=24000, **base_params)
        key2 = chunk_cache_key(sample_rate=44100, **base_params)
        assert key1 != key2

    def test_different_channels_produces_different_hash(self) -> None:
        """Different channel counts should produce different cache keys."""
        base_params = {
            "text": "Test text",
            "model_id": "test-model",
            "voice": "default",
            "lang_code": "en",
            "ref_audio_id": None,
            "ref_text": None,
            "speed": 1.0,
            "sample_rate": 24000,
        }
        key1 = chunk_cache_key(channels=1, **base_params)
        key2 = chunk_cache_key(channels=2, **base_params)
        assert key1 != key2

    def test_hash_key_starts_with_tts_prefix(self) -> None:
        """All cache keys should start with 'tts_' prefix."""
        key = chunk_cache_key(
            text="Test",
            model_id="model",
            voice="voice",
            lang_code="en",
            ref_audio_id=None,
            ref_text=None,
            speed=1.0,
            sample_rate=24000,
            channels=1,
        )
        assert key.startswith("tts_")

    def test_hash_key_is_sha256_hex_string(self) -> None:
        """Cache key should be a hex string of expected length (64 chars for SHA256)."""
        key = chunk_cache_key(
            text="Test",
            model_id="model",
            voice="voice",
            lang_code="en",
            ref_audio_id=None,
            ref_text=None,
            speed=1.0,
            sample_rate=24000,
            channels=1,
        )
        # 'tts_' prefix + 64 hex chars
        assert len(key) == 4 + 64
        # Should be valid hex
        assert all(c in "0123456789abcdef" for c in key[4:])

    def test_unicode_text_handled_correctly(self) -> None:
        """Unicode text should be handled correctly."""
        base_params = {
            "model_id": "test-model",
            "voice": "default",
            "lang_code": "en",
            "ref_audio_id": None,
            "ref_text": None,
            "speed": 1.0,
            "sample_rate": 24000,
            "channels": 1,
        }
        key1 = chunk_cache_key(text="Hello 世界", **base_params)
        key2 = chunk_cache_key(text="Hello 世界", **base_params)
        assert key1 == key2
        key3 = chunk_cache_key(text="Hello World", **base_params)
        assert key1 != key3


class TestAudioCacheLayout:
    """Tests for AudioCacheLayout directory and path management."""

    def test_layout_properties_return_expected_paths(self, tmp_path: Path) -> None:
        """Layout properties should return correct directory paths."""
        layout = AudioCacheLayout(root=tmp_path)
        assert layout.tts_dir == tmp_path / "tts"
        assert layout.chunk_dir == tmp_path / "tts" / "chunks"
        assert layout.chapter_dir == tmp_path / "chapters"

    def test_chunk_path_uses_prefix_directory(self, tmp_path: Path) -> None:
        """Chunk path should use first 2 chars of key as prefix."""
        layout = AudioCacheLayout(root=tmp_path)
        key = "tts_1234567890abcdef"
        path = layout.chunk_path(key)
        assert path == tmp_path / "tts" / "chunks" / "tt" / "tts_1234567890abcdef.wav"

    def test_chunk_path_with_short_key(self, tmp_path: Path) -> None:
        """Chunk path with short key uses first 2 chars as prefix."""
        layout = AudioCacheLayout(root=tmp_path)
        key = "tts_a"
        path = layout.chunk_path(key)
        # 'tts_a' has 5 chars, so first 2 chars are 'tt'
        assert path == tmp_path / "tts" / "chunks" / "tt" / "tts_a.wav"

    def test_chunk_path_with_very_short_key(self, tmp_path: Path) -> None:
        """Chunk path with very short key (<2 chars) uses '00' as prefix."""
        layout = AudioCacheLayout(root=tmp_path)
        key = "x"
        path = layout.chunk_path(key)
        assert path == tmp_path / "tts" / "chunks" / "00" / "x.wav"

    def test_chunk_path_with_custom_extension(self, tmp_path: Path) -> None:
        """Chunk path should support custom file extensions."""
        layout = AudioCacheLayout(root=tmp_path)
        key = "tts_1234567890abcdef"
        path = layout.chunk_path(key, ext="mp3")
        assert path.suffix == ".mp3"
        assert path == tmp_path / "tts" / "chunks" / "tt" / "tts_1234567890abcdef.mp3"

    def test_chapter_path_includes_book_slug_and_index(self, tmp_path: Path) -> None:
        """Chapter path should include book slug and zero-padded index."""
        layout = AudioCacheLayout(root=tmp_path)
        path = layout.chapter_path("test-book", 5, "final")
        assert path == tmp_path / "chapters" / "test-book" / "chapter_005_final.wav"

    def test_chapter_path_sanitizes_stage_name(self, tmp_path: Path) -> None:
        """Chapter path should replace spaces in stage with underscores."""
        layout = AudioCacheLayout(root=tmp_path)
        path = layout.chapter_path("test-book", 1, "some stage")
        assert path == tmp_path / "chapters" / "test-book" / "chapter_001_some_stage.wav"

    def test_ensure_chunk_dir_creates_parent_directory(self, tmp_path: Path) -> None:
        """ensure_chunk_dir should create the prefix directory."""
        layout = AudioCacheLayout(root=tmp_path)
        key = "tts_1234567890abcdef"
        dir_path = layout.ensure_chunk_dir(key)
        assert dir_path.exists()
        assert dir_path == tmp_path / "tts" / "chunks" / "tt"

    def test_ensure_chapter_dir_creates_book_directory(self, tmp_path: Path) -> None:
        """ensure_chapter_dir should create the book directory."""
        layout = AudioCacheLayout(root=tmp_path)
        dir_path = layout.ensure_chapter_dir("test-book")
        assert dir_path.exists()
        assert dir_path == tmp_path / "chapters" / "test-book"
