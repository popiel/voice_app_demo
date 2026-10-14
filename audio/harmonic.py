"""Octave-down harmonic for 220-440 Hz voices, voice-level trigger (AUD-B-005).

Rule: if more than `trigger_fraction` (default 3%) of ALL frames have a
periodic f0 inside [band_lo, band_hi], the voice counts as in-band and EVERY
frame with a valid periodic f0 gets an f0/2 harmonic at `harmonic_ratio`
(default 0.5x) primary energy -- consistently across the whole recording so
there are no tonal shifts between modified/unmodified passages. Frames
without a valid f0 (silence, unvoiced) are untouched: there is no pitch to
build a harmonic from, and inventing one would inject tones into pauses.
The whole processed voice is renormalized to the original total energy.
"""
from __future__ import annotations

import numpy as np

from .dsp import raised_cosine, upsample_envelope


def estimate_f0_frame(frame: np.ndarray, sr: int,
                      fmin: float = 60.0, fmax: float = 1000.0,
                      thresh: float = 0.15) -> tuple[float, float]:
    """Return (f0_hz, periodicity). f0 = 0.0 if aperiodic/silent."""
    x = np.asarray(frame, dtype=np.float64)
    x = x - x.mean()
    if np.sqrt(np.mean(x ** 2)) < 1e-6:
        return 0.0, 0.0
    n = len(x)
    spec = np.abs(np.fft.rfft(x, n=2 * n)) ** 2
    ac = np.fft.irfft(spec)[:n]
    if ac[0] <= 0:
        return 0.0, 0.0
    ac = ac / ac[0]
    lo = max(1, int(sr / fmax))
    hi = min(n - 2, int(sr / fmin))
    # Cumulative-mean-normalized difference (YIN): same sequential math as
    # the scalar loop, computed as one vector op instead of ~750 Python
    # iterations. Then the first sub-threshold dip, walking forward to its
    # local minimum.
    cmn = np.ones(hi + 1)
    if hi >= lo:
        d = 1.0 - ac[lo:hi + 1]
        run = np.cumsum(d)
        cmn[lo:hi + 1] = d * np.arange(1, hi - lo + 2) / np.maximum(run, 1e-12)
    best = -1
    for tau in range(lo, hi + 1):
        if cmn[tau] < thresh:
            while tau + 1 <= hi and cmn[tau + 1] < cmn[tau]:
                tau += 1
            best = tau
            break
    if best < 0:
        tau0 = int(np.argmax(ac[lo:hi + 1]) + lo)
        if ac[tau0] < 0.3:
            return 0.0, float(ac[tau0])
        best = tau0
    # Parabolic interpolation.
    y0, y1, y2 = ac[best - 1], ac[best], ac[best + 1]
    denom = (y0 - 2 * y1 + y2)
    shift = 0.5 * (y0 - y2) / denom if abs(denom) > 1e-12 else 0.0
    shift = float(np.clip(shift, -1.0, 1.0))
    period = best + shift
    return float(sr / period), float(np.clip(y1, 0.0, 1.0))


def fundamental_amplitude(frame: np.ndarray, sr: int, f0: float) -> float:
    """Least-squares amplitude of sin/cos at f0 over the frame."""
    n = len(frame)
    t = np.arange(n) / sr
    c = np.cos(2 * np.pi * f0 * t)
    s = np.sin(2 * np.pi * f0 * t)
    a = 2 * np.mean(frame * c)
    b = 2 * np.mean(frame * s)
    return float(np.sqrt(a * a + b * b))


def add_octave_harmonic(voice: np.ndarray, sr: int = 48000,
                        n_fft: int = 4096, hop: int = 2048,
                        band_lo: float = 220.0, band_hi: float = 440.0,
                        harmonic_ratio: float = 0.5,
                        trigger_fraction: float = 0.03,
                        periodicity_min: float = 0.3,
                        ) -> tuple[np.ndarray, list[dict]]:
    """Apply AUD-B-005. Returns (voice_processed, events).

    A single whole-recording event (or none) is ever emitted.
    """
    voice = np.asarray(voice, dtype=np.float64)
    n_frames = 1 + max(0, (len(voice) - n_fft) // hop)

    f0s = np.zeros(n_frames)
    amps = np.zeros(n_frames)
    pers = np.zeros(n_frames)
    w = np.hanning(n_fft)
    for i in range(n_frames):
        s = i * hop
        frame = voice[s:s + n_fft]
        if len(frame) < n_fft:
            frame = np.pad(frame, (0, n_fft - len(frame)))
        f0, per = estimate_f0_frame(frame * w, sr)
        if f0 > 0 and per >= periodicity_min:
            f0s[i] = f0
            pers[i] = per
            amps[i] = fundamental_amplitude(frame, sr, f0)

    inband = (f0s >= band_lo) & (f0s <= band_hi)
    fraction = float(inband.sum()) / max(n_frames, 1)
    if fraction <= trigger_fraction:
        return voice.copy(), []

    # Triggered: harmonic on every frame with a valid f0 (any frequency),
    # phase-continuous across the whole voice.
    valid = f0s > 0
    f0_s = upsample_envelope(f0s, len(voice), hop, n_fft)
    a_s = upsample_envelope(amps, len(voice), hop, n_fft)
    vmask = upsample_envelope(valid.astype(float), len(voice), hop, n_fft) > 0.25
    phase = np.cumsum(2 * np.pi * f0_s / 2 / sr)
    harm = (a_s / np.sqrt(2)) * np.sin(phase) * vmask
    # Click guard at file edges on the ADDED harmonic only.
    edge = max(1, int(0.01 * sr))
    if len(harm) > 2 * edge:
        r = raised_cosine(edge)
        harm[:edge] *= r
        harm[-edge:] *= r[::-1]
    out = voice + harm
    # Whole-voice renormalization (README: same total energy as original).
    orig_e = float(np.sum(voice ** 2))
    new_e = float(np.sum(out ** 2))
    if new_e > 0:
        out = out * np.sqrt(orig_e / new_e)
    dur = round(len(voice) / sr, 1)
    fmean = float(f0s[inband].mean())
    return out, [{
        "type": "octave-harmonic",
        "start": 0.0, "end": dur,
        "f0_mean_hz": round(fmean, 1),
        "harmonic_ratio": harmonic_ratio,
        "trigger_fraction": round(fraction, 4),
    }]
