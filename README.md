# epub2audio

**epub2audio** is a command-line tool that converts EPUB ebooks into high-quality audiobooks (`.m4b`) using local, offline Text-to-Speech (TTS) models. It is optimized for Apple Silicon using the [MLX](https://github.com/ml-explore/mlx) framework.

## Features

- **Local & Private:** Runs entirely on your machine. No cloud APIs, no data leaks.
- **Apple Silicon Optimized:** Leverages MLX for efficient, high-performance inference on Mac.
- **Smart Text Processing:** parses EPUB structure, cleans text, and segments it intelligently for natural-sounding speech.
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
cd epub2audio

# Recommended: Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .
```

## Usage

### 1. Initialize
Set up the default folder structure and configuration file:

```bash
epub2audio init
```

This creates:
- `epubs/`: Place your input `.epub` files here.
- `out/`: Destination for generated `.m4b` audiobooks.
- `cache/`: Intermediate storage for synthesized audio chunks (speeds up re-runs).
- `logs/`: Log files for debugging.
- `config.toml`: Configuration file with default settings.

**Options:**
- `--force`: Overwrite existing `config.toml` if it exists.
- `--no-config`: Skip creating `config.toml` (folders only).

### 2. Check Environment
Run the doctor command to verify your setup and test the TTS model:

```bash
epub2audio doctor
```

This checks for GPU availability, model readiness, and runs a quick smoke test.

### 3. Convert Books
Process all EPUBs in the default `epubs/` directory:

```bash
epub2audio
```

Or specify individual files/folders:

```bash
epub2audio my_book.epub another_folder/
```

## Configuration

You can customize behavior via `config.toml`. Key options include:

- **TTS Settings:** Model selection, speed, and sample rate.
- **Audio Processing:** Silence duration, loudness targets (LUFS).
- **Paths:** Custom directories for inputs, outputs, and logs.

Example `config.toml` snippet:

```toml
[tts]
speed = 1.0
model_id = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit"

[audio]
normalize = true
target_lufs = -23.0
silence_ms = 250
```

## Development

This project uses `pytest` for testing.

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```

See `documentation/development_plan.md` for the architectural roadmap and implementation details.

## License

[MIT](LICENSE)
