# epub2audio

**epub2audio** is a command-line tool that converts EPUB ebooks into high-quality audiobooks (`.m4b`) using local, offline Text-to-Speech (TTS) models. It is optimized for Apple Silicon using the [MLX](https://github.com/ml-explore/mlx) framework.

## Features

- **Local & Private:** Runs entirely on your machine. No cloud APIs, no data leaks.
- **Apple Silicon Optimized:** Leverages MLX for efficient, high-performance inference on Mac.
- **Smart Text Processing:** Parses EPUB structure, cleans text, and segments it intelligently for natural-sounding speech.
- **High-Quality Audio:**
  - Uses state-of-the-art open models (default: `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit`).
  - Automatically inserts silence between sentences and paragraphs.
  - Performs EBU R128 loudness normalization for professional audio levels.
- **Audiobook Packaging:** Outputs chapterized `.m4b` files complete with metadata (title, author) and cover art.
- **Resumable:** Tracks progress per book. If interrupted, it resumes exactly where it left off.
- **Robust:** Handles failures gracefully—a single error won't stop the entire batch.

## Prerequisites

- **OS:** macOS (Apple Silicon recommended for performance).
- **Python:** 3.10 or higher.
- **FFmpeg:** Required for audio processing and packaging.
  ```bash
  brew install ffmpeg
  ```

## Installation

Clone the repository and install the package:

```bash
git clone https://github.com/vinicius741/EPUB-to-Audiobook-CLI.git
cd EPUB-to-Audiobook-CLI

# Recommended: Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip3 install -e .
```

## Quick Start

```bash
# 1. Initialize the project structure
epub2audio init

# 2. (Optional) Verify your environment
epub2audio doctor --smoke-test

# 3. Place EPUB files in the 'epubs/' folder and run
epub2audio
```

## Usage

### Commands

#### `epub2audio init`
Initialize the project structure with default folders and configuration.

```bash
epub2audio init [options]
```

**Creates:**
- `epubs/` - Place your input `.epub` files here
- `out/` - Destination for generated `.m4b` audiobooks
- `cache/` - Intermediate storage for synthesized audio chunks (speeds up re-runs)
- `logs/` - Log files for debugging
- `errors/` - Per-book error logs in JSON format
- `config.toml` - Configuration file with default settings

**Options:**
- `--force` - Overwrite existing `config.toml` if it exists
- `--no-config` - Skip creating `config.toml` (folders only)

#### `epub2audio` (run)
Process EPUB files and convert them to audiobooks.

```bash
epub2audio [inputs...] [options]
```

**Arguments:**
- `inputs` - Optional EPUB files or folders to process. If omitted, uses the `epubs/` folder.

**Examples:**
```bash
# Process all EPUBs in the default epubs/ folder
epub2audio

# Process specific files
epub2audio my_book.epub another_book.epub

# Process all EPUBs in a folder
epub2audio ~/Documents/ebooks/

# Mix files and folders
epub2audio book1.epub ~/ebooks/scifi/
```

**Debug Options:**
| Option | Description |
|--------|-------------|
| `--debug` | Enable debug logging (sets both file and console to DEBUG) |
| `--verbose`, `-v` | Enable verbose console output (sets console to DEBUG, file stays at configured level) |
| `--log-level LEVEL` | Override log level (e.g., INFO, DEBUG, WARNING, ERROR) |
| `--config PATH` | Path to custom `config.toml` file |

**Priority order for log levels:** `--debug` > `--verbose` > `--log-level` > config file

#### `epub2audio doctor`
Check your environment and test the TTS model.

```bash
epub2audio doctor [options]
```

**Options:**
| Option | Description |
|--------|-------------|
| `--smoke-test` | Run a basic synthesis smoke test |
| `--rtf-test` | Measure real-time factor (processing speed vs audio duration) |
| `--long-text-test` | Run a long-text resilience test |
| `--verify` | Run all verification checks |
| `--text TEXT` | Custom text to synthesize (default: "Hello world.") |
| `--output-dir PATH` | Directory to write test audio output |

## Configuration

The `config.toml` file controls all aspects of epub2audio. If not specified, the tool looks for `config.toml` in the current directory.

### Default Configuration

```toml
# epub2audio configuration

[paths]
epubs = "epubs"           # Input EPUB files directory
out = "out"               # Output M4B files directory
cache = "cache"           # Cache for TTS chunks and intermediate files
logs = "logs"             # Log files directory
errors = "errors"         # Per-book error logs (JSON format)

[logging]
level = "INFO"            # File log level
console_level = "INFO"    # Console log level

[tts]
engine = "mlx"                                    # TTS engine (only mlx supported)
model_id = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit"  # HuggingFace model ID
voice = null                                      # Voice preset (model-dependent)
lang_code = null                                  # Language code (null = auto-detect)
speed = 1.0                                       # Playback speed multiplier
sample_rate = 24000                               # Audio sample rate in Hz
channels = 1                                      # Number of audio channels (1 = mono)
max_chars = 1000                                  # Target max characters per TTS request
min_chars = 200                                   # Min characters to consider for splitting
hard_max_chars = 1250                             # Absolute limit for TTS input
max_retries = 2                                   # Retry count for transient failures
backoff_base = 0.5                                # Base backoff delay in seconds
backoff_jitter = 0.1                              # Random jitter for backoff
output_format = "wav"                             # TTS output format

[audio]
silence_ms = 250          # Silence duration to insert between segments (milliseconds)
normalize = true          # Enable EBU R128 loudness normalization
target_lufs = -23.0       # Target loudness in LUFS (EBU R128 standard)
lra = 7.0                 # Loudness range target (EBU R128)
true_peak = -1.0          # True peak limit in dBTP
```

### Configuration Reference

#### `[paths]` Section
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `epubs` | string | `"epubs"` | Directory containing input EPUB files |
| `out` | string | `"out"` | Directory for output `.m4b` files |
| `cache` | string | `"cache"` | Directory for cached TTS chunks and intermediate files |
| `logs` | string | `"logs"` | Directory for log files |
| `errors` | string | `"errors"` | Directory for per-book error logs (JSON) |

#### `[logging]` Section
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `level` | string | `"INFO"` | Log level for file logs |
| `console_level` | string | `"INFO"` | Log level for console output |

**Valid log levels:** `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

#### `[tts]` Section
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `engine` | string | `"mlx"` | TTS engine (only `mlx` supported) |
| `model_id` | string | `"mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit"` | HuggingFace model identifier |
| `voice` | string or `null` | `null` | Voice preset (model-dependent) |
| `lang_code` | string or `null` | `null` | Language code (`null` = auto-detect) |
| `speed` | float | `1.0` | Playback speed multiplier (0.5 = 2x slower, 2.0 = 2x faster) |
| `sample_rate` | int | `24000` | Audio sample rate in Hz |
| `channels` | int | `1` | Number of audio channels (1 = mono, 2 = stereo) |
| `max_chars` | int | `1000` | Target maximum characters per TTS request |
| `min_chars` | int | `200` | Minimum characters to consider when splitting text |
| `hard_max_chars` | int | `1250` | Absolute limit for TTS input size |
| `max_retries` | int | `2` | Number of retries for transient failures |
| `backoff_base` | float | `0.5` | Base backoff delay in seconds (exponential) |
| `backoff_jitter` | float | `0.1` | Random jitter added to backoff delays |
| `output_format` | string | `"wav"` | TTS output format |

#### `[audio]` Section
| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `silence_ms` | int | `250` | Silence duration between segments (milliseconds) |
| `normalize` | bool | `true` | Enable EBU R128 loudness normalization |
| `target_lufs` | float | `-23.0` | Target integrated loudness (LUFS) |
| `lra` | float | `7.0` | Loudness range target (LU) |
| `true_peak` | float | `-1.0` | True peak limit (dBTP) |

### Configuration Tips

**Faster processing (lower quality):**
```toml
[tts]
sample_rate = 24000
max_chars = 1500       # Larger chunks = fewer TTS calls

[audio]
silence_ms = 150       # Less silence between segments
normalize = false      # Skip normalization (faster)
```

**Higher quality (slower):**
```toml
[tts]
sample_rate = 48000    # Higher sample rate
max_chars = 500        # Smaller chunks = better prosody

[audio]
silence_ms = 500       # More dramatic pauses
normalize = true
target_lufs = -23.0
lra = 7.0
true_peak = -2.0       # More conservative peak limit
```

**Faster speech:**
```toml
[tts]
speed = 1.25           # 25% faster
```

**Slower speech:**
```toml
[tts]
speed = 0.8            # 20% slower
```

## Directory Layout

After running `epub2audio init`, your project will look like:

```
.
├── config.toml          # Configuration file
├── epubs/               # Input EPUB files
│   ├── book1.epub
│   └── book2.epub
├── out/                 # Output M4B files
│   ├── book1/
│   │   └── book1.m4b
│   └── book2/
│       └── book2.m4b
├── cache/               # Cached data
│   ├── tts/
│   │   └── chunks/     # Cached TTS audio chunks
│   ├── chapters/       # Per-chapter audio files
│   ├── work/           # Temporary processing
│   ├── packaging/      # M4B intermediate files
│   └── state/          # Per-book state JSON files
├── logs/                # Log files
│   └── run-*.log       # Per-run logs
└── errors/              # Error logs
    ├── book1.json      # Per-book error logs
    └── book2.json
```

## Output

### Audiobook Files
Each EPUB produces an `.m4b` file in the `out/` directory:

```
out/<book-slug>/<book-slug>.m4b
```

The `.m4b` file includes:
- Chapter markers for navigation
- Metadata (title, author, from EPUB)
- Cover art (if present in EPUB)

### Logs
- **Per-run log:** `logs/run-<timestamp>.log` - Overall processing log
- **Per-book log:** `logs/<book-slug>/<run-id>.log` - Book-specific log

### Error Logs
Per-book error logs are stored in `errors/<book_slug>.json` with structured information including:
- Timestamp, category, severity
- Chapter and segment details
- Exception messages and stack traces

## Development

This project uses `pytest` for testing.

```bash
# Install dev dependencies
pip3 install -e ".[dev]"

# Run tests
pytest

# Run specific test file
pytest tests/test_tts_pipeline.py
```

See `documentation/development_plan.md` for the architectural roadmap and implementation details.

## License

[MIT](LICENSE)
