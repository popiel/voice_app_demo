# Tech Stack — Voice Processing Demo

Source requirements: `README.md` — rebalance + pitch-shift voice vs. background
in podcast streams, enforce voice +2 dB in highest-energy frequencies with 3 s
smooth-step attenuation, add -1 octave harmonic at 0.5x energy for voices
dominant in 220–440 Hz with total-energy renormalization, publish private
site with original link + full-stream summary + modification log with timestamps.

Constraint: all components must be perpetually free / OSS. No commercial
free-trials expiring in < 1 month (e.g. Picovoice products).

## 0. Demo corpus (rights-cleared, replaces NPR audio)

Full definition: `specs/00-demo-corpus.md`. NPR podcasts are link-only;
no NPR bytes are downloaded, modified, or served.

* Voice: LibriVox (public-domain dedication, remix allowed) primary;
  LibriSpeech / Hi-Fi TTS (both `CC-BY 4.0`, attribution) and VCTK
  (`ODC-By 1.0`, attribution + Produced Work notice) permitted.
  Excluded from demo mixes: `CC-BY-SA` Google crowdsourced OpenSLR sets,
  DEMAND (`BY-SA`), PTDB (`ODbL`), CREMA-D (`DBCL`), Edinburgh-56 custom,
  VoxCeleb.
* Noise: Freesound CC0 subset + Xiph RNNoise packs (`background_noise.sw` /
  `foreground_noise.sw` / contributions) + AudioSet (`CC-BY 4.0`).
  DEMAND (`BY-SA`) excluded from mixes.
* Music beds: ONLY Musopen / IMSLP / Open Goldberg recordings where BOTH
  composition and recording are PD/CC0 in the US (e.g. Musopen Czech
  National Symphony Orchestra Beethoven 3, Public Domain dedicated).
  Exclude all `Non-PD US`, `NC`, `ND`, `SA` items. Composition-PD alone
  is insufficient.
* Synthesis: `corpus/{clip_id}.wav + provenance.json + ATTRIBUTION.md`,
  deterministic mixes at known SNRs incl. a 220–440 Hz fixture
  (see `COR-S-001`–`COR-S-005`).

## 1. Ingest (stream submission + podcast discovery)

* `feedparser` (BSD-2) + `requests` / `httpx` (MIT / BSD) — poll favorite
  podcast RSS feeds, detect new episodes, download enclosure URLs.
* `yt-dlp` (Unlicense) — fallback downloader for non-RSS / hosted audio.
* `FastAPI` (MIT) — `POST /submit` upload endpoint + polling worker.
  Alternative: `Flask` (BSD).

## 2. Voice / background segregation + VAD (control logic)

* `Silero VAD v6` (`snakers4/silero-vad`) (MIT) — primary speech-timestamp
  source. Drives attenuation on/off decisions and modification-log
  start/end marks. ONNX/CPU, no telemetry, no keys, no expiration.
* `Meta Demucs` (`facebookresearch/demucs`) (MIT) — offline
  `vocals / drums / bass / other` separation. Use when background is
  music. Best OSS vocal SDR (~9.19 dB). Default `htdemucs` (single model)
  on CPU; `htdemucs_ft` (4x ensemble) reserved for GPU runs.
  `pip install demucs`.
* `DeepFilterNet / DeepFilterNet2` (`Rikorose/DeepFilterNet`)
  (MIT/Apache-2.0 dual) — `RNNoise` successor for noisy-speech podcasts.
  Full-band 48 kHz enhancement. CLI `deep-filter audio.wav` + LADSPA plugin.
* `RNNoise` (BSD) — retained only as lightweight fallback, not primary
  separator (denoise-only, poor on music).
* `Spleeter` (`Deezer/spleeter`) (MIT) — lighter 2-stem
  `vocals/accompaniment` fallback if Demucs is too heavy for demo hardware.
  Lower quality than Demucs.
* `WebRTC VAD` (BSD) — ultra-light fallback gate only.
* `pyannote.audio 3.x` (MIT + free HF weights, requires free HF token) —
  optional, only if multi-speaker diarization is needed for the summary.

Decision: `Silero VAD` for control + `Demucs` for music podcasts /
`DeepFilterNet` for noisy-speech podcasts.

## 3. DSP / analysis / remix

* `ffmpeg` / `libav` (LGPL/GPL) — decode, filter
  (`afftdn, acompressor, afade, sidechaincompress, loudnorm`), remix, encode.
  Already approved baseline.
* `numpy` + `scipy.signal` + `soundfile` (BSD) — STFT band-energy
  measurement, +2 dB enforcement, 3 s raised-cosine (`1-cos`) ramps,
  additive harmonic synthesis, RMS/total-energy renormalization.
* `librosa` (ISC) — `stft`, `pyin`, effects, band analysis. Used for
  220–440 Hz dominance test and `f0` estimation.
* `CREPE` (MIT) — alternative `f0` estimator if `pyin` is too noisy.
* Transcription alignment: `WhisperX` (BSD) for word timestamps.

Harmonic recipe: voice-level trigger — if >3% of frames have periodic
`f0` in 220–440 Hz, add phase-continuous `sine(f0/2)` at 0.5x primary energy
to every voiced frame across the whole recording → renormalize whole voice
to original total energy.

Avoid for this demo: `Spotify pedalboard` (GPLv3), `Essentia` (AGPLv3),
`Rubber Band library` (GPL) — copyleft taint if distributed; use `ffmpeg`
filters + `numpy`/`librosa` instead.

## 4. Transcription → summarization

* `faster-whisper` (`SYSTRAN/faster-whisper`) (MIT) — primary STT.
  CTranslate2, ~4x `openai/whisper`, `int8` CPU-friendly.
* `whisper.cpp` (`ggml-org/whisper.cpp`) (MIT) — alternative STT, 5–10x,
  no Python/CUDA dependency.
* `Vosk` (Apache-2.0) — tiny offline fallback.
* `Ollama` (Apache-2.0 server) + `llama3.2` / `qwen2.5` / `mistral` / `phi4`
  (Llama Community / Apache / MIT) — local summarizer via
  `http://localhost:11434/api/chat`. Produces full-stream summary locally.
* `HuggingFace transformers: facebook/bart-large-cnn, google-t5`
  (Apache/MIT) — pure-Python alternative if no `ollama` daemon is desired.

Pipeline: `audio → faster-whisper/whisper.cpp → transcript (+ WhisperX
timestamps) → Ollama/llama3.2 → summary.md`.

## 5. Publishing (private site + audit log)

* `FastAPI` (MIT) static routes + `SQLite` (public domain) — serve
  `original.mp3 | remixed.mp3 | summary.md | mods.json`.
* `mods.json` schema: `[{type, start, end, detail_dB_or_f0}]`, derived from
  `Silero VAD` segments + DSP stage parameters. `ffmpeg -progress`
  provides encode timestamps.

## 6. Explicitly rejected (trial expiry risk)

* `Picovoice (Cheetah/Leopard/Cobra/etc.)`, `Descript`, `Dolby.io`,
  `AssemblyAI` / cloud STT — free tier / trial < 1 month, expires before
  live demo. Replaced by `faster-whisper` + `Silero VAD` + `Ollama` above.

## 7. Reference pipeline

```text
feedparser/yt-dlp → ffmpeg decode → Silero VAD timestamps
  → Demucs or DeepFilterNet stems
  → numpy/scipy + librosa.pyin (+2 dB / 3 s ramp / octave harmonic + renorm)
  → ffmpeg remix/loudnorm
  → faster-whisper → Ollama/llama3.2 summary
  → FastAPI + SQLite private site
```
