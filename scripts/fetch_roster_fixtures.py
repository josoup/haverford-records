#!/usr/bin/env python3
"""
Pull roster fixtures from haverfordathletics.com.

Recon established the platform: Sidearm Sports, rosters at
/sports/<slug>/roster, with archived seasons at /sports/<slug>/roster/<year>.
This grabs the current roster for every sport plus an archive-depth probe on
one sport, saving each page so parsers can be written and regression-tested
against real HTML.

robots.txt asks unlisted agents for Crawl-delay: 30, which is what this
defaults to. /sports/ is not disallowed for `*`; /services/, /common/,
/documents/ and /images/ are, and this script stays out of them.

Stdlib only.

    python3 scripts/fetch_roster_fixtures.py              # ~25 min, polite
    python3 scripts/fetch_roster_fixtures.py --delay 5    # ~4 min
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
import hashlib
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://haverfordathletics.com"
UA = (
    "HaverfordAthleticsRecon/0.3 "
    "(athletics communications committee; internal records project)"
)

# Discovered by recon. Kept explicit rather than re-crawled so this run is
# reproducible and we can see at a glance what is covered.
SPORTS = [
    "baseball", "cricket", "field-hockey",
    "mens-basketball", "mens-cross-country", "mens-fencing",
    "mens-indoor-track", "mens-lacrosse", "mens-soccer", "mens-squash",
    "mens-tennis", "mens-track-and-field",
    # women's tennis 404s on the modern slug; recon saw the legacy "wten"
    "softball",
    "womens-basketball", "womens-cross-country", "womens-fencing",
    "womens-indoor-track", "womens-lacrosse", "womens-soccer",
    "womens-squash", "wten", "womens-track-and-field",
    "womens-volleyball",
]

ARCHIVE_PROBE_SPORT = "mens-soccer"


def fetch(url: str, delay: float, last: list[float]) -> tuple[int, str]:
    wait = delay - (time.time() - last[0])
    if wait > 0:
        time.sleep(wait)
    last[0] = time.time()
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "text/html", "Accept-Encoding": "gzip"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return r.status, raw.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        print(f"    !! {url} -> {type(e).__name__}: {e}")
        return 0, ""


def looks_like_roster(html: str) -> tuple[bool, int]:
    """Rough yield check: how many athlete-ish links does the page carry?"""
    hits = len(re.findall(r'/roster/[A-Za-z0-9._-]*/?\d+', html))
    hits += len(re.findall(r'sidearm-roster-player', html))
    return hits >= 5, hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("tests/fixtures"))
    ap.add_argument("--delay", type=float, default=30.0,
                    help="seconds between requests; robots.txt asks 30 (default)")
    ap.add_argument("--earliest", type=int, default=2000)
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    last = [0.0]
    summary: dict = {"current": {}, "archive": {}}

    est = (len(SPORTS) + (2026 - args.earliest + 1)) * args.delay / 60
    print(f"{len(SPORTS)} sports + archive probe at {args.delay}s delay -> ~{est:.0f} min\n")

    print("=== current rosters ===")
    for slug in SPORTS:
        url = f"{BASE}/sports/{slug}/roster"
        st, body = fetch(url, args.delay, last)
        ok, hits = looks_like_roster(body)
        if st == 200 and body:
            (args.out / f"roster-{slug}-current.html").write_text(body, encoding="utf-8")
        flag = "OK " if ok else "?? "
        print(f"  {flag} {slug:28s} {st}  {len(body):>7,}b  ~{hits} player refs")
        summary["current"][slug] = {"status": st, "bytes": len(body), "player_refs": hits}

    print(f"\n=== archive depth: {ARCHIVE_PROBE_SPORT} ===")
    # Fingerprint the current roster first. Any "archived" year whose body
    # hashes the same is the site falling back, not a real season.
    cur = args.out / f"roster-{ARCHIVE_PROBE_SPORT}-current.html"
    current_hash = (
        hashlib.sha256(cur.read_bytes()).hexdigest() if cur.exists() else None
    )
    found, fallbacks = [], []
    for year in range(2026, args.earliest - 1, -1):
        url = f"{BASE}/sports/{ARCHIVE_PROBE_SPORT}/roster/{year}"
        st, body = fetch(url, args.delay, last)
        ok, hits = looks_like_roster(body)
        digest = hashlib.sha256(body.encode()).hexdigest() if body else ""
        if st == 200 and ok and digest == current_hash:
            fallbacks.append(year)
            print(f"  ==  {year}  identical to current roster -- NOT an archive")
            continue
        if st == 200 and ok:
            found.append(year)
            # Keep a spread of seasons, not all of them.
            if year in (2026, 2020, 2015, 2010, 2005, 2000):
                (args.out / f"roster-{ARCHIVE_PROBE_SPORT}-{year}.html").write_text(
                    body, encoding="utf-8")
            print(f"  OK  {year}  ~{hits} player refs")
        else:
            print(f"  --  {year}  status {st}")
    summary["archive"][ARCHIVE_PROBE_SPORT] = {"real": found, "fallbacks": fallbacks}
    if fallbacks:
        print(f"\n  {len(fallbacks)} year(s) served the current roster verbatim: "
              f"{min(fallbacks)}-{max(fallbacks)}")
    if found:
        print(f"\n  real archive floor: {min(found)}  ({len(found)} genuine seasons)")
    else:
        print("\n  !! no archived seasons found -- the year URL pattern may differ")

    Path("recon").mkdir(exist_ok=True)
    Path("recon/roster_summary.json").write_text(json.dumps(summary, indent=2))
    n = len(list(args.out.glob("*.html")))
    print(f"\nDone. {n} fixtures in {args.out}")
    print("Send me recon/roster_summary.json + tests/fixtures/roster-mens-soccer-current.html")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\ninterrupted -- fixtures already saved are kept")
        raise SystemExit(130)
