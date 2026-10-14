"""Pipeline configuration (AUD-NF-002: recorded verbatim into run.json)."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PipelineConfig:
    sample_rate: int = 48000          # AUD-B-001 normalized decode rate
    # Analysis framing (AUD-B-004 example: ~100 ms STFT frames).
    n_fft: int = 4096
    hop: int = 2048                   # ~42.7 ms @48k
    db_margin: float = 2.0            # AUD-B-004: voice must exceed bg by >= 2 dB
    ramp_s: float = 3.0               # AUD-B-004: smooth step before AND after
    # Harmonic (AUD-B-005).
    band_lo_hz: float = 220.0
    band_hi_hz: float = 440.0
    harmonic_ratio: float = 0.5       # harmonic energy = 0.5 x primary energy
    trigger_fraction: float = 0.03  # AUD-B-005: >3% frames with f0 in band
    # Component selection; values recorded in run.json ("passthrough" and
    # "energy-fallback"/"unavailable" are honest stand-ins, see modules).
    vad: str = "silero-v6"             # or "energy-fallback"
    separator: str = "demucs-htdemucs"  # or "passthrough" / "demucs-htdemucs_ft" / "deepfilternet2"
    transcriber: str = "unavailable"  # or "faster-whisper" / "whisper.cpp"
    summarizer: str = "unavailable"   # or "ollama/llama3.2" / "bart"
    peak_limit: float = 0.89          # AUD-B-006: peak < 0 dBFS (-1 dBFS)

    def to_dict(self) -> dict:
        return asdict(self)
