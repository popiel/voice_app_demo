"""Private website: submissions (Spec 1) + hosting processed audio (Spec 3).

Single-process FastAPI app, localhost-only, no external assets (SITE-NF-001/003).
Server-side HTML only (SITE-B-007). Never serves staging/ (SITE-S-002) and
never stages NPR bytes (DIS-IN-004 / SITE-S-006).
"""
from __future__ import annotations

import hashlib
import html
import json
import os
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import db
from .auth import require_auth
from .submit import (
    ALLOWED_EXTS,
    create_job,
    find_duplicate,
    is_denied_url,
    looks_like_audio,
    sha256_file,
    validate_staged,
)

AUDIO_MIME = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
}


def fmt_time(s: float) -> str:
    """mm:ss.t plus raw seconds (SITE-B-007)."""
    if s < 0:
        s = 0
    m = int(s // 60)
    sec = s - 60 * m
    return f"{m:02d}:{sec:04.1f} ({s:.1f}s)"


def page(title: str, body: str) -> str:
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:sans-serif;max-width:60rem;margin:2rem auto;"
        "padding:0 1rem}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #999;padding:.3rem .5rem;text-align:left}"
        ".reason{background:#fee;padding:.5rem}</style></head><body>"
        f"{body}</body></html>"
    )


def license_block(job_id: str) -> str:
    """License display (SITE-S-005, COR-L-001..004)."""
    prov_path = db.processed_dir(job_id) / "provenance.json"
    info = ""
    if prov_path.exists():
        try:
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prov = None
        if isinstance(prov, dict):
            parts = []
            for key in ("voice_src", "music_or_noise_src", "music_src", "noise_src"):
                src = prov.get(key)
                if isinstance(src, dict):
                    lic = html.escape(str(src.get("license", "")))
                    url = html.escape(str(src.get("url", "")))
                    parts.append(f"<li>{html.escape(key)}: {lic} {url}</li>")
            if parts:
                info += "<ul>" + "".join(parts) + "</ul>"
    notice = ""
    blob = info.lower()
    if "odc-by" in blob or "vctk" in blob:
        notice = (
            "<p><strong>ODC-By 1.0 notice:</strong> this remixed demo derives "
            "from VCTK and the database portion is available under ODC-By 1.0 "
            "terms (COR-L-003).</p>"
        )
    if "cc-by" in blob:
        info += ("<p>CC-BY 4.0 content: credited above with license link "
                 "<a href='https://creativecommons.org/licenses/by/4.0/'>"
                 "CC-BY 4.0</a>; modifications noted in the table below "
                 "(COR-L-001).</p>")
    attrib = db.storage_root() / "ATTRIBUTION.md"
    attrib_link = ""
    if attrib.exists():
        attrib_link = "<p><a href='/attribution'>ATTRIBUTION.md</a></p>"
    prov_link = ""
    if prov_path.exists():
        prov_link = (f"<p><a href='/media/{html.escape(job_id)}/provenance'>"
                     "provenance.json</a></p>")
    if not (info or notice or attrib_link or prov_link):
        return ""
    return f"<section><h3>License / attribution</h3>{info}{notice}{attrib_link}{prov_link}</section>"


def create_app() -> FastAPI:
    app = FastAPI(title="Voice demo (private)")

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/", response_class=HTMLResponse)
    async def index(_: None = Depends(require_auth)):
        con = db.connect()
        try:
            db.init_db(con)
            rows = con.execute(
                "SELECT j.id, j.status, j.reason, j.created_at,"
                " e.title, e.duration_s FROM jobs j LEFT JOIN episodes e"
                " ON e.job_id=j.id ORDER BY j.created_at DESC, j.id DESC"
            ).fetchall()
        finally:
            con.close()
        items = []
        for r in rows:
            jid = html.escape(r["id"])
            title = html.escape(r["title"] or r["id"])
            status = html.escape(r["status"])
            dur = f"{float(r['duration_s'] or 0):.1f}s" if r["duration_s"] else "—"
            date = html.escape(r["created_at"] or "")
            reason = ""
            if r["status"] in ("failed", "rejected") and r["reason"]:
                reason = f"<br><span>{html.escape(r['reason'])}</span>"
            items.append(
                f"<li><a href='/episodes/{jid}'>{title}</a> — {status} — "
                f"{dur} — {date}{reason}</li>"
            )
        body = (
            "<h1>Episodes (private demo)</h1>"
            "<form action='/api/submit' method='post' enctype='multipart/form-data'>"
            "<h2>Submit audio</h2>"
            "<p><input type='file' name='file'></p>"
            "<p><input type='text' name='url' placeholder='https://… audio/RSS enclosure URL' size='60'></p>"
            "<p><button type='submit'>Submit</button></p></form>"
            "<h2>All jobs (newest first)</h2>"
            f"<ul>{''.join(items) if items else '<li>no jobs yet</li>'}</ul>"
        )
        return HTMLResponse(page("Episodes", body))

    @app.get("/episodes/{job_id}", response_class=HTMLResponse)
    async def episode(job_id: str, _: None = Depends(require_auth)):
        con = db.connect()
        try:
            db.init_db(con)
            job = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            ep = con.execute(
                "SELECT * FROM episodes WHERE job_id=?", (job_id,)
            ).fetchone()
        finally:
            con.close()
        if job is None:
            return HTMLResponse(page("Not found", "<h1>Unknown job</h1>"), status_code=404)
        status = job["status"]
        if status in ("failed", "rejected"):
            body = (f"<h1>{html.escape((ep['title'] if ep else None) or job_id)}</h1>"
                    f"<p>Status: {html.escape(status)}</p>"
                    f"<p class='reason'>{html.escape(job['reason'] or 'no reason recorded')}</p>"
                    "<p><a href='/'>back</a></p>")
            return HTMLResponse(page("Job " + job_id, body))
        title = (ep["title"] if ep and ep["title"] else job_id)
        pdir = db.processed_dir(job_id)
        # Summary (SITE-NF-002: degrade gracefully).
        summary_file = pdir / "summary.md"
        if summary_file.exists():
            summary = html.escape(summary_file.read_text(encoding="utf-8"))
        else:
            summary = "<em>processing…</em>"
            summary = summary  # already HTML
            summary_html = f"<p>{summary}</p>"
        if summary_file.exists():
            summary_html = f"<pre>{summary}</pre>"
        # Modifications (AUD-IF-001 rendered verbatim, SITE-B-003).
        mods_file = pdir / "mods.json"
        try:
            mods = json.loads(mods_file.read_text(encoding="utf-8")) if mods_file.exists() else []
        except (OSError, ValueError):
            mods = []
        rows = []
        for m in mods if isinstance(mods, list) else []:
            if not isinstance(m, dict):
                continue
            try:
                start = float(m.get("start", 0))
                end = float(m.get("end", 0))
            except (TypeError, ValueError):
                continue
            mtype = html.escape(str(m.get("type", "")))
            if mtype == "attenuate-background":
                detail = f"attenuation {m.get('attenuation_db', '?')} dB, ramp {m.get('ramp_s', '?')} s"
            elif mtype == "octave-harmonic":
                detail = (f"f0 {m.get('f0_mean_hz', '?')} Hz, "
                          f"ratio {m.get('harmonic_ratio', '?')}")
            else:
                detail = html.escape(json.dumps(m))
            rows.append(
                f"<tr><td>{mtype}</td><td><a href='?t={start:.1f}'>"
                f"{fmt_time(start)} → {fmt_time(end)}</a></td>"
                f"<td>{html.escape(detail)}</td></tr>"
            )
        mods_html = (f"<table><tr><th>type</th><th>start → end</th><th>detail</th></tr>"
                     f"{''.join(rows)}</table>" if rows else "<p>No modifications.</p>")
        # Original link: external URL or local media (SITE-B-003, SITE-S-006).
        original_ref = (ep["original_ref"] if ep and ep["original_ref"] else job["source_url"])
        if original_ref.startswith("http"):
            original_html = f"<a href='{html.escape(original_ref)}'>original audio (external link)</a>"
        elif (pdir / "original.mp3").exists():
            original_html = f"<a href='/media/{html.escape(job_id)}/original'>original audio</a>"
        else:
            original_html = html.escape(original_ref or "—")
        remixed_exists = (pdir / "remixed.mp3").exists()
        player = (f"<audio controls preload='metadata' src='/media/{html.escape(job_id)}/remixed'>"
                  "</audio>" if remixed_exists else "<p><em>remixed audio pending…</em></p>")
        transcript_html = ""
        for name in ("transcript.txt", "transcript.json"):
            if (pdir / name).exists():
                transcript_html = (f"<p><a href='/media/{html.escape(job_id)}/"
                                   f"{html.escape(name)}'>transcript ({html.escape(name)})</a></p>")
                break
        body = (
            f"<h1>{html.escape(title)}</h1>"
            f"<p>Status: {html.escape(status)}</p>"
            f"<h2>Remixed</h2>{player}"
            f"<h2>Original</h2><p>{original_html}</p>"
            f"<h2>Summary</h2>{summary_html}"
            f"<h2>Modifications</h2>{mods_html}"
            f"{transcript_html}"
            f"{license_block(job_id)}"
            "<p><a href='/'>back</a></p>"
        )
        return HTMLResponse(page(title, body))

    @app.get("/media/{job_id}/{kind}")
    async def media(job_id: str, kind: str, _: None = Depends(require_auth)):
        pdir = db.processed_dir(job_id)
        mapping = {
            "remixed": pdir / "remixed.mp3",
            "original": pdir / "original.mp3",
            "transcript.txt": pdir / "transcript.txt",
            "transcript.json": pdir / "transcript.json",
            "provenance": pdir / "provenance.json",
        }
        path = mapping.get(kind)
        if path is None or not path.exists():
            return JSONResponse({"detail": "not found"}, status_code=404)
        if kind == "provenance":
            media_type = "application/json"
        elif path.suffix in AUDIO_MIME:
            media_type = AUDIO_MIME[path.suffix]
        elif path.suffix == ".json":
            media_type = "application/json"
        else:
            media_type = "text/plain; charset=utf-8"
        # Starlette FileResponse handles Range/Accept-Ranges (SITE-B-004).
        return FileResponse(str(path), media_type=media_type)

    @app.get("/attribution")
    async def attribution(_: None = Depends(require_auth)):
        path = db.storage_root() / "ATTRIBUTION.md"
        if not path.exists():
            return JSONResponse({"detail": "not found"}, status_code=404)
        return FileResponse(str(path), media_type="text/markdown; charset=utf-8")

    @app.get("/api/episodes/{job_id}.json")
    async def episode_json(job_id: str, _: None = Depends(require_auth)):
        con = db.connect()
        try:
            db.init_db(con)
            job = con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            ep = con.execute(
                "SELECT * FROM episodes WHERE job_id=?", (job_id,)
            ).fetchone()
        finally:
            con.close()
        if job is None:
            return JSONResponse({"detail": "not found"}, status_code=404)
        pdir = db.processed_dir(job_id)
        summary = ""
        if (pdir / "summary.md").exists():
            summary = (pdir / "summary.md").read_text(encoding="utf-8")
        try:
            mods = json.loads((pdir / "mods.json").read_text(encoding="utf-8")) \
                if (pdir / "mods.json").exists() else []
        except (OSError, ValueError):
            mods = []
        return {
            "title": (ep["title"] if ep and ep["title"] else job_id),
            "duration_s": float(ep["duration_s"]) if ep and ep["duration_s"] else 0.0,
            "original_ref": (ep["original_ref"] if ep and ep["original_ref"]
                             else job["source_url"]),
            "remixed_url": f"/media/{job_id}/remixed",
            "summary": summary,
            "modifications": mods,
        }

    @app.post("/api/submit")
    async def submit(
        request: Request,
        file: UploadFile | None = File(default=None),
        url: str | None = Form(default=None),
    ):
        # Accept JSON {url} as well as multipart (DIS-B-001).
        json_url: str | None = None
        if request.headers.get("content-type", "").startswith("application/json"):
            try:
                payload = await request.json()
            except ValueError:
                payload = {}
            if isinstance(payload, dict) and payload.get("url"):
                json_url = str(payload["url"])
        source_url = (url or json_url or "").strip()
        if file is not None and file.filename:
            return await _submit_file(file)
        if source_url:
            return await _submit_url(source_url)
        return JSONResponse({"detail": "provide a file or url"}, status_code=400)

    async def _submit_file(file: UploadFile):
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTS:
            return JSONResponse(
                {"detail": f"unsupported extension {ext or '(none)'}"}, status_code=400)
        data = await file.read()
        if not data:
            return await _record_rejected("", "empty file")
        if len(data) > _max_bytes():
            return await _record_rejected("", "file exceeds size limit")
        if not looks_like_audio(data[:65536], ext):
            return await _record_rejected("", "unrecognized audio content")
        digest = hashlib.sha256(data).hexdigest()
        con = db.connect()
        try:
            db.init_db(con)
            dup = find_duplicate(con, digest, "")
            if dup:
                return {"job_id": dup, "status": "duplicate"}
            job_id = create_job(con, trigger="manual", source_url="",
                                local_path="", sha256=digest, status="pending")
        finally:
            con.close()
        sdir = db.staging_dir(job_id)
        sdir.mkdir(parents=True, exist_ok=True)
        staged = sdir / f"source{ext}"
        staged.write_bytes(data)
        ok, reason = validate_staged(staged, ext)
        con = db.connect()
        try:
            if not ok:
                con.execute("UPDATE jobs SET status='rejected', reason=? WHERE id=?",
                            (reason, job_id))
                con.commit()
                return JSONResponse({"job_id": job_id, "status": "rejected",
                                     "reason": reason}, status_code=422)
            con.execute("UPDATE jobs SET local_path=? WHERE id=?",
                        (str(staged), job_id))
            con.commit()
        finally:
            con.close()
        return JSONResponse({"job_id": job_id, "status": "pending"}, status_code=202)

    async def _submit_url(source_url: str):
        if is_denied_url(source_url):
            return await _record_rejected(
                source_url, "NPR sources are link-only in demo config (DIS-IN-004)")
        con = db.connect()
        try:
            db.init_db(con)
            dup = find_duplicate(con, "", source_url)
            if dup:
                return {"job_id": dup, "status": "duplicate"}
            job_id = create_job(con, trigger="manual", source_url=source_url,
                                local_path="", sha256="", status="pending")
        finally:
            con.close()
        return JSONResponse({"job_id": job_id, "status": "pending"}, status_code=202)

    async def _record_rejected(source_url: str, reason: str):
        con = db.connect()
        try:
            db.init_db(con)
            job_id = create_job(con, trigger="manual", source_url=source_url,
                                local_path="", sha256="", status="rejected",
                                reason=reason)
        finally:
            con.close()
        return JSONResponse({"job_id": job_id, "status": "rejected",
                             "reason": reason}, status_code=422)

    def _max_bytes() -> int:
        return int(float(os.environ.get("MAX_UPLOAD_MB", "500")) * 1024 * 1024)

    @app.post("/api/ingest-corpus")
    async def ingest_corpus(payload: dict, _: None = Depends(require_auth)):
        """Demo corpus ingest (DIS-B-007, trigger=corpus)."""
        clip_id = str((payload or {}).get("clip_id", ""))
        if not clip_id:
            return JSONResponse({"detail": "clip_id required"}, status_code=400)
        src = Path("corpus") / f"{clip_id}.wav"
        if not src.exists():
            return JSONResponse({"detail": "unknown clip_id"}, status_code=404)
        digest = sha256_file(src)
        con = db.connect()
        try:
            db.init_db(con)
            dup = find_duplicate(con, digest, f"corpus:{clip_id}")
            if dup:
                return {"job_id": dup, "status": "duplicate"}
            job_id = create_job(con, trigger="corpus",
                                source_url=f"corpus:{clip_id}",
                                local_path=str(src), sha256=digest,
                                status="pending")
        finally:
            con.close()
        return JSONResponse({"job_id": job_id, "status": "pending"}, status_code=202)

    return app


app = create_app()
