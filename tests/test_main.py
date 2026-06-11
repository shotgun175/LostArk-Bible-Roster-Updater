"""Tests for main.py: per-tab player lists under --all, friendly setup errors."""
from unittest.mock import MagicMock

import pytest

import main
from models import Character


def make_char(name: str = "Char", ilvl: int = 1750) -> Character:
    return Character(name=name, ilvl=ilvl, cp=5000.0, char_class="Bard")


def test_run_update_uses_each_tabs_own_player_list(monkeypatch):
    """--all used to take tab 0's column A and rewrite every tab with it,
    silently clobbering tabs whose player lists differ."""
    scraped: dict[str, list[Character]] = {
        "Alice": [make_char("A1", 1760)],
        "Bob": [make_char("B1", 1760)],
        "Carol": [make_char("C1", 1760)],
    }
    monkeypatch.setattr(main, "scrape_roster", lambda page, name: scraped[name])

    rewrites: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(
        main,
        "rewrite_sheet_sorted",
        lambda spreadsheet, tab, eligibility, ordered, svc: rewrites.append(
            (tab, sorted(eligibility.keys()))
        ),
    )

    main.run_update(
        page=None,
        spreadsheet=MagicMock(),
        sheets_service=MagicMock(),
        tab_names=["Hard (1700+)", "Soft (1750+)"],
        player_names=["Alice", "Bob", "Carol"],  # union across tabs
        overrides={},
        priority_players=[],
        tab_player_lists={
            "Hard (1700+)": ["Alice", "Bob"],
            "Soft (1750+)": ["Bob", "Carol"],
        },
    )

    assert rewrites == [
        ("Hard (1700+)", ["Alice", "Bob"]),
        ("Soft (1750+)", ["Bob", "Carol"]),
    ]


def test_open_spreadsheet_missing_credentials_is_friendly(monkeypatch, capsys):
    def raise_missing(*args, **kwargs):
        raise FileNotFoundError("credentials.json")

    monkeypatch.setattr(main.Credentials, "from_service_account_file", raise_missing)
    with pytest.raises(SystemExit) as exc:
        main._open_spreadsheet("Some Sheet")
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "credentials.json" in out
    assert "service" in out.lower()


def test_open_spreadsheet_unshared_sheet_is_friendly(monkeypatch, capsys):
    monkeypatch.setattr(
        main.Credentials, "from_service_account_file", lambda *a, **k: MagicMock()
    )

    client = MagicMock()
    client.open.side_effect = main.gspread.SpreadsheetNotFound("nope")
    monkeypatch.setattr(main.gspread, "authorize", lambda creds: client)

    with pytest.raises(SystemExit) as exc:
        main._open_spreadsheet("Some Sheet")
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Some Sheet" in out
    assert "shared" in out.lower() or "share" in out.lower()
