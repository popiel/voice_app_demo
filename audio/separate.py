"""Voice/background separation interface (AUD-B-003).

Spec targets: Demucs htdemucs_ft (music-heavy) and DeepFilterNet2
(noise-only), RNNoise as documented fallback only. Those need torch and
large weights, so the runnable default is PassthroughSeparator
(voice = mixture, background = silence) with the method honestly recorded
in run.json. With a silent background the AUD-B-004 margin is trivially
satisfied and no attenuation events are emitted -- real attenuation
requires a real separator (unit-tested in tests/test_audio_dsp.py).
"""
from __future__ import annotations

import numpy as np
import os


class Unavailable(RuntimeError):
    pass


_MODEL_CACHE: dict = {}


def torch_threads() -> int:
    """Intra-op pool size Demucs actually runs with (diagnostic)."""
    try:
        import torch
        return int(torch.get_num_threads())
    except ImportError:
        return 0


def ensure_threads() -> int:
    """Size the torch intra-op pool (default: all CPUs).

    The pool is frequently inherited small (4 was observed on a 28-core
    box); Demucs CPU inference scales with it. `TORCH_THREADS` overrides.
    """
    try:
        import torch
    except ImportError:
        return 0
    try:
        n = int(os.environ.get("TORCH_THREADS", "0") or 0)
    except ValueError:
        n = 0
    if n <= 0:
        n = os.cpu_count() or 4
    try:
        torch.set_num_threads(n)
    except Exception:
        pass
    return torch_threads()


class PassthroughSeparator:
    """Fallback: no separation available; background is silence."""

    method = "passthrough"

    def separate(self, x: np.ndarray, sr: int = 48000
                 ) -> tuple[np.ndarray, np.ndarray, str]:
        x = np.asarray(x, dtype=np.float64)
        return x.copy(), np.zeros_like(x), self.method


class DemucsSeparator:
    """Meta Demucs separation, voice = `vocals` stem (AUD-B-003, music-heavy).

    Default model `htdemucs` (single, 84 MB): the CPU-practical member of the
    htdemucs family (`htdemucs_ft` is a 4x ensemble reserved for GPU runs).
    Pipeline audio is mono 48 kHz; Demucs runs stereo 44.1 kHz, so we
    duplicate/resample on the way in and average vocals back to mono on the
    way out. Background = drums + bass + other.
    """

    method = "demucs-htdemucs"

    def __init__(self, model_name: str = "htdemucs"):
        self.model_name = model_name
        self._model = None

    def _load(self):
        # Process-wide cache: model weights load once per name, shared by
        # every job in this process (multi-job runs otherwise reload them).
        if self.model_name not in _MODEL_CACHE:
            import torch
            from demucs.pretrained import get_model
            model = get_model(self.model_name)
            model.eval()
            _MODEL_CACHE[self.model_name] = model
        self._model = _MODEL_CACHE[self.model_name]
        return self._model

    def separate(self, x: np.ndarray, sr: int = 48000):
        import torch
        import torchaudio.functional as F
        from demucs.apply import apply_model
        model = self._load()
        threads = ensure_threads()
        self._threads = threads
        x = np.asarray(x, dtype=np.float64)
        wav = torch.from_numpy(x.astype(np.float32))
        if sr != model.samplerate:
            wav = F.resample(wav, sr, model.samplerate)
        stereo = torch.stack([wav, wav])  # Demucs expects (2, T)
        with torch.no_grad():
            out = apply_model(model, stereo[None], device="cpu",
                              progress=False)[0]
        sources = list(model.sources)
        stems = {s: out[i].mean(dim=0) for i, s in enumerate(sources)}
        vocals = stems["vocals"]
        bg = sum(v for k, v in stems.items() if k != "vocals")
        if model.samplerate != sr:
            vocals = F.resample(vocals, model.samplerate, sr)
            bg = F.resample(bg, model.samplerate, sr)
        n = len(x)
        return (vocals.numpy()[:n].astype(np.float64),
                bg.numpy()[:n].astype(np.float64), self.method)


class DeepFilterNetSeparator:
    """Hook for DeepFilterNet2 enhancement (spec target, noise-only)."""

    method = "deepfilternet2"

    def separate(self, x: np.ndarray, sr: int = 48000):
        raise Unavailable("DeepFilterNet inference not wired yet")


def make_separator(name: str):
    if name == "passthrough":
        return PassthroughSeparator()
    if name == "demucs-htdemucs":
        return DemucsSeparator("htdemucs")
    if name == "demucs-htdemucs_ft":
        # 4x ensemble: GPU use; CPU runs should prefer demucs-htdemucs.
        return DemucsSeparator("htdemucs_ft")
    if name == "deepfilternet2":
        return DeepFilterNetSeparator()
    raise ValueError(f"unknown separator {name!r}")
