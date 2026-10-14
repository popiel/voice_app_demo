# Spec 1 — Discovery / Submission of Audio Files

Source: `README.md:5`, stack: `specs/tech_stack.md` §1.
Produces work items consumed by Spec 2 (audio processing). No audio
mutation here — only acquire, validate, deduplicate, and enqueue.

Requirement IDs in this file use prefix `DIS-` and are stable for
cross-referencing (e.g. `DIS-B-006` is consumed by `AUD-IN-001`).

## 1. Goal

Trigger processing when (a) a user submits an audio stream, or (b) a newly
posted episode is discovered from a configured list of favorite podcast sources.

## 2. Inputs

* **[DIS-IN-001]** Manual file upload: `mp3`, `wav`, `m4a`, `ogg`, `flac`;
  max size configurable, default 500 MB.
* **[DIS-IN-002]** Manual URL submission: direct audio URL, RSS enclosure URL,
  or YouTube/podcast page resolvable by `yt-dlp`.
* **[DIS-IN-003]** Automatic discovery config: `favorites.yaml` / DB table
  `podcast_sources(id, name, feed_url, poll_interval_s, last_seen_guid)`
  (schema owned by `SITE-S-003`).
* **[DIS-IN-004]** RSS/Atom feeds parsed with `feedparser`. NPR Short Wave
  (`https://feeds.npr.org/510351/podcast.xml`) is a LINK-ONLY illustrative
  example: per `specs/00-demo-corpus.md` and NPR Terms of Use (personal
  noncommercial, no derivatives), the demo configuration MUST NOT download,
  modify, or re-serve NPR bytes. `favorites.yaml` in demo config contains
  no NPR entries.
* **[DIS-IN-005]** No website scraping: per politeness policy, discovery uses
  only publisher-provided RSS/feeds and user-submitted URLs/files.
* **[DIS-IN-006]** Demo corpus source (default and only demo ingest path):
  local rights-cleared clips at `corpus/{clip_id}.wav` with
  `provenance.json` per `COR-S-004`/`COR-S-005`. Ingested as local files,
  not via RSS/poller.

## 3. Behavior

* **[DIS-B-001]** `POST /api/submit` accepts `{url?}` or multipart file.
  Returns `job_id` immediately (202 Accepted) for new jobs; duplicates
  follow `DIS-B-005`. No blocking on download.
* **[DIS-B-002]** Poller (interval loop / cron, default 15 min per feed,
  staggered) fetches each favorite feed, compares each item's `guid` /
  enclosure URL against the `seen_episodes` table (`SITE-S-003`), and
  enqueues unseen items — newest first, at most the 10 most recent items
  per feed per cycle, so out-of-order or backfilled episodes fill holes
  without unbounded local storage growth. Evaluated items (downloaded,
  rejected, or failed) stay in `seen_episodes` and are never re-evaluated.
  If a feed fails after retries, mark the poll run `degraded` and retry on
  the next cycle — do not fall back to website scraping.
* **[DIS-B-003]** Downloader resolves URL → downloads bytes to staging
  (`storage/staging/{job_id}/source.*`), records `source_url`,
  `submitted_at`, `trigger: manual|feed|corpus`, `feed_id?`, `guid?`.
  Uses `requests/httpx` for direct files, `yt-dlp` fallback for pages.
* **[DIS-B-004]** Validator checks: file exists, size > 0, `ffprobe` reports
  a decodable audio stream, duration > 5 s. Enforcement check: jobs carrying
  corpus provenance outside `COR-V-001`–`COR-M-003` (i.e. any `COR-V-005`,
  `COR-N-004`, or `COR-M-004` denylisted source) are rejected, enforcing
  `AUD-IN-002` at ingest. Any failure is recorded as a persistent `jobs`
  row with `status: rejected + reason` (including `sha256` / `source_url`
  where known), so resubmission hits `DIS-B-005` dedup and rejections are
  never re-evaluated.
* **[DIS-B-005]** Deduplication: SHA-256 of downloaded bytes + canonical
  enclosure URL. Re-submission of identical bytes/URL returns the existing
  `job_id` (`status: duplicate`), does not re-enqueue, and does not re-run
  validation — including previously `rejected` jobs, so recorded rejections
  are never re-evaluated. API callers receive the existing record with HTTP
  `200`; browser form submissions redirect (`303`) to the job's status page
  (`/episodes/{job_id}`).
* **[DIS-B-006]** Enqueue: creates `jobs` row (`pending`) with pointer to
  staged file; Spec 2 (`AUD-IN-001`) picks it up. Retry downloads up to 3x
  with backoff; failures marked `failed` with error string.
* **[DIS-B-007]** Demo corpus ingest: each `corpus/{clip_id}.wav` is ingested
  as a local-file submission (`trigger: corpus`, `source_url:` empty or
  `corpus:{clip_id}`, provenance copied from `COR-S-004`). The RSS poller
  (`DIS-B-002`) is empty/disabled in demo config; it MUST NOT fetch NPR
  feeds (see `DIS-IN-004`, `COR-AC-004`).

## 4. Interfaces / data contracts

* **[DIS-IF-001]** Produces:
  `jobs{id, trigger, source_url, local_path, sha256, status, reason,
  feed_id, guid, submitted_at, created_at}`.
  `trigger` is `manual | feed | corpus` (`corpus` is the demo path,
  see `DIS-B-007`).
* **[DIS-IF-002]** Consumed by: Spec 2 processing worker polling
  `jobs WHERE status=pending` (see `AUD-IN-001`).
* **[DIS-IF-003]** No dependency on Spec 3 except `source_url` is later
  displayed there (see `SITE-B-003`).

## 5. Non-functional

* **[DIS-NF-001]** Offline-safe deps only: `feedparser`, `httpx`, `yt-dlp`
  (per tech stack).
* **[DIS-NF-002]** Poller must not hammer feeds; respect per-feed interval +
  ETag/Last-Modified when available. No website scraping.
* **[DIS-NF-003]** Private demo: no auth required for poller;
  `POST /api/submit` behind same private-site gate as Spec 3 (shared auth,
  see `SITE-B-001`).

## 6. Acceptance criteria

* **[DIS-AC-001]** Uploading an mp3 returns `job_id` and creates `pending`
  job with staged file.
* **[DIS-AC-002]** Posting a known enclosure URL twice returns same `job_id`
  second time.
* **[DIS-AC-003]** Adding a test RSS feed with a new item causes one new
  `pending` job within two poll cycles; re-poll creates none.
* **[DIS-AC-004]** Corrupt/empty file is marked `rejected` with reason, never
  reaches Spec 2.
* **[DIS-AC-005]** No commercial / trial-gated API is called in this path.
* **[DIS-AC-006]** Demo config ingests only `corpus/` clips via `DIS-B-007`
  (see `COR-AC-004`): no NPR bytes exist under `storage/staging/`; the RSS
  poller list contains no NPR entries.
