"""Numpy-only DSP primitives: STFT/ISTFT, framing, envelopes (AUD-B-004/005).

Kept dependency-free (no scipy/librosa) so the pipeline runs anywhere.
"""
from __future__ import annotations

import numpy as np


def hann(n: int) -> np.ndarray:
    return np.hanning(n)


def _frame_view(x: np.ndarray, n_frames: int, frame: int,
                hop: int) -> np.ndarray:
    """Strided (frames, frame) view of x, zero-padded to fit (no copies)."""
    need = (n_frames - 1) * hop + frame
    if len(x) < need:
        x = np.pad(x, (0, need - len(x)))
    stride = x.strides[0]
    return np.lib.stride_tricks.as_strided(
        x, shape=(n_frames, frame),
        strides=(hop * stride, stride))


def stft(x: np.ndarray, n_fft: int = 4096, hop: int = 2048) -> np.ndarray:
    """Return complex spectrogram, shape (frames, n_fft//2 + 1)."""
    x = np.asarray(x, dtype=np.float64)
    w = hann(n_fft)
    n_frames = 1 + max(0, (len(x) - n_fft) // hop)
    return np.fft.rfft(_frame_view(x, n_frames, n_fft, hop) * w, axis=1)


def istft(spec: np.ndarray, n_fft: int = 4096, hop: int = 2048,
          length: int | None = None) -> np.ndarray:
    """Overlap-add inverse of stft()."""
    w = hann(n_fft)
    n_frames = spec.shape[0]
    total = (n_frames - 1) * hop + n_fft
    y = np.zeros(total)
    wn = np.zeros(total)
    for i in range(n_frames):
        seg = np.fft.irfft(spec[i], n=n_fft) * w
        y[i * hop:i * hop + n_fft] += seg
        wn[i * hop:i * hop + n_fft] += w ** 2
    nz = wn > 1e-8
    y[nz] /= wn[nz]
    if length is not None:
        if len(y) < length:
            y = np.pad(y, (0, length - len(y)))
        else:
            y = y[:length]
    return y


def frame_times(n_frames: int, n_fft: int, hop: int, sr: int) -> np.ndarray:
    return (np.arange(n_frames) * hop + n_fft / 2) / sr


def raised_cosine(n: int) -> np.ndarray:
    """0 -> 1 raised-cosine ramp of length n (empty-safe)."""
    if n <= 0:
        return np.empty(0)
    if n == 1:
        return np.ones(1)
    t = np.arange(n) / (n - 1)
    return 0.5 - 0.5 * np.cos(np.pi * t)


def frame_rms_frames(x: np.ndarray, frame: int, hop: int) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    n = 1 + max(0, (len(x) - frame) // hop)
    frames = _frame_view(x, n, frame, hop)
    return np.sqrt(np.mean(frames ** 2, axis=1) + 1e-12)


def upsample_envelope(env_frames: np.ndarray, n_samples: int, hop: int,
                      n_fft: int) -> np.ndarray:
    """Linear-interp frame envelope to sample rate, anchored at frame centers."""
    centers = np.arange(len(env_frames)) * hop + n_fft / 2
    t = np.arange(n_samples, dtype=np.float64)
    return np.interp(t, centers, env_frames,
                     left=env_frames[0], right=env_frames[-1])


def to_db(power: np.ndarray, floor: float = 1e-12) -> np.ndarray:
    return 10.0 * np.log10(np.maximum(power, floor))
