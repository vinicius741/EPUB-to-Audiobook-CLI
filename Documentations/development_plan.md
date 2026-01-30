# EPUB to Audiobook CLI — Development Plan (Phased)

This plan is designed for phased delivery with discrete tasks, explicit dependencies, and verification steps. Each task includes a status checkbox, parallelization marker, difficulty, and research requirement.

Legend:
- Status: [ ] not done, [x] done
- Parallel?: Parallel = can be done in parallel with other tasks in the same phase; Sequential = should be completed before dependent tasks
- Difficulty: Easy / Medium / Hard
- Research?: Yes (what) / No

## Phase 0 — Project foundation & structure
Goal: Establish repository structure, coding standards, and initial CLI scaffolding.

| Status | Task | Parallel? | Difficulty | Research? | Notes/Dependencies |
|---|---|---|---|---|---|
| [x] | Create base package layout (src/, tests/, resources/) | Sequential | Easy | No | Foundation for all modules |
| [x] | Define module interfaces/contracts (EPUB, cleaner, segmenter, TTS, audio, packaging, state) | Sequential | Medium | No | Aligns all downstream work |
| [x] | Create initial CLI entrypoint `epub2audio` | Sequential | Medium | No | Can be minimal: prints help + runs pipeline stub |
| [x] | Add logging framework + per-book log structure | Parallel | Medium | No | Needed for error handling and resumability |
| [x] | Add config loader (defaults + optional config.toml) | Parallel | Medium | No | Will be used in most modules |

Verification (Phase 0):
- `epub2audio` runs and prints a calm summary stub
- `config.toml` (if present) is read and overrides defaults
- Logs created for a dummy run

## Phase 1 — EPUB ingestion + text pipeline
Goal: Extract chapters in correct order, clean/normalize text, segment into safe chunks.

| Status | Task | Parallel? | Difficulty | Research? | Notes/Dependencies |
|---|---|---|---|---|---|
| [x] | Implement EPUB reader + TOC/reading order extraction | Sequential | Hard | [Done](research/01_epub_parsing_research.md) | Critical correctness task |
| [x] | Extract metadata (title, author, cover) | Parallel | Medium | [Done](research/02_epub_metadata_research.md) | Needed for packaging |
| [x] | Build text cleaner/normalizer (whitespace, unicode normalization, citations) | Parallel | Medium | No | Keep defaults conservative |
| [x] | Implement text segmenter with punctuation + length rules | Sequential | Medium | No | Used by TTS and caching |
| [x] | Add chunk retry/split logic on synth failure (design) | Parallel | Medium | No | Used in Phase 2 |

Verification (Phase 1):
- For a known EPUB, chapters extracted in correct order
- Cleaned text is readable and normalized
- Segmenter outputs safe, bounded chunks ending with punctuation
- Metadata and cover are extracted when present

## Phase 2 — TTS abstraction + default engine
The select model is mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit
Goal: Add TTS engine interface, default local model, and chunk synthesis flow.

| Status | Task | Parallel? | Difficulty | Research? | Notes/Dependencies |
|---|---|---|---|---|---|
| [ ] | Define TTS interface (synthesize(text, voice, config) -> audio) | Sequential | Medium | No | Enables swappable engines |
| [ ] | Select and integrate default local TTS model | Sequential | Hard | Yes (model capabilities, licensing, runtime deps) | Must be zero-config |
| [ ] | Implement chunk synthesis pipeline using TTS interface | Sequential | Medium | No | Uses segmenter outputs |
| [ ] | Add failure retry by splitting chunk | Parallel | Medium | No | Use exponential backoff / split strategy |
| [ ] | Add CLI `doctor` checks for TTS model loadability | Parallel | Medium | Yes (model init patterns) | Improves UX |

Verification (Phase 2):
- Single chunk synthesizes audio via default engine
- Long chunk triggers automatic split and succeeds
- `epub2audio doctor` reports model availability

## Phase 3 — Audio pipeline + caching
Goal: Deterministic chunk caching, silence insertion, normalization, stitching to chapter audio.

| Status | Task | Parallel? | Difficulty | Research? | Notes/Dependencies |
|---|---|---|---|---|---|
| [ ] | Deterministic chunk hashing (text + voice + model config) | Sequential | Medium | No | Cache key for reuse |
| [ ] | Cache storage layout in `cache/` | Sequential | Medium | No | Must be resumable |
| [ ] | Add silence insertion between chunks | Parallel | Medium | No | Use ffmpeg or audio lib |
| [ ] | Add loudness normalization | Parallel | Hard | Yes (EBU R128 / ffmpeg filters) | Must be consistent |
| [ ] | Stitch chunks into chapter-level audio | Sequential | Medium | No | Consumes cached chunks |

Verification (Phase 3):
- Cache hit prevents re-synthesis
- Chapters play with pauses between chunks
- Normalized audio levels are consistent

## Phase 4 — Packaging to .m4b + metadata
Goal: Create final audiobook output with chapter markers and metadata.

| Status | Task | Parallel? | Difficulty | Research? | Notes/Dependencies |
|---|---|---|---|---|---|
| [ ] | Define packaging pipeline interface | Sequential | Medium | No | M4B output contract |
| [ ] | Implement .m4b creation from chapter audio | Sequential | Hard | Yes (ffmpeg/MP4 container specifics) | Must support chapters |
| [ ] | Embed metadata (title, author) | Parallel | Medium | Yes (mp4 tags) | Use extracted metadata |
| [ ] | Embed cover image (if present) | Parallel | Medium | Yes (mp4 cover tagging) | Optional but required when available |
| [ ] | Validate output path structure and naming | Parallel | Easy | No | `out/<book_slug>/<book_slug>.m4b` |

Verification (Phase 4):
- .m4b plays in Apple Books or standard player
- Chapters are visible and correct
- Metadata and cover appear when available

## Phase 5 — Resumability + state management
Goal: Durable per-book state tracking, safe resumability, and error isolation.

| Status | Task | Parallel? | Difficulty | Research? | Notes/Dependencies |
|---|---|---|---|---|---|
| [ ] | Define state file schema (JSON/TOML) | Sequential | Medium | No | Tracks pipeline progress |
| [ ] | Record per-step completion in state file | Sequential | Medium | No | Required for resume |
| [ ] | Skip completed steps on re-run | Sequential | Medium | No | Deterministic behavior |
| [ ] | Ensure per-book errors don’t halt others | Parallel | Medium | No | Process remaining books |
| [ ] | Final summary report (success/fail, output paths) | Parallel | Medium | No | Needed for UX |

Verification (Phase 5):
- Interrupt mid-run and resume without redoing work
- A failing book does not stop subsequent books
- Summary lists success/fail + outputs

## Phase 6 — CLI polish + user workflows
Goal: Finish CLI behavior and default folders; add init/doctor and UX polish.

| Status | Task | Parallel? | Difficulty | Research? | Notes/Dependencies |
|---|---|---|---|---|---|
| [ ] | Ensure folder auto-creation (epubs/, out/, cache/) | Sequential | Easy | No | Core UX |
| [ ] | Implement `epub2audio init` | Parallel | Medium | No | Creates folders + optional config |
| [ ] | Implement quiet-by-default output + progress indicators | Parallel | Medium | No | Calm, readable output |
| [ ] | Add structured error logs per book | Parallel | Medium | No | Improves diagnostics |
| [ ] | Add minimal debug flags (optional) | Parallel | Easy | No | Keep defaults zero-config |

Verification (Phase 6):
- Running `epub2audio` with no args processes all ./epubs
- `epub2audio init` creates folders and optional config
- Output is readable and not noisy by default

## Phase 7 — Hardening, tests, and docs
Goal: Improve reliability, add tests, and document usage.

| Status | Task | Parallel? | Difficulty | Research? | Notes/Dependencies |
|---|---|---|---|---|---|
| [ ] | Add unit tests for segmenter + hash + state | Parallel | Medium | No | Deterministic tests |
| [ ] | Add integration test for EPUB -> m4b (sample) | Sequential | Hard | No | Requires sample EPUB |
| [ ] | Add failure-case tests (bad EPUB, TTS fail) | Parallel | Medium | No | Ensures resilience |
| [ ] | Write README usage + defaults | Parallel | Easy | No | User onboarding |
| [ ] | Add developer docs (architecture, module contracts) | Parallel | Medium | No | Supports extensibility |

Verification (Phase 7):
- Tests pass locally
- README matches CLI behavior and defaults

---

## Cross-cutting considerations
- Determinism: Use consistent hashing and stable processing order
- Extensibility: Keep TTS engine and packaging pluggable
- Fail-safe: Every stage should be idempotent and resumable

## Tracking notes
- Mark tasks as [x] when completed.
- If research is needed, log findings in a short note file under `Documentations/research/`.
