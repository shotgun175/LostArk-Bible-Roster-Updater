"""CLI entry point for the Lost Ark roster updater."""
import argparse
import sys

from config import load_overrides, get_threshold_and_cap
from scraper import scrape_roster, filter_and_sort, MAX_CHARS_PER_PLAYER
from sheets import (
    get_spreadsheet,
    get_tab_names,
    get_players_from_sheet,
    sort_players,
    update_sheet,
)

SPREADSHEET_NAME = "BOZO BOZONGOS"


def confirm(prompt: str) -> bool:
    """Prompt the user for yes/no confirmation. Returns True only for exact 'yes'."""
    answer = input(f"{prompt} (yes/no): ").strip().lower()
    return answer == "yes"


def process_player_for_sheet(
    nickname: str,
    character_name: str,
    tab_name: str,
    threshold: int,
    cap: int | None = None,
) -> list:
    """Scrape and filter one player's roster for a specific sheet tab."""
    print(f"Scraping {nickname} ({character_name})...", flush=True, end=" ")

    try:
        all_chars = scrape_roster(character_name)
    except RuntimeError as e:
        print(f"\n{e}")
        return []

    eligible = filter_and_sort(all_chars, threshold, cap)
    total_eligible_before_display_cap = len(
        [c for c in all_chars if c.ilvl >= threshold and (cap is None or c.ilvl <= cap)]
    )

    print(f"{len(all_chars)} characters found, {len(eligible)} eligible for '{tab_name}'")

    if total_eligible_before_display_cap > MAX_CHARS_PER_PLAYER:
        print(
            f"  Warning: {nickname} has {total_eligible_before_display_cap} eligible characters "
            f"for '{tab_name}' but only {MAX_CHARS_PER_PLAYER} will be shown (cap reached)."
        )

    if len(eligible) == 0:
        print(f"  {nickname}: 0 eligible characters for '{tab_name}', skipping.")

    return eligible


def run_update(
    tab_names: list[str],
    player_map: dict[str, str],
    overrides: dict[str, int],
    spreadsheet,
) -> None:
    """Run the full update pipeline for the given tabs and players."""
    for tab_name in tab_names:
        result = get_threshold_and_cap(tab_name, overrides)
        if result is None:
            print(f"Skipping '{tab_name}' — could not parse iLvl threshold from tab name.")
            continue
        threshold, cap = result

        range_label = f"{threshold}–{cap}" if cap is not None else f"{threshold}+"
        print(f"\n--- Updating '{tab_name}' (ilvl: {range_label}) ---")

        player_eligibility: dict[str, list] = {}
        for nickname, character_name in player_map.items():
            eligible = process_player_for_sheet(nickname, character_name, tab_name, threshold, cap)
            player_eligibility[nickname] = eligible

        print("Writing to sheet...", flush=True, end=" ")
        if len(player_map) == 1:
            # Single-player run: update only that player's row in place
            update_sheet(spreadsheet, tab_name, player_eligibility)
        else:
            # Full update: sort by most eligible chars, rewrite A–G
            ordered = sort_players(player_eligibility, priority=[])
            update_sheet(spreadsheet, tab_name, player_eligibility, ordered_players=ordered)
        print("done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Update the '{SPREADSHEET_NAME}' Lost Ark roster Google Sheet."
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Update all sheets for all players.",
    )
    parser.add_argument(
        "--sheet",
        metavar="SHEET_NAME",
        help="Update one specific sheet for all players.",
    )
    parser.add_argument(
        "--player",
        metavar="NICKNAME",
        help="Update sheets for one specific player only.",
    )

    args = parser.parse_args()

    if args.all and (args.sheet or args.player):
        parser.error("--all cannot be combined with --sheet or --player")

    if not args.all and not args.sheet and not args.player:
        parser.print_help()
        sys.exit(1)

    overrides = load_overrides()
    spreadsheet = get_spreadsheet(SPREADSHEET_NAME)
    all_tabs = get_tab_names(spreadsheet)

    # Validate --sheet
    if args.sheet and args.sheet not in all_tabs:
        print(f"Error: Sheet '{args.sheet}' not found in spreadsheet.")
        print(f"Available sheets: {', '.join(all_tabs)}")
        sys.exit(1)

    # Determine target tabs (before reading players so we know which tab to read from)
    target_tabs = [args.sheet] if args.sheet else all_tabs

    # Read player list from the sheet (column A, rows 2+)
    player_names = get_players_from_sheet(spreadsheet.worksheet(target_tabs[0]))

    # Build a case-insensitive lookup: lowercase → actual sheet name
    players_lower = {n.lower(): n for n in player_names}

    if args.player:
        resolved_player = players_lower.get(args.player.lower())
        if resolved_player is None:
            print(f"Error: Player '{args.player}' not found in the sheet.")
            print(f"Known players: {', '.join(player_names)}")
            sys.exit(1)
    else:
        resolved_player = None

    # {char_name: char_name} — column A names are used directly as lostark.bible lookups
    if resolved_player:
        target_players = {resolved_player: resolved_player}
    else:
        target_players = {name: name for name in player_names}

    # Confirmation gates
    if args.all and not args.sheet and not args.player:
        prompt = (
            f"You are about to update all {len(all_tabs)} sheets for all {len(player_names)} players."
        )
        if not confirm(prompt):
            print("Aborted.")
            sys.exit(0)
    elif args.sheet and not args.player:
        prompt = f'You are about to update "{args.sheet}" for {len(player_names)} players.'
        if not confirm(prompt):
            print("Aborted.")
            sys.exit(0)
    elif args.player and not args.sheet:
        prompt = (
            f"You are about to update all {len(all_tabs)} sheets for {resolved_player}."
        )
        if not confirm(prompt):
            print("Aborted.")
            sys.exit(0)
    # --player + --sheet together: no confirmation needed

    run_update(target_tabs, target_players, overrides, spreadsheet)

    print("\nAll done.")


if __name__ == "__main__":
    main()
