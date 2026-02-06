# Cross-Platform TTS Support

This project now supports both:

- macOS (Apple Silicon)
- Linux x86_64 (including handheld devices like ROG Ally X on Bazzite)

## Backend Strategy

- Default backend: `kokoro_onnx` with model `onnx-community/Kokoro-82M-v1.0-ONNX`
- Optional backend: `mlx` for Apple Silicon compatibility

The default aims for reliable local inference on both operating systems, with Linux defaulting to CPU provider resolution in `auto` mode.

## Install Matrix

### macOS (cross-platform default)

```bash
pip install -e ".[tts-kokoro]"
```

### macOS (default + MLX compatibility backend)

```bash
pip install -e ".[tts-kokoro,tts-mlx]"
```

### Linux

```bash
pip install -e ".[tts-kokoro]"
```

## Suggested Verification

Run these checks on each device after install:

```bash
epub2audio doctor --verify
```

## Troubleshooting

### `kokoro-onnx` missing

Install the Kokoro extras:

```bash
pip install -e ".[tts-kokoro]"
```

### `onnxruntime` missing

Install the Kokoro extras (includes `onnxruntime`):

```bash
pip install -e ".[tts-kokoro]"
```

### ONNX provider issues on Linux

Use CPU explicitly:

```toml
[tts]
execution_provider = "CPUExecutionProvider"
```

### MLX backend not available

MLX is optional and typically macOS Apple Silicon only. Install with:

```bash
pip install -e ".[tts-mlx]"
```

### First run is slow

The first synthesis/download will populate Hugging Face cache with model files (`model_q8f16.onnx`, `voices-v1.0.bin`).
