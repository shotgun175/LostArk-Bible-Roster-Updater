"""Tests for the Python-side roster extraction (replaces the in-page JS eval).

Fixtures: valid_roster.html is a trimmed copy of a real lostark.bible roster
page (the hydration <script> structure is verbatim; character/guild/server
names and the account id were replaced with CharNN-style placeholders);
bracket_in_string.html is the same page with brackets injected into a name
string (the case that broke the old depth-counting scanner); no_roster.html
has no roster key at all.
"""
from pathlib import Path

import pytest

from scraper import RosterExtractionError, extract_roster_json

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_extracts_the_real_roster():
    entries = extract_roster_json(load("valid_roster.html"))
    assert isinstance(entries, list)
    assert len(entries) == 14  # the fixture page's roster array has 14 entries
    first = entries[0]
    assert first["name"] == "Char01"
    assert first["class"] == "bard"
    assert first["ilvl"] == 1795
    assert first["combatPower"]["score"] == 7120.76


def test_brackets_inside_string_values_do_not_break_the_scan():
    entries = extract_roster_json(load("bracket_in_string.html"))
    assert entries is not None
    assert len(entries) == 14  # the old scanner truncated the slice here
    assert entries[0]["name"] == "[Guild] Brack{et}eer]"
    # the rest of the array survives intact
    assert entries[1]["name"] == "Char01"


def test_page_without_a_roster_returns_none():
    assert extract_roster_json(load("no_roster.html")) is None


def test_unparseable_roster_raises_extraction_error():
    html = "<script>kit.start({ roster:[ {name:'broken </script>"
    with pytest.raises(RosterExtractionError):
        extract_roster_json(html)


def test_void_0_fields_map_to_null():
    # The site's minifier serializes undefined as `void 0` (see the fixture's
    # own userData field). One undefined field must not drop a whole roster.
    html = '<script>kit.start({ roster:[{name:"A",ilvl:1700,combatPower:void 0}] });</script>'
    entries = extract_roster_json(html)
    assert entries is not None
    assert entries[0]["combatPower"] is None


def test_escaped_quotes_inside_strings_are_honored():
    # HTML carries name:"a\"[b]" — the escaped quote must not end the string
    # early (which would let the [b] miscount the depth).
    html = '<script>var d = { roster:[{name:"a\\"[b]",ilvl:1700}] };</script>'
    entries = extract_roster_json(html)
    assert entries is not None
    assert entries[0]["name"] == 'a"[b]'
    assert entries[0]["ilvl"] == 1700
