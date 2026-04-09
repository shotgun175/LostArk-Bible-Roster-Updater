"""Load config.json and parse iLvl thresholds from sheet tab names."""
import json
import re
from pathlib import Path


def load_overrides(path: str = "config.json") -> dict[str, int]:
    # Values in "overrides" must be integers (e.g. 1750, not "1750").
    config_path = Path(path)
    if not config_path.exists():
        return {}
    with open(config_path) as f:
        data = json.load(f)
    return data.get("overrides", {})


def parse_threshold_from_tab(tab_name: str) -> int | None:
    # Anchor to end-of-string so "(1740+)" only matches at the end of the tab name.
    match = re.search(r'\((\d+)\+\)$', tab_name)
    if match:
        return int(match.group(1))
    return None


def get_threshold(tab_name: str, overrides: dict[str, int]) -> int | None:
    if tab_name in overrides:
        return overrides[tab_name]
    return parse_threshold_from_tab(tab_name)
