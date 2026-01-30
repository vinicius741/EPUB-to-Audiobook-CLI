# Developer Guide - Architecture & Module Contracts

This guide provides comprehensive documentation for developers extending or modifying epub2audio.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Pipeline Flow](#pipeline-flow)
3. [Module Contracts](#module-contracts)
4. [Data Flow](#data-flow)
5. [Caching Strategy](#caching-strategy)
6. [State Management](#state-management)
7. [Error Handling](#error-handling)
8. [CLI Architecture](#cli-architecture)
9. [Testing Guidelines](#testing-guidelines)
10. [Extending the Pipeline](#extending-the-pipeline)

---

## Architecture Overview

epub2audio follows a **protocol-driven architecture** where all core operations are defined as Python Protocols (interfaces). This enables:

- **Swappable implementations**: Easy to swap TTS engines, audio processors, or packagers
- **Testability**: Protocol-compliant dummies for unit testing
- **Extensibility**: New implementations without modifying core logic

### Core Design Principles

1. **Protocol-Oriented**: All major components defined as `Protocol` types in `interfaces.py`
2. **Frozen Dataclasses**: Immutable data structures prevent accidental mutation
3. **Deterministic Caching**: Content-addressable cache based on SHA-256 hashes
4. **Resumable Execution**: Per-book state tracking allows interruption and recovery
5. **Error Isolation**: Failures in one book don't stop processing of others
6. **Calm Logging**: Quiet-by-default with optional verbose/debug modes

### Project Structure

```
src/epub2audio/
├── cli/                    # CLI package
│   ├── __init__.py         # Re-exports main()
│   ├── main.py             # CLI entrypoint and command routing
│   ├── commands.py         # Command runners (run_main, run_doctor, run_init)
│   ├── parsers.py          # Argument parser builders
│   ├── rendering.py        # Output rendering functions
│   └── progress.py         # Progress display and output formatting
│
├── pipeline.py             # Main orchestration (single/multiple book processing)
├── interfaces.py           # Protocol definitions and data classes
├── config.py               # TOML configuration loading + defaults
├── logging_setup.py        # Per-run and per-book logging
├── error_log.py            # Structured error logging (ErrorLogStore, ErrorCategory)
├── state_store.py          # JSON-based state persistence
│
├── epub_reader.py          # Ebooklib-based EPUB parsing
├── text_cleaner.py         # Unicode normalization, citation removal
├── text_segmenter.py       # Sentence/paragraph segmentation
│
├── tts_engine.py           # MlxTtsEngine implementation
├── tts_pipeline.py         # Synthesis with retry/backoff
│
├── audio_cache.py          # Deterministic chunk caching
├── audio_processing.py     # FFmpeg-based audio pipeline
├── packaging.py            # M4B creation via FFmpeg
│
├── doctor.py               # Environment validation
└── utils.py                # Utilities (slugify, run_id, ensure_dir)
```

---

## Pipeline Flow

The complete pipeline transforms EPUB ebooks into audiobooks through a series of well-defined stages:

```
EPUB File
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 1: Ingestion                                          │
│  - EpubReader.read() → EpubBook                             │
│  - Extract metadata (title, author, cover)                  │
│  - Extract chapters in spine order                          │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 2: Text Processing (per chapter)                      │
│  - TextCleaner.clean() → normalized text                    │
│  - TextSegmenter.segment() → [Segment]                      │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 3: TTS Synthesis (per segment)                        │
│  - Check cache for existing chunk                           │
│  - If miss: TtsEngine.synthesize() → AudioChunk             │
│  - On TtsSizeError: split and retry                         │
│  - On TtsTransientError: retry with backoff                 │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 4: Audio Processing (per chapter)                     │
│  - AudioProcessor.insert_silence() → [AudioChunk]           │
│  - AudioProcessor.stitch() → chapter audio                  │
│  - AudioProcessor.normalize() → normalized audio            │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ Phase 5: Packaging                                          │
│  - Packager.package() → M4B file                            │
│  - Embed chapter markers, metadata, cover                   │
└─────────────────────────────────────────────────────────────┘
    ↓
M4B Audiobook
```

### Orchestration

The main pipeline is orchestrated by `pipeline.run_pipeline()`, which:

1. Expands input paths (directories → EPUB files)
2. For each book:
   - Loads/initializes state from `JsonStateStore`
   - Checks if already packaged (skip if complete)
   - Processes chapters through the pipeline
   - Packages chapter audio into M4B
   - Updates state and logs errors
3. Returns summary results

---

## Module Contracts

### Protocol Definitions (`interfaces.py`)

All core operations use Python's `Protocol` type. This enables structural subtyping - any class with matching methods is compatible.

#### Data Classes

```python
@dataclass(frozen=True)
class BookMetadata:
    title: str
    author: str | None = None
    language: str | None = None
    cover_image: Path | None = None

@dataclass(frozen=True)
class Chapter:
    index: int        # Chapter position in book
    title: str
    text: str         # Raw chapter text

@dataclass(frozen=True)
class Segment:
    index: int        # Segment position within chapter
    text: str         # Text segment ready for TTS

@dataclass(frozen=True)
class AudioChunk:
    index: int
    path: Path        # Path to audio file
    duration_ms: int | None = None

@dataclass(frozen=True)
class ChapterAudio:
    index: int
    title: str
    path: Path        # Path to chapter audio file

@dataclass(frozen=True)
class EpubBook:
    metadata: BookMetadata
    chapters: Sequence[Chapter]
```

#### Core Protocols

##### EpubReader

```python
@runtime_checkable
class EpubReader(Protocol):
    """Read EPUB files and extract chapters in correct order."""

    def read(self, path: Path) -> EpubBook:
        """
        Parse EPUB and extract metadata + chapters.

        Requirements:
        - Follow EPUB spine order for correct chapter sequence
        - Extract metadata (title, author, language, cover)
        - Handle both TOC-based and spine-based chapter ordering

        Raises:
            Exception: If EPUB is malformed or unreadable
        """
        ...
```

**Implementation**: `EbooklibEpubReader` in `epub_reader.py`

##### TextCleaner

```python
@runtime_checkable
class TextCleaner(Protocol):
    """Normalize and clean text for TTS processing."""

    def clean(self, text: str) -> str:
        """
        Normalize text content.

        Typical operations:
        - Unicode normalization (NFC)
        - Whitespace cleanup
        - Citation/footnote removal
        - Special character handling

        Returns:
            Empty string if text has no usable content
        """
        ...
```

**Implementation**: `BasicTextCleaner` in `text_cleaner.py`

##### TextSegmenter

```python
@runtime_checkable
class TextSegmenter(Protocol):
    """Break text into TTS-safe chunks."""

    def segment(self, text: str) -> Iterable[Segment]:
        """
        Split text into segments suitable for TTS.

        Requirements:
        - Respect max_chars limit
        - Prefer breaks at sentence/paragraph boundaries
        - Ensure segments end with punctuation
        - Return segments in order

        Segments may be empty (filtered out by TTS pipeline).
        """
        ...
```

**Implementation**: `BasicTextSegmenter` in `text_segmenter.py`

**Configuration**:
- `max_chars`: Soft limit for segment size
- `min_chars`: Minimum preferred segment size
- `hard_max_chars`: Absolute maximum (triggers hard split if exceeded)

##### TtsEngine

```python
@runtime_checkable
class TtsEngine(Protocol):
    """Text-to-speech synthesis engine."""

    def synthesize(
        self,
        text: str,
        voice: str | None = None,
        config: Mapping[str, object] | None = None,
    ) -> AudioChunk:
        """
        Synthesize audio from text.

        Config keys may include:
        - speed: float (1.0 = normal)
        - lang_code: str | None
        - sample_rate: int
        - channels: int
        - output_path: Path | None (if provided, write directly)

        Raises:
            TtsInputError: Text is empty or non-speech
            TtsSizeError: Input exceeds maximum length
            TtsTransientError: Runtime failure (retryable)
            TtsModelError: Model load failure
        """
        ...
```

**Implementation**: `MlxTtsEngine` in `tts_engine.py`

**Error Taxonomy**:
- `TtsInputError`: Empty or non-speech content
- `TtsSizeError`: Input exceeds model limits (triggers split)
- `TtsTransientError`: Temporary failures (retry with backoff)
- `TtsModelError`: Model load/configuration failures

##### AudioProcessor

```python
@runtime_checkable
class AudioProcessor(Protocol):
    """Audio processing operations."""

    def insert_silence(
        self, chunks: Sequence[AudioChunk], silence_ms: int
    ) -> Sequence[AudioChunk]:
        """Insert silence between chunks using FFmpeg."""
        ...

    def normalize(self, chunks: Sequence[AudioChunk]) -> Sequence[AudioChunk]:
        """
        Apply EBU R128 loudness normalization.

        Config (LoudnessConfig):
        - target_lufs: Target integrated loudness (-23.0 for audiobooks)
        - lra: Loudness range (7.0 typical)
        - true_peak: True peak limit (-1.0 dBTP)
        """
        ...

    def stitch(self, chunks: Sequence[AudioChunk], out_path: Path) -> Path:
        """Concatenate chunks into single audio file."""
        ...
```

**Implementation**: `FfmpegAudioProcessor` in `audio_processing.py`

##### Packager

```python
@runtime_checkable
class Packager(Protocol):
    """Package chapter audio into final audiobook format."""

    def package(
        self,
        chapters: Sequence[ChapterAudio],
        metadata: BookMetadata,
        out_path: Path,
        cover_image: Path | None = None,
    ) -> Path:
        """
        Create audiobook file (M4B) with chapters.

        Requirements:
        - Embed chapter markers at correct timestamps
        - Embed metadata (title, author, etc.)
        - Embed cover image if provided
        - Output to out_path (must be .m4b)

        Returns:
            Path to the created M4B file
        """
        ...
```

**Implementation**: `FfmpegPackager` in `packaging.py`

##### StateStore

```python
@runtime_checkable
class StateStore(Protocol):
    """Persist and load pipeline state."""

    def load(self, book_id: str) -> PipelineState | None:
        """Load state for a book. Returns None if not found."""
        ...

    def save(self, state: PipelineState) -> None:
        """Persist state atomically."""
        ...
```

**Implementation**: `JsonStateStore` in `state_store.py`

---

## Data Flow

### Per-Book Processing

For each EPUB, the pipeline maintains:

1. **Per-book logger**: `logging_setup.LoggingContext.get_book_logger()`
2. **Error log**: `ErrorLogStore.get_logger()` for structured error tracking
3. **State**: `JsonStateStore` for resumability

### Chapter Processing Flow

```python
# From pipeline._process_chapter()

1. Check if chapter audio already exists (skip if present)
2. Clean chapter text → cleaned
3. If empty after cleaning:
   - Log warning to error log
   - Return ChapterResult(status="empty")
4. Synthesize cleaned text → [AudioChunk]
   - Uses TTS pipeline with retry/backoff
   - Checks chunk cache first
5. If synthesis fails:
   - Log error to error log
   - Return ChapterResult(status="failed")
6. If no chunks generated:
   - Log warning to error log
   - Return ChapterResult(status="empty")
7. Insert silence between chunks (if configured)
8. Stitch chunks → chapter audio file
9. Normalize audio (if configured)
10. Return ChapterResult(status="ok", output_paths=(audio_path,))
```

### Error Handling Flow

All errors are logged to both:
1. **Python logger**: For console/file output
2. **ErrorLogStore**: Structured JSON for diagnostics

```python
# Example from pipeline.py
error_log.add_error(
    ErrorCategory.TTS_SYNTHESIS,
    ErrorSeverity.ERROR,
    message,
    step="tts_synthesis",
    chapter_index=chapter.index,
    details={"chapter_title": chapter.title},
    exc=exc,  # Captures exception type, message, and stack trace
)
log_ctx.error_log_store.save(error_log)
```

---

## Caching Strategy

### Chunk Cache

Audio chunks are cached deterministically based on their content and synthesis parameters.

#### Cache Key Calculation

```python
def chunk_cache_key(
    text: str,
    model_id: str,
    voice: str | None,
    lang_code: str | None,
    speed: float,
    sample_rate: int,
    channels: int,
) -> str:
    """
    Generate SHA-256 hash of cacheable parameters.

    The key is deterministic: same text + parameters = same key.
    """
    data = f"{text}|{model_id}|{voice}|{lang_code}|{speed}|{sample_rate}|{channels}"
    return hashlib.sha256(data.encode()).hexdigest()
```

#### Cache Layout

```
cache/
└── tts/
    └── chunks/
        ├── <hash_1>.wav
        ├── <hash_2>.wav
        └── ...
```

#### Cache Invalidation

The cache is **content-addressable** - it doesn't track time or dependencies. Instead:
- Cache hits are determined by hash matches
- To invalidate: delete the cache directory
- Cache is safe to share across runs/books

---

## State Management

### State File Schema

Per-book state is stored in `cache/state/<book_slug>.json`:

```json
{
  "version": 1,
  "book_id": "my-book",
  "updated_at": "2026-01-30T12:00:00",
  "steps": {
    "chapters": true,
    "packaged": false
  },
  "artifacts": {
    "source_path": "/path/to/book.epub",
    "chapter_dir": "cache/chapters/my-book",
    "output_m4b": "out/my-book/my-book.m4b",
    "last_error": "",
    "error_log": "errors/my-book.json"
  }
}
```

### State Machine

```
Initial → Chapters Complete → Packaged → Done
    ↑            |                  |
    |____________| (if output       |
                 |  missing)        |
                 |__________________|
```

- **Initial**: No state file or `steps.chapters = false`
- **Chapters Complete**: All chapter audio generated successfully
- **Packaged**: M4B file created successfully
- **Done**: Complete, skips on re-run

### State Updates

State is updated atomically using `JsonStateStore.save()`:
1. Write to temporary file (`<book_slug>.json.tmp`)
2. Rename to final path (atomic on POSIX)

---

## Error Handling

### Error Categories

`error_log.py` defines `ErrorCategory` enum:

| Category | Description |
|----------|-------------|
| `EPUB_PARSING` | EPUB file read failures |
| `EPUB_INVALID` | Malformed EPUB structure |
| `EPUB_METADATA` | Metadata extraction failures |
| `TEXT_CLEANING` | Text normalization issues |
| `TEXT_SEGMENTATION` | Segmentation failures |
| `TTS_MODEL_LOAD` | TTS model load failures |
| `TTS_INPUT` | Empty/invalid TTS input |
| `TTS_SIZE` | Input size exceeded |
| `TTS_TRANSIENT` | Transient TTS failures |
| `TTS_SYNTHESIS` | General TTS synthesis errors |
| `AUDIO_SILENCE` | Silence insertion failures |
| `AUDIO_NORMALIZATION` | Normalization failures |
| `AUDIO_STITCHING` | Audio stitching failures |
| `PACKAGING` | M4B packaging failures |
| `METADATA` | Metadata embedding failures |
| `FILE_IO` | File I/O errors |
| `DISK_SPACE` | Disk space issues |
| `PERMISSION` | Permission errors |
| `UNKNOWN` | Uncategorized errors |

### Error Severity

| Severity | Usage |
|----------|-------|
| `INFO` | Informational messages |
| `WARNING` | Non-critical issues (empty chapters, etc.) |
| `ERROR` | Failures that prevent completion |
| `CRITICAL` | Severe failures that halt processing |

### Error Entry Structure

```json
{
  "timestamp": "2026-01-30T12:00:00+00:00",
  "category": "tts_synthesis",
  "severity": "error",
  "step": "synthesize_chapters",
  "chapter_index": 3,
  "message": "TTS synthesis failed for segment",
  "details": {"segment_index": 42, "text_length": 500},
  "exception_type": "RuntimeError",
  "exception_message": "...",
  "stack_trace": "..."
}
```

---

## CLI Architecture

### Command Routing

`cli/main.py` routes commands based on first argument:

```
epub2audio              → Run main pipeline (default)
epub2audio doctor       → Run diagnostics
epub2audio init         → Initialize project
epub2audio <paths>      → Run pipeline on specified paths
```

### Debug Flags

Priority order (highest to lowest):
1. `--debug`: Full debug (file + console at DEBUG level)
2. `--verbose` / `-v`: Verbose console only
3. `--log-level LEVEL`: Override both file and console
4. Config file values

### Progress Display

`cli/progress.py` provides `ProgressDisplay` with methods:
- `print_processing()`: Signal book processing start
- `print_chapter_progress()`: Chapter progress updates
- `print_book_complete()`: Successful completion
- `print_book_failed()`: Failure notification
- `print_book_skipped()`: Already completed
- `print_book_missing()`: Input file not found

### Output Rendering

`cli/rendering.py` provides:
- `render_config_summary()`: Format configuration for display
- `render_run_summary()`: Format pipeline results
- `render_doctor_report()`: Format diagnostic output

---

## Testing Guidelines

### Protocol-Based Testing

Use protocol-compliant dummies for unit tests:

```python
@dataclass
class DummyTtsEngine:
    """Protocol-compliant TTS engine for testing."""
    should_fail: bool = False
    size_limit: int = 1000

    def synthesize(self, text: str, voice: str | None = None,
                   config: Mapping[str, object] | None = None) -> AudioChunk:
        if self.should_fail:
            raise TtsTransientError("Test failure")
        if len(text) > self.size_limit:
            raise TtsSizeError(f"Text too long: {len(text)}")
        # Return dummy AudioChunk
        ...
```

### Test Fixtures

Use `tmp_path` fixture for temporary directories:

```python
def test_segmenter(tmp_path):
    segmenter = BasicTextSegmenter(max_chars=500)
    text = "This is a test. " * 100
    segments = list(segmenter.segment(text))
    assert all(len(s.text) <= 500 for s in segments)
```

### Integration Testing

For end-to-end tests, use:
1. Small sample EPUB files
2. Fast TTS settings (small model, low sample rate)
3. Temporary output directories

---

## Extending the Pipeline

### Adding a New TTS Engine

1. Implement the `TtsEngine` protocol:

```python
class MyTtsEngine:
    def __init__(self, model_id: str, ...):
        ...

    def synthesize(self, text: str, voice: str | None = None,
                   config: Mapping[str, object] | None = None) -> AudioChunk:
        # Your synthesis logic
        ...
```

2. Update `pipeline._build_engine()`:

```python
def _build_engine(config: Config) -> TtsEngine:
    if config.tts.engine == "my_engine":
        return MyTtsEngine(...)
    # ... existing engines
```

3. Add config option in `config.toml`:

```toml
[tts]
engine = "my_engine"  # or "mlx"
```

### Adding a New Packager

1. Implement the `Packager` protocol:

```python
class MyPackager:
    def package(self, chapters: Sequence[ChapterAudio],
                metadata: BookMetadata, out_path: Path,
                cover_image: Path | None = None) -> Path:
        # Your packaging logic
        ...
```

2. Update `pipeline.run_pipeline()` to use your packager:

```python
packager = MyPackager(...)
```

### Adding Custom Text Processing

Create custom implementations of `TextCleaner` or `TextSegmenter`:

```python
class AggressiveTextCleaner:
    def clean(self, text: str) -> str:
        # More aggressive cleaning
        text = unicodedata.normalize("NFC", text)
        text = re.sub(r'\s+', ' ', text)
        # Remove more patterns
        return text.strip()

# Use in pipeline:
cleaner = AggressiveTextCleaner()
```

---

## Configuration System

### Config Loading

`config.load_config()` merges:
1. `DEFAULT_CONFIG` (hardcoded defaults)
2. `config.toml` (user overrides)
3. CLI flags (highest priority)

### Config Sections

#### Paths (`[paths]`)

```toml
[paths]
epubs = "epubs"        # Input EPUB directory
out = "out"            # Output M4B directory
cache = "cache"        # Cache root
logs = "logs"          # Log files
errors = "errors"      # Error logs (JSON)
```

#### Logging (`[logging]`)

```toml
[logging]
level = "INFO"         # File log level
console_level = "INFO" # Console log level
```

#### TTS (`[tts]`)

```toml
[tts]
engine = "mlx"
model_id = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit"
voice = null           # Default voice
lang_code = null       # Default language
speed = 1.0            # Playback speed
sample_rate = 24000    # Audio sample rate (Hz)
channels = 1           # Audio channels (1=mono, 2=stereo)
max_chars = 1000       # Soft limit for segment size
min_chars = 200        # Minimum segment size
hard_max_chars = 1250  # Absolute maximum (null = auto)
max_retries = 2        # Retry attempts for transient errors
backoff_base = 0.5     # Base delay for backoff (seconds)
backoff_jitter = 0.1   # Jitter factor for backoff
output_format = "wav"  # Output audio format
```

#### Audio (`[audio]`)

```toml
[audio]
silence_ms = 250       # Silence between chunks (milliseconds)
normalize = true       # Enable EBU R128 normalization
target_lufs = -23.0    # Target integrated loudness
lra = 7.0              # Loudness range
true_peak = -1.0       # True peak limit (dBTP)
```

---

## Summary

This architecture enables:
- **Extensibility**: Swap any component via protocol implementations
- **Testability**: Protocol-compliant dummies for isolated testing
- **Reliability**: State management and error isolation
- **Performance**: Deterministic caching and resumable execution

For questions or contributions, please refer to `CLAUDE.md` for project-specific guidance.
