# haverford-records

Athletics records aggregator for the Haverford athletics communications
committee. Pulls roster and results data from several sources into one place
and surfaces **record candidates** — records just broken, and records being
approached — for a human to sign off on.

> **The system never makes the final call.** It presents evidence with
> provenance; a person decides. Every design choice below follows from that.

## Status

Early scaffold. The schema is real and tested; the parsers are not written yet
because they need real HTML first (see *Getting unblocked*).

## Architecture

An overnight batch job, run once a night:

```
fetch → parse → normalize → resolve identities → evaluate → review queue → digest
```

Six ideas do most of the work:

**Incremental fetch, full re-evaluate.** Only fetch what's new — that's where
the cost and the courtesy live. But re-evaluate the *entire* corpus against the
record book every night. A player's distance to a career record changes nightly
even when they don't play, because games remaining just went down. Nothing new
arrived; the conclusion still changed.

**Candidates carry a stable key.** Full recompute would re-emit the same
candidate every night. `candidate.candidate_key` is a deterministic hash, and
the nightly job upserts on it. So the review state lives on a stable row: a
candidate someone dismissed *stays* dismissed instead of refilling the queue
every morning.

**Raw documents are immutable.** Every response body is kept, keyed by
`(url, sha256)`. Parsers will have bugs, and reprocessing history must never
mean re-crawling. It also means results are allowed to *change*: a DQ applied
days later or a corrected wind reading arrives as a new version we can diff,
not a silent overwrite. Results are not immutable at publish time — which is
exactly why human sign-off is the right design.

**Identity resolution is human-owned, and permanent.** `athlete_alias` is the
crosswalk. Use the source's stable ID where one exists, fuzzy-match only where
you must, route low confidence to a person — and never re-match a pair a human
already resolved.

**The record book belongs to the committee.** The engine reads
`record_definition` / `record_holder` and never writes them. A sign-off is what
promotes a candidate into the book.

**Sources disagree in the open.** When TFRRS and the live stats feed report
different marks, that's a `conflict` row shown to a reviewer, not something
resolved silently by picking a favorite.

### The failure mode this is built to survive

Batch pipelines fail *quietly*. A parser breaks, zero rows come back, and
everyone assumes it was a slow week. `source_health` records each run's yield
per source against a trailing average, so a zero-row Saturday in April pages
somebody instead of passing for good news.

## Record types

Different records need different math:

- **counting** — career assists, career points. Signal is
  `projected_final = current + rate × opportunities_remaining`, which beats a
  naive "within 10%" threshold and works across sports.
- **best_mark** — fastest 800m, longest javelin. Not accumulation: the signal is
  season PR trajectory, gap to the record, and meets remaining — weighted,
  because championship meets are where marks fall.
- **streak** — consecutive games with a goal. Fiddly; deferred.

Track marks are not comparable without their conditions, so wind, timing method
(FAT vs hand), track size and banking are **columns**, not notes.

## Layout

```
schema/001_init.sql   canonical Postgres schema (14 tables) — tested, applies clean
src/haverford_records/
  fetch.py            polite fetcher + immutable raw store
  sources/            one adapter per source; dumb on purpose
scripts/recon_haverford.py   site reconnaissance (stdlib only, no install)
tests/fixtures/       saved HTML — parsers are tested against these
```

Adapters fetch and emit source-shaped rows. No cross-source logic ever lives in
an adapter.

## Getting unblocked

Parsers can't be written against a site nobody has looked at. Run:

```sh
python3 scripts/recon_haverford.py
```

It reports the platform (Sidearm vs PrestoSports — completely different DOM),
what robots.txt permits, whether a sitemap exists, the roster URL pattern, and
how far back the archives actually go. It saves every page it touches into
`tests/fixtures/`. Parsers get built against those fixtures, so a site redesign
shows up as a failing test rather than a silent zero-row night.

## Sources

| Source | Status | Notes |
|---|---|---|
| haverfordathletics.com | recon pending | athlete spine — identity, not stats |
| TFRRS | not started | track marks; no public API |
| Athletic.net | not started | no public API |
| NCAA live stats | later | needed only when live detection matters |

Note that roster pages give **identity** (name, class year, hometown,
position) — not career stats. This scrape builds the spine everything else
resolves against; it is not yet the records dataset.

## Conventions

- Be a polite citizen: identify the scraper in its User-Agent, keep the delay,
  cache aggressively. Worth asking whether the College already has a data
  agreement with these providers.
- This repository is private. Rosters contain student names, hometowns and
  class years.

## Recon findings (2026-08-21)

- **Platform: Sidearm Sports.** Roster URLs are `/sports/<slug>/roster`, with
  archived seasons at `/sports/<slug>/roster/<year>`.
- **23 varsity sports**, slugs recorded in `scripts/fetch_roster_fixtures.py`.
- **No sitemap.xml, no reachable JSON API.** `/api` and `/api/v2` 404;
  `/services/` is `Disallow`ed for `*` in robots.txt so it is off-limits
  regardless. The homepage does embed JSON-LD, worth a look. This means HTML
  parsing, not a JSON feed.
- **robots.txt allows `/sports/`** for `*` and asks `Crawl-delay: 30`.
  Disallowed and avoided: `/common/`, `/images/`, `/documents/`, `/admin/`,
  `/services/`, `/site/`, `/hidden/`, and `*print=true*`.
