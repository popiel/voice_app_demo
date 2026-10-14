# Attribution — `test/samples/`

All audio in this directory is public domain in the US. No permission,
license fee, or trial is required to use, modify, or redistribute it
(see `specs/00-demo-corpus.md`, `COR-L-002`).

## Voice — LibriVox (public-domain dedication)

Continuous narration in all three samples, three different volunteer
readers, from **Short Ghost and Horror Story Collection Vol. 016**
(`ghost_and_horror_16_1205_librivox`, https://archive.org/details/ghost_and_horror_16_1205_librivox):

* `sample_01.wav` ← `ghohor016_03_ovalportrait_poe_ep.mp3` (Poe)
* `sample_02.wav` ← `ghohor016_04_xmasgoblins_dickens_bm.mp3` (Dickens)
* `sample_03.wav` ← `ghohor016_05_adarkmirror_CC.mp3`

LibriVox volunteers release their recordings into the public domain;
anyone may remix them, with no attribution legally required. Voice tracks
are used whole (no truncation). Full URLs in `provenance.json`.

## Music — Musopen (Public Domain Mark 1.0)

Sporadic orchestral bursts (see `manifest.json` for time marks), from the
**Musopen Collection** (`MusopenCollectionAsFlac`,
https://archive.org/details/MusopenCollectionAsFlac, PD Mark 1.0 —
both composition and recording public domain):

* `sample_01.wav` ← Beethoven, Coriolan Overture
* `sample_02.wav` ← Mozart, Magic Flute Overture
* `sample_03.wav` ← Mendelssohn, Italian Symphony No. 4, iv. Saltarello

Courtesy credit: recordings via the Musopen project (musopen.org),
a 501(c)(3) nonprofit dedicated to setting music free.

## Mixes

Built with `scripts/build_samples.py`: 48 kHz mono 16-bit WAV, voice
continuous, music in raised-cosine-edged bursts at 0 / +2 / −2 dB SNR vs.
voice (audibly interfering with comprehensibility during bursts),
peak-normalized to −1 dBFS. Durations 8.7–9.5 min (within the required
3–10 min). Details in `manifest.json` + `provenance.json`.
