"""Measure 220-440 Hz actionable coverage in voice files.

Reports, per file: fraction of frames with (a) periodic f0 in-band,
(b) spectral band dominance, (c) BOTH (AUD-B-005 actionable), plus the
longest continuous actionable stretch and f0 distribution.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

WORKSPACE = Path(__file__).resolve().parent.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from audio import ffmpeg_io, harmonic  # noqa: E402
from audio.dsp import stft  # noqa: E402

SR, NFFT, HOP = 48000, 4096, 2048
LO, HI = 220.0, 440.0


def analyze(path: str, tag: str) -> None:
    work = Path(f"/tmp/analyze_{tag}.wav")
    if not work.exists():
        ffmpeg_io.decode_to_wav(path, work, SR)
    x = ffmpeg_io.load_mono_wav(work, SR)
    spec = np.abs(stft(x, NFFT, HOP))
    freqs = np.fft.rfftfreq(NFFT, 1 / SR)
    band = (freqs >= LO) & (freqs <= HI)
    tot = spec ** 2
    dom = (tot[:, band].sum(axis=1) / (tot.sum(axis=1) + 1e-12)) >= 0.5
    n = spec.shape[0]
    inband = np.zeros(n, dtype=bool)
    f0s = np.zeros(n)
    w = np.hanning(NFFT)
    for i in range(n):
        if not dom[i]:
            continue
        s = i * HOP
        frame = x[s:s + NFFT]
        if len(frame) < NFFT:
            frame = np.pad(frame, (0, NFFT - len(frame)))
        f0, per = harmonic.estimate_f0_frame(frame * w, SR)
        if LO <= f0 <= HI and per >= 0.3:
            inband[i] = True
            f0s[i] = f0
    both = dom & inband
    # Longest continuous actionable run.
    best = cur = 0
    for v in both:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    f = f0s[f0s > 0]
    dur = len(x) / SR
    print(f"{tag}: {dur/60:.1f} min, frames={n}")
    print(f"  f0 in-band: {inband.mean()*100:.2f}%  band-dominant: {dom.mean()*100:.2f}%  "
          f"BOTH(actionable): {both.mean()*100:.2f}%")
    print(f"  longest actionable stretch: {best*HOP/SR:.2f}s")
    if len(f):
        print(f"  in-band f0: median={np.median(f):.0f} p90={np.percentile(f,90):.0f} "
              f"max={f.max():.0f} Hz over {len(f)} frames")
    else:
        print("  no in-band periodic frames at all")


if __name__ == "__main__":
    import tempfile
    if len(sys.argv) > 2:
        # argv: tag path [tag path ...]
        args = sys.argv[1:]
        for tag, path in zip(args[0::2], args[1::2]):
            analyze(path, tag)
    else:
        tmp = Path(tempfile.gettempdir())
        analyze(str(tmp / "voice1.mp3"), "voice1(sample_01)")
        analyze(str(tmp / "voice2.mp3"), "voice2(sample_02)")
        analyze(str(tmp / "voice3.mp3"), "voice3(sample_03)")
