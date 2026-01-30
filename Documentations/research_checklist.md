# Research Checklist

This document tracks all research tasks identified in the development plan that need to be completed before implementation.

## Phase 1 — EPUB ingestion + text pipeline

### 1. EPUB Reader and TOC/Reading Order Extraction
**Task**: Implement EPUB reader + TOC/reading order extraction
**Research needed**: EPUB specification and library capabilities

- [ ] Research EPUB file format specification (EPUB 2.0 and 3.0+)
- [ ] Identify and evaluate Python libraries for EPUB parsing:
  - [ ] ebooklib
  - [ ] epub2txt
  - [ ] Other available options
- [ ] Understand TOC (Table of Contents) structure in EPUB files
- [ ] Understand reading order extraction (spine/linear attribute)
- [ ] Document recommended library and approach

---

### 2. EPUB Metadata Extraction
**Task**: Extract metadata (title, author, cover)
**Research needed**: EPUB metadata fields

- [ ] Research EPUB metadata format and fields (dc:title, dc:creator, etc.)
- [ ] Identify all standard metadata fields available
- [ ] Understand cover image extraction from EPUB
- [ ] Document metadata extraction strategy
- [ ] Identify edge cases (missing metadata, multiple authors, etc.)

---

## Phase 2 — TTS abstraction + default engine

### 3. Default Local TTS Model Selection
**Task**: Select and integrate default local TTS model
**Research needed**: Model capabilities, licensing, runtime dependencies

- [ ] Research available local TTS models:
  - [ ] Piper TTS
  - [ ] Coqui TTS
  - [ ] Espeak-ng
  - [ ] Other open-source options
- [ ] Evaluate model capabilities and quality
- [ ] Verify licensing compatibility (must be permissible for distribution)
- [ ] Identify runtime dependencies (Python packages, system libraries)
- [ ] Test model download/initialization process
- [ ] Document recommended model and integration approach
- [ ] Verify zero-config requirement (no API keys, works offline)

---

### 4. TTS Model Loadability Checks
**Task**: Add CLI `doctor` checks for TTS model loadability
**Research needed**: Model initialization patterns

- [ ] Research how selected TTS model initializes
- [ ] Identify common failure modes for model loading
- [ ] Determine what checks can be performed for "doctor" command
- [ ] Document doctor command specification

---

## Phase 3 — Audio pipeline + caching

### 5. Loudness Normalization
**Task**: Add loudness normalization
**Research needed**: EBU R128 / ffmpeg filters

- [ ] Research EBU R128 loudness normalization standard
- [ ] Identify ffmpeg filters for loudness normalization
- [ ] Determine target loudness values for audiobooks
- [ ] Research compatibility across different audio formats
- [ ] Document normalization approach and ffmpeg commands

---

## Phase 4 — Packaging to .m4b + metadata

### 6. M4B Creation with Chapter Markers
**Task**: Implement .m4b creation from chapter audio
**Research needed**: ffmpeg/MP4 container specifics

- [ ] Research MP4/M4B container format
- [ ] Identify how to embed chapter markers in M4B files
- [ ] Determine ffmpeg commands for M4B creation with chapters
- [ ] Test chapter marker format (Apple's chapter format vs alternatives)
- [ ] Document M4B creation workflow

---

### 7. M4B Metadata Embedding
**Task**: Embed metadata (title, author)
**Research needed**: MP4 tags

- [ ] Research MP4 metadata tag format (iTunes-style tags)
- [ ] Identify standard tags for audiobooks (©nam, ©ART, ©gen, etc.)
- [ ] Determine ffmpeg commands for metadata embedding
- [ ] Document metadata embedding strategy

---

### 8. M4B Cover Image Embedding
**Task**: Embed cover image (if present)
**Research needed**: MP4 cover tagging

- [ ] Research how to embed cover images in M4B files
- [ ] Identify correct ffmpeg commands for cover embedding
- [ ] Determine optimal cover image dimensions and formats
- [ ] Document cover embedding strategy

---

## Summary

**Total Research Tasks**: 8

| Phase | Research Tasks |
|-------|---------------|
| Phase 1 | 2 |
| Phase 2 | 2 |
| Phase 3 | 1 |
| Phase 4 | 3 |

## Research Notes

Each research task should produce:
1. A brief summary of findings
2. Recommended approach/technology
3. Code examples where applicable
4. Any caveats or edge cases discovered

Research findings should be saved to `Documentations/research/` with descriptive filenames (e.g., `epub_parsing_research.md`, `tts_model_evaluation.md`, etc.).
