"""Voice activity detection (AUD-B-002).

Target: Silero VAD v6 timestamps [{start, end, confidence}]. Silero needs
torch, which is not a demo dependency yet, so the default is an honest
energy-based fallback with the identical output contract; SileroVAD is the
drop-in hook (raises Unavailable until torch + weights are installed).
The method used is recorded in run.json.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .dsp import frame_rms_frames


class Unavailable(RuntimeError):
    pass


@dataclass
class Segment:
    start: float
    end: float
    confidence: float

    def to_dict(self) -> dict:
        return {"start": round(self.start, 1), "end": round(self.end, 1),
                "confidence": round(self.confidence, 3)}


class SileroVAD:
    """Silero VAD v6 speech timestamps (spec target, AUD-B-002).

    Runs at 16 kHz via torchaudio resampling; per-segment confidence is the
    max speech probability over the segment in 512-sample (32 ms) windows.
    Model weights auto-download on first use (~2 MB).
    """

    method = "silero-v6"

    def __init__(self, sr: int = 48000):
        self.sr = sr
        self._model = None

    def _load(self):
        if self._model is None:
            from silero_vad import load_silero_vad
            self._model = load_silero_vad()
        return self._model

    def segments(self, x: np.ndarray) -> list[Segment]:
        try:
            import torch
            import torchaudio.functional as F
            from silero_vad import get_speech_timestamps
        except ImportError as e:
            raise Unavailable(f"silero dependencies missing: {e}") from e
        model = self._load()
        wav = torch.from_numpy(np.asarray(x, dtype=np.float32))
        if self.sr != 16000:
            wav = F.resample(wav, self.sr, 16000)
        with torch.no_grad():
            stamps = get_speech_timestamps(wav, model, sampling_rate=16000,
                                           return_seconds=True)
        out: list[Segment] = []
        with torch.no_grad():
            for s in stamps:
                t0, t1 = float(s["start"]), float(s["end"])
                i0, i1 = int(t0 * 16000), int(t1 * 16000)
                # One batched forward per segment (not one per 512-sample
                # chunk): identical per-chunk math, far fewer dispatches.
                batch = []
                for j in range(i0, max(i0 + 1, i1), 512):
                    chunk = wav[j:j + 512]
                    if len(chunk) < 512:
                        pad = torch.zeros(512 - len(chunk))
                        chunk = torch.cat([chunk, pad])
                    batch.append(chunk)
                probs = model(torch.stack(batch), 16000).flatten()
                conf = float(probs.max().item()) if len(probs) else 0.9
                out.append(Segment(t0, t1, conf))
        if not out:
            out = [Segment(0.0, len(x) / self.sr, 0.5)]
        return out


class EnergyVAD:
    """Fallback: speech where frame RMS exceeds noise floor + 12 dB.

    Correct for continuous-speech demo material (voice present throughout);
    merge/hangover logic keeps music-only swells from fragmenting segments.
    """

    method = "energy-fallback"

    def __init__(self, sr: int = 48000, frame_s: float = 0.05,
                 hop_s: float = 0.025, margin_db: float = 12.0,
                 hangover_s: float = 0.5, merge_gap_s: float = 0.5,
                 min_seg_s: float = 0.3):
        self.sr = sr
        self.frame = int(frame_s * sr)
        self.hop = int(hop_s * sr)
        self.margin = 10 ** (margin_db / 20)
        self.hang = int(hangover_s / hop_s)
        self.merge_gap = merge_gap_s
        self.min_seg = min_seg_s

    def segments(self, x: np.ndarray) -> list[Segment]:
        x = np.asarray(x, dtype=np.float64)
        e = frame_rms_frames(x, self.frame, self.hop)
        floor = float(np.median(e)) + 1e-9
        speech = e > floor * self.margin
        # Hangover: extend speech through brief dips.
        idx = np.flatnonzero(speech)
        if len(idx) == 0:
            return [Segment(0.0, len(x) / self.sr, 0.5)]
        keep = np.zeros_like(speech, dtype=bool)
        for i in idx:
            keep[i:min(len(keep), i + self.hang + 1)] = True
        # Contiguous runs -> segments, merging small gaps.
        segs: list[Segment] = []
        start = None
        prev = None
        hop_s = self.hop / self.sr
        frame_s = self.frame / self.sr
        for i in np.flatnonzero(keep):
            t = i * hop_s
            if start is None:
                start, prev = t, t
            elif t - prev > self.merge_gap:
                if prev + frame_s - start >= self.min_seg:
                    segs.append(Segment(start, prev + frame_s, 0.9))
                start = t
            prev = t
        if start is not None and prev + frame_s - start >= self.min_seg:
            segs.append(Segment(start, prev + frame_s, 0.9))
        if not segs:
            segs = [Segment(0.0, len(x) / self.sr, 0.5)]
        return segs


def make_vad(name: str, sr: int = 48000):
    if name == "silero-v6":
        return SileroVAD(sr)
    if name == "energy-fallback":
        return EnergyVAD(sr)
    raise ValueError(f"unknown vad {name!r}")
