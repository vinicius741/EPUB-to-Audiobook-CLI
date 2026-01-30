# M4B Packaging, Metadata, and Chapters Research

This document outlines the findings for Phase 4 of the research checklist, focusing on the creation of `.m4b` audiobook files using FFmpeg, embedding chapter markers, and applying iTunes-compatible metadata and cover art.

## 1. M4B Container and Chapters

The `.m4b` format is essentially an MP4 container (MPEG-4 Part 14) that typically contains AAC-encoded audio. The primary distinction from `.m4a` is the extension, which signals to players (like Apple Books/iTunes) that the file is an audiobook.

### FFMETADATA Format
FFmpeg uses a specific metadata file format (`ffmetadata`) to define global tags and chapter markers.

**Example `metadata.txt`:**
```ini
;FFMETADATA1
title=The Great Adventure
artist=Jane Doe
album=The Adventure Series
genre=Audiobook
date=2026
comment=A thrilling tale of research.
stik=2

[CHAPTER]
TIMEBASE=1/1000
START=0
END=300000
title=Chapter 1: The Beginning

[CHAPTER]
TIMEBASE=1/1000
START=300000
END=900000
title=Chapter 2: The Middle
```
*   `stik=2`: Crucial tag to identify the file as an audiobook in Apple ecosystems.
*   `TIMEBASE=1/1000`: Timestamps are in milliseconds.

## 2. Metadata Tagging

FFmpeg maps common keys to MP4 atoms. For audiobook-specific needs:

| FFmpeg Key | MP4 Atom | Purpose |
| :--- | :--- | :--- |
| `title` | `©nam` | Audiobook Title |
| `artist` | `©ART` | Author |
| `album` | `©alb` | Series / Book Title |
| `genre` | `©gen` | Genre |
| `date` | `©day` | Release Date / Year |
| `description` | `desc` | Long Description / Synopsis |
| `stik` | `stik` | Media Type (Set to `2` for Audiobook) |

## 3. Cover Image Embedding

### Recommendations
*   **Aspect Ratio:** 1:1 (Square).
*   **Dimensions:** Minimum 1400x1400 pixels; Recommended 2400x2400 pixels or higher (up to 4000x4000).
*   **Format:** JPG (preferred for compatibility) or PNG.

### FFmpeg Command
To embed the cover image as "Album Art" rather than a video track, use the `attached_pic` disposition.

## 4. Final FFmpeg Command Workflow

The recommended command to combine audio, cover, and metadata/chapters:

```bash
ffmpeg -i input_audio.wav -i cover.jpg -i metadata.txt \
  -map 0:a -map 1:v -map_metadata 2 \
  -c:a aac -b:a 128k \
  -disposition:v:0 attached_pic \
  -metadata:s:v title="Album cover" \
  -metadata:s:v comment="Cover (front)" \
  output_audiobook.m4b
```

### Explanation:
*   `-i input_audio.wav`: Primary audio (Stream 0).
*   `-i cover.jpg`: Cover image (Stream 1).
*   `-i metadata.txt`: FFMETADATA file (Stream 2).
*   `-map 0:a`: Map audio from stream 0.
*   `-map 1:v`: Map video (image) from stream 1.
*   `-map_metadata 2`: Pull global and chapter metadata from stream 2.
*   `-c:a aac -b:a 128k`: Encode to AAC at 128kbps (Standard for audiobooks).
*   `-disposition:v:0 attached_pic`: Marks the video stream as a static cover image.

## 5. Caveats and Edge Cases
*   **Zero-Copy:** If the input audio is already AAC, use `-c:a copy` to avoid re-encoding and preserve quality.
*   **Character Encoding:** Ensure the `metadata.txt` file is UTF-8 encoded to handle special characters in titles or author names.
*   **Multiple Files:** If the project produces multiple chapter files, they should be concatenated using FFmpeg's `concat` demuxer before or during the final packaging.
