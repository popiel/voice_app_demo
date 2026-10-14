# Plan — Processing Speedup (single-stream latency, CPU-only)

Status: **Phase 0 + Phase 1 IMPLEMENTED and measured (2026-10-14).**
Phase 2 (segment parallelism) deferred — revisit only if further gains
needed. Original deferral gate (other session's test campaign) cleared:
their harmonic-retune commits `b3b838c`/`7a53578` landed before this work.

## 0. Results (sample_03, 520.5 s audio, 28-core CPU-only box)

| Run | Total | Per min | Demucs | Transcribe | Notes |
|---|---|---|---|---|---|
| Baseline (`337bdadd8226`) | 471.3 s | 54.3 s | (unmeasured) | (unmeasured) | beam 5, no vad_filter, 4 torch threads (observed) |
| + Phase 1, 4 threads (`541334939886`) | 429.9 s | 49.6 s | 396.5 s (92%) | 12.7 s | per-stage timing added; whisper already cheap |
| + 28 threads (`402dc1ee27c7`) | **151.7 s** | **17.5 s** | **120.6 s** | 13.1 s | **3.1× vs baseline** |

Remaining budget: VAD 4.1 s, harmonic 3.4 s, remix 2.2 s, finalize
(mp3 encode) 1.9 s, decode 0.1 s. Demucs is still 80% — further gains
need GPU or segment-parallel Demucs (Phase 2).

## 1. Baseline (measured 2026-10-14)

- `storage/processed/337bdadd8226/run.json`: **471.3 s wall-clock for
  520.5 s of audio → 54.3 s/min (~0.9× realtime)** on sample_03.
- Second run (`4d0bb5d8a43a`, sample_01): 498.9 s for 564.0 s → 53.1 s/min.
- Full stack engaged in both: `silero-v6` → `demucs-htdemucs` →
  `faster-whisper/base` → `ollama/llama3.2`.
- `run.json` records stages but **no per-stage durations** — exact
  attribution is currently impossible (motivates Phase 0).

## 2. Diagnosis (code analysis, `audio/`)

Serial chain, mostly single-core Python — one pegged core reads as idle on a
28-core box:

- **Demucs `htdemucs` on CPU** (`audio/separate.py:67`, `device="cpu"`):
  84 MB transformer, stereo 44.1 kHz, chunks run sequentially in one
  process. Expected dominant share.
- **faster-whisper `base`, `beam_size=5`, `vad_filter=False`**
  (`audio/transcribe.py:36-38`): ~5× decoder work vs greedy, including
  silence/music beds.
- **Silero confidence loop** (`audio/vad.py:68-79`): one `model(chunk)`
  dispatch per 512-sample chunk (~12k dispatches for sample_03).
- **YIN f0 loop** (`audio/harmonic.py:37-51,101-111`): pure-Python
  per-frame loop; runs even when yielding 0 events.
- **`voiced_mask`** (`audio/pipeline.py:64-75`): O(frames × segments)
  nested Python loop. **`dsp.stft` / `frame_rms_frames`**: per-frame
  Python loops (3 full STFTs per job).
- **Model reload per job**: `process_job` builds fresh Demucs + Whisper
  instances each call (per-instance cache only) — repeated cost on
  multi-job runs.

## 3. Agreed constraints (user answers, 2026-10-14)

- **CPU-only.** `torch 2.11.0+cpu`, no `nvidia-smi`; display GPU unusable
  without a CUDA torch reinstall (parked as optional follow-up).
- **Small numerical diffs acceptable.** Parallel paths validate against
  quality metrics (`AUD-AC-001/002`, `tests/test_audio_dsp.py`) with
  tolerance, not bit-identity (`COR-AC-003` relaxed for these paths —
  requires a spec note when implemented).
- **Single-stream latency first.** Cross-job worker pool deferred.

## 4. Phases

### Phase 0 — Instrument (extends `AUD-B-010`)

Per-stage wall-clock into `run.json` + episodes row. Files:
`audio/pipeline.py`, `app/db.py`, specs `02`/`03` touch-up.
Rerun sample_03 and rank stages before further spending.

### Phase 1 — Zero-quality-change wins (est. ~2–4× combined)

- Whisper `beam_size=1` + `vad_filter=True` (`audio/transcribe.py`).
- Batched Silero confidence: one stacked forward, not ~12k dispatches
  (`audio/vad.py:68-79`).
- Vectorize `voiced_mask`; gate f0 estimation to qualifying frames only.
- torch thread audit (`OMP/MKL_NUM_THREADS`, verify Demucs spreads over
  the 20 configured threads).

### Phase 2 — Segment parallelism within one job

- Transcription first: split on VAD/silence boundaries → shard workers →
  offset timestamps back.
- VAD on overlapped chunks + merge; Demucs chunk worker pool (one 84 MB
  model copy per worker — bound by RAM); rebalance/harmonic with ≥3 s
  overlap, crossfade, event dedup at seams.
- Acceptance: `AUD-AC-001/002` within tolerance, `tests/test_audio_dsp.py`
  green, close-match (not bit-identical) determinism check.

### Phase 3 — Pipeline overlap (secondary)

Overlap Demucs→rebalance streaming; keep `AUD-B-007` parallel allowance.
Cross-job pool explicitly deferred.

## 5. Out of scope

CUDA torch reinstall; quality-reducing model swaps (`tiny` whisper,
separator downgrades); frequency-band or licensing changes (other
session's territory).

## 6. Implementation gate

Begin Phase 0 only after the other session's test campaign
(`tests/test_audio_dsp.py` and related `audio/*` work) is committed and
green, then rebase this plan against the final code.
