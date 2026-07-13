"""CLI entry point for the Lost Ark roster updater."""
import argparse
import sys
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from playwright.sync_api import Page, sync_playwright

from config import load_config, get_threshold_and_cap
from models import Character
from scraper import (
    MAX_CHARS_PER_PLAYER,
    ScrapeFailedError,
    count_eligible,
    filter_and_sort,
    scrape_roster,
)
from sheets import (
    read_tab,
    rewrite_sheet_sorted,
    sort_players,
    update_player_rows,
)

CREDENTIALS_PATH = str(Path(__file__).resolve().parent / "credentials.json")
DEFAULT_SPREADSHEET_NAME = "Your Spreadsheet Name"  # override via config.json
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def confirm(prompt: str) -> bool:
    """Prompt the user for yes/no confirmation. Returns True only for exact 'yes'."""
    return input(f"{prompt} (yes/no): ").strip().lower() == "yes"


def _open_spreadsheet(spreadsheet_name: str):
    """Authorize and open the spreadsheet.

    Translates the two common first-run failures into actionable messages
    instead of raw tracebacks in the launcher's console window.
    """
    try:
        creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    except FileNotFoundError:
        print(
            f"Error: '{CREDENTIALS_PATH}' not found. Create a Google Cloud "
            "service-account key and save it next to main.py as "
            f"'{CREDENTIALS_PATH}' — see the README's Google Cloud setup steps."
        )
        sys.exit(1)
    try:
        spreadsheet = gspread.authorize(creds).open(spreadsheet_name)
    except gspread.SpreadsheetNotFound:
        print(
            f"Error: spreadsheet '{spreadsheet_name}' was not found. Check "
            "spreadsheet_name in config.json, and make sure the sheet is "
            "shared (Editor) with the service account's client_email from "
            f"'{CREDENTIALS_PATH}' — see the README."
        )
        sys.exit(1)
    return creds, spreadsheet


def _scrape_all_rosters(
    page: Page, player_names: list[str]
) -> dict[str, list[Character] | None]:
    """Scrape each player's full roster once. Returns {player: characters}.

    None marks a failed scrape: downstream writers must preserve that
    player's existing sheet cells instead of blanking them.
    """
    rosters: dict[str, list[Character] | None] = {}
    for name in player_names:
        print(f"Scraping {name}...", flush=True, end=" ")
        try:
            chars = scrape_roster(page, name)
            print(f"{len(chars)} characters found")
            rosters[name] = chars
        except RuntimeError as e:
            print(f"\n{e}")
            rosters[name] = None
    return rosters


def _filter_for_tab(
    rosters: dict[str, list[Character] | None],
    tab_name: str,
    threshold: int,
    cap: int | None,
) -> dict[str, list[Character] | None]:
    """Apply tab-specific iLvl filtering to every cached roster, with status output."""
    eligibility: dict[str, list[Character] | None] = {}
    for name, all_chars in rosters.items():
        if all_chars is None:
            eligibility[name] = None
            print(f"  {name}: scrape FAILED - existing sheet data preserved.")
            continue
        eligible = filter_and_sort(all_chars, threshold, cap)
        total = count_eligible(all_chars, threshold, cap)
        eligibility[name] = eligible

        if not eligible:
            print(f"  {name}: 0 eligible characters for '{tab_name}'.")
        else:
            print(f"  {name}: {len(eligible)} eligible")
        if total > MAX_CHARS_PER_PLAYER:
            print(
                f"    Warning: {name} has {total} eligible characters "
                f"for '{tab_name}' but only {MAX_CHARS_PER_PLAYER} will be shown."
            )
    return eligibility


def run_update(
    page: Page,
    sheets_service,
    spreadsheet_id: str,
    tabs: dict[str, tuple],
    player_names: list[str],
    overrides: dict,
    priority_players: list[str],
    single_player: bool,
) -> list[str]:
    """Run the full update pipeline for the given tabs and players.

    Scrapes each player's roster once (regardless of tab count), then filters
    per tab from the cached roster. tabs maps each tab name to its pre-read
    (worksheet, player_rows, existing) triple (see sheets.read_tab): each tab
    is written against its OWN column-A player list, and neither this function
    nor the writers read from the worksheet again.

    Returns the names whose scrape failed (their sheet rows were preserved).
    """
    rosters = _scrape_all_rosters(page, player_names)
    failed_players = [n for n in player_names if rosters[n] is None]

    for tab_name, (ws, player_rows, existing) in tabs.items():
        result = get_threshold_and_cap(tab_name, overrides)
        if result is None:
            print(f"Skipping '{tab_name}' — could not parse iLvl threshold from tab name.")
            continue
        threshold, cap = result

        range_label = f"{threshold}–{cap}" if cap is not None else f"{threshold}+"
        print(f"\n--- Updating '{tab_name}' (ilvl: {range_label}) ---")

        print_eligibility_for = rosters
        if not single_player:
            # An empty player_rows means the tab's column A is empty: write
            # nothing there (rewrite no-ops on zero rows) rather than falling
            # back to the union and populating a deliberately empty tab.
            tab_list = [n for _, n in player_rows]
            print_eligibility_for = {n: rosters.get(n, []) for n in tab_list}
        player_eligibility = _filter_for_tab(print_eligibility_for, tab_name, threshold, cap)

        print("Writing to sheet...", flush=True, end=" ")
        if single_player:
            update_player_rows(
                ws, spreadsheet_id, player_eligibility, player_rows, sheets_service
            )
        else:
            ordered = sort_players(player_eligibility, priority=priority_players)
            rewrite_sheet_sorted(
                ws, spreadsheet_id, player_eligibility, ordered,
                player_rows, existing, sheets_service,
            )
        print("done.")

    return failed_players


def _build_confirmation_prompt(
    args: argparse.Namespace,
    all_tabs: list[str],
    player_names: list[str],
    resolved_player: str | None,
) -> str | None:
    """Return the confirmation prompt string, or None if no confirmation is needed."""
    if args.player and args.sheet:
        return None
    if args.all:
        return f"You are about to update all {len(all_tabs)} sheets for all {len(player_names)} players."
    if args.sheet:
        return f'You are about to update "{args.sheet}" for {len(player_names)} players.'
    if args.player:
        return f"You are about to update all {len(all_tabs)} sheets for {resolved_player}."
    return None


def main() -> None:
    config = load_config()
    spreadsheet_name = config.get("spreadsheet_name", DEFAULT_SPREADSHEET_NAME)
    priority_players = config.get("priority_players", [])
    overrides = config.get("overrides", {})

    parser = argparse.ArgumentParser(
        description=f"Update the '{spreadsheet_name}' Lost Ark roster Google Sheet."
    )
    parser.add_argument("--all", action="store_true", help="Update all sheets for all players.")
    parser.add_argument("--sheet", metavar="SHEET_NAME", help="Update one specific sheet for all players.")
    parser.add_argument("--player", metavar="NICKNAME", help="Update sheets for one specific player only.")
    args = parser.parse_args()

    if args.all and (args.sheet or args.player):
        parser.error("--all cannot be combined with --sheet or --player")
    if not args.all and not args.sheet and not args.player:
        parser.print_help()
        sys.exit(1)

    creds, spreadsheet = _open_spreadsheet(spreadsheet_name)
    sheets_service = build("sheets", "v4", credentials=creds)
    all_worksheets = spreadsheet.worksheets()
    all_tabs = [ws.title for ws in all_worksheets]
    ws_by_title = {ws.title: ws for ws in all_worksheets}

    if args.sheet and args.sheet not in all_tabs:
        print(f"Error: Sheet '{args.sheet}' not found in spreadsheet.")
        print(f"Available sheets: {', '.join(all_tabs)}")
        sys.exit(1)

    target_tabs = [args.sheet] if args.sheet else all_tabs

    # Each tab's column A is its own source of truth; read each tab exactly
    # once here and scrape the union so every tab can be written against its
    # own list without any further reads.
    tabs = {tab: (ws_by_title[tab], *read_tab(ws_by_title[tab])) for tab in target_tabs}
    tab_player_lists = {tab: [n for _, n in tabs[tab][1]] for tab in target_tabs}
    sheet_player_names = list(
        dict.fromkeys(n for tab in target_tabs for n in tab_player_lists[tab])
    )
    players_lower = {n.lower(): n for n in sheet_player_names}

    resolved_player = None
    if args.player:
        resolved_player = players_lower.get(args.player.lower())
        if resolved_player is None:
            print(f"Error: Player '{args.player}' not found in the sheet.")
            print(f"Known players: {', '.join(sheet_player_names)}")
            sys.exit(1)

    target_players = [resolved_player] if resolved_player else sheet_player_names

    prompt = _build_confirmation_prompt(args, all_tabs, sheet_player_names, resolved_player)
    if prompt and not confirm(prompt):
        print("Aborted.")
        sys.exit(0)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            failed = run_update(
                page=page,
                sheets_service=sheets_service,
                spreadsheet_id=spreadsheet.id,
                tabs=tabs,
                player_names=target_players,
                overrides=overrides,
                priority_players=priority_players,
                single_player=resolved_player is not None,
            )
        finally:
            browser.close()

    if failed:
        print(
            f"\nDone with {len(failed)} scrape failure(s): {', '.join(failed)}. "
            "Their sheet rows were left unchanged."
        )
        sys.exit(1)
    print("\nAll done.")


if __name__ == "__main__":
    main()
