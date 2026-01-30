# Loudness Normalization Research

## Executive Summary
For the EPUB-to-Audiobook CLI, we will implement loudness normalization using FFmpeg's `loudnorm` filter. This ensures consistent volume levels across chapters and compliance with industry standards. We will support the EBU R128 standard (-23 LUFS) by default, while noting that ACX (Audible) has slightly different RMS-based requirements.

## Standards Overview

### 1. EBU R128 (Broadcast Standard)
*   **Target Loudness:** -23 LUFS (±0.5 LU)
*   **True Peak:** -1 dBTP
*   **Loudness Range (LRA):** No specific limit, but often restricted for comfort.
*   **Use Case:** TV, Radio, and general high-fidelity audio.

### 2. ACX (Audiobook Creation Exchange / Audible)
*   **Measurement:** RMS (Root Mean Square) rather than LUFS.
*   **Target Range:** -23 dB RMS to -18 dB RMS.
*   **Peak Limit:** -3 dB.
*   **Noise Floor:** -60 dB RMS.
*   **Use Case:** Submission to Audible/iTunes.

### 3. Podcast / Mobile Standard
*   **Target Loudness:** -16 LUFS (Stereo) / -19 LUFS (Mono).
*   **True Peak:** -1 dBTP or -1.5 dBTP.
*   **Use Case:** Consumption on mobile devices in noisy environments.

## Recommended Approach

We will use **EBU R128 (-23 LUFS)** as the safe, high-quality default. It is widely supported and ensures dynamic range is preserved. However, for users targeting mobile consumption specifically, a target of -16 LUFS is often preferred.

Since our TTS output is synthetic, it usually has a consistent noise floor (near silent) and stable dynamics, making normalization straightforward.

## FFmpeg Implementation

We will use a **two-pass** approach with the `loudnorm` filter for optimal accuracy.

### Pass 1: Analysis
Measure the audio properties without modifying the file.

```bash
ffmpeg -i input_chapter.wav -af loudnorm=I=-23:LRA=7:TP=-1.0:print_format=json -f null -
```

**Output (JSON):**
```json
{
    "input_i": "-25.0",
    "input_tp": "-2.0",
    "input_lra": "5.0",
    "input_thresh": "-35.0",
    "target_offset": "2.0"
}
```

### Pass 2: Normalization
Apply the normalization using values measured in Pass 1.

```bash
ffmpeg -i input_chapter.wav -af loudnorm=I=-23:LRA=7:TP=-1.0:measured_I=-25.0:measured_LRA=5.0:measured_TP=-2.0:measured_thresh=-35.0:offset=2.0:linear=true -ar 44100 -c:a pcm_s16le output_normalized.wav
```

*   `I`: Target Integrated Loudness (default -23).
*   `TP`: Target True Peak (default -1.0).
*   `LRA`: Target Loudness Range (default 7.0).
*   `linear=true`: Uses linear normalization (preserves dynamics better).
*   `-ar 44100`: Resample to 44.1kHz (standard for audiobooks).
*   `-c:a pcm_s16le`: Output as 16-bit WAV for intermediate processing before M4B encoding.

## Integration Plan

1.  **Stage:** After TTS generation for a chapter.
2.  **Input:** Raw WAV from TTS model.
3.  **Process:**
    *   Run Pass 1 (fast analysis).
    *   Parse JSON output.
    *   Run Pass 2 (normalization).
4.  **Output:** Normalized WAV ready for encoding/concatenation.

## Compatibility
*   **WAV/AIFF:** Fully supported (best for intermediate steps).
*   **MP3/AAC:** Supported, but we should normalize *before* final encoding to avoid generation loss.

## References
*   [EBU R128 Tech Doc](https://tech.ebu.ch/loudness)
*   [FFmpeg loudnorm filter documentation](https://ffmpeg.org/ffmpeg-filters.html#loudnorm)
*   [ACX Audio Submission Requirements](https://www.acx.com/help/acx-audio-submission-requirements/201456300)
