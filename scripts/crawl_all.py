#!/usr/bin/env python3
"""Full crawl: every sport, every genuine season, and every athlete's bio page.

Runs in two stages, and is RESUMABLE -- anything already on disk is skipped, so
you can stop it with Ctrl-C and start it again without refetching.

  stage 1  rosters   23 sports x N seasons        (~400 pages)
  stage 2  bios      one page per athlete found   (thousands)

Sidearm serves the CURRENT roster for seasons it has no archive for, so each
archived page is hashed against the current one and discarded if identical.
That silent fallback is why the first pass appeared to find seasons back to
2000 when the real archive starts much later.

    python3 scripts/crawl_all.py --stage rosters --delay 5
    python3 scripts/crawl_all.py --stage bios    --delay 5
    python3 scripts/crawl_all.py --stage all     --delay 30   # robots.txt rate
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from haverford_records.sources.haverford_site import parse_roster  # noqa: E402

BASE = "https://haverfordathletics.com"
UA = ("HaverfordAthleticsRecon/0.4 "
      "(athletics communications committee; internal records project)")

SPORTS = [
    "baseball", "cricket", "field-hockey", "mens-basketball", "mens-cross-country",
    "mens-fencing", "mens-indoor-track", "mens-lacrosse", "mens-soccer",
    "mens-squash", "mens-tennis", "mens-track-and-field", "softball",
    "womens-basketball", "womens-cross-country", "womens-fencing",
    "womens-indoor-track", "womens-lacrosse", "womens-soccer", "womens-squash",
    "wten", "womens-track-and-field", "womens-volleyball",
]

RAW = ROOT / "data" / "raw"


class Crawler:
    def __init__(self, delay: float) -> None:
        self.delay = delay
        self._last = 0.0
        self.fetched = 0
        self.skipped = 0
        self.failed = 0

    def get(self, url: str, dest: Path) -> str | None:
        """Fetch unless already on disk. Returns the body, or None on failure."""
        if dest.exists():
            self.skipped += 1
            return dest.read_text(encoding="utf-8")
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Accept": "text/html",
                          "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                body = raw.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print(f"    !! {url} -> HTTP {e.code}")
            self.failed += 1
            return None
        except Exception as e:
            print(f"    !! {url} -> {type(e).__name__}: {e}")
            self.failed += 1
            return None
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        self.fetched += 1
        return body


def digest(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def stage_rosters(c: Crawler, earliest: int, latest: int) -> dict:
    found: dict[str, list[str]] = {}
    for slug in SPORTS:
        print(f"\n[{slug}]")
        cur = c.get(f"{BASE}/sports/{slug}/roster", RAW / slug / "current.html")
        if not cur:
            print("  no current roster; skipping sport")
            continue
        cur_hash = digest(cur)
        seasons = ["current"]
        for year in range(latest, earliest - 1, -1):
            body = c.get(f"{BASE}/sports/{slug}/roster/{year}",
                         RAW / slug / f"{year}.html")
            if not body:
                continue
            if digest(body) == cur_hash:
                # Fallback page, not an archive. Remove it so a later run does
                # not mistake the cached copy for a real season.
                (RAW / slug / f"{year}.html").unlink(missing_ok=True)
                print(f"  {year}: fallback to current -- archive ends here")
                break
            seasons.append(str(year))
        found[slug] = seasons
        print(f"  {len(seasons)} season(s) held")
    return found


def stage_bios(c: Crawler) -> int:
    """Fetch each athlete's own page, discovered from the rosters on disk."""
    targets: dict[str, str] = {}
    for f in sorted(RAW.glob("*/*.html")):
        if f.parent.name == "bios":
            continue
        try:
            page = parse_roster(f.read_text(encoding="utf-8"), expect_min=1)
        except Exception:
            continue
        for r in page.rows:
            if r.bio_url:
                targets[r.source_athlete_id] = r.bio_url
    print(f"{len(targets)} distinct athletes discovered across saved rosters\n")
    for i, (aid, url) in enumerate(sorted(targets.items()), 1):
        c.get(f"{BASE}{url}", RAW / "bios" / f"{aid}.html")
        if i % 25 == 0:
            print(f"  {i}/{len(targets)}  (fetched {c.fetched}, cached {c.skipped})")
    return len(targets)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["rosters", "bios", "all"], default="rosters")
    ap.add_argument("--delay", type=float, default=30.0,
                    help="seconds between requests; robots.txt asks 30")
    ap.add_argument("--earliest", type=int, default=2005)
    ap.add_argument("--latest", type=int, default=2026)
    args = ap.parse_args()

    c = Crawler(args.delay)
    summary: dict = {}
    try:
        if args.stage in ("rosters", "all"):
            print("=" * 60 + "\nSTAGE 1: rosters\n" + "=" * 60)
            summary["seasons"] = stage_rosters(c, args.earliest, args.latest)
        if args.stage in ("bios", "all"):
            print("\n" + "=" * 60 + "\nSTAGE 2: bios\n" + "=" * 60)
            summary["bios"] = stage_bios(c)
    except KeyboardInterrupt:
        print("\ninterrupted -- everything already saved is kept; re-run to resume")
    finally:
        RAW.mkdir(parents=True, exist_ok=True)
        (RAW / "crawl_summary.json").write_text(json.dumps(summary, indent=1))
        print(f"\nfetched {c.fetched}  cached {c.skipped}  failed {c.failed}")
        print(f"raw pages under {RAW}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
