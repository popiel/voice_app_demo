"""ffmpeg decode/encode helpers (AUD-B-001, AUD-B-006).

Uses the imageio-ffmpeg static binary so no system ffmpeg is required.
Only stdlib + imageio_ffmpeg + soundfile + numpy are needed.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import soundfile as sf

EXE = imageio_ffmpeg.get_ffmpeg_exe()


def _run(*args: str) -> None:
    subprocess.run([EXE, "-y", "-v", "error", *args], check=True)


def decode_to_wav(src: str | Path, dst: str | Path, sr: int = 48000) -> dict:
    """Decode any audio to mono s16 PCM WAV at `sr` (AUD-B-001).

    Returns {"duration_s": float}. Raises on undecodable input.
    """
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    _run("-i", str(src), "-ac", "1", "-ar", str(sr), "-sample_fmt", "s16",
         str(dst))
    info = sf.info(str(dst))
    return {"duration_s": info.frames / info.samplerate}


def load_mono_wav(path: str | Path, sr: int = 48000) -> np.ndarray:
    data, rate = sf.read(str(path), dtype="float32", always_2d=True)
    if rate != sr:
        raise ValueError(f"expected {sr} Hz, got {rate} Hz ({path})")
    return data[:, 0].astype(np.float64)


def write_wav(path: str | Path, x: np.ndarray, sr: int = 48000) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.clip(x, -1.0, 1.0).astype(np.float32), sr,
             subtype="PCM_16")


def encode_mp3(wav_path: str | Path, mp3_path: str | Path,
               bitrate: str = "128k") -> None:
    """Encode WAV -> MP3 (site player requires remixed.mp3, SITE-B-003)."""
    mp3_path = Path(mp3_path)
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    _run("-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", bitrate,
         str(mp3_path))
