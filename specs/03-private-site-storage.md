# Spec 3 — Private Site Webserver + File Storage

Source: `README.md:8`, stack: `specs/tech_stack.md` §5.
Serves outputs of Spec 2 plus original-audio links. Owns the on-disk layout
and the jobs/episodes database. No audio DSP here.

Requirement IDs in this file use prefix `SITE-` and are stable for
cross-referencing (e.g. `SITE-B-003` renders `AUD-IF-001`).

## 1. Goal

Private website listing each processed stream with: playable remixed audio,
link to original audio, full-stream summary, and list of all modifications
with begin/end time marks.

## 2. Storage layout (single root, e.g. `storage/`)

* **[SITE-S-001]** Layout:

```text
storage/
  staging/{job_id}/source.*            # Spec 1 raw download (DIS-B-003)
  processed/{job_id}/
    remixed.mp3                        # Spec 2 output (AUD-OUT-001, served)
    original.mp3                       # canonical copy or symlink (served)
    transcript.json / transcript.txt   # Spec 2 output (AUD-OUT-003, served)
    summary.md                         # Spec 2 output (AUD-OUT-003, rendered)
    mods.json                          # Spec 2 output (AUD-OUT-002, rendered)
    run.json                           # models/params audit (AUD-NF-002, not served)
```

* **[SITE-S-002]** `original.mp3` may be an external URL instead of bytes; if
  bytes are kept, serve via local path. Never expose `staging/`
  directly.
* **[SITE-S-003]** DB (`sqlite`, e.g. `app.db`):
  * `podcast_sources(id, name, feed_url, poll_interval_s, last_seen_guid)`
  * `jobs(id, trigger, source_url, local_path, sha256, status, reason,
    feed_id, guid, submitted_at, created_at, done_at)`
  * `episodes(job_id PK, title, duration_s, original_ref, remixed_path,
    transcript_path, summary_path, mods_path)` — one row per `done` job.
  * `seen_episodes(guid PK, feed_id, enclosure_url, job_id?, seen_at)` —
    every feed item ever evaluated (downloaded, rejected, or failed),
    backing `DIS-B-002` hole-filling dedup.
* **[SITE-S-004]** Statuses: `pending → processing → done | failed | rejected`.
  `failed/rejected` shown in admin list with reason, without audio player.
* **[SITE-S-005]** License display (from `COR-L-001`–`COR-L-004`): each episode
  page links `ATTRIBUTION.md` + per-clip `provenance.json`; `CC-BY 4.0`
  credits + license links shown; VCTK-derived clips carry the `ODC-By 1.0`
  Produced Work notice.
* **[SITE-S-006]** No NPR bytes stored or served: `storage/` contains only
  corpus-derived audio (`COR-AC-004`). `original_ref` for demo episodes points
  to the corpus clip + provenance; any NPR reference is an outbound text link
  only, never a playable/hosted file.

## 3. Webserver behavior (`FastAPI`, MIT)

* **[SITE-B-001]** Private gate: bind `127.0.0.1` + simple shared-token auth
  (`Authorization: Bearer $SITE_TOKEN` or login cookie) for demo. All routes
  except `/healthz`, `GET /login`, and `POST /login` require it. No public
  registration. Shared with `DIS-NF-003` / `DIS-B-001`.
* **[SITE-B-001a]** Browser login: `GET /login` (public, no auth) renders a
  token-entry form (`SITE-NF-003`: plain HTML, no external assets).
  `POST /login` compares the submitted token against `$SITE_TOKEN` with a
  constant-time comparison; on match it issues the login cookie
  (`site_token`, `HttpOnly`, `SameSite=Lax`, `Path=/`) and redirects
  (`303`) to the `next` target (default `/`). On mismatch it re-renders
  the form with an error message and reveals nothing about the expected
  token. `POST /logout` (or `GET /logout`) clears the cookie and redirects
  to `/login`. The `next` target MUST be a same-origin relative path
  (starts with `/` but not `//`); any other value falls back to `/`.
* **[SITE-B-002]** Route `GET /`: episode list (newest first): title, date,
  duration, status.
* **[SITE-B-003]** Route `GET /episodes/{job_id}`: detail page with HTML5
  `<audio>` for remixed (`AUD-OUT-001`), link to original (`source_url`
  external from `DIS-IF-001` or `/media/{job_id}/original`), rendered
  `summary.md` (`AUD-OUT-003`), modifications table from `mods.json`
  (`AUD-IF-001`: `type | start → end | detail`), link to transcript.
* **[SITE-B-004]** Routes `GET /media/{job_id}/{remixed|original}`:
  byte-range-capable audio streaming (`Accept-Ranges`), correct MIME.
  Small-file routes `GET /media/{job_id}/{transcript.txt|transcript.json|provenance}`
  serve the transcript and the per-clip `provenance.json` (`application/json`
  for `.json` / `provenance`, plain text otherwise). `run.json` is never
  served.
* **[SITE-B-005]** Route `GET /api/episodes/{job_id}.json`: machine-readable
  `{title, duration_s, original_ref, remixed_url, summary, modifications[]}`.
* **[SITE-B-006]** Reuses `POST /api/submit` from Spec 1 (`DIS-B-001`; form
  lives on `/`).
* **[SITE-B-007]** Rendering: server-side templates (no SPA framework). Times
  displayed as `mm:ss.t` plus raw seconds. Mod table rows anchor-link to
  audio time (`?t=start`) where player supports it.
* **[SITE-B-008]** Browser vs. API denial: unauthenticated requests to page
  routes (`/`, `/episodes/{job_id}`, `/attribution`) redirect (`303`) to
  `/login?next=<original-path>` so a standard web browser lands on the
  token prompt instead of a bare `401`. Unauthenticated requests to
  machine routes (`/api/*`, `/media/*`) keep the `401 JSON` response so
  scripts can detect denial programmatically. `/healthz` and `/login`
  stay public.

## 4. Interfaces

* **[SITE-IF-001]** Reads only: `storage/processed/*/`, `app.db` rows written
  by Specs 1–2.
* **[SITE-IF-002]** Never writes audio; only Specs 1–2 write. Site marks
  nothing `done` itself.
* **[SITE-IF-003]** `mods.json` schema is owned by Spec 2 (`AUD-IF-001`);
  this spec renders it verbatim — any schema change must update both specs.

## 5. Non-functional

* **[SITE-NF-001]** Local-only demo: single process, `uvicorn` on localhost,
  no CDN/cloud.
* **[SITE-NF-002]** Missing files degrade gracefully (e.g. summary pending →
  “processing…”).
* **[SITE-NF-003]** No analytics, no external fonts/scripts (works offline in
  demo room).

## 6. Acceptance criteria

* **[SITE-AC-001]** Opening `/episodes/{done_id}` shows working remixed
  player, clickable original link, full summary text, and every `mods.json`
  entry with correct begin/end times.
* **[SITE-AC-002]** `/` lists episodes newest-first; `failed/rejected` jobs
  show reason and no player.
* **[SITE-AC-003]** Audio seeking works (range requests, correct duration).
* **[SITE-AC-004]** Unauthenticated request to `/` or episode page redirects
  to `/login` (`SITE-B-008`); unauthenticated API request returns `401`;
  token/cookie request succeeds.
* **[SITE-AC-005]** Site runs read-only against fixture
  `storage/` + `app.db` containing one `done` job with all four artifacts.
* **[SITE-AC-006]** Attribution fixture: episode page for a VCTK-voice and a
  Musopen-bed clip shows correct credits/notice (`SITE-S-005`), and no
  playable NPR audio exists anywhere on the site (`SITE-S-006`).
* **[SITE-AC-007]** Browser login round-trip: `GET /login` renders the token
  form with no credentials; `POST /login` with a wrong token re-renders
  the form with an error and grants nothing; with the correct token it sets
  the login cookie and redirects to `next`; the cookie then grants access
  to `/` and episode pages; logout clears the cookie and access is denied
  again.
