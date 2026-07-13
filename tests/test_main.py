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

    rewrites: list[tuple[object, list[str]]] = []
    monkeypatch.setattr(
        main,
        "rewrite_sheet_sorted",
        lambda ws, sid, eligibility, ordered, player_rows, existing, svc: rewrites.append(
            (ws, sorted(eligibility.keys()))
        ),
    )

    ws_hard, ws_soft = MagicMock(), MagicMock()
    main.run_update(
        page=None,
        sheets_service=MagicMock(),
        spreadsheet_id="sid",
        tabs={
            "Hard (1700+)": (ws_hard, [(3, "Alice"), (4, "Bob")], {}),
            "Soft (1750+)": (ws_soft, [(3, "Bob"), (4, "Carol")], {}),
        },
        player_names=["Alice", "Bob", "Carol"],  # union across tabs
        overrides={},
        priority_players=[],
        single_player=False,
    )

    assert rewrites == [
        (ws_hard, ["Alice", "Bob"]),
        (ws_soft, ["Bob", "Carol"]),
    ]


def test_run_update_leaves_a_deliberately_empty_tab_empty(monkeypatch):
    """A tab whose column A is empty must not be back-filled with the union
    list — the rewrite should receive an empty eligibility and no-op."""
    monkeypatch.setattr(main, "scrape_roster", lambda page, name: [make_char("A1", 1760)])

    rewrites: list[tuple[object, list[str]]] = []
    monkeypatch.setattr(
        main,
        "rewrite_sheet_sorted",
        lambda ws, sid, eligibility, ordered, player_rows, existing, svc: rewrites.append(
            (ws, sorted(eligibility.keys()))
        ),
    )

    ws_hard, ws_empty = MagicMock(), MagicMock()
    main.run_update(
        page=None,
        sheets_service=MagicMock(),
        spreadsheet_id="sid",
        tabs={
            "Hard (1700+)": (ws_hard, [(3, "Alice"), (4, "Bob")], {}),
            "Empty (1750+)": (ws_empty, [], {}),
        },
        player_names=["Alice", "Bob"],
        overrides={},
        priority_players=[],
        single_player=False,
    )

    assert rewrites == [
        (ws_hard, ["Alice", "Bob"]),
        (ws_empty, []),
    ]


def test_sheet_mode_with_one_player_still_uses_full_rewrite(monkeypatch):
    monkeypatch.setattr(main, "scrape_roster", lambda page, name: [make_char("A1", 1760)])
    calls: list[str] = []
    monkeypatch.setattr(main, "rewrite_sheet_sorted", lambda *a, **k: calls.append("rewrite"))
    monkeypatch.setattr(main, "update_player_rows", lambda *a, **k: calls.append("update"))

    main.run_update(
        page=None, sheets_service=MagicMock(), spreadsheet_id="sid",
        tabs={"Hard (1700+)": (MagicMock(), [(3, "Alice")], {})},
        player_names=["Alice"], overrides={}, priority_players=[],
        single_player=False,
    )
    assert calls == ["rewrite"]


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


def test_failed_scrape_becomes_none_sentinel_and_is_reported(monkeypatch):
    """A scrape failure must not masquerade as an empty roster: the writer
    receives None and run_update returns the failed player's name."""
    def boom(page, name):
        raise main.ScrapeFailedError(f"down for {name}")
    monkeypatch.setattr(main, "scrape_roster", boom)

    received: list[dict] = []
    monkeypatch.setattr(
        main,
        "rewrite_sheet_sorted",
        lambda ws, sid, eligibility, ordered, player_rows, existing, svc: received.append(
            eligibility
        ),
    )

    failed = main.run_update(
        page=None,
        sheets_service=MagicMock(),
        spreadsheet_id="sid",
        tabs={"Hard (1700+)": (MagicMock(), [(3, "Alice"), (4, "Bob")], {})},
        player_names=["Alice", "Bob"],
        overrides={},
        priority_players=[],
        single_player=False,
    )

    assert failed == ["Alice", "Bob"]
    assert received[0] == {"Alice": None, "Bob": None}


def test_run_update_never_reads_from_worksheet_objects(monkeypatch):
    """Writers get pre-read data; run_update itself must not touch the ws.
    A bare object() raises AttributeError on ANY attribute access, so this
    fails loudly if run_update sneaks a read back in (MagicMock would hide it)."""
    monkeypatch.setattr(main, "scrape_roster", lambda page, name: [make_char("A1", 1760)])
    writes: list[object] = []
    monkeypatch.setattr(main, "rewrite_sheet_sorted", lambda ws, *a, **k: writes.append(ws))
    monkeypatch.setattr(main, "update_player_rows", lambda ws, *a, **k: writes.append(ws))
    sentinel = object()
    main.run_update(
        page=None, sheets_service=MagicMock(), spreadsheet_id="sid",
        tabs={"Hard (1700+)": (sentinel, [(3, "Alice")], {})},
        player_names=["Alice"], overrides={}, priority_players=[],
        single_player=False,
    )
    assert writes == [sentinel]
