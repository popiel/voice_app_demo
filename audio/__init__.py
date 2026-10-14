"""Audio processing pipeline (Spec 2: AUD-* requirements).

Stages: decode -> VAD -> separate -> rebalance -> harmonic -> remix,
with transcribe/summarize running after (or in parallel). See
specs/02-audio-processing.md. Heavy-model stages (Silero/Demucs/
DeepFilterNet/faster-whisper/Ollama) are defined interfaces with honest
recorded fallbacks so the pipeline runs CPU-only; see audio/separate.py,
audio/vad.py, audio/transcribe.py and run.json `method` fields.
"""
from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
