# Spec 4 — Public RSS Feeds (speech-heavy, rights-cleared)

Source: background research for `README.md` podcast scenario, constrained by
`specs/00-demo-corpus.md` (`COR-AC-001`, `COR-AC-004`) and
`specs/01-discovery-submission.md` (`DIS-IN-004`, `DIS-B-002`).
Informative / advisory: this file does NOT authorize adding a feed to
`favorites.yaml`. Adding any feed as a demo ingest path requires a spec
amendment per `COR-L-004`.

Requirement IDs in this file use prefix `RSS-` and are stable for
cross-referencing.

Research date: 2026-10-14. Feed reachability + `<enclosure>` presence
verified with `curl` on that date (details in §5). License statements
quoted from publisher pages visited same date.

## 1. Copyright gate (from `COR-AC-001`)

A feed is eligible as demo *bytes* (download → modify → re-serve under
`SITE-S-001`) ONLY if every enclosure resolves to exactly one of:
PD dedication, `CC0`, `CC-BY 4.0`, `ODC-By 1.0`, Apache-2.0, BSD,
MIT/ISC/Unlicense. No `BY-SA/BY-NC/BY-ND` (any version), `ODbL`, `DBCL`,
or `Non-PD US` entries.

Consequences used below:

* Public-domain *text* alone is NOT sufficient — the *recording* must also
  be clear (same two-layer rule as `COR-M-001`).
* `CC-BY 3.0` is NOT on the `COR-AC-001` allowlist (version matters).
  A feed containing `CC-BY 3.0` audio needs a spec amendment before use.
* US federal-government works (17 U.S.C. §105) are PD in the US, but
  episodes can embed third-party copyrighted material (music, AP wire
  copy, commissioned art). The feed-level PD claim does not transfer to
  those embedded items — per-episode filtering is required.
* Trademark / insignia / endorsement rules (NASA insignia, `VOA` marks)
  are separate from copyright: do not display logos or imply endorsement
  (`RSS-N-001`).

## 2. Findings — RECOMMENDED (meets gate, enclosures verified)

### [RSS-F-001] LibriVox per-book RSS — PRIMARY recommendation

* Feed URL pattern: `https://librivox.org/rss/{project_id}`
  (discovered from the per-book `RSS` link, e.g. `itpc://librivox.org/rss/20232`
  on the catalog page for *The Story of Slavery* by Booker T. Washington).
* Example verified 2026-10-14: `https://librivox.org/rss/20232` returns
  valid RSS 2.0 with one `<item>` per chapter, each with
  `<enclosure url="https://www.archive.org/download/..." type="audio/mpeg">`
  plus `<media:content>` duplicate.
* Content: speech-heavy audiobooks, solo or collaborative narration.
  Minimal music beds — ideal clean-voice baseline for `AUD-B-002`/`AUD-B-003`
  (DeepFilterNet path) and full-length transcripts for `AUD-B-007`.
  Thousands of books to choose from; durations from minutes (poetry) to
  hours (novels).
* License basis: recordings are a public-domain dedication in the US
  (volunteers donate recordings to the public domain; anyone may
  use/remix/sell without permission — courtesy credit only).
  Refs: `librivox.org/pages/public-domain/`,
  `wiki.librivox.org — Copyright and Public Domain`, catalog footer
  `LibriVox recordings are Public Domain in the USA`.
  Satisfies `COR-V-001` directly.
* Caveats: PD status is US-scoped (`If you are not in the USA, please verify
  the copyright status ... in your own country`). EU/CH note applies.
  Each catalog page links its Internet Archive source — retain that URL in
  `provenance.json` (`COR-S-004`).
* Integration: works with `feedparser` + `DIS-B-002`/`DIS-B-003` today
  (standard RSS 2.0 + mp3 enclosures on `archive.org`).

### [RSS-F-002] LibriVox Community Podcast — RECOMMENDED

* Feed URLs (all live 2026-10-14):
  * Canonical audio feed (verified enclosures):
    `https://librivox.org/category/librivox-community-podcast/feed/`
  * Legacy alias: `http://feeds.feedburner.com/LibrivoxCommunityPodcast`
    (resolves to the above WordPress category feed).
  * Discovery/directory feeds (no enclosures, NOT for ingest):
    `https://librivox.org/rss/latest_releases` (new-release announcements,
    `<link>`/`<guid>` to catalog pages only — verified no `<enclosure>`),
    `https://librivox.org/feed/` (blog), `https://librivox.org/podcast.xml`
    (discontinued 3-chapter-a-week show).
* Enclosures verified: `<enclosure url="https://archive.org/download/librivox_community_2013/librivox_community_podcast_162_128kb.mp3" ... type="audio/mpeg" />`
  and siblings for #159–#161. Hosted on `archive.org`, PD same as `RSS-F-001`.
* Content: conversational speech (rotating hosts, interviews, LibriVox news),
  typically 12–40 min, multi-speaker — good multi-voice/VAD fixture
  (`AUD-B-002`). Occasional embedded PD readings + `pdsounds.org` effects
  (episode #114 notes this) — check `provenance.json` per episode.
* License basis: same PD dedication as `RSS-F-001`.

### [RSS-F-003] NASA podcasts — RECOMMENDED (US-government PD)

* Feed URLs (taken from `nasa.gov` podcast pages 2026-10-14, enclosures verified):
  * *Houston We Have a Podcast* (official JSC show, weekly interviews with
    astronauts/scientists/engineers):
    `https://www.nasa.gov/feeds/podcasts/houston-we-have-a-podcast`
    (self link `https://feeds.megaphone.fm/NATIONALAERONAUTICSANDSPACEADMINISTRATION1776343825`;
    enclosures e.g. `https://traffic.megaphone.fm/...mp3`, `type="audio/mpeg"`).
  * *NASA's Curious Universe* (narrative science show):
    `https://www.nasa.gov/feeds/podcasts/curious-universe`
    (self link `https://feeds.megaphone.fm/nasacuriousuniverse`;
    enclosures e.g. `https://chrt.fm/track/477F33/traffic.megaphone.fm/...mp3`).
* Content: speech-heavy long-form interviews + narrative documentary,
  30–60 min, clean studio speech with light scoring — good for the
  voice-vs-music rebalance rule (`AUD-B-004`) without extreme beds.
* License basis: `NASA content — images, audio, video ... generally are not
  subject to copyright in the United States` and `may be used for educational
  or informational purposes` without explicit permission; credit NASA as
  source. Refs: `nasa.gov — Images and Media Usage Guidelines` /
  `nasa-brand-center/images-and-media` (visited 2026-10-14).
  Qualifies as PD dedication for `COR-AC-001` purposes for NASA-created audio.
* Caveats (MUST filter per episode):
  * `NASA occasionally uses copyright-protected material of third parties
    with permission ... Those images will be marked ... NASA's use does not
    convey any rights to others.` Same applies to audio (talent/narration/
    music inserts — see STScI/NASA copyright notes). Skip any episode whose
    page credits third-party music/footage or `Courtesy of`.
  * NASA insignia/logotype are NOT PD and protected by law — do not render
    them on the demo site; text credit only.
  * Hosting is Megaphone with tracking/dynamic-insertion capability
    (per Podnews listing). Prefer the `nasa.gov` canonical feed above, pin
    enclosure URLs + SHA-256 in `provenance.json`, and re-verify bytes before
    any demo build (inserted ads would be third-party material).
  * Historic-mission audio (e.g. `archive.org` NASA collection) is likewise
    PD but quality varies; the two feeds above are the clean, maintained
    recommendation.

### [RSS-F-004] VOA Learning English — RECOMMENDED WITH FILTERING

* Feed URL pattern: `https://learningenglish.voanews.com/podcast/?zoneId={id}`
  (one feed per program; `Subscribe` link on each `/podcasts` card).
  Example verified 2026-10-14:
  `https://learningenglish.voanews.com/podcast/?zoneId=1689`
  (*VOA Learning English Podcast*, formerly Special English) returns valid
  RSS 2.0 with `<enclosure url="https://voa-audio.voanews.eu/vle/...mp3"
  type="audio/mpeg" length="...">`, `<itunes:duration>00:29:56</itunes:duration>`.
  Sibling programs (same pattern): `3521` As It Is, `986` Arts & Culture,
  `1581` American Stories, `1579` Science & Technology, `979` U.S. History,
  `959` Education, etc.
* Content: slow, clearly enunciated speech for ESL learners, limited
  vocabulary, short sentences; ~30 min magazine format. Excellent intelligibility
  baseline and transcript-alignment fixture (`AUD-B-007`); limited vocabulary
  also simplifies summary evaluation.
* License basis: `All text, audio and video material produced exclusively by
  the Voice of America is in the public domain. Credit ... voanews.com, Voice
  of America, or VOA.` Ref: `learningenglish.voanews.com/p/6021.html — Terms
  of Use and Privacy Note` (visited 2026-10-14). Qualifies as PD dedication
  for VOA-produced items.
* Caveats (MUST filter per item — do not bulk-ingest):
  * `voanews.com content may also contain ... copyrighted material ... licensed
    for use in VOA programming only ... not in the public domain`, and
    `Associated Press text, photo, graphic, audio and/or video material shall
    not be published, broadcast, rewritten ... or redistributed.` Skip any item
    crediting AP or other third parties.
  * `Voice of America` / `voanews.com` are trademarks — text credit only, no
    logo. The *What It Takes* strand (`zoneId=5254`) repackages American
    Academy of Achievement interviews — treat as third-party, excluded by
    default.
  * Prefer the Learning English strand over general `voanews.com` news feeds:
    cleaner PD provenance and slower speech better fit the hearing-loss demo.

## 3. Findings — CONDITIONAL (needs spec amendment, not demo-ready)

* **[RSS-C-001]** *Open Minds … from Creative Commons* — speech-heavy
  interviews about open culture/science, `CC BY 4.0`
  (`Open Minds ... is licensed to the public under CC BY (https://creativecommons.org/licenses/by/4.0/)`
  per episode notes; site default `Except where otherwise noted, content on
  this site is licensed under CC BY 4.0`). RSS:
  `https://anchor.fm/s/4d70d828/podcast/rss` (linked as `show's RSS feed` on
  every episode page). Would satisfy `COR-AC-001` for the *talk* track, BUT
  theme music is `Day Bird by Broke for Free ... Available for use under the
  CC BY 3.0 license, at the Free Music Archive` — `CC-BY 3.0` is NOT on the
  `COR-AC-001` allowlist. Options: (a) amend `COR-AC-001` to accept `CC-BY 3.0`
  with attribution, or (b) strip/duck the theme before ingest and document in
  `provenance.json`. Until then: research-only, do not ingest.
* **[RSS-C-002]** `https://librivox.org/rss/latest_releases` — useful as a
  *discovery* feed (new-book announcements ~3/day) + resolver to per-book
  `RSS-F-001` feeds, but has no enclosures itself. Could drive `DIS-B-002`
  polling with a resolver step; not a direct audio source.

## 4. Explicitly REJECTED (do not ingest as demo bytes)

* **[RSS-R-001]** NPR (`https://feeds.npr.org/510351/podcast.xml` and
  siblings): personal-noncommercial-only, no modification/derivatives —
  conflicts with the remix + re-serve demo. Link-only per `DIS-IN-004`.
* **[RSS-R-002]** Any feed whose license resolves to `BY-NC`, `BY-ND`, or
  `BY-SA` (any version) — conflicts with `COR-AC-001` / denylists
  `COR-V-005`, `COR-N-004`, `COR-M-004`. Concrete speech-heavy examples to
  avoid: TED Talks (`CC BY-NC-ND`), MIT OpenCourseWare lectures
  (`CC BY-NC-SA`), Wikipedia Spoken Articles / Wikisource readings
  (`CC BY-SA`), Skidmore-style `CC-BY-SA` music beds.
* **[RSS-R-003]** Commercial-podcast catch-alls (Spotify/Apple-hosted shows
  with `© All rights reserved` and no license grant): no remix right.
  Absence of a license statement is NOT permission.

## 5. Verification log (2026-10-14)

| Feed | Check | Result |
|---|---|---|
| `https://www.nasa.gov/feeds/podcasts/houston-we-have-a-podcast` | `curl` + `grep <enclosure>` | 200, RSS 2.0, `© NASA`, ≥3 `traffic.megaphone.fm/...mp3` enclosures |
| `https://www.nasa.gov/feeds/podcasts/curious-universe` | `curl` + `grep <enclosure>` | 200, RSS 2.0, `© NASA`, `chrt.fm/track/...traffic.megaphone.fm/...mp3` enclosures |
| `https://librivox.org/rss/20232` | `curl` | 200, RSS 2.0 serial, per-chapter `archive.org/download/...mp3` enclosures + `media:content` |
| `https://librivox.org/category/librivox-community-podcast/feed/` | `curl` + `grep <enclosure>` | 200, items #159–#162 each with `archive.org/download/...mp3` enclosure |
| `https://librivox.org/rss/latest_releases` | `curl` | 200, items with `<link>`/`<guid>` to catalog pages only, no `<enclosure>` — discovery-only |
| `https://learningenglish.voanews.com/podcast/?zoneId=1689` | `curl` | 200, RSS 2.0, `© 2026 - VOA`, items with `voa-audio.voanews.eu/vle/...mp3` enclosures + `itunes:duration` |
| License pages | `webfetch`/`websearch` | LibriVox PD dedication (`/pages/public-domain/`), NASA Media Usage Guidelines (audio generally not copyrighted in US; third-party carve-out; insignia excluded), VOA Terms (`p/6021.html`: VOA-produced = PD; AP/third-party excluded), CC Open Minds `CC BY 4.0` + `CC BY 3.0` theme note |

## 6. Recommendation for the demo

* **[RSS-REC-001]** If a live-RSS demo path is ever added alongside the
  synthesized corpus (`COR-S-005` remains the DEFAULT and ONLY demo ingest
  path until amended), the lowest-risk candidates in order are:
  1. `RSS-F-001` (single LibriVox book feed — pin one `project_id`, vendor
     specific chapter MP3s + SHA-256 in `provenance.json`);
  2. `RSS-F-002` (single Community Podcast episode — pin GUID);
  3. `RSS-F-003` (single NASA episode verified free of third-party credits);
  4. `RSS-F-004` (single Learning English episode verified VOA-produced, no AP credit).
* **[RSS-REC-002]** Do NOT add any of these to `favorites.yaml` in demo config
  without the `COR-L-004` amendment (per-clip `provenance.json` +
  `ATTRIBUTION.md` entries + poller enablement). The poller (`DIS-B-002`)
  stays empty/disabled in demo config per `DIS-B-007`.
* **[RSS-N-001]** Non-functional notes for any future ingest: respect
  per-feed poll interval + ETag/Last-Modified (`DIS-NF-002`); no website
  scraping (`DIS-IN-005`); credit NASA/VOA/LibriVox in text only (no
  logos/insignia); store enclosure URL + SHA-256 + license URL per clip
  (`COR-S-004`).

## 7. Acceptance criteria (for this research file)

* **[RSS-AC-001]** Every RECOMMENDED feed above has a verified enclosure URL,
  a named license basis resolving to `COR-AC-001`, and a stated caveat/filter.
* **[RSS-AC-002]** No recommended feed requires a `BY-SA/BY-NC/BY-ND`,
  `ODbL`, `DBCL`, or `Non-PD US` grant.
* **[RSS-AC-003]** Rejected categories (`RSS-R-001`–`RSS-R-003`) are listed so
  a future contributor does not re-propose NPR/TED/OCW/Wikipedia-spoken feeds
  as demo bytes.
