import pytest
from pathlib import Path

import config as config_module
from config import load_config, parse_threshold_from_tab, get_threshold_and_cap


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


# --- load_config ---

def test_load_config_missing_file(tmp_path):
    assert load_config(str(tmp_path / "nope.json")) == {}


def test_load_config_reads_utf8_accented_names(tmp_path):
    p = tmp_path / "config.json"
    p.write_text('{"priority_players": ["Remiyà"]}', encoding="utf-8")
    assert load_config(str(p))["priority_players"] == ["Remiyà"]


def test_load_config_accepts_utf8_bom(tmp_path):
    p = tmp_path / "config.json"
    p.write_bytes(b'\xef\xbb\xbf{"spreadsheet_name": "X"}')
    assert load_config(str(p)) == {"spreadsheet_name": "X"}


def test_load_config_malformed_json_exits_friendly(tmp_path, capsys):
    p = tmp_path / "config.json"
    p.write_text('{"a": 1,}', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        load_config(str(p))
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "config.json" in out and "line" in out


def test_load_config_non_utf8_exits_friendly(tmp_path, capsys):
    p = tmp_path / "config.json"
    p.write_bytes('{"n": "Remià"}'.encode("cp1252"))
    with pytest.raises(SystemExit) as exc:
        load_config(str(p))
    assert exc.value.code == 1
    assert "UTF-8" in capsys.readouterr().out


def test_default_config_path_is_anchored_next_to_config_py():
    assert config_module._CONFIG_PATH == Path(config_module.__file__).resolve().parent / "config.json"
