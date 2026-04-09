import pytest
from models import Character
from sheets import format_cell, sort_players

PRIORITY = ["Valluru", "Mabi", "Remi"]


def make_char(ilvl: int, cp: float = 5000.0) -> Character:
    return Character(name="x", ilvl=ilvl, cp=cp, char_class="Slayer")


# --- format_cell ---

def test_format_cell_multiline():
    char = Character(name="Valslayer", ilvl=1755, cp=5915.7, char_class="Slayer")
    result = format_cell(char)
    assert result == "Valslayer | 1755\nSlayer | 5916"


def test_format_cell_support_class():
    char = Character(name="Valbard", ilvl=1750, cp=5700.0, char_class="Bard")
    result = format_cell(char)
    assert result == "Valbard | 1750\nBard | 5700"


# --- sort_players ---

def test_priority_players_appear_first_in_order():
    eligibility = {
        "Valluru": [make_char(1755)] * 6,
        "Mabi":    [make_char(1755)] * 6,
        "Remi":    [make_char(1755)] * 4,
        "Other":   [make_char(1755)] * 5,
    }
    result = sort_players(eligibility, PRIORITY)
    assert result[:3] == ["Valluru", "Mabi", "Remi"]


def test_rest_sorted_by_eligible_count_descending():
    eligibility = {
        "Valluru": [make_char(1755)] * 6,
        "Mabi":    [make_char(1755)] * 6,
        "Remi":    [make_char(1755)] * 4,
        "A": [make_char(1755)] * 2,
        "B": [make_char(1755)] * 5,
        "C": [make_char(1755)] * 3,
    }
    result = sort_players(eligibility, PRIORITY)
    assert result[3:] == ["B", "C", "A"]


def test_tie_broken_by_total_cp_descending():
    eligibility = {
        "Valluru": [],
        "Mabi":    [],
        "Remi":    [],
        "A": [make_char(1755, cp=4000.0), make_char(1750, cp=4000.0)],  # 2 chars, total CP 8000
        "B": [make_char(1755, cp=5000.0), make_char(1750, cp=5000.0)],  # 2 chars, total CP 10000
    }
    result = sort_players(eligibility, PRIORITY)
    assert result[3] == "B"
    assert result[4] == "A"


def test_priority_player_absent_from_data_is_skipped():
    eligibility = {
        "Valluru": [make_char(1755)] * 3,
        "Other":   [make_char(1755)] * 2,
    }
    result = sort_players(eligibility, PRIORITY)
    assert result[0] == "Valluru"
    assert "Mabi" not in result
    assert "Remi" not in result


def test_player_with_zero_eligible_chars_sorts_last():
    eligibility = {
        "Valluru": [],
        "Mabi":    [],
        "Remi":    [],
        "A": [make_char(1755)] * 3,
        "B": [],
    }
    result = sort_players(eligibility, PRIORITY)
    assert result[-1] == "B"
