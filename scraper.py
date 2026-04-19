"""Scrape character rosters from lostark.bible."""
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

from class_map import get_class_from_name
from models import Character

MAX_CHARS_PER_PLAYER = 6
BASE_URL = "https://lostark.bible/character/NA/{}/roster"
TIMEOUT_MS = 30_000


def _parse_roster_entry(entry: dict) -> Character | None:
    """Build a Character from a roster JSON entry. Returns None if data is missing."""
    try:
        name = entry["name"]
        if not name:
            return None
        kr_class = entry["class"]
        ilvl = int(entry["ilvl"])  # truncate float: 1730.8334 → 1730
        cp_data = entry.get("combatPower") or {}
        cp = float(cp_data.get("score", 0.0))
        char_class = get_class_from_name(kr_class)
        return Character(name=name, ilvl=ilvl, cp=cp, char_class=char_class)
    except (KeyError, TypeError, ValueError):
        return None


def scrape_roster(character_name: str) -> list[Character]:
    """
    Scrape full roster from lostark.bible for the given character name.
    Raises RuntimeError with a user-facing message if character page not found.
    Returns empty list on timeout or if page is unresponsive.
    """
    url = BASE_URL.format(character_name)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            response = page.goto(url, timeout=TIMEOUT_MS)

            if response and response.status == 404:
                raise RuntimeError(
                    f"Error: Could not find roster for '{character_name}' — check players.json"
                )

            page.wait_for_load_state("networkidle", timeout=TIMEOUT_MS)

            # Extract the roster array from the inline SvelteKit <script> tag.
            # lostark.bible embeds page data as a JS literal in kit.start(..., { data: [...] })
            # inside an inline <script>.  The roster array uses unquoted JS object keys,
            # so we locate it by bracket-depth counting and evaluate it in the page context.
            roster_entries: list[dict] = page.evaluate("""
            () => {
                const scripts = document.querySelectorAll('script');
                for (const s of scripts) {
                    const text = s.textContent;
                    const rosterMatch = text.match(/roster\\s*:\\s*\\[/);
                    if (!rosterMatch) continue;
                    const rosterStart = rosterMatch.index + rosterMatch[0].length - 1;
                    let depth = 0;
                    let i = rosterStart;
                    for (; i < text.length; i++) {
                        const ch = text[i];
                        if (ch === '[' || ch === '{') depth++;
                        else if (ch === ']' || ch === '}') {
                            depth--;
                            if (depth === 0) break;
                        }
                    }
                    if (depth !== 0) return [];
                    const literal = text.slice(rosterStart, i + 1);
                    return (new Function('return ' + literal))();
                }
                return [];
            }
            """)

            if not roster_entries:
                raise RuntimeError(
                    f"Error: Could not find roster for '{character_name}' — "
                    "page loaded but returned no characters. Check players.json."
                )

            return [c for entry in roster_entries if (c := _parse_roster_entry(entry)) is not None]

        except (PlaywrightTimeoutError, PlaywrightError):
            print(f"Warning: Failed to load roster for '{character_name}' — skipping.")
            return []
        finally:
            browser.close()


def filter_and_sort(
    characters: list[Character],
    threshold: int,
    cap: int | None = None,
) -> list[Character]:
    """Filter by iLvl threshold (and optional cap), sort by iLvl desc then CP desc, cap at 6."""
    eligible = [c for c in characters if c.ilvl >= threshold and (cap is None or c.ilvl <= cap)]
    eligible.sort(key=lambda c: (c.ilvl, c.cp), reverse=True)
    return eligible[:MAX_CHARS_PER_PLAYER]
