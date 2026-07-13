from models import Character, MAX_CHARS_PER_PLAYER as MAX_ELIGIBLE
from scraper import _parse_entries, _parse_roster_entry, count_eligible, filter_and_sort


def make_char(name: str, ilvl: int, cp: float = 5000.0, char_class: str = "Slayer") -> Character:
    return Character(name=name, ilvl=ilvl, cp=cp, char_class=char_class)


def test_filter_removes_characters_below_threshold():
    chars = [make_char("A", 1750), make_char("B", 1730), make_char("C", 1740)]
    result = filter_and_sort(chars, threshold=1740)
    names = [c.name for c in result]
    assert "B" not in names
    assert "A" in names
    assert "C" in names


def test_filter_includes_characters_at_exact_threshold():
    chars = [make_char("A", 1740)]
    result = filter_and_sort(chars, threshold=1740)
    assert len(result) == 1


def test_filter_sorts_descending_by_ilvl():
    chars = [make_char("A", 1740), make_char("B", 1755), make_char("C", 1750)]
    result = filter_and_sort(chars, threshold=1740)
    assert [c.ilvl for c in result] == [1755, 1750, 1740]


def test_filter_tiebreaks_by_cp_descending():
    chars = [
        make_char("A", 1755, cp=5000.0),
        make_char("B", 1755, cp=6000.0),
        make_char("C", 1755, cp=5500.0),
    ]
    result = filter_and_sort(chars, threshold=1755)
    assert [c.name for c in result] == ["B", "C", "A"]


def test_filter_caps_at_six():
    chars = [make_char(str(i), 1740 + i) for i in range(10)]
    result = filter_and_sort(chars, threshold=1740)
    assert len(result) == MAX_ELIGIBLE


def test_filter_returns_top_six_by_ilvl_when_capped():
    chars = [make_char(str(i), 1740 + i) for i in range(10)]
    result = filter_and_sort(chars, threshold=1740)
    assert result[0].ilvl == 1749
    assert result[-1].ilvl == 1744


def test_filter_empty_input():
    assert filter_and_sort([], threshold=1740) == []


def test_filter_none_eligible():
    chars = [make_char("A", 1700), make_char("B", 1720)]
    assert filter_and_sort(chars, threshold=1740) == []


def test_filter_fewer_than_six_returns_all_eligible():
    chars = [make_char(str(i), 1750 + i) for i in range(3)]
    result = filter_and_sort(chars, threshold=1740)
    assert len(result) == 3


def test_filter_cap_excludes_characters_above_cap():
    chars = [make_char("A", 1740), make_char("B", 1760), make_char("C", 1800)]
    result = filter_and_sort(chars, threshold=1740, cap=1760)
    names = [c.name for c in result]
    assert "C" not in names
    assert "A" in names
    assert "B" in names


def test_filter_cap_includes_characters_at_exact_cap():
    chars = [make_char("A", 1760)]
    result = filter_and_sort(chars, threshold=1740, cap=1760)
    assert len(result) == 1


def test_filter_cap_none_means_uncapped():
    chars = [make_char("A", 1740), make_char("B", 9999)]
    result = filter_and_sort(chars, threshold=1740, cap=None)
    assert len(result) == 2


def test_filter_cap_and_threshold_together():
    chars = [
        make_char("low", 1700),
        make_char("in_range", 1750),
        make_char("high", 1850),
    ]
    result = filter_and_sort(chars, threshold=1740, cap=1800)
    names = [c.name for c in result]
    assert names == ["in_range"]


# --- count_eligible ---

def test_count_eligible_counts_all_at_or_above_threshold():
    chars = [make_char("A", 1740), make_char("B", 1739), make_char("C", 1900)]
    assert count_eligible(chars, threshold=1740, cap=None) == 2


def test_count_eligible_respects_cap():
    chars = [make_char("A", 1740), make_char("B", 1750), make_char("C", 1900)]
    assert count_eligible(chars, threshold=1740, cap=1799) == 2


def test_count_eligible_does_not_apply_display_cap():
    # filter_and_sort caps at 6; count_eligible does not.
    chars = [make_char(str(i), 1740) for i in range(10)]
    assert count_eligible(chars, threshold=1740, cap=None) == 10


# --- _parse_roster_entry ---

def make_entry(name="PlayerOne", kr_class="berserker_female", ilvl=1755.0, cp_score=5915.7):
    return {"name": name, "class": kr_class, "ilvl": ilvl, "combatPower": {"score": cp_score}}


def test_parse_roster_entry_valid():
    char = _parse_roster_entry(make_entry())
    assert char is not None
    assert char.name == "PlayerOne"
    assert char.char_class == "Slayer"   # berserker_female -> Slayer
    assert char.ilvl == 1755              # float truncated to int
    assert char.cp == 5915.7


def test_parse_roster_entry_truncates_float_ilvl():
    char = _parse_roster_entry(make_entry(ilvl=1730.8334))
    assert char.ilvl == 1730


def test_parse_roster_entry_unknown_class():
    char = _parse_roster_entry(make_entry(kr_class="future_class"))
    assert char is not None
    assert char.char_class == "Unknown"


def test_parse_roster_entry_empty_name_returns_none():
    assert _parse_roster_entry(make_entry(name="")) is None


def test_parse_roster_entry_missing_key_returns_none():
    assert _parse_roster_entry({"name": "X", "class": "berserker"}) is None  # no ilvl


def test_parse_roster_entry_null_combat_power_defaults_to_zero():
    entry = {"name": "X", "class": "berserker", "ilvl": 1730, "combatPower": None}
    char = _parse_roster_entry(entry)
    assert char is not None
    assert char.cp == 0.0


def test_parse_roster_entry_missing_combat_power_defaults_to_zero():
    entry = {"name": "X", "class": "berserker", "ilvl": 1730}
    char = _parse_roster_entry(entry)
    assert char is not None
    assert char.cp == 0.0


from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error as PlaywrightError

from scraper import ScrapeFailedError, scrape_roster


def test_scrape_roster_raises_scrape_failed_on_load_error(monkeypatch):
    monkeypatch.setattr("scraper.time.sleep", lambda s: None)
    page = MagicMock()
    page.goto.side_effect = PlaywrightError("net::ERR_CONNECTION_RESET")
    with pytest.raises(ScrapeFailedError) as exc:
        scrape_roster(page, "PlayerOne")
    assert "PlayerOne" in str(exc.value)
    assert "existing sheet data" in str(exc.value)


def _resp(status: int, text: str = "<html></html>") -> MagicMock:
    r = MagicMock()
    r.status = status
    r.ok = 200 <= status < 300
    r.text.return_value = text
    return r


def test_http_429_raises_site_problem_not_name_problem(monkeypatch):
    monkeypatch.setattr("scraper.time.sleep", lambda s: None)
    page = MagicMock()
    page.goto.return_value = _resp(429)
    with pytest.raises(ScrapeFailedError) as exc:
        scrape_roster(page, "PlayerOne")
    msg = str(exc.value)
    assert "429" in msg
    assert "spelling" not in msg


def test_http_404_is_still_a_name_problem():
    page = MagicMock()
    page.goto.return_value = _resp(404)
    with pytest.raises(RuntimeError) as exc:
        scrape_roster(page, "PlayerOne")
    assert not isinstance(exc.value, ScrapeFailedError)
    assert "spelling" in str(exc.value)


# --- retry/backoff ---


def test_goto_retries_once_after_load_error(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("scraper.time.sleep", lambda s: sleeps.append(s))
    page = MagicMock()
    good = _resp(200, text="<html></html>")
    page.goto.side_effect = [PlaywrightError("reset"), good]
    with pytest.raises(RuntimeError):  # empty page -> no roster key -> name error
        scrape_roster(page, "PlayerOne")
    assert page.goto.call_count == 2
    assert sleeps == [2.0]


def test_goto_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr("scraper.time.sleep", lambda s: None)
    page = MagicMock()
    page.goto.side_effect = [_resp(429), _resp(429), _resp(200)]
    with pytest.raises(RuntimeError):
        scrape_roster(page, "PlayerOne")
    assert page.goto.call_count == 3


def test_goto_exhausted_retries_raise_scrape_failed(monkeypatch):
    monkeypatch.setattr("scraper.time.sleep", lambda s: None)
    page = MagicMock()
    page.goto.side_effect = PlaywrightError("reset")
    with pytest.raises(ScrapeFailedError):
        scrape_roster(page, "PlayerOne")
    assert page.goto.call_count == 3


# --- _parse_entries ---


def test_parse_entries_warns_on_bad_entry_and_keeps_good_ones(capsys):
    entries = [make_entry(name="Good"), make_entry(name="Bad", ilvl="not-a-number")]
    result = _parse_entries(entries, "PlayerOne")
    assert [c.name for c in result] == ["Good"]
    out = capsys.readouterr().out
    assert "Bad" in out and "Warning" in out


def test_parse_entries_all_bad_raises_site_format_error():
    entries = [make_entry(ilvl="x"), make_entry(ilvl="y")]
    with pytest.raises(ScrapeFailedError) as exc:
        _parse_entries(entries, "PlayerOne")
    assert "data format" in str(exc.value)


def test_parse_entries_nameless_placeholder_stays_silent(capsys):
    entries = [make_entry(name="Good"), make_entry(name="")]
    result = _parse_entries(entries, "PlayerOne")
    assert len(result) == 1
    assert "Warning" not in capsys.readouterr().out
