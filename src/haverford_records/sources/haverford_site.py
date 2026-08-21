"""Parser for haverfordathletics.com roster pages (Sidearm Sports).

Two things about Sidearm's markup drive this implementation:

1. **Every athlete is rendered three times** -- a card view, a list view and a
   table view all sit in the DOM at once and CSS hides two of them. Selecting
   on a class like `.sidearm-roster-player-hometown` triple-counts everyone.
   We scope to `li.sidearm-roster-player`, which appears exactly once per
   athlete, and read fields relative to that node.

2. **The bio link carries a stable numeric athlete id** --
   `/sports/mens-soccer/roster/grayson-benson/10963`. That id is a
   deterministic identity key, so this source needs no fuzzy name matching:
   it populates `athlete_alias.source_athlete_id` directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from selectolax.parser import HTMLParser, Node

BIO_HREF = re.compile(r"/sports/([a-z0-9-]+)/roster/([a-z0-9-]+)/(\d+)", re.I)


class RosterParseError(RuntimeError):
    """Raised when a page does not look like a roster at all."""


@dataclass(frozen=True)
class RosterRow:
    source_athlete_id: str
    name: str
    first_name: str | None
    last_name: str | None
    sport_slug: str
    jersey: str | None = None
    position: str | None = None
    height: str | None = None
    academic_year: str | None = None
    hometown: str | None = None
    highschool: str | None = None
    previous_school: str | None = None
    bio_url: str | None = None


@dataclass
class RosterPage:
    rows: list[RosterRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _text(node: Node | None) -> str | None:
    if node is None:
        return None
    # Sidearm's templates are heavily whitespace-padded and use &nbsp;.
    cleaned = " ".join(node.text().replace("\xa0", " ").split())
    return cleaned or None


def _first(node: Node, selector: str) -> str | None:
    return _text(node.css_first(selector))


def parse_roster(html: str, *, expect_min: int = 5) -> RosterPage:
    """Extract one row per athlete from a Sidearm roster page.

    Raises RosterParseError when the page yields implausibly few athletes --
    a broken selector must fail loudly rather than quietly return nothing.
    """
    tree = HTMLParser(html)
    page = RosterPage()
    seen: set[str] = set()

    for li in tree.css("li.sidearm-roster-player"):
        link = li.css_first("a[href*='/roster/']")
        href = link.attributes.get("href", "") if link else ""
        m = BIO_HREF.search(href)
        if not m:
            page.warnings.append(f"player entry without a parseable bio link: {href!r}")
            continue

        sport_slug, _slug, athlete_id = m.groups()
        if athlete_id in seen:      # belt and braces against view duplication
            continue
        seen.add(athlete_id)

        first = _first(li, ".sidearm-roster-player-first-name")
        last = _first(li, ".sidearm-roster-player-last-name")
        name = " ".join(p for p in (first, last) if p) or _first(
            li, ".sidearm-roster-player-name a"
        )
        if not name:
            page.warnings.append(f"athlete {athlete_id} has no readable name")
            continue

        # Position sits in a bold span alongside height/custom fields, so read
        # the bold child rather than the container's full text.
        pos_container = li.css_first(".sidearm-roster-player-position")
        position = _text(pos_container.css_first("span.text-bold")) if pos_container else None

        page.rows.append(
            RosterRow(
                source_athlete_id=athlete_id,
                name=name,
                first_name=first,
                last_name=last,
                sport_slug=sport_slug,
                jersey=_first(li, ".sidearm-roster-player-jersey-number"),
                position=position,
                height=_first(li, ".sidearm-roster-player-height"),
                academic_year=_first(li, ".sidearm-roster-player-academic-year"),
                hometown=_first(li, ".sidearm-roster-player-hometown"),
                highschool=_first(li, ".sidearm-roster-player-highschool"),
                previous_school=_first(li, ".sidearm-roster-player-previous-school"),
                bio_url=href,
            )
        )

    if len(page.rows) < expect_min:
        raise RosterParseError(
            f"parsed only {len(page.rows)} athletes (expected >= {expect_min}); "
            "the page layout has probably changed"
        )
    return page
