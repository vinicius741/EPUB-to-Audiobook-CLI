# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**epub2audio** is a Python CLI application that converts EPUB ebooks into audiobooks (`.m4b`) using local Text-to-Speech models. It runs entirely offline on Apple Silicon using the MLX framework.

### Core Pipeline Flow

```
EPUB → EpubBook → Chapter Text → Segments → Audio Chunks → Chapter Audio → M4B
```

The pipeline consists of 7 phases (0-5 completed, 6-7 pending):
- **Phase 0-5:** Complete - EPUB ingestion, TTS synthesis, audio processing, M4B packaging, resumability
- **Phase 6-7:** Pending - CLI polish, tests, documentation

See `documentation/development_plan.md` for detailed task breakdown.

## Development Environment

This project uses **Python 3**. The system only has access to Python 3 - no other Python versions are available. Always use `python3` or `pip3` commands when working with this codebase.

## Commands

### Installation
```bash
pip3 install -e .
```

### Running the CLI
```bash
# Main entry point
epub2audio [inputs...]

# Process all EPUBs in default directory
epub2audio

# Initialize folders and config
epub2audio init

# Environment validation and TTS testing
epub2audio doctor [--smoke-test] [--rtf-test] [--long-text-test] [--verify]
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_tts_pipeline.py
```

## Architecture

### Protocol-Driven Design

All core operations use Protocol/ABC patterns defined in `src/epub2audio/interfaces.py`:
- `EpubReader` - EPUB parsing and chapter extraction
- `TextCleaner` - Text normalization and cleanup
- `TextSegmenter` - Breaking text into TTS-safe chunks
- `TtsEngine` - Text-to-speech synthesis
- `AudioProcessor` - Silence insertion, normalization, stitching
- `Packager` - M4B creation with chapters
- `StateStore` - State persistence for resumability

### Module Structure

```
src/epub2audio/
├── cli/                    # CLI package (commands, parsers, rendering)
│   ├── __init__.py         # Package init, re-exports main()
│   ├── main.py             # CLI entrypoint (subcommand routing)
│   ├── commands.py         # Command runners (run_main, run_doctor, run_init)
│   ├── parsers.py          # Argument parser builders
│   └── rendering.py        # Output rendering functions
├── cli.py                  # Backward compatibility stub (re-exports from cli/)
├── pipeline.py             # Main orchestration (single/multiple book processing)
├── interfaces.py           # Protocol definitions and data classes
├── config.py               # TOML configuration loading + defaults
├── logging_setup.py        # Per-run and per-book logging
├── state_store.py          # JSON-based state persistence
│
├── epub_reader.py          # Ebooklib-based EPUB parsing
├── text_cleaner.py         # Unicode normalization, citation removal
├── text_segmenter.py       # Sentence/paragraph segmentation
│
├── tts_engine.py           # MlxTtsEngine implementation
├── tts_pipeline.py         # Synthesis with retry/backoff
│
├── audio_processing.py     # FFmpeg-based audio pipeline
├── audio_cache.py          # Deterministic chunk caching
├── packaging.py            # M4B creation via FFmpeg
│
├── doctor.py               # Environment validation
└── utils.py                # Utilities (slugify, run_id, ensure_dir)
```

### Key Data Flow

1. **Ingestion:** `epub_reader.py` extracts chapters in correct order using EPUB spine
2. **Text Processing:** `text_cleaner.py` → `text_segmenter.py` produces indexed segments
3. **Synthesis:** `tts_pipeline.py` converts segments to audio with caching (via `audio_cache.py`)
4. **Audio Processing:** `audio_processing.py` inserts silence, normalizes (EBU R128), stitches chapters
5. **Packaging:** `packaging.py` creates M4B with chapter markers, metadata, cover art

### Determinism and Caching

- **Chunk cache keys:** SHA-256 hash of `text + model_id + voice + speed + sample_rate + channels`
- **Processing order:** EPUB spine order, sorted chapters by index
- **Cache layout:** `cache/tts/chunks/<hash>.wav`

### State Management

Per-book state stored in `cache/state/<book_slug>.json`:
```json
{
  "version": 1,
  "book_id": "book-slug",
  "updated_at": "2026-01-30T12:00:00",
  "steps": {
    "chapters_complete": true,
    "packaging_complete": false
  },
  "artifacts": {
    "chapter_dir": "cache/chapters/book-slug",
    "output_m4b": "out/book-slug/book-slug.m4b"
  },
  "last_error": null
}
```

### Error Taxonomy (tts_engine.py)

- `TtsInputError` - Empty or non-speech text
- `TtsSizeError` - Input exceeds max chars (triggers split)
- `TtsTransientError` - Runtime failures (retry with backoff)
- `TtsModelError` - Model load failures

### Configuration

Default config in `config.toml` (create via `epub2audio init`):

Key sections:
- `[paths]` - epubs, out, cache, logs directories
- `[logging]` - level, console_level
- `[tts]` - engine, model_id, voice, speed, sample_rate, max_chars, retry/backoff settings
- `[audio]` - silence_ms, normalize, target_lufs, lra, true_peak

### Directory Layout

```
epubs/           # Input EPUB files
out/             # Output M4B files (out/<book_slug>/<book_slug>.m4b)
cache/
├── tts/chunks/  # Cached TTS audio chunks
├── chapters/    # Per-chapter audio files
├── work/        # Temporary processing
├── packaging/   # M4B intermediate files
└── state/       # Per-book state JSON files
logs/            # Run and per-book logs
```

## Important Patterns

### TTS Chunk Splitting
When `TtsSizeError` occurs, `tts_pipeline.py` splits chunks and retries with exponential backoff. The `hard_max_chars` config (default: 125% of `max_chars`) is auto-calculated if not set.

### Chapter Ordering
EPUB chapters must follow the spine order for correct audiobook sequence. The `epub_reader.py` uses `ebooklib` to parse both TOC and spine.

### Logging Hierarchy
- Per-run log: `logs/run-<timestamp>.log`
- Per-book log: `logs/<book_slug>/<run_id>.log`
- Logger names: `epub2audio.book.<slug>`

## Dependencies

- `ebooklib` - EPUB parsing
- `beautifulsoup4` - HTML text extraction
- `mlx` + `mlx-audio` - Apple Silicon ML and TTS
- `huggingface_hub` - Model downloading
- `ffmpeg` (system) - Audio processing and M4B packaging

## Testing

Use Protocol-based dummy engines for unit tests. The `tmp_path` fixture creates temporary directories for test isolation.
