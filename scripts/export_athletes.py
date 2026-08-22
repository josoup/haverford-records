#!/usr/bin/env python3
"""Parse every roster fixture into one JSON file for the dashboard.

Only real, scraped data goes in here. Nothing is inferred or filled in.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from haverford_records.sources.haverford_site import parse_roster  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
RAW = ROOT / "data" / "raw"
def label(slug: str) -> str:
    if slug == "wten":
        return "Women's Tennis"
    s = slug.replace("mens-", "Men's ").replace("womens-", "Women's ")
    s = s.replace("-", " ").replace("and", "&")
    return " ".join(w if w.startswith(("Men", "Women")) or w == "&" else w.capitalize()
                    for w in s.split())


def discover() -> list[tuple[Path, str, str]]:
    """Prefer the full crawl in data/raw/; fall back to the checked-in fixtures.

    The crawler writes data/raw/<sport>/<season>.html, so a completed crawl is
    the real corpus. tests/fixtures/ only ever held a handful of pages for
    parser development.
    """
    out: list[tuple[Path, str, str]] = []
    if RAW.is_dir():
        for f in sorted(RAW.glob("*/*.html")):
            if f.parent.name == "bios":
                continue
            out.append((f, f.parent.name, f.stem))
    if out:
        print(f"source: data/raw/  ({len(out)} roster pages from the crawl)")
        return out
    for f in sorted(FIXTURES.glob("roster-*.html")):
        slug, _, season = f.stem.replace("roster-", "").rpartition("-")
        out.append((f, slug, season))
    print(f"source: tests/fixtures/  ({len(out)} pages -- run crawl_all.py for the full set)")
    return out
# "Timonium, Md." -> "Md."  Hometowns are inconsistent, so only take a state
# when the shape is unambiguous; otherwise leave it null rather than guess.
STATE = re.compile(r",\s*([A-Z][A-Za-z.]{1,14})$")


def main() -> int:
    out, sources = [], []
    for f, slug, season in discover():
        try:
            page = parse_roster(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  SKIP {f.name}: {e}")
            continue
        for r in page.rows:
            m = STATE.search(r.hometown or "")
            out.append({
                "id": r.source_athlete_id,
                "name": r.name,
                "sport": label(r.sport_slug),
                "sportSlug": r.sport_slug,
                "season": season,
                "jersey": r.jersey,
                "position": r.position,
                "height": r.height,
                "classYear": r.academic_year,
                "hometown": r.hometown,
                "state": m.group(1) if m else None,
                "highSchool": r.highschool,
                "bioUrl": r.bio_url,
                "headshotUrl": r.headshot_url,
            })
        sources.append({"file": f"{slug}/{season}", "athletes": len(page.rows),
                        "sport": slug, "season": season})
        print(f"  {slug + '/' + season:44s} {len(page.rows):>3} athletes")

    payload = {
        "generatedFrom": "haverfordathletics.com roster pages (Sidearm Sports)",
        "athleteSeasons": out,
        "sources": sources,
    }
    dest = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "data" / "athletes.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(payload, indent=1), encoding="utf-8")
    print(f"\n{len(out)} athlete-seasons -> {dest.relative_to(Path.cwd()) if dest.is_relative_to(Path.cwd()) else dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
