import pytest
from pathlib import Path
from config import load_overrides, parse_threshold_from_tab, get_threshold_and_cap


def test_parse_threshold_standard():
    assert parse_threshold_from_tab("Nightmare Serca (1740+)") == 1740


def test_parse_threshold_different_value():
    assert parse_threshold_from_tab("Hard Brel (1490+)") == 1490


def test_parse_threshold_no_match():
    assert parse_threshold_from_tab("Random Sheet Name") is None


def test_parse_threshold_anchored_to_end():
    # "(1234+) Prefix" should not match since the number is not at end
    assert parse_threshold_from_tab("(1234+) Some Prefix") is None


# --- get_threshold_and_cap ---

def test_get_threshold_and_cap_uses_int_override():
    overrides = {"Nightmare Serca (1740+)": 1750}
    assert get_threshold_and_cap("Nightmare Serca (1740+)", overrides) == (1750, None)


def test_get_threshold_and_cap_uses_object_override_threshold_only():
    overrides = {"Nightmare Serca (1740+)": {"threshold": 1750}}
    assert get_threshold_and_cap("Nightmare Serca (1740+)", overrides) == (1750, None)


def test_get_threshold_and_cap_uses_object_override_with_cap():
    overrides = {"Nightmare Serca (1740+)": {"threshold": 1750, "cap": 1800}}
    assert get_threshold_and_cap("Nightmare Serca (1740+)", overrides) == (1750, 1800)


def test_get_threshold_and_cap_parses_tab_when_no_override():
    assert get_threshold_and_cap("Nightmare Serca (1740+)", {}) == (1740, None)


def test_get_threshold_and_cap_returns_none_for_unrecognized_tab():
    assert get_threshold_and_cap("Random Sheet Name", {}) is None


def test_get_threshold_and_cap_cap_null_in_object():
    # Explicitly setting cap to null in JSON should be treated as uncapped
    overrides = {"Tab": {"threshold": 1600, "cap": None}}
    assert get_threshold_and_cap("Tab", overrides) == (1600, None)


# --- load_overrides ---

def test_load_overrides_missing_file(tmp_path):
    result = load_overrides(str(tmp_path / "nonexistent.json"))
    assert result == {}


def test_load_overrides_with_int_value(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"overrides": {"Nightmare Serca (1740+)": 1750}}')
    result = load_overrides(str(config_file))
    assert result == {"Nightmare Serca (1740+)": 1750}


def test_load_overrides_with_object_value(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"overrides": {"Tab": {"threshold": 1750, "cap": 1800}}}')
    result = load_overrides(str(config_file))
    assert result == {"Tab": {"threshold": 1750, "cap": 1800}}


def test_load_overrides_empty_overrides(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"overrides": {}}')
    result = load_overrides(str(config_file))
    assert result == {}
