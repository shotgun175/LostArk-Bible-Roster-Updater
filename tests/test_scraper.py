import pytest
from models import Character
from scraper import filter_and_sort

MAX_ELIGIBLE = 6


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


from scraper import _parse_roster_entry


def make_entry(name="Valslayer", kr_class="berserker_female", ilvl=1755.0, cp_score=5915.7):
    return {"name": name, "class": kr_class, "ilvl": ilvl, "combatPower": {"score": cp_score}}


def test_parse_roster_entry_valid():
    char = _parse_roster_entry(make_entry())
    assert char is not None
    assert char.name == "Valslayer"
    assert char.char_class == "Slayer"   # berserker_female → Slayer
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
