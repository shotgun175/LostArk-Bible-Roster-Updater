"""Google Sheets read/write for the Lost Ark roster updater."""
from googleapiclient.discovery import Resource
from gspread.utils import ValueInputOption

from models import Character, MAX_CHARS_PER_PLAYER

HEADER_ROWS = 2                  # row 1 = title, row 2 = column headers
DATA_START_ROW = HEADER_ROWS + 1  # player rows start at row 3

# Per-player character cells live in columns B.._LAST_CHAR_COL; everything that
# touches row widths or ranges derives from MAX_CHARS_PER_PLAYER.
_ROW_WIDTH = 1 + MAX_CHARS_PER_PLAYER            # column A + one cell per character
_LAST_CHAR_COL = chr(ord("B") + MAX_CHARS_PER_PLAYER - 1)  # "G" for a cap of 6

# Rich text colors: Name=navy, ilvl=plum, Class=purple, CP=deep teal
_COLORS = {
    "name":  {"red": 31/255,  "green": 56/255,  "blue": 100/255},  # #1F3864
    "ilvl":  {"red": 74/255,  "green": 20/255,  "blue": 140/255},  # #4A148C
    "class": {"red": 123/255, "green": 31/255,  "blue": 162/255},  # #7B1FA2
    "cp":    {"red": 0/255,   "green": 95/255,  "blue": 115/255},  # #005F73
}


def _text_format_runs(cell_text: str) -> list[dict]:
    """Build textFormatRuns for 'Name | ilvl\\nClass | CP' cell format."""
    try:
        line1, line2 = cell_text.split("\n", 1)
        sep1 = line1.index(" | ")
        sep2 = line2.index(" | ")
    except ValueError:
        return []

    class_start = len(line1) + 1  # +1 for \n
    cp_start = class_start + sep2

    def fmt(key, bold=False):
        return {"foregroundColorStyle": {"rgbColor": _COLORS[key]}, "bold": bold}

    return [
        {"startIndex": 0,           "format": fmt("name",  bold=True)},
        {"startIndex": sep1,        "format": fmt("ilvl",  bold=True)},
        {"startIndex": class_start, "format": fmt("class", bold=False)},
        {"startIndex": cp_start,    "format": fmt("cp",    bold=False)},
    ]


def _apply_rich_text(
    sheets_service: Resource,
    spreadsheet_id: str,
    sheet_id: int,
    cell_positions: list[tuple[int, int, str]],
) -> None:
    """Apply per-character color formatting to a list of (row_0, col_0, text) cells."""
    requests = []
    for row_0, col_0, text in cell_positions:
        if not text:
            continue
        runs = _text_format_runs(text)
        if not runs:
            continue
        requests.append({
            "updateCells": {
                "rows": [{"values": [{"textFormatRuns": runs}]}],
                "fields": "textFormatRuns",
                "start": {"sheetId": sheet_id, "rowIndex": row_0, "columnIndex": col_0},
            }
        })
    if requests:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()


def format_cell(character: Character) -> str:
    """Format a character as a multi-line cell string."""
    return f"{character.name} | {character.ilvl}\n{character.char_class} | {round(character.cp)}"


def sort_players(
    player_eligibility: dict[str, list[Character]],
    priority: list[str] | None = None,
) -> list[str]:
    """
    Return player nicknames in display order.
    Priority players come first (in given order), then remaining players
    sorted by eligible character count descending, tie-broken by sum of CP
    across all eligible characters descending.
    """
    priority = priority or []
    all_nicknames = list(player_eligibility.keys())
    norm = {n.strip().lower(): n for n in all_nicknames}
    priority_present: list[str] = []
    for p in priority:
        match = norm.get(p.strip().lower())
        if match is None:
            print(
                f"Warning: priority player '{p}' (config.json) not found in "
                "column A - check the spelling."
            )
        elif match not in priority_present:
            priority_present.append(match)
    priority_lower = {p.strip().lower() for p in priority}
    rest = [n for n in all_nicknames if n.strip().lower() not in priority_lower]

    def sort_key(nickname: str) -> tuple[int, float]:
        chars = player_eligibility[nickname] or []
        return (-len(chars), -sum(c.cp for c in chars))

    rest.sort(key=sort_key)
    return priority_present + rest


def _is_run_marker(cell_text: str) -> bool:
    """True for the column-A cell that starts the hand-maintained run planner.

    Matches "Run" exactly or any cell starting with "Run " ("Run Planner",
    "Run 1"), case-insensitive. Lost Ark character names cannot contain
    spaces, so a real player ("Runeblade") can never false-positive.
    """
    lowered = cell_text.strip().lower()
    return lowered == "run" or lowered.startswith("run ")


def read_tab(worksheet) -> tuple[list[tuple[int, str]], dict[str, list[str]]]:
    """Read a tab's roster rectangle once.

    Returns (player_rows, existing): (1-based sheet row, name) for occupied
    column-A cells, and current B..G values keyed by name. Blank spacer rows
    keep their positions; the scan stops at the run-planner marker.
    """
    fetched = worksheet.get(f"A{DATA_START_ROW}:{_LAST_CHAR_COL}")
    player_rows: list[tuple[int, str]] = []
    existing: dict[str, list[str]] = {}
    for offset, row in enumerate(fetched):
        name = (row[0] if row else "").strip()
        if _is_run_marker(name):
            break
        if not name:
            continue
        player_rows.append((DATA_START_ROW + offset, name))
        existing[name] = list(row[1:]) + [""] * (MAX_CHARS_PER_PLAYER - (len(row) - 1))
    return player_rows, existing


def rewrite_sheet_sorted(
    ws,
    spreadsheet_id: str,
    player_eligibility: dict[str, list[Character]],
    ordered_players: list[str],
    player_rows: list[tuple[int, str]],
    existing: dict[str, list[str]],
    sheets_service: Resource,
) -> None:
    """Rewrite columns A-G for all players in the given order.

    A single full-rectangle overwrite, deliberately with no clear first: a
    network/API failure between a clear and a rewrite used to destroy column A
    (the documented source of truth). Stale rows beyond the new player list
    are blanked by padding the payload instead.

    Works entirely from the pre-read player_rows/existing (see read_tab);
    performs no reads of its own.
    """
    last_occupied = player_rows[-1][0] if player_rows else DATA_START_ROW - 1
    num_rows = max(len(ordered_players), last_occupied - DATA_START_ROW + 1)
    if num_rows == 0:
        return

    rows = []
    for name in ordered_players:
        chars = player_eligibility.get(name)
        if chars is None:
            row = [name] + existing.get(name, [""] * MAX_CHARS_PER_PLAYER)
        else:
            row = [name] + [format_cell(c) for c in chars]
        while len(row) < _ROW_WIDTH:
            row.append("")
        rows.append(row)
    while len(rows) < num_rows:
        rows.append([""] * _ROW_WIDTH)
    # gspread 6: values first, range second (the old order is a deprecated shim).
    # RAW is passed explicitly (scraped names are attacker-controllable); never
    # switch to USER_ENTERED without sanitizing leading = + @.
    ws.update(rows, f"A{DATA_START_ROW}", value_input_option=ValueInputOption.raw)

    rich_text_cells = [
        (DATA_START_ROW - 1 + i, 1 + j, text)
        for i, row in enumerate(rows)
        for j, text in enumerate(row[1:])
        if text
    ]
    _apply_rich_text(sheets_service, spreadsheet_id, ws.id, rich_text_cells)


def update_player_rows(
    ws,
    spreadsheet_id: str,
    player_eligibility: dict[str, list[Character]],
    player_rows: list[tuple[int, str]],
    sheets_service: Resource,
) -> None:
    """Update only B-G for the players in player_eligibility, preserving sheet order.

    player_rows is the tab's pre-read column A (see read_tab); this function
    performs no reads of its own.
    """
    eligibility_lower = {
        name.lower(): chars
        for name, chars in player_eligibility.items()
        if chars is not None
    }
    rows_to_update = [
        (row_num, name)
        for row_num, name in player_rows
        if name.lower() in eligibility_lower
    ]
    if not rows_to_update:
        return

    cell_updates = []
    rich_text_cells: list[tuple[int, int, str]] = []
    for row_num, name in rows_to_update:
        chars = eligibility_lower[name.lower()]
        cells = [format_cell(c) for c in chars]
        while len(cells) < MAX_CHARS_PER_PLAYER:
            cells.append("")
        cell_updates.append(
            {"range": f"B{row_num}:{_LAST_CHAR_COL}{row_num}", "values": [cells]}
        )
        rich_text_cells += [(row_num - 1, 1 + j, format_cell(c)) for j, c in enumerate(chars)]
    # RAW is passed explicitly (scraped names are attacker-controllable); never
    # switch to USER_ENTERED without sanitizing leading = + @.
    ws.batch_update(cell_updates, value_input_option=ValueInputOption.raw)

    _apply_rich_text(sheets_service, spreadsheet_id, ws.id, rich_text_cells)
