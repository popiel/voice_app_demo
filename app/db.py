"""SQLite schema + helpers. Owns storage layout paths (SITE-S-001/S-003)."""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from pathlib import Path


def storage_root() -> Path:
    return Path(os.environ.get("STORAGE_ROOT", "storage"))


def db_path() -> Path:
    return Path(os.environ.get("DB_PATH", str(storage_root() / "app.db")))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    return con


def init_db(con: sqlite3.Connection | None = None) -> sqlite3.Connection:
    own = con is None
    con = con or connect()
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS podcast_sources(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          feed_url TEXT NOT NULL UNIQUE,
          poll_interval_s INTEGER NOT NULL DEFAULT 900,
          last_seen_guid TEXT
        );
        CREATE TABLE IF NOT EXISTS jobs(
          id TEXT PRIMARY KEY,
          trigger TEXT NOT NULL,
          source_url TEXT NOT NULL DEFAULT '',
          local_path TEXT NOT NULL DEFAULT '',
          sha256 TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'pending',
          reason TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT '',
          done_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS episodes(
          job_id TEXT PRIMARY KEY,
          title TEXT NOT NULL DEFAULT '',
          duration_s REAL NOT NULL DEFAULT 0,
          original_ref TEXT NOT NULL DEFAULT '',
          remixed_path TEXT NOT NULL DEFAULT '',
          transcript_path TEXT NOT NULL DEFAULT '',
          summary_path TEXT NOT NULL DEFAULT '',
          mods_path TEXT NOT NULL DEFAULT '',
          processing_time_s REAL NOT NULL DEFAULT 0,
          FOREIGN KEY(job_id) REFERENCES jobs(id)
        );
        """
    )
    # Migrate pre-existing databases (new columns default 0 = unrecorded).
    _ensure_columns(con, "episodes", {"processing_time_s": "REAL NOT NULL DEFAULT 0"})
    con.commit()
    if own:
        return con
    return con


def _ensure_columns(con: sqlite3.Connection, table: str,
                    columns: dict[str, str]) -> None:
    existing = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
    for name, ddl in columns.items():
        if name not in existing:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def processed_dir(job_id: str) -> Path:
    return storage_root() / "processed" / job_id


def staging_dir(job_id: str) -> Path:
    return storage_root() / "staging" / job_id
