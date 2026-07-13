"""Load config.json and parse iLvl thresholds from sheet tab names."""
import json
import re
import sys
from pathlib import Path

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def load_config(path: str | None = None) -> dict:
    """Read config.json (UTF-8, BOM tolerated). Returns {} when missing.

    Defaults to the config.json next to this file so the tool works from any
    working directory. Exits with an actionable message on malformed JSON or
    a non-UTF-8 save instead of dumping a traceback.

    Recognized top-level keys:
      - "spreadsheet_name": str - name of the Google Sheet to update
      - "priority_players": list[str] - players that always appear at the top
      - "overrides":        dict   - per-tab iLvl threshold/cap overrides
    """
    config_path = Path(path) if path is not None else _CONFIG_PATH
    if not config_path.exists():
        return {}
    try:
        with open(config_path, encoding="utf-8-sig") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(
            f"Error: {config_path.name} is not valid JSON "
            f"(line {e.lineno}, column {e.colno}). Fix it and re-run."
        )
        sys.exit(1)
    except UnicodeDecodeError:
        print(
            f"Error: {config_path.name} is not valid UTF-8. Re-save it with "
            "UTF-8 encoding (Notepad: Save As, Encoding: UTF-8)."
        )
        sys.exit(1)


def parse_threshold_from_tab(tab_name: str) -> int | None:
    # Anchor to end-of-string so "(1740+)" only matches at the end of the tab name.
    match = re.search(r'\((\d+)\+\)$', tab_name)
    if match:
        return int(match.group(1))
    return None


def get_threshold_and_cap(tab_name: str, overrides: dict) -> tuple[int, int | None] | None:
    """Return (threshold, cap) for a tab. cap is None when uncapped.

    Override format in config.json:
      "Tab Name": 1750                          -> threshold=1750, cap=None
      "Tab Name": {"threshold": 1750}           -> threshold=1750, cap=None
      "Tab Name": {"threshold": 1750, "cap": 1800} -> threshold=1750, cap=1800
    """
    if tab_name in overrides:
        value = overrides[tab_name]
        if isinstance(value, int):
            return (value, None)
        if isinstance(value, dict):
            threshold = value.get("threshold")
            if not isinstance(threshold, int):
                return None
            cap = value.get("cap")  # None if key absent or explicitly null
            return (threshold, cap if isinstance(cap, int) else None)
        return None
    threshold = parse_threshold_from_tab(tab_name)
    if threshold is None:
        return None
    return (threshold, None)
