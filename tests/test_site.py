"""Acceptance tests for Spec 1 (submit) + Spec 3 (private site).

Covers SITE-AC-001..006 (applicable subset) and DIS-AC-001/002/004/006.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

TOKEN = "test-token-123"

# Minimal fake mp3: ID3 header + padding (passes looks_like_audio sniff).
FAKE_MP3 = b"ID3\x04\x00\x00\x00\x00\x01\x02" + bytes(4096)

MODS = [
    {"type": "attenuate-background", "start": 12.4, "end": 45.0,
     "attenuation_db": 4.5, "ramp_s": 3.0},
    {"type": "octave-harmonic", "start": 13.0, "end": 20.5,
     "f0_mean_hz": 520.0, "harmonic_ratio": 0.5},
]

PROVENANCE = {
    "clip_id": "demo01",
    "voice_src": {"url": "https://example.org/vctk/p225", "license": "ODC-By 1.0 (VCTK)"},
    "music_or_noise_src": {"url": "https://example.org/musopen/beethoven3",
                            "license": "CC0 (Musopen, PD dedicated)"},
    "mix_snr_db": 0,
}


@pytest.fixture()
def store(tmp_path, monkeypatch):
    storage = tmp_path / "storage"
    monkeypatch.setenv("STORAGE_ROOT", str(storage))
    monkeypatch.setenv("DB_PATH", str(storage / "app.db"))
    monkeypatch.setenv("SITE_TOKEN", TOKEN)
    from app import db
    con = db.connect()
    db.init_db(con)
    # done job with all four artifacts (SITE-AC-005)
    con.execute(
        "INSERT INTO jobs(id, trigger, source_url, local_path, sha256, status,"
        " reason, created_at, done_at) VALUES(?,?,?,?,?,?,?,?,?)",
        ("done01", "corpus", "corpus:demo01", "corpus/demo01.wav", "abc",
         "done", "", "2026-10-14T00:00:00", "2026-10-14T00:01:00"),
    )
    con.execute(
        "INSERT INTO episodes(job_id, title, duration_s, original_ref,"
        " remixed_path, transcript_path, summary_path, mods_path)"
        " VALUES(?,?,?,?,?,?,?,?)",
        ("done01", "Demo One", 60.0, "corpus:demo01", "remixed.mp3",
         "transcript.txt", "summary.md", "mods.json"),
    )
    # failed job, no player (SITE-AC-002)
    con.execute(
        "INSERT INTO jobs(id, trigger, source_url, local_path, sha256, status,"
        " reason, created_at) VALUES(?,?,?,?,?,?,?,?)",
        ("fail01", "manual", "https://example.org/x.mp3", "", "",
         "failed", "download failed", "2026-10-14T00:02:00"),
    )
    con.commit()
    con.close()
    pdir = storage / "processed" / "done01"
    pdir.mkdir(parents=True)
    (pdir / "remixed.mp3").write_bytes(FAKE_MP3)
    (pdir / "original.mp3").write_bytes(FAKE_MP3)
    (pdir / "summary.md").write_text("Full summary of the entire stream.",
                                     encoding="utf-8")
    (pdir / "mods.json").write_text(json.dumps(MODS), encoding="utf-8")
    (pdir / "transcript.txt").write_text("hello world", encoding="utf-8")
    (pdir / "provenance.json").write_text(json.dumps(PROVENANCE),
                                          encoding="utf-8")
    (pdir / "run.json").write_text(json.dumps({"model": "test"}),
                                   encoding="utf-8")
    (storage / "ATTRIBUTION.md").write_text("# Attribution\n", encoding="utf-8")
    yield storage


@pytest.fixture()
def client(store):
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c


def auth():
    return {"Authorization": f"Bearer {TOKEN}"}


def test_healthz_no_auth(client):
    assert client.get("/healthz").json() == {"ok": True}


def test_unauthenticated_denied(client):
    # Page routes redirect browsers to the login prompt (SITE-B-008).
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303  # SITE-AC-004
    assert r.headers["location"].startswith("/login?next=")
    r = client.get("/episodes/done01", follow_redirects=False)
    assert r.status_code == 303
    # Machine routes keep 401 JSON (SITE-B-008).
    assert client.get("/api/episodes/done01.json").status_code == 401
    assert client.get("/media/done01/remixed").status_code == 401


def test_login_round_trip(client):
    # Login form is public (SITE-AC-007).
    r = client.get("/login")
    assert r.status_code == 200
    assert "Access token" in r.text
    # Wrong token: error, no access granted.
    r = client.post("/login", data={"token": "nope", "next": "/"})
    assert r.status_code == 401
    assert "Wrong token" in r.text
    assert client.get("/", follow_redirects=False).status_code == 303
    # Correct token: cookie issued + redirect to next.
    r = client.post("/login", data={"token": TOKEN, "next": "/episodes/done01"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/episodes/done01"
    # Cookie now grants access without a Bearer header.
    r = client.get("/")
    assert r.status_code == 200
    assert "Demo One" in r.text
    # Open-redirect guard: absolute URLs fall back to /.
    r = client.post("/login", data={"token": TOKEN, "next": "https://evil.example/"},
                    follow_redirects=False)
    assert r.headers["location"] == "/"
    # Logout clears the cookie; access is denied again.
    client.get("/logout", follow_redirects=False)
    assert client.get("/", follow_redirects=False).status_code == 303


def test_index_lists_newest_first_and_failed_reason(client):
    r = client.get("/", headers=auth())
    assert r.status_code == 200
    body = r.text
    assert "Demo One" in body
    assert "download failed" in body  # SITE-AC-002
    assert body.index("fail01") < body.index("done01")  # newest first


def test_episode_done_shows_player_summary_mods(client):
    r = client.get("/episodes/done01", headers=auth())
    assert r.status_code == 200  # SITE-AC-001
    assert "<audio" in r.text and "/media/done01/remixed" in r.text
    assert "Full summary of the entire stream." in r.text
    for token in ("attenuate-background", "12.4", "45.0",
                  "octave-harmonic", "520.0"):
        assert token in r.text
    assert "00:12.4" in r.text  # mm:ss.t rendering (SITE-B-007)


def test_episode_failed_shows_reason_no_player(client):
    r = client.get("/episodes/fail01", headers=auth())
    assert r.status_code == 200
    assert "download failed" in r.text
    assert "<audio" not in r.text  # SITE-AC-002


def test_media_range_and_mime(client):
    r = client.get("/media/done01/remixed", headers=auth())
    assert r.status_code == 200  # SITE-AC-003
    assert r.headers["content-type"].startswith("audio/")
    assert r.headers.get("accept-ranges") == "bytes"
    r2 = client.get("/media/done01/remixed", headers={**auth(), "Range": "bytes=0-99"})
    assert r2.status_code == 206


def test_episode_json_contract(client):
    r = client.get("/api/episodes/done01.json", headers=auth())
    assert r.status_code == 200  # SITE-B-005
    data = r.json()
    assert data["title"] == "Demo One"
    assert data["remixed_url"] == "/media/done01/remixed"
    assert "Full summary" in data["summary"]
    assert data["modifications"] == MODS


def test_attribution_vctk_notice_no_npr_bytes(client, store):
    r = client.get("/episodes/done01", headers=auth())
    assert "ODC-By 1.0" in r.text  # SITE-AC-006
    assert "ATTRIBUTION.md" in r.text
    assert "provenance.json" in r.text
    # SITE-S-006: no playable NPR audio anywhere
    assert "npr.org" not in r.text.lower()
    assert not list((store / "staging").rglob("*npr*"))
    # run.json exists but is never served
    assert client.get("/media/done01/run.json", headers=auth()).status_code == 404


def test_submit_upload_and_duplicate(client, store):
    files = {"file": ("clip.mp3", FAKE_MP3, "audio/mpeg")}
    r = client.post("/api/submit", files=files, headers=auth())  # DIS-AC-001
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    staged = list((store / "staging" / job_id).glob("source.*"))
    assert staged and staged[0].stat().st_size > 0
    r2 = client.post("/api/submit", files={"file": ("clip.mp3", FAKE_MP3,
                                                   "audio/mpeg")},
                     headers=auth())
    assert r2.json() == {"job_id": job_id, "status": "duplicate"}  # DIS-AC-002


def test_submit_corrupt_rejected(client):
    files = {"file": ("note.mp3", b"this is not audio at all", "audio/mpeg")}
    r = client.post("/api/submit", files=files, headers=auth())
    assert r.status_code == 422  # DIS-AC-004
    assert r.json()["status"] == "rejected"


def test_submit_npr_url_never_staged(client, store):
    r = client.post("/api/submit",
                    data={"url": "https://feeds.npr.org/510351/podcast.xml"},
                    headers=auth())
    assert r.status_code == 422  # DIS-IN-004 / DIS-AC-006
    assert "link-only" in r.json()["reason"]
    staged_files = list((store / "staging").rglob("*")) if (store / "staging").exists() else []
    assert not [p for p in staged_files if p.is_file()]


def test_submit_url_dedup(client):
    url = "https://example.org/ep1.mp3"
    r1 = client.post("/api/submit", data={"url": url}, headers=auth())
    assert r1.status_code == 202
    r2 = client.post("/api/submit", json={"url": url}, headers=auth())
    assert r2.json()["status"] == "duplicate"
