"""Parser tests pinned to real saved HTML.

These exist so a Sidearm redesign shows up as a failing test on a known input
rather than as a quiet zero-row night in production.
"""

import pytest

from haverford_records.sources.haverford_site import RosterParseError, parse_roster

from . import fixture


@pytest.mark.parametrize(
    "name,expected_count",
    [
        ("roster-mens-soccer-current", 33),
        ("roster-mens-track-and-field-current", 48),
        ("roster-mens-soccer-2015", 29),
    ],
)
def test_expected_athlete_count(name, expected_count):
    page = parse_roster(fixture(name))
    assert len(page.rows) == expected_count
    assert page.warnings == []


def test_no_duplicate_athletes():
    """Sidearm renders each athlete in three view modes; we must count once."""
    rows = parse_roster(fixture("roster-mens-soccer-current")).rows
    ids = [r.source_athlete_id for r in rows]
    assert len(ids) == len(set(ids))


def test_every_row_has_identity_and_a_stable_source_id():
    for row in parse_roster(fixture("roster-mens-soccer-current")).rows:
        assert row.name.strip()
        assert row.source_athlete_id.isdigit()
        assert row.sport_slug == "mens-soccer"


def test_known_athlete_parses_completely():
    """One fully specified row, so field drift is caught rather than inferred."""
    rows = parse_roster(fixture("roster-mens-soccer-current")).rows
    benson = next(r for r in rows if r.source_athlete_id == "10963")
    assert benson.name == "Grayson Benson"
    assert benson.jersey == "0"
    assert benson.position == "GK"
    assert benson.height == "5'11\""
    assert benson.academic_year == "Jr."
    assert benson.hometown == "Timonium, Md."
    assert benson.highschool == "St. Paul's School"


def test_archived_season_is_not_the_current_squad():
    """Sidearm serves the current roster for seasons it has no archive for."""
    current = {r.source_athlete_id for r in parse_roster(fixture("roster-mens-soccer-current")).rows}
    archived = {r.source_athlete_id for r in parse_roster(fixture("roster-mens-soccer-2015")).rows}
    assert not (current & archived)


def test_broken_layout_raises_rather_than_returning_nothing():
    with pytest.raises(RosterParseError):
        parse_roster("<html><body><p>nothing here</p></body></html>")


def test_headshots_are_extracted_and_distinct():
    """Sidearm lazy-loads images; the real URL is in data-src, not src."""
    rows = parse_roster(fixture("roster-mens-soccer-current")).rows
    shots = [r.headshot_url for r in rows if r.headshot_url]
    assert len(shots) == len(rows)
    assert len(set(shots)) == len(rows), "each athlete should have their own image"
    assert all(s.startswith("/images/") and "?" not in s for s in shots)
