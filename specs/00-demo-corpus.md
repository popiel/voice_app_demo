# Spec 0 — Synthesized Demo Corpus (rights-cleared)

Source: `README.md` podcast scenario, constrained by NPR Terms of Use
(personal noncommercial only; no modification/derivatives; stream from
originating servers). The live demo therefore does NOT download, modify,
or re-serve NPR audio. All processing/demos use this synthesized,
rights-cleared corpus.

Requirement IDs in this file use prefix `COR-` and are stable for
cross-referencing (consumed by `DIS-`, `AUD-`, `SITE-` specs).

## 1. Goal

Provide a small, reproducible, legally remixable demo set that exercises
every README behavior: voice + music/noise mixes at known SNRs (to trigger
the ≥ 2 dB attenuation rule), 3 s ramp audibility, 440–880 Hz-dominant
voices (to trigger the octave-down harmonic), and full-length transcripts
for the summary feature.

## 2. Voice sources (allowlist only)

* **[COR-V-001]** LibriVox recordings: public-domain dedication. Volunteers
  release recordings into the public domain; anyone may use/remix/sell them
  without permission or attribution (courtesy credit only). PRIMARY voice
  source. Ref: `wiki.librivox.org — Copyright and Public Domain`.
* **[COR-V-002]** LibriSpeech corpus (OpenSLR SLR12, derived from LibriVox):
  `CC-BY 4.0`. Reproduces/shares Adapted Material allowed with attribution.
  Allowed as cut/segmented demo voice.
* **[COR-V-003]** Hi-Fi TTS (OpenSLR SLR109, LibriVox-derived): `CC-BY 4.0`.
  Allowed with attribution.
* **[COR-V-004]** VCTK (CSTR, Edinburgh DataShare): `ODC-By 1.0`. Freely
  share/modify/use including commercial, subject to attribution + Produced
  Work notice (see `COR-L-003`). Allowed with attribution notice.
* **[COR-V-005]** DENYLIST for demo audio content (do NOT place these bytes
  in redistributed demo mixes): Google crowdsourced OpenSLR sets
  (`CC-BY-SA 4.0` ShareAlike), DEMAND (`CC-BY-SA 3.0`), PTDB-TUG (`ODbL`),
  CREMA-D (`DBCL`), Edinburgh-56 custom terms, VoxCeleb. Rationale:
  ShareAlike/copyleft or custom terms would attach to the remixed demo
  output. These datasets may have trained the *models* (RNNoise /
  DeepFilterNet weights) but their audio is not demo content.

## 3. Noise sources (allowlist only)

* **[COR-N-001]** Freesound CC0 subset (as curated in DNS-Challenge):
  `CC0` public domain. Allowed, no attribution required.
* **[COR-N-002]** Xiph RNNoise noise packs (`background_noise.sw`,
  `foreground_noise.sw`, `rnnoise_contributions.tar.gz` via
  `media.xiph.org/rnnoise/data/`): project-distributed training noise,
  BSD-licensed project. Allowed per RNNoise training docs.
* **[COR-N-003]** AudioSet clips: `CC-BY 4.0`. Allowed with attribution.
* **[COR-N-004]** DENYLIST: DEMAND noise (`CC-BY-SA 3.0`) excluded from
  redistributed demo mixes (ShareAlike). May be referenced for model
  training only.

## 4. Orchestral music beds (allowlist only — both layers must be clear in the US)

Recordings carry two copyrights (composition + performance). A bed is
eligible ONLY if both are clear in the US:

* **[COR-M-001]** Musopen Public-Domain-dedicated / `CC0` / Public Domain
  Mark 1.0 recordings of public-domain compositions (composer death +70y or
  earlier; e.g. Beethoven d.1827, Mendelssohn d.1847, Mussorgsky d.1881).
  Remix/redistribute/commercial allowed, no permission needed. Anchor
  example: Czech National Symphony Orchestra, Beethoven Symphony No. 3
  (Musopen 2012, Public Domain dedicated) via IMSLP/Musopen.
* **[COR-M-002]** Open Goldberg Variations (Bach; `CC0` recording + PD
  composition). Allowed.
* **[COR-M-003]** IMSLP files tagged `Public Domain (dedicated)` or `CC0`
  where the page confirms US public-domain status for BOTH work and
  recording. Courtesy attribution to performers requested.
* **[COR-M-004]** DENYLIST: any IMSLP/Musopen item tagged `Non-PD US`,
  `Non-PD EU`, `CC-BY-NC`, `CC-BY-ND`, or `CC-BY-SA` (incl. e.g. Skidmore
  College Orchestra / Mussorgsky `CC-BY-SA 3.0`, Toscanini-era
  `Non-PD US` pressings). NC/ND/SA terms conflict with remixed demo
  playback. Composition-PD alone is NOT sufficient — the recording must
  also be clear.

## 5. Synthesis recipe

* **[COR-S-001]** Voice prep: take utterances from `COR-V-001`–`COR-V-004`,
  resample to 48 kHz mono/stereo PCM, trim silence, loudness-normalize
  voices to a common target (e.g. −23 LUFS speech).
* **[COR-S-002]** Bed prep: take orchestral excerpts from `COR-M-001`–
  `COR-M-003`, normalize beds to a fixed level below voice (e.g. voice
  −23 LUFS, bed −30 LUFS baseline) so mixes start near/above the 2 dB
  margin and the attenuator has work to do.
* **[COR-S-003]** Mix fixtures at known SNRs (e.g. voice+music at 0 dB and
  −5 dB voice-relative; voice+CC0 noise at 5 dB) with deterministic seeds.
  Include: (a) music-bed fixture for `AUD-B-004`; (b) noise fixture for
  `AUD-B-003` DeepFilterNet path; (c) 440–880 Hz-dominant voice fixture
  (high-pitched speakers and/or calibrated validation tone) for `AUD-B-005`.
* **[COR-S-004]** Provenance: every clip ships with `provenance.json`
  `{clip_id, voice_src{url,license}, music_or_noise_src{url,license},
  mix_snr_db, seed, f0_range_hz}` plus a human-readable `ATTRIBUTION.md`.
  Generator (`scripts/build_samples.py`) is deterministic.
* **[COR-S-005]** Corpus lives at `corpus/{clip_id}.wav + provenance.json`
  and is the DEFAULT and ONLY audio the demo pipeline processes and the
  site serves. NPR URLs appear link-only, never as bytes (see `DIS-IN-004`).

## 6. License compliance display

* **[COR-L-001]** `CC-BY 4.0` content (LibriSpeech, Hi-Fi TTS, AudioSet):
  credit creator, link license, note modifications.
* **[COR-L-002]** `CC0` / Public Domain dedication (LibriVox, Freesound-CC0
  subset, Musopen-PD, Open Goldberg): no legal attribution required;
  courtesy credit retained in `ATTRIBUTION.md`.
* **[COR-L-003]** `ODC-By 1.0` content (VCTK): attribution + Produced Work
  notice on any public use — the site (`SITE-S-005`) must state the
  remixed demo derives from VCTK and is available under `ODC-By 1.0`
  terms for the database portion.
* **[COR-L-004]** `ATTRIBUTION.md` + per-clip `provenance.json` are shipped
  with the repo and rendered/linked by the site. Adding a source outside
  `COR-V-001`–`COR-M-003` requires a spec amendment.

## 7. Acceptance criteria

* **[COR-AC-001]** Every `corpus/*.wav` has a `provenance.json` whose
  licenses resolve to exactly one of: PD dedication, `CC0`, `CC-BY 4.0`,
  `ODC-By 1.0`, Apache-2.0, BSD, MIT/ISC/Unlicense. No `BY-SA/BY-NC/BY-ND`,
  `ODbL`, `DBCL`, or `Non-PD US` entries exist.
* **[COR-AC-002]** Fixtures cover: music-bed mix, noise mix, and
  440–880 Hz-dominant voice mix, each ≥ 30 s with at least one 3 s
  ramp-exercising transition.
* **[COR-AC-003]** Re-running the generator with the same seed reproduces
  bit-identical mixes (or documents the nondeterminism source).
* **[COR-AC-004]** No NPR bytes exist anywhere under `corpus/`,
  `storage/staging/`, or `storage/processed/` in the demo configuration.
