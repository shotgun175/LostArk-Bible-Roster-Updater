"""CLI entry point for the Lost Ark roster updater."""
import argparse
import sys

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from playwright.sync_api import Page, sync_playwright

from config import load_config, get_threshold_and_cap
from models import Character
from scraper import (
    MAX_CHARS_PER_PLAYER,
    count_eligible,
    filter_and_sort,
    scrape_roster,
)
from sheets import (
    get_tab_names,
    get_players_from_sheet,
    rewrite_sheet_sorted,
    sort_players,
    update_player_rows,
)

CREDENTIALS_PATH = "credentials.json"
DEFAULT_SPREADSHEET_NAME = "BOZO BOZONGOS"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def confirm(prompt: str) -> bool:
    """Prompt the user for yes/no confirmation. Returns True only for exact 'yes'."""
    return input(f"{prompt} (yes/no): ").strip().lower() == "yes"


def _scrape_all_rosters(
    page: Page, player_names: list[str]
) -> dict[str, list[Character]]:
    """Scrape each player's full roster once. Returns {player: characters}."""
    rosters: dict[str, list[Character]] = {}
    for name in player_names:
        print(f"Scraping {name}...", flush=True, end=" ")
        try:
            chars = scrape_roster(page, name)
            print(f"{len(chars)} characters found")
            rosters[name] = chars
        except RuntimeError as e:
            print(f"\n{e}")
            rosters[name] = []
    return rosters


def _filter_for_tab(
    rosters: dict[str, list[Character]],
    tab_name: str,
    threshold: int,
    cap: int | None,
) -> dict[str, list[Character]]:
    """Apply tab-specific iLvl filtering to every cached roster, with status output."""
    eligibility: dict[str, list[Character]] = {}
    for name, all_chars in rosters.items():
        eligible = filter_and_sort(all_chars, threshold, cap)
        total = count_eligible(all_chars, threshold, cap)
        eligibility[name] = eligible

        if not eligible:
            print(f"  {name}: 0 eligible characters for '{tab_name}', skipping.")
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
    spreadsheet,
    sheets_service,
    tab_names: list[str],
    player_names: list[str],
    overrides: dict,
    priority_players: list[str],
) -> None:
    """Run the full update pipeline for the given tabs and players.

    Scrapes each player's roster once (regardless of tab count), then filters
    per tab from the cached roster.
    """
    rosters = _scrape_all_rosters(page, player_names)

    for tab_name in tab_names:
        result = get_threshold_and_cap(tab_name, overrides)
        if result is None:
            print(f"Skipping '{tab_name}' — could not parse iLvl threshold from tab name.")
            continue
        threshold, cap = result

        range_label = f"{threshold}–{cap}" if cap is not None else f"{threshold}+"
        print(f"\n--- Updating '{tab_name}' (ilvl: {range_label}) ---")

        player_eligibility = _filter_for_tab(rosters, tab_name, threshold, cap)

        print("Writing to sheet...", flush=True, end=" ")
        if len(player_names) == 1:
            update_player_rows(spreadsheet, tab_name, player_eligibility, sheets_service)
        else:
            ordered = sort_players(player_eligibility, priority=priority_players)
            rewrite_sheet_sorted(
                spreadsheet, tab_name, player_eligibility, ordered, sheets_service
            )
        print("done.")


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

    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    spreadsheet = gspread.authorize(creds).open(spreadsheet_name)
    sheets_service = build("sheets", "v4", credentials=creds)
    all_tabs = get_tab_names(spreadsheet)

    if args.sheet and args.sheet not in all_tabs:
        print(f"Error: Sheet '{args.sheet}' not found in spreadsheet.")
        print(f"Available sheets: {', '.join(all_tabs)}")
        sys.exit(1)

    target_tabs = [args.sheet] if args.sheet else all_tabs

    sheet_player_names = get_players_from_sheet(spreadsheet.worksheet(target_tabs[0]))
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
            run_update(
                page=page,
                spreadsheet=spreadsheet,
                sheets_service=sheets_service,
                tab_names=target_tabs,
                player_names=target_players,
                overrides=overrides,
                priority_players=priority_players,
            )
        finally:
            browser.close()

    print("\nAll done.")


if __name__ == "__main__":
    main()
