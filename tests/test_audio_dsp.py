"""DSP unit tests: rebalance (AUD-B-004) and harmonic (AUD-B-005) on synthetic
stems with known ground truth (independent of separator availability).
"""
from __future__ import annotations

import numpy as np

from audio import harmonic, rebalance
from audio.dsp import istft, stft

SR = 48000


def tone(freq: float, seconds: float, amp: float = 0.5) -> np.ndarray:
    t = np.arange(int(seconds * SR)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float64)


def test_stft_roundtrip():
    x = tone(330, 1.0)
    y = istft(stft(x), length=len(x))
    edge = 4096
    err = np.abs(x[edge:-edge] - y[edge:-edge]).max()
    assert err < 1e-6, err


def test_rebalance_enforces_margin_with_ramps():
    # Voice 300 Hz @ -20 dBFS, background 300 Hz @ -10 dBFS for 12 s.
    n = 12 * SR
    voice = tone(300, 12.0, amp=0.1)
    bg = tone(300, 12.0, amp=1.0)
    bg_proc, events = rebalance.attenuate_background(
        voice, bg, SR, db_margin=2.0, ramp_s=3.0)
    assert len(events) >= 1
    e = events[0]
    assert e["type"] == "attenuate-background" and e["ramp_s"] >= 3.0
    # Body (excluding ramp transitions): margin must hold.
    V = np.abs(stft(voice, 4096, 2048))
    B = np.abs(stft(bg_proc, 4096, 2048))
    pv, _ = rebalance.peak_band_power(V)
    pb, _ = rebalance.peak_band_power(B)
    margin = 10 * np.log10(np.maximum(pv, 1e-12)) - 10 * np.log10(np.maximum(pb, 1e-12))
    i0 = int((e["start"] + e["ramp_s"]) * SR / 2048)
    i1 = int(max(e["start"] + e["ramp_s"] + 0.5, e["end"] - e["ramp_s"]) * SR / 2048)
    assert margin[i0:i1].min() >= 1.9, margin[i0:i1].min()
    # Gain-envelope smoothness (our processing): recompute envelope steps.
    gain, need = rebalance.compute_gain_frames(voice, bg, 4096, 2048, 2.0)
    need_db = -20.0 * np.log10(np.maximum(gain, 1e-12))
    env, _ = rebalance.constant_depth_envelope(need_db, 70, SR, 2048)
    edb = 20 * np.log10(np.maximum(env, 1e-9))
    step = float(np.abs(np.diff(edb)).max())
    assert step <= 1.0, step


def test_rebalance_silent_background_is_noop():
    voice = tone(300, 4.0, amp=0.3)
    bg = np.zeros_like(voice)
    bg_proc, events = rebalance.attenuate_background(voice, bg, SR)
    assert events == []
    assert np.allclose(bg_proc, 0.0)

def test_harmonic_adds_f0_over_2_and_preserves_energy():
    # 330 Hz voice (inside 220-440 band), 4 s.
    voice = tone(330, 4.0, amp=0.4)
    out, events = harmonic.add_octave_harmonic(voice, SR)
    assert len(events) >= 1
    e = events[0]
    assert e["type"] == "octave-harmonic" and e["harmonic_ratio"] == 0.5
    assert 220 <= e["f0_mean_hz"] <= 440
    # Energy preserved within +-5% over the event region.
    i0, i1 = int(e["start"] * SR), int(e["end"] * SR)
    ratio = (out[i0:i1] ** 2).sum() / (voice[i0:i1] ** 2).sum()
    assert 0.95 <= ratio <= 1.05, ratio
    # f0/2 component present: project output region onto 165 Hz.
    t = np.arange(i1 - i0) / SR
    proj = abs(np.mean(out[i0:i1] * np.exp(-2j * np.pi * 165 * t)))
    assert proj > 0.01, proj


def test_harmonic_ignores_out_of_band_voice():
    voice = tone(150, 4.0, amp=0.4)  # below the 220-440 band: no event
    out, events = harmonic.add_octave_harmonic(voice, SR)
    assert events == []
    assert np.allclose(out, voice)


def test_harmonic_ignores_sub_threshold_blips():
    # 0.15 s in-band blip inside silence: too short for an event.
    voice = np.zeros(2 * SR)
    t = np.arange(int(0.15 * SR)) / SR
    voice[SR:SR + len(t)] = 0.4 * np.sin(2 * np.pi * 330 * t)
    out, events = harmonic.add_octave_harmonic(voice, SR)
    assert events == []
