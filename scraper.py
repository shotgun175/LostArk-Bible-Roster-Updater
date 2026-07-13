"""Scrape character rosters from lostark.bible."""
import json
import re
import string
import time

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, Error as PlaywrightError

from class_map import get_class_from_name
from models import Character, MAX_CHARS_PER_PLAYER

BASE_URL = "https://lostark.bible/character/NA/{}/roster"
TIMEOUT_MS = 30_000
RETRY_DELAYS_S = (2.0, 5.0)  # backoff before attempt 2 and attempt 3
_RETRYABLE_STATUSES = {429, 503}


class RosterExtractionError(Exception):
    """A roster key was found but the array could not be sliced or parsed.

    Distinct from "the page has no roster" (extract_roster_json returns None):
    this means lostark.bible's inline data format changed and the scraper
    itself needs updating - not a character-name problem.
    """


class ScrapeFailedError(RuntimeError):
    """The roster could not be fetched (timeout, load error, site failure).

    Distinct from a name problem (plain RuntimeError telling the operator to
    check the spelling): callers must preserve the player's existing sheet
    data instead of treating the roster as empty.
    """


_SCRIPT_RE = re.compile(r"<script\b[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
_ROSTER_KEY_RE = re.compile(r"\broster\s*:\s*\[")
_IDENT_START = set(string.ascii_letters + "_$")
_IDENT_CHARS = set(string.ascii_letters + string.digits + "_$")


def _scan_js_array(text: str, start: int) -> str | None:
    """Slice the balanced JS array literal beginning at text[start] == '['.

    String-aware: brackets inside ' " ` literals (with backslash escapes) do
    not affect the depth count - the failure mode of the old in-page scanner.
    Returns None if the array never balances.
    """
    depth = 0
    quote: str | None = None
    i = start
    n = len(text)
    while i < n:
        ch = text[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    return None


def _js_array_to_json(literal: str) -> str:
    """Make the JS array literal JSON-parseable.

    The site emits unquoted object keys ({id:1,name:"X"}); quote them, map a
    bare `undefined` to null, and leave string contents untouched. Anything
    fancier than that simply fails json.loads and surfaces as a
    RosterExtractionError - loud, not silent.
    """
    out: list[str] = []
    quote: str | None = None
    i = 0
    n = len(literal)
    while i < n:
        ch = literal[i]
        if quote is not None:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(literal[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch in _IDENT_START:
            j = i + 1
            while j < n and literal[j] in _IDENT_CHARS:
                j += 1
            ident = literal[i:j]
            k = j
            while k < n and literal[k] in " \t\r\n":
                k += 1
            if k < n and literal[k] == ":":
                out.append(f'"{ident}"')
            elif ident == "undefined":
                out.append("null")
            elif ident == "void" and k < n and literal[k] == "0":
                # The site's minifier emits `void 0` for undefined values.
                out.append("null")
                j = k + 1
            else:
                out.append(ident)
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def extract_roster_json(html: str) -> list[dict] | None:
    """Extract the roster array from a lostark.bible page's inline script.

    Returns the parsed list of roster entries, or None when no roster key
    exists anywhere in the page (no roster / wrong page). Raises
    RosterExtractionError when a roster key exists but no candidate can be
    sliced and parsed (site layout change).
    """
    found_key = False
    for script_match in _SCRIPT_RE.finditer(html):
        text = script_match.group(1)
        for key_match in _ROSTER_KEY_RE.finditer(text):
            found_key = True
            literal = _scan_js_array(text, key_match.end() - 1)
            if literal is None:
                continue
            try:
                parsed = json.loads(_js_array_to_json(literal))
            except ValueError:
                continue
            if isinstance(parsed, list):
                return parsed
    if found_key:
        raise RosterExtractionError(
            "found a roster key but could not parse the array - the site's "
            "inline data format may have changed"
        )
    return None


def _parse_roster_entry(entry: dict) -> Character | None:
    """Build a Character from a roster JSON entry. Returns None if data is missing."""
    try:
        name = entry["name"]
        if not name:
            return None
        kr_class = entry["class"]
        ilvl = int(entry["ilvl"])  # truncate float: 1730.8334 -> 1730
        cp_data = entry.get("combatPower") or {}
        cp = float(cp_data.get("score", 0.0))
        char_class = get_class_from_name(kr_class)
        return Character(name=name, ilvl=ilvl, cp=cp, char_class=char_class)
    except (KeyError, TypeError, ValueError):
        return None


def _parse_entries(roster_entries: list, character_name: str) -> list[Character]:
    """Parse raw roster entries, warning per unparseable entry.

    Nameless placeholder entries are skipped silently (expected site noise).
    Raises ScrapeFailedError when a non-empty list yields zero characters:
    that is field-level site drift, not a name problem, and must be loud.
    """
    characters: list[Character] = []
    for idx, entry in enumerate(roster_entries):
        char = _parse_roster_entry(entry)
        if char is not None:
            characters.append(char)
            continue
        if isinstance(entry, dict) and not entry.get("name"):
            continue
        label = (isinstance(entry, dict) and entry.get("name")) or f"entry #{idx + 1}"
        print(
            f"Warning: skipping unparseable roster entry ({label}) "
            f"for '{character_name}'."
        )
    if roster_entries and not characters:
        raise ScrapeFailedError(
            f"Error: none of the {len(roster_entries)} roster entries for "
            f"'{character_name}' could be parsed - the site's data format "
            "may have changed. Keeping their existing sheet data."
        )
    return characters


def _goto_with_retry(page: Page, url: str):
    """page.goto with bounded retries on load errors and 429/503 responses."""
    attempts = 1 + len(RETRY_DELAYS_S)
    last_exc: Exception | None = None
    for i in range(attempts):
        if i:
            time.sleep(RETRY_DELAYS_S[i - 1])
        try:
            response = page.goto(url, timeout=TIMEOUT_MS)
        except (PlaywrightTimeoutError, PlaywrightError) as exc:
            last_exc = exc
            continue
        if response and response.status in _RETRYABLE_STATUSES and i < attempts - 1:
            continue
        return response
    raise last_exc


def scrape_roster(page: Page, character_name: str) -> list[Character]:
    """
    Scrape full roster from lostark.bible for the given character name.
    Raises RuntimeError with a user-facing message if character page not found.
    Raises ScrapeFailedError on timeout or load error (caller preserves sheet data).

    Caller owns the Playwright Page lifecycle so a single browser can be
    reused across many scrapes.
    """
    url = BASE_URL.format(character_name)
    try:
        response = _goto_with_retry(page, url)

        if response and response.status == 404:
            raise RuntimeError(
                f"Error: Could not find roster for '{character_name}' on lostark.bible — "
                "check the character name/spelling in the Google Sheet."
            )

        if response and not response.ok and response.status != 404:
            raise ScrapeFailedError(
                f"Error: lostark.bible returned HTTP {response.status} for "
                f"'{character_name}' - a site problem, not a name problem. "
                "Keeping their existing sheet data."
            )

        # The roster array ships in the initial document's inline SvelteKit
        # hydration <script> (verified against the live site 2026-06-11), so
        # there is nothing to wait for after goto and no need to run JS in the
        # page: extract from the raw response HTML, unit-testable in Python.
        html = response.text() if response else page.content()
        try:
            roster_entries = extract_roster_json(html)
        except RosterExtractionError as exc:
            raise RuntimeError(
                f"Error: Failed to extract the roster for '{character_name}' - "
                f"{exc}. This is a scraper/site-layout problem, not a "
                "character-name problem."
            ) from exc

        if not roster_entries:
            raise RuntimeError(
                f"Error: Could not find roster for '{character_name}' — "
                "page loaded but returned no characters. Check the character "
                "name/spelling in the Google Sheet."
            )

        return _parse_entries(roster_entries, character_name)

    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        raise ScrapeFailedError(
            f"Warning: Failed to load roster for '{character_name}' - "
            "keeping their existing sheet data."
        ) from exc


def count_eligible(characters: list[Character], threshold: int, cap: int | None) -> int:
    """Total characters meeting the iLvl threshold (and optional cap), pre-display-cap."""
    return sum(1 for c in characters if c.ilvl >= threshold and (cap is None or c.ilvl <= cap))


def filter_and_sort(
    characters: list[Character],
    threshold: int,
    cap: int | None = None,
) -> list[Character]:
    """Filter by iLvl threshold (and optional cap), sort by iLvl desc then CP desc, cap at 6."""
    eligible = [c for c in characters if c.ilvl >= threshold and (cap is None or c.ilvl <= cap)]
    eligible.sort(key=lambda c: (c.ilvl, c.cp), reverse=True)
    return eligible[:MAX_CHARS_PER_PLAYER]
