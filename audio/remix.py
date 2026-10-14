"""Remix: sum processed stems, limit peak, encode (AUD-B-006)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .ffmpeg_io import encode_mp3, write_wav


def remix(voice: np.ndarray, bg: np.ndarray, peak_limit: float = 0.89) -> np.ndarray:
    """Sum stems and normalize peak to `peak_limit` (< 0 dBFS)."""
    n = max(len(voice), len(bg))
    v = np.pad(np.asarray(voice, dtype=np.float64), (0, n - len(voice)))
    b = np.pad(np.asarray(bg, dtype=np.float64), (0, n - len(bg)))
    mix = v + b
    peak = float(np.abs(mix).max()) if len(mix) else 0.0
    if peak > peak_limit and peak > 0:
        mix = mix * (peak_limit / peak)
    return mix


def write_remix(mix: np.ndarray, sr: int, out_dir: str | Path) -> tuple[Path, Path]:
    """Write remixed.wav + remixed.mp3 (site player needs mp3, SITE-B-003)."""
    out_dir = Path(out_dir)
    wav = out_dir / "remixed.wav"
    mp3 = out_dir / "remixed.mp3"
    write_wav(wav, mix, sr)
    encode_mp3(wav, mp3)
    return wav, mp3
