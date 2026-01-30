# Architecture Diagrams

Visual representations of the epub2audio architecture and data flows.

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              CLI Layer                                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                              │
│  │   run    │  │  doctor  │  │   init   │                              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                              │
│       │             │              │                                    │
│       └──────────────┴──────────────┴──→ cli/main.py                    │
│                                                 │                        │
└─────────────────────────────────────────────────┼────────────────────────┘
                                                  │
                                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           Pipeline Layer                                 │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    run_pipeline()                               │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐            │   │
│  │  │  Input  │→ │ State   │→ │  Cache  │→ │ Output  │            │   │
│  │  │ Expansion│ │ Load    │  │ Check   │  │ Summary │            │   │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘            │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│                              ▼                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    _process_book()                               │   │
│  │                                                                   │   │
│  │    EPUB ─→ Chapters ─→ Segments ─→ Audio Chunks ─→ M4B          │   │
│  │      │          │           │              │           │          │   │
│  │      ▼          ▼           ▼              ▼           ▼          │   │
│  │  ┌──────┐  ┌──────┐   ┌──────┐      ┌──────┐   ┌──────┐         │   │
│  │  │Reader│  │Cleaner│  │Segment│      │  TTS │   │Package│         │   │
│  │  └──────┘  └──────┘   └──────┘      └──────┘   └──────┘         │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Module Dependency Graph

```
                    ┌──────────────┐
                    │ interfaces.py│
                    │ (Protocols)  │
                    └──────┬───────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌────────────┐ ┌────────────┐ ┌────────────┐
    │ epub_reader│ │text_cleaner│ │text_segment│
    └─────┬──────┘ └────────────┘ └─────┬──────┘
          │                             │
          └──────────┬──────────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ tts_pipeline │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │ audio_proc   │
              └──────┬───────┘
                     │
                     ▼
              ┌──────────────┐
              │  packaging   │
              └──────────────┘

        ┌─────────────┐         ┌─────────────┐
        │   config    │         │  logging    │
        └─────────────┘         └─────────────┘
        ┌─────────────┐         ┌─────────────┐
        │state_store  │         │  error_log  │
        └─────────────┘         └─────────────┘
```

## Data Flow Diagram

```
EPUB File
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. INGESTION (EpubReader)                                   │
│    - Parse EPUB structure                                   │
│    - Extract metadata (title, author, cover)                │
│    - Extract chapters in spine order                        │
│    Output: EpubBook { metadata, chapters[] }                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. TEXT PROCESSING (per chapter)                            │
│                                                              │
│    Chapter ─→ TextCleaner ─→ cleaned text                   │
│                                    │                         │
│                                    ▼                         │
│                            TextSegmenter                    │
│                                    │                         │
│                                    ▼                         │
│                          Segment[] { index, text }           │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. TTS SYNTHESIS (per segment)                              │
│                                                              │
│    Segment ─→ Check Cache ─→ Hit? ──Yes──→ Return Chunk    │
│                      │                                      │
│                      No                                     │
│                      ▼                                      │
│              TtsEngine.synthesize()                          │
│                      │                                      │
│                      ▼                                      │
│              AudioChunk { index, path }                     │
│                      │                                      │
│                      ▼                                      │
│              Save to Cache                                  │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. AUDIO PROCESSING (per chapter)                           │
│                                                              │
│    AudioChunk[] ─→ insert_silence() ─→ AudioChunk[]         │
│                      │                                      │
│                      ▼                                      │
│                  stitch()                                   │
│                      │                                      │
│                      ▼                                      │
│              chapter_audio.wav                              │
│                      │                                      │
│                      ▼                                      │
│                  normalize() ────┐                           │
│                      │            │                          │
│                      ▼            ▼                          │
│              normalized.wav   stitched.wav                   │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. PACKAGING                                                │
│                                                              │
│    ChapterAudio[] ─→ Packager.package() ─→ M4B              │
│                        │                                    │
│                        ├─ Embed chapter markers             │
│                        ├─ Embed metadata                    │
│                        └─ Embed cover image                 │
│                                                              │
│    Output: out/<book_slug>/<book_slug>.m4b                  │
└─────────────────────────────────────────────────────────────┘
```

## State Management Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    JsonStateStore                           │
│                                                              │
│  cache/state/<book_slug>.json                               │
│                                                              │
│  {                                                           │
│    "version": 1,                                            │
│    "book_id": "my-book",                                    │
│    "updated_at": "2026-01-30T12:00:00",                     │
│    "steps": {                                               │
│      "chapters": true,        ← Chapter audio complete?     │
│      "packaged": false        ← M4B created?                │
│    },                                                        │
│    "artifacts": {                                           │
│      "source_path": "/path/to/book.epub",                   │
│      "chapter_dir": "cache/chapters/my-book",               │
│      "output_m4b": "out/my-book/my-book.m4b",               │
│      "last_error": "",                                      │
│      "error_log": "errors/my-book.json"                     │
│    }                                                         │
│  }                                                           │
└─────────────────────────────────────────────────────────────┘

State Machine:

┌─────────┐    load/create    ┌─────────────┐
│  None   │ ─────────────────▶ │  Initial    │
└─────────┘                   └──────┬──────┘
                                     │ chapters=true
                                     ▼
                              ┌─────────────┐
                              │  Chapters   │
                              │  Complete   │
                              └──────┬──────┘
                                     │ packaged=true
                                     ▼
                              ┌─────────────┐
                              │  Packaged   │
                              └──────┬──────┘
                                     │
                    ┌────────────────┴────────────────┐
                    │                                 │
                    ▼                                 ▼
            ┌─────────────┐                   ┌─────────────┐
            │  Skip on    │                   │  Re-process │
            │  re-run     │                   │  if missing │
            └─────────────┘                   └─────────────┘
```

## Error Handling Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    Error Logging                            │
│                                                              │
│  Exception occurs in pipeline step                          │
│         │                                                    │
│         ▼                                                    │
│  Log to Python logger (console + file)                      │
│         │                                                    │
│         ▼                                                    │
│  Add to ErrorLogStore                                       │
│  - ErrorCategory (enum)                                     │
│  - ErrorSeverity (enum)                                     │
│  - Message                                                  │
│  - Step name                                                │
│  - Chapter index (if applicable)                            │
│  - Details (dict)                                           │
│  - Exception info (type, message, stack trace)              │
│         │                                                    │
│         ▼                                                    │
│  Save to errors/<book_slug>.json (atomic write)             │
│         │                                                    │
│         ▼                                                    │
│  Update state.artifacts["last_error"] and                   │
│  state.artifacts["error_log"]                               │
│         │                                                    │
│         ▼                                                    │
│  Continue processing remaining books                        │
└─────────────────────────────────────────────────────────────┘

Error Log Structure:

errors/<book_slug>.json
{
  "book_slug": "my-book",
  "book_id": "my-book",
  "run_id": "20260130_120000",
  "error_count": 3,
  "errors": [
    {
      "timestamp": "2026-01-30T12:00:00+00:00",
      "category": "tts_synthesis",
      "severity": "error",
      "step": "tts_synthesis",
      "chapter_index": 3,
      "message": "TTS synthesis failed for segment",
      "details": {"segment_index": 42},
      "exception_type": "RuntimeError",
      "exception_message": "...",
      "stack_trace": "..."
    },
    ...
  ]
}
```

## Cache Structure

```
cache/
├── tts/
│   └── chunks/
│       ├── <sha256_hash_1>.wav  ← Cached TTS chunk
│       ├── <sha256_hash_2>.wav
│       └── ...
├── chapters/
│   ├── <book_slug>/
│   │   ├── chapter_000_stitched.wav
│   │   ├── chapter_000_normalized.wav
│   │   ├── chapter_001_stitched.wav
│   │   └── ...
└── state/
    ├── <book_slug_1>.json
    ├── <book_slug_2>.json
    └── ...

Cache Key Determinism:

text: "Hello world."
model_id: "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit"
voice: null
lang_code: null
speed: 1.0
sample_rate: 24000
channels: 1
    │
    ▼
SHA256("Hello world.|mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit|None|None|1.0|24000|1")
    │
    ▼
"a3f5c9d8e1b2f4a6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
    │
    ▼
cache/tts/chunks/a3f5c9d8e1b2f4a6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0.wav
```

## CLI Command Flow

```
epub2audio [args]
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  cli/main.py :: main()                                      │
│                                                              │
│  Parse first argument:                                       │
│  ┌──────────┬─────────────┬─────────────┬──────────────┐   │
│  │"doctor"  │  "init"     │  <path>     │  (none)      │   │
│  └────┬─────┴──────┬──────┴──────┬──────┴──────┬───────┘   │
│       │             │             │              │          │
│       ▼             ▼             ▼              ▼          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐    ┌─────────┐     │
│  │ doctor  │  │  init   │  │   run   │    │   run   │     │
│  │ parser  │  │  parser  │  │ parser  │    │ parser  │     │
│  └────┬────┘  └────┬────┘  └────┬────┘    └────┬────┘     │
│       │            │            │               │          │
│       ▼            ▼            ▼               �          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                  │
│  │run_doctor│ │run_init  │ │run_main  │                  │
│  └─────────┘  └─────────┘  └─────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

## Retry and Backoff Flow

```
Segment.synthesize()
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Try TtsEngine.synthesize()                                 │
│         │                                                    │
│         ├── TtsInputError ──→ Skip segment (return empty)   │
│         │                                                    │
│         ├── TtsSizeError ──→ Split and retry                │
│         │                          │                         │
│         │                          ▼                         │
│         │                 _split_and_synthesize()            │
│         │                          │                         │
│         │                          └─→ Recursive call        │
│         │                              (depth + 1)           │
│         │                                                    │
│         ├── TtsTransientError ──→ Retry with backoff        │
│         │                          │                         │
│         │                          ▼                         │
│         │                 delay = base * 2^attempt          │
│         │                 delay += delay * jitter           │
│         │                 sleep(delay)                      │
│         │                 attempt++                         │
│         │                          │                         │
│         │                          └─→ Retry (if attempt <  │
│         │                                          max_retries)│
│         │                                                    │
│         └── TtsError / TtsModelError ──→ Raise (fail)        │
│                                                              │
│  Max split depth: 8 (prevents infinite recursion)           │
└─────────────────────────────────────────────────────────────┘
```

## Protocol Implementation Map

```
Protocol               │ Implementation          │ Module
───────────────────────┼─────────────────────────┼──────────────────
EpubReader            │ EbooklibEpubReader      │ epub_reader.py
TextCleaner           │ BasicTextCleaner        │ text_cleaner.py
TextSegmenter         │ BasicTextSegmenter      │ text_segmenter.py
TtsEngine             │ MlxTtsEngine            │ tts_engine.py
AudioProcessor        │ FfmpegAudioProcessor    │ audio_processing.py
Packager              │ FfmpegPackager          │ packaging.py
StateStore            │ JsonStateStore          │ state_store.py

All protocols defined in: interfaces.py
```

## Directory Layout

```
epub2audio/
├── epubs/                    # Input EPUB files
│   └── *.epub
├── out/                      # Output M4B files
│   └── <book_slug>/
│       └── <book_slug>.m4b
├── cache/                    # Cached intermediate files
│   ├── tts/
│   │   └── chunks/
│   │       └── <sha256>.wav
│   ├── chapters/
│   │   └── <book_slug>/
│   │       ├── chapter_000_*.wav
│   │       └── ...
│   ├── work/                 # Temporary processing
│   ├── packaging/            # M4B intermediate files
│   └── state/
│       └── <book_slug>.json
├── logs/                     # Log files
│   ├── run-<timestamp>.log
│   └── <book_slug>/
│       └── <run_id>.log
├── errors/                   # Structured error logs
│   └── <book_slug>.json
└── config.toml               # Optional configuration
```

## Class Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                     Pipeline Orchestrator                    │
│                                                               │
│  pipeline.run_pipeline()                                     │
│      │                                                        │
│      ├── Uses: EbooklibEpubReader        (EpubReader)       │
│      ├── Uses: BasicTextCleaner          (TextCleaner)      │
│      ├── Uses: BasicTextSegmenter        (TextSegmenter)    │
│      ├── Uses: MlxTtsEngine              (TtsEngine)        │
│      ├── Uses: FfmpegAudioProcessor       (AudioProcessor)  │
│      ├── Uses: FfmpegPackager             (Packager)        │
│      └── Uses: JsonStateStore             (StateStore)      │
│                                                               │
│  All dependencies injected - no hard coupling!              │
└─────────────────────────────────────────────────────────────┘

Configuration Flow:

config.toml ─→ load_config() ─→ Config dataclass ─→ pipeline
                                                            │
                                                            ▼
                                                   ┌─────────────────┐
                                                   │  Component      │
                                                   │  Initialization │
                                                   │  - model_id     │
                                                   │  - sample_rate  │
                                                   │  - max_chars    │
                                                   │  - ...          │
                                                   └─────────────────┘
```
