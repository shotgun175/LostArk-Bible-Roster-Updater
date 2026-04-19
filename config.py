"""Load config.json and parse iLvl thresholds from sheet tab names."""
import json
import re
from pathlib import Path


def load_overrides(path: str = "config.json") -> dict:
    # Override values may be:
    #   - an int (threshold only, no cap), e.g. 1750
    #   - an object with "threshold" and optional "cap", e.g. {"threshold": 1750, "cap": 1800}
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


def get_threshold_and_cap(tab_name: str, overrides: dict) -> tuple[int, int | None] | None:
    """Return (threshold, cap) for a tab. cap is None when uncapped.

    Override format in config.json:
      "Tab Name": 1750                          → threshold=1750, cap=None
      "Tab Name": {"threshold": 1750}           → threshold=1750, cap=None
      "Tab Name": {"threshold": 1750, "cap": 1800} → threshold=1750, cap=1800
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
