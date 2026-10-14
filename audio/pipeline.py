"""End-to-end audio job processing (AUD-IN-001..AUD-B-008).

Reads pending jobs from the site DB (app.db), writes per-job outputs to
storage/processed/{job_id}/, updates jobs + episodes rows. No HTTP here.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
import traceback
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
if str(WORKSPACE) not in sys.path:
    sys.path.insert(0, str(WORKSPACE))

from app import db  # noqa: E402
from audio import __version__  # noqa: E402
from audio.config import PipelineConfig  # noqa: E402
from audio import ffmpeg_io, harmonic, rebalance, remix, transcribe, vad  # noqa: E402
from audio import separate  # noqa: E402
from audio.vad import Segment  # noqa: E402

ALLOWED_LICENSE_MARKERS = ("public domain", "cc0", "cc-by 4.0", "odc-by",
                           "apache", "bsd", "mit", "isc", "unlicense")
DENIED_LICENSE_MARKERS = ("by-sa", "by-nc", "by-nd", "odbl", "dbcl", "non-pd")


def find_clip_provenance(local_path: str) -> dict | None:
    """Locate COR-S-004 provenance for a corpus clip by filename match."""
    name = Path(local_path).name
    candidates = [WORKSPACE / "test" / "samples" / "provenance.json",
                  WORKSPACE / "corpus" / "provenance.json"]
    for prov_file in candidates:
        if not prov_file.exists():
            continue
        try:
            data = json.loads(prov_file.read_text(encoding="utf-8"))
        except ValueError:
            continue
        clips = data.get("clips", []) if isinstance(data, dict) else []
        for clip in clips:
            if clip.get("file") == name:
                return clip
    return None


def check_provenance_licenses(clip: dict) -> tuple[bool, str]:
    """COR-AC-001: licenses must be allowlisted, never denylisted."""
    texts = []
    for key in ("voice_src", "music_src", "music_or_noise_src", "noise_src"):
        src = clip.get(key) or {}
        if isinstance(src, dict) and src.get("license"):
            texts.append(str(src["license"]))
    blob = " ".join(texts).lower()
    if any(m in blob for m in DENIED_LICENSE_MARKERS):
        return False, f"denylisted license in provenance: {blob[:160]}"
    if texts and not any(m in blob for m in ALLOWED_LICENSE_MARKERS):
        return False, f"no allowlisted license in provenance: {blob[:160]}"
    return True, ""


def per_min_rate(processing_time_s: float, duration_s: float) -> float:
    """Processing seconds per minute of audio (AUD-B-010)."""
    if duration_s <= 0:
        return 0.0
    return round(processing_time_s / (duration_s / 60), 1)


def voiced_mask(segments: list[Segment], n_frames: int, n_fft: int,
                hop: int) -> list[bool]:
    import numpy as np  # local import: keeps module import light
    centers = (np.arange(n_frames) * hop + n_fft / 2)
    mask = [False] * n_frames
    for i, c in enumerate(centers):
        t = c  # samples; converted below
        for s in segments:
            if s.start * 48000 <= t <= s.end * 48000:
                mask[i] = True
                break
    return mask


def process_job(job_id: str, cfg: PipelineConfig | None = None) -> dict:
    """Run the full pipeline for one job. Returns run summary dict."""
    cfg = cfg or PipelineConfig()
    con = db.connect()
    db.init_db(con)
    job = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if job is None:
        raise KeyError(f"unknown job {job_id}")
    con.execute("UPDATE jobs SET status='processing' WHERE id=?", (job_id,))
    con.commit()
    t0 = time.monotonic()  # AUD-B-010 processing-time clock starts at claim.

    pdir = db.processed_dir(job_id)
    pdir.mkdir(parents=True, exist_ok=True)
    run: dict = {"pipeline_version": __version__, "job_id": job_id,
                 "config": cfg.to_dict(), "stages": {}}
    try:
        # --- Provenance gate (AUD-IN-002, only for corpus/demo jobs).
        clip = None
        if (job["trigger"] or "") == "corpus":
            clip = find_clip_provenance(job["local_path"] or "")
            if clip is None:
                raise ValueError("corpus job lacks provenance (COR-S-004)")
            ok, reason = check_provenance_licenses(clip)
            if not ok:
                raise ValueError(reason)
            run["stages"]["provenance"] = {"method": "corpus-allowlist",
                                           "clip": clip.get("file")}
        # --- AUD-B-001 decode.
        work = pdir / "work_decode.wav"
        dec = ffmpeg_io.decode_to_wav(job["local_path"], work, cfg.sample_rate)
        x = ffmpeg_io.load_mono_wav(work, cfg.sample_rate)
        duration_s = len(x) / cfg.sample_rate
        run["stages"]["decode"] = {"duration_s": round(duration_s, 2)}
        # --- AUD-B-002 VAD.
        vad_impl = vad.make_vad(cfg.vad, cfg.sample_rate)
        try:
            segments = vad_impl.segments(x)
            vad_method = vad_impl.method
        except vad.Unavailable as e:
            fb = vad.EnergyVAD(cfg.sample_rate)
            segments = fb.segments(x)
            vad_method = fb.method + f" (silero unavailable: {e})"
        run["stages"]["vad"] = {"method": vad_method,
                                "n_segments": len(segments)}
        # --- AUD-B-003 separate.
        sep_impl = separate.make_separator(cfg.separator)
        try:
            voice, bg, sep_method = sep_impl.separate(x, cfg.sample_rate)
        except separate.Unavailable as e:
            fb = separate.PassthroughSeparator()
            voice, bg, _ = fb.separate(x, cfg.sample_rate)
            sep_method = fb.method + f" (requested {cfg.separator} unavailable: {e})"
        run["stages"]["separate"] = {"method": sep_method}
        ffmpeg_io.write_wav(pdir / "voice.wav", voice, cfg.sample_rate)
        ffmpeg_io.write_wav(pdir / "background.wav", bg, cfg.sample_rate)
        # --- AUD-B-004 rebalance (voiced frames only).
        import numpy as np  # noqa: E402
        n_f = 1 + max(0, (len(voice) - cfg.n_fft) // cfg.hop)
        vmask = voiced_mask(segments, n_f, cfg.n_fft, cfg.hop)
        bg_proc, att_events = rebalance.attenuate_background(
            voice, bg, cfg.sample_rate, cfg.n_fft, cfg.hop, cfg.db_margin,
            cfg.ramp_s, np.array(vmask))
        # --- AUD-B-005 harmonic (voice-level trigger, whole-voice application).
        voice_proc, harm_events = harmonic.add_octave_harmonic(
            voice, cfg.sample_rate, cfg.n_fft, cfg.hop, cfg.band_lo_hz,
            cfg.band_hi_hz, cfg.harmonic_ratio,
            trigger_fraction=cfg.trigger_fraction)
        # --- AUD-B-006 remix + encode.
        mix = remix.remix(voice_proc, bg_proc, cfg.peak_limit)
        if abs(len(mix) / cfg.sample_rate - duration_s) > 0.05:
            raise ValueError("remix duration drift exceeds 50 ms (AUD-OUT-001)")
        remix.write_remix(mix, cfg.sample_rate, pdir)
        peak = float(np.abs(mix).max())
        run["stages"]["remix"] = {"peak": round(peak, 4)}
        # --- AUD-B-007 transcribe + summarize (record source used).
        # Non-fatal: ASR/LLM failures degrade to honest placeholders so the
        # DSP outputs + mods.json are still finalized (AUD-B-008).
        stem_for_asr = "voice"
        try:
            asr = transcribe.faster_whisper_transcribe(
                str(pdir / "voice.wav"), str(pdir))
            run["stages"]["transcribe"] = {"method": "faster-whisper",
                                           "source": stem_for_asr, **asr}
        except Exception as e:  # noqa: BLE001 - degraded, never fatal
            fb = transcribe.write_pending_transcript(
                pdir, duration_s, stem_for_asr,
                f"faster-whisper failed: {e}")
            run["stages"]["transcribe"] = {"source": stem_for_asr, **fb}
        if (pdir / "transcript.txt").exists():
            text = (pdir / "transcript.txt").read_text(encoding="utf-8")
            try:
                transcribe.ollama_summarize(text, pdir / "summary.md")
                run["stages"]["summarize"] = {"method": "ollama/llama3.2"}
            except Exception as e1:  # noqa: BLE001
                try:
                    transcribe.bart_summarize(text, pdir / "summary.md")
                    run["stages"]["summarize"] = {
                        "method": "bart-large-cnn",
                        "note": f"ollama unavailable: {e1}"}
                except Exception as e2:  # noqa: BLE001
                    fb = transcribe.write_pending_summary(pdir, duration_s, str(e2))
                    run["stages"]["summarize"] = fb
        # --- AUD-B-008 finalize: mods.json (union, sorted), run.json.
        mods = sorted(att_events + harm_events, key=lambda m: m["start"])
        (pdir / "mods.json").write_text(json.dumps(mods, indent=2),
                                        encoding="utf-8")
        # original.mp3 for local playback + provenance copy (SITE-B-003).
        ffmpeg_io.encode_mp3(work, pdir / "original.mp3")
        if clip is not None:
            (pdir / "provenance.json").write_text(
                json.dumps(clip, indent=2), encoding="utf-8")
        run["stages"]["mods"] = {"n_attenuate": len(att_events),
                                 "n_harmonic": len(harm_events)}
        run["status"] = "done"
        # AUD-B-010: wall-clock processing time + per-minute-of-audio rate.
        processing_time_s = round(time.monotonic() - t0, 1)
        run["timing"] = {
            "processing_time_s": processing_time_s,
            "duration_s": round(duration_s, 1),
            "processing_time_per_min": per_min_rate(processing_time_s,
                                                   duration_s),
        }
        (pdir / "run.json").write_text(json.dumps(run, indent=2),
                                       encoding="utf-8")
        try:
            work.unlink()  # redundant with voice.wav; saves ~50 MB/job
        except OSError:
            pass
        title = (clip or {}).get("file", job_id)
        original_ref = job["source_url"] or f"corpus:{title}"
        con.execute(
            "INSERT OR REPLACE INTO episodes(job_id, title, duration_s,"
            " original_ref, remixed_path, transcript_path, summary_path,"
            " mods_path, processing_time_s) VALUES(?,?,?,?,?,?,?,?,?)",
            (job_id, title, round(duration_s, 1), original_ref,
             "remixed.mp3", "transcript.txt", "summary.md", "mods.json",
             processing_time_s))
        con.execute("UPDATE jobs SET status='done', done_at=? WHERE id=?",
                    (db.now_iso(), job_id))
        con.commit()
    except Exception as e:
        run["status"] = "failed"
        run["error"] = f"{type(e).__name__}: {e}"
        run["timing"] = {
            "processing_time_s": round(time.monotonic() - t0, 1),
            "duration_s": 0.0,
            "processing_time_per_min": 0.0,
        }
        run["traceback"] = traceback.format_exc(limit=5)
        (pdir / "run.json").write_text(json.dumps(run, indent=2),
                                       encoding="utf-8")
        con.execute("UPDATE jobs SET status='failed', reason=? WHERE id=?",
                    (run["error"][:500], job_id))
        con.commit()
    finally:
        con.close()
    return run


def process_pending(limit: int | None = None) -> list[dict]:
    con = db.connect()
    db.init_db(con)
    rows = con.execute(
        "SELECT id FROM jobs WHERE status='pending' ORDER BY created_at").fetchall()
    con.close()
    ids = [r["id"] for r in rows][:limit] if limit else [r["id"] for r in rows]
    return [process_job(i) for i in ids]
