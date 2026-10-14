"""Verify a processed job meets AUD-AC-001/002 on steady-state frames.

Steady state = voiced frames inside raw violated blocks (constant-depth
bodies): post margin must be >= 2 dB. Ramp-transition frames are reported
separately (smooth by design). Gain-envelope steps (our processing only,
not the music's own dynamics) must stay <= 1 dB/frame (~43 ms).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

WORKSPACE = Path(__file__).resolve().parent.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from audio import ffmpeg_io, rebalance, vad as vadmod  # noqa: E402
from audio.config import PipelineConfig  # noqa: E402
from audio.dsp import stft, to_db  # noqa: E402
from audio.pipeline import voiced_mask  # noqa: E402

SR = 48000


def main(job_dir: str) -> int:
    cfg = PipelineConfig()
    d = Path(job_dir)
    v = ffmpeg_io.load_mono_wav(d / "voice.wav")
    b = ffmpeg_io.load_mono_wav(d / "background.wav")
    mix = v + b
    # Same input scaling the pipeline used (no normalization) so the voiced
    # mask matches the run being verified.
    segs = vadmod.SileroVAD().segments(mix)
    n_f = 1 + max(0, (len(v) - cfg.n_fft) // cfg.hop)
    vm = np.array(voiced_mask(segs, n_f, cfg.n_fft, cfg.hop))

    V = np.abs(stft(v, cfg.n_fft, cfg.hop))
    B = np.abs(stft(b, cfg.n_fft, cfg.hop))
    pv, _ = rebalance.peak_band_power(V)
    pb, _ = rebalance.peak_band_power(B)

    gain, need = rebalance.compute_gain_frames(
        v, b, cfg.n_fft, cfg.hop, cfg.db_margin, vm)
    need_db = -20.0 * np.log10(np.maximum(gain, 1e-12))
    env, blocks = rebalance.constant_depth_envelope(
        need_db, int(round(cfg.ramp_s * SR / cfg.hop)), SR, cfg.hop)

    bp, events = rebalance.attenuate_background(
        v, b, SR, cfg.n_fft, cfg.hop, cfg.db_margin, cfg.ramp_s, vm)
    Bp = np.abs(stft(bp, cfg.n_fft, cfg.hop))
    pb2, _ = rebalance.peak_band_power(Bp)
    post = to_db(np.maximum(pv, 1e-12)) - to_db(np.maximum(pb2, 1e-12))

    ok = True
    body = (need_db > 1e-9) & vm
    if body.sum() == 0:
        print("no violated voiced frames; nothing to enforce")
    else:
        mn = float(post[body].min())
        print(f"violated voiced body frames: {body.sum()}, min post "
              f"margin: {mn:.2f} dB (require >= 2.0)")
        ok = mn >= 2.0 - 1e-6
    edb = 20 * np.log10(np.maximum(env, 1e-9))
    step = float(np.abs(np.diff(edb)).max()) if len(edb) > 1 else 0.0
    print(f"max gain-envelope step per frame (~43ms): {step:.3f} dB "
          f"(require <= 1.0)")
    ok = ok and step <= 1.0
    print(f"events: {len(events)}; ramps: "
          f"{sorted({e['ramp_s'] for e in events})}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
