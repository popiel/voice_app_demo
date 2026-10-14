"""Submission ingest helpers (DIS-B-001/B-004/B-005/B-007, DIS-IN-004 guard)."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

from . import db

ALLOWED_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}  # DIS-IN-001
# Demo guard: never stage NPR bytes (DIS-IN-004, COR-AC-004, SITE-S-006).
DENIED_URL_SUBSTRINGS = ("npr.org",)


def max_upload_bytes() -> int:
    mb = float(os.environ.get("MAX_UPLOAD_MB", "500"))  # DIS-IN-001
    return int(mb * 1024 * 1024)


def is_denied_url(url: str) -> bool:
    low = url.lower()
    return any(s in low for s in DENIED_URL_SUBSTRINGS)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def looks_like_audio(data: bytes, ext: str) -> bool:
    """Best-effort validator when ffprobe is unavailable (DIS-B-004).

    Prefers ffprobe if present; otherwise sniffs container magic so that
    corrupt/text uploads are rejected instead of enqueued (DIS-AC-004).
    """
    if not data:
        return False
    head = data[:16]
    if head.startswith(b"ID3") or head[:2] == b"\xff\xfb" or head[:2] == b"\xff\xf3":
        return True  # mp3
    if head.startswith(b"RIFF") or head.startswith(b"RF64"):
        return True  # wav
    if head.startswith(b"OggS"):
        return True  # ogg
    if head.startswith(b"fLaC"):
        return True  # flac
    if head[4:8] == b"ftyp":
        return True  # m4a/mp4
    return False


def ffprobe_ok(path: Path) -> bool | None:
    """Return True/False if ffprobe ran, else None if unavailable."""
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    try:
        proc = subprocess.run(
            [exe, "-v", "error", "-show_entries", "stream=codec_type",
             "-show_entries", "format=duration", "-of",
             "default=noprint_wrappers=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return False
    out = proc.stdout.lower()
    if "codec_type=audio" not in out:
        return False
    for line in out.splitlines():
        if line.startswith("duration="):
            try:
                if float(line.split("=", 1)[1]) <= 5.0:  # DIS-B-004
                    return False
            except ValueError:
                return False
    return True


def validate_staged(path: Path, ext: str) -> tuple[bool, str]:
    try:
        size = path.stat().st_size
    except OSError:
        return False, "missing staged file"
    if size == 0:
        return False, "empty file"
    if size > max_upload_bytes():
        return False, "file exceeds size limit"
    probe = ffprobe_ok(path)
    if probe is True:
        return True, ""
    if probe is False:
        return False, "ffprobe reports no decodable audio stream"
    with open(path, "rb") as f:
        head = f.read(65536)
    if looks_like_audio(head, ext):
        return True, ""
    return False, "unrecognized audio content"


def find_duplicate(con, sha256: str, source_url: str):
    if sha256:
        row = con.execute(
            "SELECT id FROM jobs WHERE sha256=? AND sha256!='' LIMIT 1", (sha256,)
        ).fetchone()
        if row:
            return row["id"]
    if source_url:
        row = con.execute(
            "SELECT id FROM jobs WHERE source_url=? AND source_url!='' LIMIT 1",
            (source_url,),
        ).fetchone()
        if row:
            return row["id"]
    return None


def create_job(con, *, trigger: str, source_url: str, local_path: str,
               sha256: str, status: str, reason: str = "") -> str:
    job_id = db.new_job_id()
    con.execute(
        "INSERT INTO jobs(id, trigger, source_url, local_path, sha256, status,"
        " reason, created_at) VALUES(?,?,?,?,?,?,?,?)",
        (job_id, trigger, source_url, local_path, sha256, status, reason,
         db.now_iso()),
    )
    con.commit()
    return job_id
