"""Google Sheets read/write for the Lost Ark roster updater."""
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

from models import Character

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]
PRIORITY_PLAYERS = ["Valluru", "Mabi", "Remi"]
DATA_START_ROW = 3      # Row 1 = title, row 2 = headers, row 3+ = player data

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
    spreadsheet_id: str,
    sheet_id: int,
    cell_positions: list[tuple[int, int, str]],
    credentials_path: str,
) -> None:
    """Apply per-character color formatting to a list of (row_0, col_0, text) cells."""
    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    requests = [
        {
            "updateCells": {
                "rows": [{"values": [{"textFormatRuns": _text_format_runs(text)}]}],
                "fields": "textFormatRuns",
                "start": {"sheetId": sheet_id, "rowIndex": row_0, "columnIndex": col_0},
            }
        }
        for row_0, col_0, text in cell_positions
        if text and _text_format_runs(text)
    ]
    if requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()


def format_cell(character: Character) -> str:
    """Format a character as a multi-line cell string."""
    return f"{character.name} | {character.ilvl}\n{character.char_class} | {round(character.cp)}"


def sort_players(
    player_eligibility: dict[str, list[Character]],
    priority: list[str] = PRIORITY_PLAYERS,
) -> list[str]:
    """
    Return player nicknames in display order.
    Priority players come first (in given order), then remaining players
    sorted by eligible character count descending, tie-broken by sum of CP
    across all eligible characters descending.
    """
    all_nicknames = list(player_eligibility.keys())
    priority_present = [p for p in priority if p in all_nicknames]
    rest = [p for p in all_nicknames if p not in priority]

    def sort_key(nickname: str) -> tuple[int, float]:
        chars = player_eligibility[nickname]
        count = len(chars)
        total_cp = sum(c.cp for c in chars)
        return (-count, -total_cp)

    rest.sort(key=sort_key)
    return priority_present + rest


def get_players_from_sheet(worksheet) -> list[str]:
    """Return character names from column A (rows 3 onward).

    Stops at the first cell containing 'Run' (the scheduling section marker),
    so the player list and the run schedule can coexist in the same column.
    """
    players = []
    for v in worksheet.col_values(1)[2:]:   # skip title (row 1) and headers (row 2)
        stripped = v.strip()
        if stripped.lower() == "run":
            break
        if stripped:
            players.append(stripped)
    return players


def get_spreadsheet(spreadsheet_name: str, credentials_path: str = "credentials.json"):
    """Open the named spreadsheet using the service account credentials."""
    creds = Credentials.from_service_account_file(credentials_path, scopes=SCOPES)
    gc = gspread.authorize(creds)
    return gc.open(spreadsheet_name)


def get_tab_names(spreadsheet) -> list[str]:
    """Return all worksheet tab names in the spreadsheet."""
    return [ws.title for ws in spreadsheet.worksheets()]


def update_sheet(
    spreadsheet,
    tab_name: str,
    player_eligibility: dict[str, list[Character]],
    ordered_players: list[str] | None = None,
    credentials_path: str = "credentials.json",
) -> None:
    """
    Write roster data to the sheet.

    Full update (ordered_players provided): rewrites A–G for all players in
    sorted order. Column A is updated to reflect the new ranking.

    Partial update (ordered_players omitted): finds each player's current row
    in column A and updates only their B–G cells. Used for single-player runs.
    """
    ws = spreadsheet.worksheet(tab_name)

    if ordered_players is not None:
        # Full sorted rewrite — clear from DATA_START_ROW to cover existing + new data
        current_names = get_players_from_sheet(ws)
        num_rows = max(len(ordered_players), len(current_names))
        if num_rows == 0:
            return
        last_row = DATA_START_ROW + num_rows - 1
        ws.batch_clear([f"A{DATA_START_ROW}:G{last_row}"])
        rows = []
        for name in ordered_players:
            chars = player_eligibility.get(name, [])
            row = [name] + [format_cell(c) for c in chars]
            while len(row) < 7:   # A + B–G = 7 columns
                row.append("")
            rows.append(row)
        ws.update(f"A{DATA_START_ROW}", rows)
        rich_text_cells = [
            (DATA_START_ROW - 1 + i, 1 + j, format_cell(c))
            for i, name in enumerate(ordered_players)
            for j, c in enumerate(player_eligibility.get(name, []))
        ]
    else:
        # Partial update — only touch rows for players in player_eligibility
        player_names = get_players_from_sheet(ws)
        rows_to_update = [
            (DATA_START_ROW + i, name)
            for i, name in enumerate(player_names)
            if name in player_eligibility
        ]
        if not rows_to_update:
            return
        ws.batch_clear([f"B{row}:G{row}" for row, _ in rows_to_update])
        cell_updates = []
        rich_text_cells = []
        for row_num, name in rows_to_update:
            chars = player_eligibility[name]
            cells = [format_cell(c) for c in chars]
            while len(cells) < 6:
                cells.append("")
            cell_updates.append({"range": f"B{row_num}:G{row_num}", "values": [cells]})
            rich_text_cells += [(row_num - 1, 1 + j, format_cell(c)) for j, c in enumerate(chars)]
        ws.batch_update(cell_updates)

    _apply_rich_text(spreadsheet.id, ws.id, rich_text_cells, credentials_path)
