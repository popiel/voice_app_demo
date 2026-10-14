# Spec 2 — Audio Processing (rebalance + pitch-shift + summary)

Source: `README.md:6-7`, stack: `specs/tech_stack.md` §2–§4.
Consumes `pending` jobs from Spec 1. Produces remixed audio + modification
log + transcript + summary consumed by Spec 3. No HTTP serving here.

Requirement IDs in this file use prefix `AUD-` and are stable for
cross-referencing (e.g. `AUD-OUT-001` is rendered by `SITE-B-003`).

## 1. Goal

For each job, output a remixed stream where voice is always ≥ 2 dB above
non-voice in their respective highest-energy frequencies (by attenuating
non-voice, with 3 s smooth-step ramps in/out), plus an octave-down harmonic
at 0.5x primary energy for 220–440 Hz-dominant voices with total voice-energy
renormalization.

## 2. Inputs / outputs

* **[AUD-IN-001]** In: `jobs.local_path` (staged source from `DIS-B-006`,
  or corpus clip via `DIS-B-007`), `job_id`. Worker polls
  `jobs WHERE status=pending`.
* **[AUD-IN-002]** Demo jobs MUST carry corpus provenance (`COR-S-004`):
  voice from `COR-V-001`–`COR-V-004`, bed/noise from `COR-N-001`–`COR-N-003`
  / `COR-M-001`–`COR-M-003` only. Denylists `COR-V-005`, `COR-N-004`,
  `COR-M-004` are rejected at ingest.
* **[AUD-OUT-001]** Out `remixed.{mp3|wav}` (per job, under
  `storage/processed/{job_id}/`): final mix with the same sample rate and
  channel count as the original (normalized decode default 48 kHz; channels
  match the source) and duration within ±50 ms.
* **[AUD-OUT-002]** Out `mods.json`: ordered list of all modifications with
  begin/end times (schema in `AUD-IF-001`).
* **[AUD-OUT-003]** Out `transcript.{json,txt}` + `summary.md`: full-stream
  contents summary.
* **[AUD-OUT-004]** Intermediate voice/non-voice stems retained for audit,
  not served.

## 3. Pipeline stages

* **[AUD-B-001]** Decode/normalize: `ffmpeg` → 48 kHz PCM WAV. Record
  `duration`, channels.
* **[AUD-B-002]** VAD + timestamps: `Silero VAD v6` → speech segments
  `[{start, end, confidence}]`. These are the candidate voice regions and
  the basis of `mods.json` time marks.
* **[AUD-B-003]** Separation: split into `voice` and `background` stems.
  * Music-heavy: `Demucs htdemucs` family, voice = `vocals` stem.
    Default `htdemucs` (single model) on CPU; `htdemucs_ft` (4x ensemble)
    reserved for GPU runs. Record `method` used.
  * Noise-only: `DeepFilterNet2` enhancement (voice = enhanced, background =
    residual `source − voice`).
  * `RNNoise` allowed only as documented fallback. Record `method` used.
* **[AUD-B-004]** Rebalance (≥ 2 dB rule):
  * Frame analysis (e.g. 100 ms STFT via `numpy/scipy`, `librosa`) finds
    highest-energy frequency bin of voice vs. background per frame.
  * Where `voice_dB − background_dB < 2`, compute background attenuation
    gain to restore exactly 2 dB margin (attenuate only, never boost voice).
  * Apply gain with 3 s raised-cosine (`1-cos`) ramp before AND after each
    attenuated region so there are no jarring steps. Overlapping ramps merge.
  * Log each attenuated region as
    `{type: "attenuate-background", start, end, attenuation_db, ramp_s: 3}`.
* **[AUD-B-005]** Harmonic (220–440 Hz rule, voice-level trigger):
  * Per frame, estimate `f0` and periodicity (autocorrelation;
    `librosa.pyin` / `CREPE` allowed as estimators).
  * Count frames with a periodic `f0` inside 220–440 Hz. If MORE than 3%
    of ALL frames qualify, the voice triggers: EVERY frame with a valid
    periodic `f0` (any frequency) gets a phase-continuous `sine(f0/2)`
    harmonic at 0.5x primary energy — consistently across the entire
    recording, so the voice never shifts character mid-stream. Frames
    without a valid `f0` (silence, unvoiced) are untouched.
  * Renormalize: scale the whole processed voice so its total energy equals
    the original voice total (energy-preserving).
  * Log a SINGLE whole-recording event as
    `{type: "octave-harmonic", start: 0.0, end: duration,
    f0_mean_hz, harmonic_ratio: 0.5, trigger_fraction}`.
    Below threshold: voice bit-identical, no events.
* **[AUD-B-006]** Remix: `voice_processed + background_processed` →
  `ffmpeg loudnorm`, encode. Verify duration and no clipping
  (peak < 0 dBFS or limiter applied).
* **[AUD-B-007]** Transcribe + summarize (runs in parallel with
  `AUD-B-002`–`AUD-B-006` or after; uses ORIGINAL or voice stem — record
  which): `faster-whisper` (or `whisper.cpp`) → transcript; `WhisperX` word
  timestamps optional; `Ollama + llama3.2` (or `bart/t5` fallback) →
  `summary.md` covering ENTIRE stream.
* **[AUD-B-008]** Finalize: mark job `done`, write `mods.json` (union of
  `AUD-B-004` + `AUD-B-005` events). Entries from all sources are collated
  and sorted for display in timestamp order.
* **[AUD-B-009]** Status transitions: the worker atomically claims a `pending`
  job by setting `processing` before any DSP runs; on success `AUD-B-008`
  marks it `done`; on failure it marks `failed` with a `reason` string and
  writes no audio outputs. Only `done` jobs gain an `episodes` row.
* **[AUD-B-010]** Processing-time statistics: the worker measures wall-clock
  time with a monotonic clock from claim (`processing`) to finalize
  (`done`/`failed`), stores `processing_time_s` on the `episodes` row (and
  in `run.json` under `timing`), and derives processing time per minute of
  audio as `processing_time_s / (duration_s / 60)` (0 when `duration_s` is 0).

## 4. `mods.json` contract (also read by Spec 3)

* **[AUD-IF-001]** Schema (rendered verbatim by `SITE-B-003`):

```json
[
  {"type": "attenuate-background", "start": 12.4, "end": 45.0,
   "attenuation_db": 4.5, "ramp_s": 3.0},
  {"type": "octave-harmonic", "start": 13.0, "end": 20.5,
   "f0_mean_hz": 520.0, "harmonic_ratio": 0.5}
]
```

* **[AUD-IF-002]** Times in seconds (float, 0.1 s resolution). Empty list is
  valid (no modification needed) but must still be written.

## 5. Non-functional

* **[AUD-NF-001]** Deps per tech stack only (`ffmpeg`,
  `numpy/scipy/soundfile`, `librosa`, `torch` for Silero/Demucs,
  `faster-whisper`, `ollama` client). No Picovoice or other trial-gated calls.
* **[AUD-NF-002]** Deterministic for same input + config: record model
  names/versions and DSP parameters in `run.json` alongside outputs.
* **[AUD-NF-003]** CPU-runnable for demo (GPU optional acceleration for
  Demucs/whisper).

## 6. Acceptance criteria

* **[AUD-AC-001]** On the corpus music-bed fixture (`COR-S-003` item (a)), voice band
  measures ≥ 2 dB over background band in every VAD-voiced frame of
  `remixed.*`.
* **[AUD-AC-002]** Attenuation edges show ~3 s continuous ramp
  (no step > 1 dB per 100 ms).
* **[AUD-AC-003]** On a voice with >3% in-band frames: exactly one
  whole-recording `octave-harmonic` event; spectrum shows `f0/2`
  components; total voice energy matches original within ±5%. On a
  below-threshold voice: no events and bit-identical voice.
* **[AUD-AC-004]** `mods.json` entries cover every applied DSP region with
  start/end; unmodified regions have no entries.
* **[AUD-AC-005]** `summary.md` + transcript exist and correspond to full
  duration.
* **[AUD-AC-006]** Job never requires network beyond local models (after
  first model download).
* **[AUD-AC-007]** No NPR bytes processed: all test fixtures are corpus clips
  satisfying `COR-AC-001`/`COR-AC-004`.
* **[AUD-AC-008]** Every `done` job's `episodes` row carries `processing_time_s`
  greater than 0 and `run.json` contains a matching `timing` block.
