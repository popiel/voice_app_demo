"""Octave-down harmonic for 220-440 Hz-dominant voices (AUD-B-005).

Per voiced frame: estimate f0 (autocorrelation + parabolic interpolation),
test whether voice energy is dominant in [band_lo, band_hi], and if so
synthesize sin(f0/2) with HALF the primary (fundamental) energy. Phase is
continuous across each region; regions get short raised-cosine edges; each
region is then renormalized so total voice energy equals the pre-harmonic
energy. Returns processed voice plus AUD-IF-001 `octave-harmonic` events.
"""
from __future__ import annotations

import numpy as np

from .dsp import raised_cosine, stft, upsample_envelope


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
    # Cumulative-mean-normalized difference (YIN): full curve first, then
    # the first sub-threshold dip, walking forward to its local minimum.
    cmn = np.ones(hi + 1)
    run = 0.0
    for tau in range(lo, hi + 1):
        run += (1 - ac[tau])
        cmn[tau] = (1 - ac[tau]) * (tau - lo + 1) / max(run, 1e-12)
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
                        dominance: float = 0.5,
                        voiced: np.ndarray | None = None,
                        min_region_s: float = 0.3,
                        ) -> tuple[np.ndarray, list[dict]]:
    """Apply AUD-B-005. Returns (voice_processed, events)."""
    voice = np.asarray(voice, dtype=np.float64)
    spec = np.abs(stft(voice, n_fft, hop))
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)
    band = (freqs >= band_lo) & (freqs <= band_hi)
    total = spec ** 2
    band_e = total[:, band].sum(axis=1)
    tot_e = total.sum(axis=1) + 1e-12
    dom = (band_e / tot_e) >= dominance

    n_frames = spec.shape[0]
    if voiced is None:
        vmask = np.ones(n_frames, dtype=bool)
    else:
        vmask = np.asarray(voiced, dtype=bool)
        if len(vmask) != n_frames:
            vmask = np.ones(n_frames, dtype=bool)

    f0s = np.zeros(n_frames)
    amps = np.zeros(n_frames)
    w = np.hanning(n_fft)
    for i in range(n_frames):
        if not (dom[i] and vmask[i]):
            continue
        s = i * hop
        frame = voice[s:s + n_fft]
        if len(frame) < n_fft:
            frame = np.pad(frame, (0, n_fft - len(frame)))
        f0, per = estimate_f0_frame(frame * w, sr)
        if f0 >= band_lo and f0 <= band_hi and per >= 0.3:
            f0s[i] = f0
            amps[i] = fundamental_amplitude(frame, sr, f0)

    qual = f0s > 0
    harm = np.zeros(len(voice))
    if np.any(qual):
        # Per-sample f0/amplitude tracks, phase-continuous synthesis.
        f0_s = upsample_envelope(f0s, len(voice), hop, n_fft)
        a_s = upsample_envelope(amps, len(voice), hop, n_fft)
        # Zero amplitude where no qualifying neighbor frames exist.
        mask = upsample_envelope(qual.astype(float), len(voice), hop, n_fft) > 0.25
        phase = np.cumsum(2 * np.pi * f0_s / 2 / sr)
        harm_seg = (a_s / np.sqrt(2)) * np.sin(phase) * mask
        harm = harm_seg

    out = voice + harm
    events: list[dict] = []
    if np.any(qual):
        idx = np.flatnonzero(qual)
        s = p = idx[0]
        frame_s = hop / sr
        center = n_fft / 2 / sr
        edge = max(1, int(0.01 * sr))  # 10 ms temp edges before renorm accounting
        blocks = []
        for i in idx[1:]:
            if i == p + 1:
                p = i
            else:
                blocks.append((s, p))
                s = p = i
        blocks.append((s, p))
        for (a, b) in blocks:
            i0 = int(a * hop + n_fft / 2)
            i1 = min(len(out), int(b * hop + n_fft / 2))
            if (i1 - i0) / sr < min_region_s:
                continue  # ignore sub-threshold estimation blips
            if i1 - i0 < edge * 2 + 1:
                continue
            # Short edge fade on the ADDED harmonic only, then renormalize.
            add = out[i0:i1] - voice[i0:i1]
            r = raised_cosine(edge)
            add[:edge] *= r
            add[-edge:] *= r[::-1]
            orig_e = float(np.sum(voice[i0:i1] ** 2))
            new_e = float(np.sum((voice[i0:i1] + add) ** 2))
            scale = np.sqrt(orig_e / new_e) if new_e > 0 else 1.0
            # Energy-preserving: scale voice+harmonic so region energy is unchanged.
            out[i0:i1] = (voice[i0:i1] + add) * scale
            fmean = float(f0s[a:b + 1][f0s[a:b + 1] > 0].mean())
            events.append({
                "type": "octave-harmonic",
                "start": round(i0 / sr, 1), "end": round(i1 / sr, 1),
                "f0_mean_hz": round(fmean, 1),
                "harmonic_ratio": harmonic_ratio,
            })
    return out, events
