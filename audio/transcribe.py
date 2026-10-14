"""Transcription + summarization (AUD-B-007).

Spec targets: faster-whisper (or whisper.cpp) -> transcript, WhisperX word
timestamps optional, Ollama + llama3.2 (or bart/t5) -> summary.md covering
the ENTIRE stream; record whether ORIGINAL or voice stem was used.

Neither engine is a demo dependency yet, so the default writes honest
`pending` placeholders (files exist per AUD-OUT-003, content states what is
missing). FasterWhisperTranscriber / OllamaSummarizer are the drop-in hooks.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path


class Unavailable(RuntimeError):
    pass


_MODEL_CACHE: dict = {}


def _get_model(model: str = "base"):
    """Process-wide WhisperModel cache: load weights once per model name."""
    if model not in _MODEL_CACHE:
        try:
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise Unavailable("faster-whisper not installed") from e
        _MODEL_CACHE[model] = WhisperModel(model, device="cpu",
                                           compute_type="int8")
    return _MODEL_CACHE[model]


def faster_whisper_transcribe(wav_path: str | Path, out_dir: str | Path,
                              model: str = "base") -> dict:
    """Transcribe 48 kHz WAV with faster-whisper (AUD-B-007).

    Writes transcript.json {status done, segments[{start,end,text}]} and
    transcript.txt. Model weights auto-download on first use
    (tiny ~75 MB, base ~145 MB). CPU int8. Greedy decode (beam 1) with
    VAD filtering: skips silence/music beds instead of transcribing them.
    """
    fw = _get_model(model)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    segments, info = fw.transcribe(str(wav_path), beam_size=1,
                                   vad_filter=True)
    segs = [{"start": round(s.start, 1), "end": round(s.end, 1),
             "text": s.text.strip()} for s in segments]
    payload = {"status": "done", "model": f"faster-whisper/{model}",
               "beam_size": 1, "vad_filter": True,
               "language": info.language,
               "language_probability": round(info.language_probability, 3),
               "duration_s": round(info.duration, 1), "segments": segs}
    (out_dir / "transcript.json").write_text(json.dumps(payload, indent=2),
                                             encoding="utf-8")
    (out_dir / "transcript.txt").write_text(
        "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segs)
        + "\n", encoding="utf-8")
    return {"method": f"faster-whisper/{model}", "n_segments": len(segs),
            "language": info.language, "beam_size": 1, "vad_filter": True}


def ollama_summarize(transcript: str, out_path: str | Path,
                     model: str = "llama3.2",
                     url: str = "http://localhost:11434/api/chat") -> str:
    """Hook: summarize via local Ollama. Raises Unavailable if unreachable."""
    req_body = json.dumps(
        {"model": model, "stream": False,
         "messages": [{"role": "user",
                       "content": "Summarize this transcript:\n" + transcript}]}
    ).encode()
    try:
        req = urllib.request.Request(url, data=req_body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        text = data.get("message", {}).get("content", "")
        if not text:
            raise Unavailable("empty Ollama response")
    except Exception as e:
        raise Unavailable(f"Ollama unreachable: {e}") from e
    Path(out_path).write_text(text, encoding="utf-8")
    return text


def bart_summarize(transcript: str, out_path: str | Path,
                   model: str = "facebook/bart-large-cnn") -> str:
    """Summarize locally with BART (spec fallback for Ollama, AUD-B-007).

    Long transcripts are chunked (~700 words), each chunk summarized, then
    concatenated. Weights auto-download on first use (~1.6 GB). CPU.
    """
    try:
        from transformers import pipeline as hf_pipeline
    except ImportError as e:
        raise Unavailable("transformers not installed") from e
    words = transcript.split()
    chunks = [" ".join(words[i:i + 700]) for i in range(0, len(words), 700)]
    summarizer = hf_pipeline("summarization", model=model, device="cpu")
    parts = []
    for ch in chunks:
        if not ch.strip():
            continue
        out = summarizer(ch, max_length=160, min_length=40, do_sample=False)
        parts.append(out[0]["summary_text"].strip())
    text = "\n\n".join(parts) if parts else "(empty transcript)"
    header = ("# Summary\n\nSummarized locally with "
              f"{model} from the full transcript.\n\n")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + text + "\n", encoding="utf-8")
    return text


def write_pending_transcript(out_dir: str | Path, duration_s: float,
                             source: str, reason: str) -> dict:
    """Honest placeholder so AUD-OUT-003 files exist before ASR is wired."""
    out_dir = Path(out_dir)
    payload = {"status": "pending", "reason": reason, "source": source,
               "duration_s": round(duration_s, 1), "segments": []}
    (out_dir / "transcript.json").write_text(json.dumps(payload, indent=2),
                                             encoding="utf-8")
    (out_dir / "transcript.txt").write_text(
        f"[transcript pending: {reason}]\nsource: {source}\n"
        f"duration: {duration_s:.1f}s\n", encoding="utf-8")
    return {"method": "pending", "reason": reason}


def write_pending_summary(out_dir: str | Path, duration_s: float,
                          reason: str) -> dict:
    out_dir = Path(out_dir)
    (out_dir / "summary.md").write_text(
        f"# Summary (pending)\n\n[summary pending: {reason}]\n"
        f"Audio duration: {duration_s:.1f}s.\n", encoding="utf-8")
    return {"method": "pending", "reason": reason}
