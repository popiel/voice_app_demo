"""CLI for the audio pipeline (Spec 2). No HTTP;website session owns serving.

Usage:
  python scripts/run_audio_pipeline.py --pending [--limit N]
  python scripts/run_audio_pipeline.py --job JOB_ID
  python scripts/run_audio_pipeline.py --wav test/samples/sample_03.wav [--trigger corpus]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from app import db
from app.submit import create_job, sha256_file
from audio.config import PipelineConfig
from audio.pipeline import process_job, process_pending


def ensure_job_for_wav(wav: Path, trigger: str) -> str:
    wav = wav.resolve()
    con = db.connect()
    db.init_db(con)
    try:
        digest = sha256_file(wav)
        job_id = create_job(con, trigger=trigger, source_url=f"{trigger}:{wav.name}",
                            local_path=str(wav), sha256=digest, status="pending")
    finally:
        con.close()
    return job_id


def main() -> int:
    ap = argparse.ArgumentParser(description="Run audio pipeline jobs (Spec 2).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pending", action="store_true")
    g.add_argument("--job", default=None)
    g.add_argument("--wav", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--trigger", default="corpus")
    ap.add_argument("--vad", default="silero-v6")
    ap.add_argument("--separator", default="demucs-htdemucs")
    args = ap.parse_args()

    cfg = PipelineConfig(vad=args.vad, separator=args.separator)
    if args.wav:
        job_id = ensure_job_for_wav(Path(args.wav), args.trigger)
        print(f"created job {job_id} for {args.wav}")
        runs = [process_job(job_id, cfg)]
    elif args.job:
        runs = [process_job(args.job, cfg)]
    else:
        runs = process_pending(args.limit)
    for r in runs:
        print(json.dumps({k: r.get(k) for k in ("job_id", "status", "stages", "error")},
                         indent=2))
    return 0 if all(r.get("status") == "done" for r in runs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
