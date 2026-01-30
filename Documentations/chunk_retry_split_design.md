# Chunk Retry + Split Design (Phase 1)

## Goal
Provide a deterministic, resumable strategy for retrying TTS synthesis failures and splitting oversized or problematic chunks. This design feeds Phase 2+ implementation.

## Failure Handling Strategy
1. **Attempt synthesis** for a chunk with a bounded retry count.
2. **Classify failure**:
   - **Transient** (timeouts, temporary load, GPU/CPU spikes): retry with backoff.
   - **Deterministic/size-related** (model max input, decoder errors): split the chunk and retry per split.
3. **Escalate** when retries are exhausted or chunk is already at minimum size.

## Retry Policy
- `max_retries`: 2–3 (configurable).
- `backoff`: exponential (e.g., 0.5s, 1s, 2s) with small jitter.
- Log failure type, chunk hash, attempt count, and error class for diagnostics.

## Split Policy
Splitting should be **deterministic** and **stable** so caching/resume is safe.

Order of split attempts:
1. **Sentence boundaries** (preferred).
2. **Clause boundaries** (commas/semicolons) if still too large.
3. **Word boundaries** (last resort).
4. **Hard split** for single-word oversize chunks.

Constraints:
- Respect `min_chars` and `hard_max_chars` used by the segmenter.
- Always end split chunks with punctuation (append "." if missing).
- Preserve original ordering and text fidelity (only minimal punctuation addition).

## Resumability + Caching
- Each chunk (original or split) should have a **deterministic hash** derived from:
  - chunk text (post-clean/segment)
  - voice/model configuration
  - TTS engine version/identifier
- Split children should derive an identifier from the parent hash + child index.
- Successful synthesis should be cached immediately so retries resume safely.

## Proposed Flow (Pseudo)
```
def synthesize_with_retry(chunk):
    for attempt in range(max_retries + 1):
        try:
            return tts.synthesize(chunk)
        except SizeError or InputError:
            return split_and_synthesize(chunk)
        except TransientError:
            backoff(attempt)
    raise FinalError

def split_and_synthesize(chunk):
    if chunk.length <= min_chars:
        raise FinalError
    children = split_chunk(chunk)
    return [synthesize_with_retry(child) for child in children]
```

## Open Questions (Phase 2+)
- How to classify errors (exception types vs error strings).
- Whether to persist per-chunk retry metadata in the state file.
- How to expose retry/split knobs in config/CLI.
