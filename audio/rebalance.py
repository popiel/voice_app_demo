"""Rebalance: voice must exceed background by >= db_margin dB (AUD-B-004).

Per STFT frame, compare the highest-energy frequency bin of the voice stem
against that of the background stem. Where the margin is violated, attenuate
ONLY the background (never boost voice) to restore exactly the margin, with a
raised-cosine `ramp_s` smooth step before AND after each attenuated region
(overlapping ramps merge via elementwise minimum). Returns the processed
background plus AUD-IF-001 `attenuate-background` events.
"""
from __future__ import annotations

import numpy as np

from .dsp import raised_cosine, stft, to_db, upsample_envelope


def peak_band_power(mag: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-frame peak-bin power (peak +- 1 bin) and peak-bin index."""
    mag = np.asarray(mag)
    k = np.argmax(mag, axis=1)
    n_bins = mag.shape[1]
    k0 = np.clip(k - 1, 0, n_bins - 1)
    k1 = np.clip(k + 1, 0, n_bins - 1)
    p = mag[np.arange(len(k)), k] ** 2
    p = p + mag[np.arange(len(k)), k0] ** 2 + mag[np.arange(len(k)), k1] ** 2
    return p, k


def compute_gain_frames(voice: np.ndarray, bg: np.ndarray,
                        n_fft: int = 4096, hop: int = 2048,
                        db_margin: float = 2.0,
                        voiced: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Return (gain_frames, atten_db_frames) for the background stem."""
    V = np.abs(stft(voice, n_fft, hop))
    B = np.abs(stft(bg, n_fft, hop))
    pv, _ = peak_band_power(V)
    pb, _ = peak_band_power(B)
    margin = to_db(pv) - to_db(pb)  # +inf where bg is silent: no attenuation
    need = np.zeros(len(margin))
    if voiced is None:
        voiced = np.ones(len(margin), dtype=bool)
    else:
        voiced = np.asarray(voiced, dtype=bool)
        if len(voiced) != len(margin):
            voiced = np.ones(len(margin), dtype=bool)
    viol = voiced & np.isfinite(margin) & (margin < db_margin)
    need[viol] = db_margin - margin[viol]
    gain = 10.0 ** (-need / 20.0)
    return gain, need


def smooth_with_ramps(gain: np.ndarray, ramp_frames: int) -> np.ndarray:
    """Legacy fixed-ramp smoother (kept for API compatibility).

    Prefer attenuate_background(), which sizes ramps from block depth so the
    slope never exceeds ~1 dB/100 ms (see MAX_SLOPE_DB_S).
    """
    env = np.ones_like(gain)
    if ramp_frames <= 0:
        return np.minimum(env, gain)
    below = gain < (1.0 - 1e-9)
    if not np.any(below):
        return env
    idx = np.flatnonzero(below)
    # Contiguous blocks.
    blocks: list[tuple[int, int]] = []
    s = p = idx[0]
    for i in idx[1:]:
        if i == p + 1:
            p = i
        else:
            blocks.append((s, p))
            s = p = i
    blocks.append((s, p))
    up = raised_cosine(ramp_frames)
    for (a, b) in blocks:
        edge_in = gain[a]
        edge_out = gain[b]
        # Ramp-in: preceding frames go 1.0 -> edge gain.
        i0 = max(0, a - ramp_frames)
        if a - i0 > 0:
            seg = 1.0 - (1.0 - edge_in) * up[-(a - i0):]
            env[i0:a] = np.minimum(env[i0:a], seg)
        # Block body.
        env[a:b + 1] = np.minimum(env[a:b + 1], gain[a:b + 1])
        # Ramp-out: following frames go edge gain -> 1.0.
        i1 = min(len(env), b + 1 + ramp_frames)
        seg = 1.0 - (1.0 - edge_out) * up[:i1 - (b + 1)][::-1]
        env[b + 1:i1] = np.minimum(env[b + 1:i1], seg)
    return env


# Maximum attenuation slope: 1 dB per 100 ms == 10 dB/s would still exceed
# the limit on a cosine flank (peak slope ~= pi/2 x average), so budget
# 6 dB/s average -> peak flank step ~= 0.4 dB/frame (~0.94 dB/100 ms).
MAX_SLOPE_DB_S = 6.0
MIN_RAMP_S = 3.0  # spec floor: smooth step never shorter than 3 s each side


def constant_depth_envelope(need_db: np.ndarray, ramp_floor_frames: int,
                            sr: int, hop: int
                            ) -> tuple[np.ndarray, list[tuple[int, int, float, float]]]:
    """Build the gain envelope from per-frame attenuation need (dB, >= 0).

    Each contiguous need>0 block is held at its CONSTANT worst-case depth
    (README: voice AT LEAST +2 dB, so over-attenuating non-worst frames is
    compliant, while per-frame tracking would inject jarring steps). Edges
    get raised-cosine ramps of max(3 s, depth/6dB-per-s). Overlapping ramps
    merge via elementwise minimum.

    Returns (env_frames, blocks) with blocks = (start, end, depth_db,
    ramp_s) in frame units for the RAW blocks (ramps extend beyond).
    """
    env = np.ones_like(need_db, dtype=float)
    blocks: list[tuple[int, int, float, float]] = []
    idx = np.flatnonzero(need_db > 1e-9)
    if len(idx) == 0:
        return env, blocks
    s = p = idx[0]
    raw: list[tuple[int, int]] = []
    for i in idx[1:]:
        if i == p + 1:
            p = i
        else:
            raw.append((s, p))
            s = p = i
    raw.append((s, p))
    # Merge near-adjacent raw blocks: a constant-depth junction between two
    # touching blocks would be a gain cliff, so spans separated by only a
    # few clean frames share one (max) depth. Over-attenuating the gap is
    # compliant (README: voice AT LEAST +2 dB).
    merge_gap = max(1, int(0.5 * sr / hop))
    merged: list[tuple[int, int]] = []
    for (a, b) in raw:
        if merged and a - merged[-1][1] - 1 <= merge_gap:
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    raw = merged
    for (a, b) in raw:
        depth = float(need_db[a:b + 1].max())
        ramp_s = max(MIN_RAMP_S, depth / MAX_SLOPE_DB_S)
        ramp_frames = max(ramp_floor_frames, int(round(ramp_s * sr / hop)))
        g = 10.0 ** (-depth / 20.0)
        # Ramps are raised-cosines in the dB DOMAIN (0 -> -depth), so the
        # per-frame dB step is bounded by depth*pi/(2*ramp_frames) ~= 0.4 dB
        # by construction. (A linear-domain cosine would have an unbounded
        # dB slope where it meets a deep body gain.)
        # Ramp-in: full cosine when it fits; otherwise start the file
        # already attenuated (flat = no transition = no jarring step).
        i0 = max(0, a - ramp_frames)
        k_in = a - i0
        if k_in >= ramp_frames:
            seg = 10.0 ** (-depth * raised_cosine(k_in) / 20.0)
            env[i0:a] = np.minimum(env[i0:a], seg)
        elif k_in > 0:
            env[i0:a] = np.minimum(env[i0:a], g)
        env[a:b + 1] = np.minimum(env[a:b + 1], g)
        # Ramp-out: symmetric.
        i1 = min(len(env), b + 1 + ramp_frames)
        k_out = i1 - (b + 1)
        if k_out >= ramp_frames:
            seg = 10.0 ** (-depth * raised_cosine(k_out)[::-1] / 20.0)
            env[b + 1:i1] = np.minimum(env[b + 1:i1], seg)
        elif k_out > 0:
            env[b + 1:i1] = np.minimum(env[b + 1:i1], g)
        blocks.append((a, b, depth, ramp_s))
    return env, blocks


def attenuate_background(voice: np.ndarray, bg: np.ndarray, sr: int = 48000,
                         n_fft: int = 4096, hop: int = 2048,
                         db_margin: float = 2.0, ramp_s: float = 3.0,
                         voiced: np.ndarray | None = None
                         ) -> tuple[np.ndarray, list[dict]]:
    """Apply AUD-B-004. Returns (bg_processed, events).

    `ramp_s` is the floor (spec: 3 s each side); deeper blocks get longer
    ramps so the slope stays under ~1 dB/100 ms, and the actual `ramp_s` is
    reported per event (AUD-IF-001).
    """
    voice = np.asarray(voice, dtype=np.float64)
    bg = np.asarray(bg, dtype=np.float64)
    n = max(len(voice), len(bg))
    if len(voice) < n:
        voice = np.pad(voice, (0, n - len(voice)))
    if len(bg) < n:
        bg = np.pad(bg, (0, n - len(bg)))
    gain, need = compute_gain_frames(voice, bg, n_fft, hop, db_margin, voiced)
    need_db = -20.0 * np.log10(np.maximum(gain, 1e-12))
    ramp_floor = int(round(ramp_s * sr / hop))
    env_frames, blocks = constant_depth_envelope(need_db, ramp_floor, sr, hop)
    env = upsample_envelope(env_frames, n, hop, n_fft)
    bg_proc = bg * env
    # Events: contiguous env<1 regions (ramps included); depth/ramp from the
    # raw blocks they cover. Times at 0.1 s (AUD-IF-002).
    events: list[dict] = []
    below = env_frames < (1.0 - 1e-9)
    frame_s = hop / sr
    center = n_fft / 2 / sr
    if np.any(below):
        idx = np.flatnonzero(below)
        s = p = idx[0]
        regions = []
        for i in idx[1:]:
            if i == p + 1:
                p = i
            else:
                regions.append((s, p))
                s = p = i
        regions.append((s, p))
        # Map raw blocks to regions by overlap.
        for (rs, re) in regions:
            cov = [(d, r) for (a, b, d, r) in blocks if a <= re and b >= rs]
            depth = max([d for (d, _) in cov]) if cov else 0.0
            rsamp = max([r for (_, r) in cov]) if cov else ramp_s
            events.append({
                "type": "attenuate-background",
                "start": round(rs * frame_s + center, 1),
                "end": round(re * frame_s + center, 1),
                "attenuation_db": round(float(depth), 1),
                "ramp_s": round(float(rsamp), 1),
            })
    return bg_proc, events
