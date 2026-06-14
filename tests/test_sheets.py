from unittest.mock import MagicMock

from models import Character
from sheets import DATA_START_ROW, format_cell, rewrite_sheet_sorted, sort_players

PRIORITY = ["PlayerOne", "PlayerTwo", "PlayerThree"]


def make_char(ilvl: int, cp: float = 5000.0) -> Character:
    return Character(name="x", ilvl=ilvl, cp=cp, char_class="Slayer")


# --- format_cell ---

def test_format_cell_multiline():
    char = Character(name="PlayerOne", ilvl=1755, cp=5915.7, char_class="Slayer")
    result = format_cell(char)
    assert result == "PlayerOne | 1755\nSlayer | 5916"


def test_format_cell_support_class():
    char = Character(name="SampleBard", ilvl=1750, cp=5700.0, char_class="Bard")
    result = format_cell(char)
    assert result == "SampleBard | 1750\nBard | 5700"


# --- sort_players ---

def test_priority_players_appear_first_in_order():
    eligibility = {
        "PlayerOne": [make_char(1755)] * 6,
        "PlayerTwo":      [make_char(1755)] * 6,
        "PlayerThree":      [make_char(1755)] * 4,
        "Other":     [make_char(1755)] * 5,
    }
    result = sort_players(eligibility, PRIORITY)
    assert result[:3] == ["PlayerOne", "PlayerTwo", "PlayerThree"]


def test_rest_sorted_by_eligible_count_descending():
    eligibility = {
        "PlayerOne": [make_char(1755)] * 6,
        "PlayerTwo":      [make_char(1755)] * 6,
        "PlayerThree":      [make_char(1755)] * 4,
        "A": [make_char(1755)] * 2,
        "B": [make_char(1755)] * 5,
        "C": [make_char(1755)] * 3,
    }
    result = sort_players(eligibility, PRIORITY)
    assert result[3:] == ["B", "C", "A"]


def test_tie_broken_by_total_cp_descending():
    eligibility = {
        "PlayerOne": [],
        "PlayerTwo":      [],
        "PlayerThree":      [],
        "A": [make_char(1755, cp=4000.0), make_char(1750, cp=4000.0)],  # 2 chars, total CP 8000
        "B": [make_char(1755, cp=5000.0), make_char(1750, cp=5000.0)],  # 2 chars, total CP 10000
    }
    result = sort_players(eligibility, PRIORITY)
    assert result[3] == "B"
    assert result[4] == "A"


def test_priority_player_absent_from_data_is_skipped():
    eligibility = {
        "PlayerOne": [make_char(1755)] * 3,
        "Other":     [make_char(1755)] * 2,
    }
    result = sort_players(eligibility, PRIORITY)
    assert result[0] == "PlayerOne"
    assert "PlayerTwo" not in result
    assert "PlayerThree" not in result


def test_player_with_zero_eligible_chars_sorts_last():
    eligibility = {
        "PlayerOne": [],
        "PlayerTwo":      [],
        "PlayerThree":      [],
        "A": [make_char(1755)] * 3,
        "B": [],
    }
    result = sort_players(eligibility, PRIORITY)
    assert result[-1] == "B"


def test_sort_players_no_priority_argument():
    # Default priority is None / empty — sort purely by count then CP.
    eligibility = {
        "A": [make_char(1755)] * 2,
        "B": [make_char(1755)] * 5,
        "C": [make_char(1755)] * 3,
    }
    assert sort_players(eligibility) == ["B", "C", "A"]


# --- rewrite_sheet_sorted ---

def _make_ws(current_names: list[str]) -> MagicMock:
    ws = MagicMock()
    # get_players_from_sheet reads col_values(1): two header rows then names.
    ws.col_values.return_value = ["Title", "Header", *current_names]
    ws.id = 0
    return ws


def _make_spreadsheet(ws: MagicMock) -> MagicMock:
    spreadsheet = MagicMock()
    spreadsheet.worksheet.return_value = ws
    spreadsheet.id = "sheet-id"
    return spreadsheet


def test_rewrite_never_clears_before_writing():
    """A failure between a clear and the rewrite destroyed column A (the
    documented source of truth); the rewrite must be a single overwrite."""
    ws = _make_ws(["Alice", "Bob"])
    spreadsheet = _make_spreadsheet(ws)

    rewrite_sheet_sorted(
        spreadsheet, "Tab", {"Alice": [make_char(1750)], "Bob": []}, ["Alice", "Bob"], MagicMock()
    )

    ws.batch_clear.assert_not_called()
    assert ws.update.call_count == 1


def test_rewrite_overwrites_the_full_rectangle_with_values_first():
    """Stale rows (more current names than ordered players) must be blanked by
    the overwrite itself, and gspread 6 wants update(values, range_name)."""
    ws = _make_ws(["Alice", "Bob", "Carol"])  # Carol dropped from the new order
    spreadsheet = _make_spreadsheet(ws)

    rewrite_sheet_sorted(
        spreadsheet, "Tab", {"Alice": [make_char(1750)], "Bob": []}, ["Alice", "Bob"], MagicMock()
    )

    args, kwargs = ws.update.call_args
    rows = args[0] if args else kwargs["values"]
    assert isinstance(rows, list), "values must be the first positional argument"
    assert len(rows) == 3  # max(ordered, current) — Carol's old row gets blanked
    assert all(len(r) == 7 for r in rows)  # A + B..G
    assert rows[2] == [""] * 7
    range_arg = args[1] if len(args) > 1 else kwargs.get("range_name")
    assert range_arg == f"A{DATA_START_ROW}"
