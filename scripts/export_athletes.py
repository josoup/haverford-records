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

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
SPORT_LABEL = {
    "mens-soccer": "Men's Soccer",
    "mens-track-and-field": "Men's Track & Field",
    "wten": "Women's Tennis",
}
# "Timonium, Md." -> "Md."  Hometowns are inconsistent, so only take a state
# when the shape is unambiguous; otherwise leave it null rather than guess.
STATE = re.compile(r",\s*([A-Z][A-Za-z.]{1,14})$")


def main() -> int:
    out, sources = [], []
    for f in sorted(FIXTURES.glob("roster-*.html")):
        stem = f.stem.replace("roster-", "")
        slug, _, season = stem.rpartition("-")
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
                "sport": SPORT_LABEL.get(r.sport_slug, r.sport_slug),
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
            })
        sources.append({"file": f.name, "athletes": len(page.rows),
                        "sport": slug, "season": season})
        print(f"  {f.name:44s} {len(page.rows):>3} athletes")

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
