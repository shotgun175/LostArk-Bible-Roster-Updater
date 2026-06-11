"""Tests for the KR -> English class mapping fallback behavior."""
from class_map import get_class_from_name


def test_known_class_maps_silently(capsys):
    assert get_class_from_name("bard") == "Bard"
    assert capsys.readouterr().out == ""


def test_unknown_class_warns_and_returns_unknown(capsys):
    assert get_class_from_name("brand_new_kr_class") == "Unknown"
    out = capsys.readouterr().out
    assert "brand_new_kr_class" in out
    assert "class_map.py" in out
