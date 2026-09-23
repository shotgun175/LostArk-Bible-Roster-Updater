"""Tests for main.py: per-tab player lists under --all, friendly setup errors."""
from unittest.mock import MagicMock

import pytest

import main
from models import Character


def make_char(name: str = "Char", ilvl: int = 1750) -> Character:
    return Character(name=name, ilvl=ilvl, cp=5000.0, char_class="Bard")


@pytest.fixture
def echo_read_tab(monkeypatch):
    """Column A did not change during the run: main.read_tab returns each
    tab's own snapshot. Returns a function that registers a tabs dict and
    passes it through."""
    snapshots: dict[int, tuple] = {}

    def register(tabs: dict[str, tuple]) -> dict[str, tuple]:
        for ws, player_rows, existing in tabs.values():
            snapshots[id(ws)] = (player_rows, existing)
        return tabs

    monkeypatch.setattr(main, "read_tab", lambda ws: snapshots[id(ws)])
    return register


def test_run_update_uses_each_tabs_own_player_list(monkeypatch, echo_read_tab):
    """--all used to take tab 0's column A and rewrite every tab with it,
    silently clobbering tabs whose player lists differ."""
    scraped: dict[str, list[Character]] = {
        "Alice": [make_char("A1", 1760)],
        "Bob": [make_char("B1", 1760)],
        "Carol": [make_char("C1", 1760)],
    }
    monkeypatch.setattr(main, "scrape_roster", lambda page, name: scraped[name])
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

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
        tabs=echo_read_tab({
            "Hard (1700+)": (ws_hard, [(3, "Alice"), (4, "Bob")], {}),
            "Soft (1750+)": (ws_soft, [(3, "Bob"), (4, "Carol")], {}),
        }),
        player_names=["Alice", "Bob", "Carol"],  # union across tabs
        overrides={},
        priority_players=[],
        single_player=False,
    )

    assert rewrites == [
        (ws_hard, ["Alice", "Bob"]),
        (ws_soft, ["Bob", "Carol"]),
    ]


def test_run_update_leaves_a_deliberately_empty_tab_empty(monkeypatch, echo_read_tab):
    """A tab whose column A is empty must not be back-filled with the union
    list — the rewrite should receive an empty eligibility and no-op."""
    monkeypatch.setattr(main, "scrape_roster", lambda page, name: [make_char("A1", 1760)])
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

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
        tabs=echo_read_tab({
            "Hard (1700+)": (ws_hard, [(3, "Alice"), (4, "Bob")], {}),
            "Empty (1750+)": (ws_empty, [], {}),
        }),
        player_names=["Alice", "Bob"],
        overrides={},
        priority_players=[],
        single_player=False,
    )

    assert rewrites == [
        (ws_hard, ["Alice", "Bob"]),
        (ws_empty, []),
    ]


def test_sheet_mode_with_one_player_still_uses_full_rewrite(monkeypatch, echo_read_tab):
    monkeypatch.setattr(main, "scrape_roster", lambda page, name: [make_char("A1", 1760)])
    calls: list[str] = []
    monkeypatch.setattr(main, "rewrite_sheet_sorted", lambda *a, **k: calls.append("rewrite"))
    monkeypatch.setattr(main, "update_player_rows", lambda *a, **k: calls.append("update"))

    main.run_update(
        page=None, sheets_service=MagicMock(), spreadsheet_id="sid",
        tabs=echo_read_tab({"Hard (1700+)": (MagicMock(), [(3, "Alice")], {})}),
        player_names=["Alice"], overrides={}, priority_players=[],
        single_player=False,
    )
    assert calls == ["rewrite"]


def test_single_player_mode_only_updates_b_to_g(monkeypatch, echo_read_tab):
    monkeypatch.setattr(main, "scrape_roster", lambda page, name: [make_char("A1", 1760)])
    calls: list[str] = []
    monkeypatch.setattr(main, "rewrite_sheet_sorted", lambda *a, **k: calls.append("rewrite"))
    monkeypatch.setattr(main, "update_player_rows", lambda *a, **k: calls.append("update"))

    main.run_update(
        page=None, sheets_service=MagicMock(), spreadsheet_id="sid",
        tabs=echo_read_tab({
            "Hard (1700+)": (MagicMock(), [(3, "Alice"), (4, "Bob")], {}),
            "Soft (1750+)": (MagicMock(), [(3, "Bob"), (4, "Alice")], {}),
        }),
        player_names=["Alice"], overrides={}, priority_players=[],
        single_player=True,
    )
    assert calls == ["update", "update"]


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


def test_failed_scrape_becomes_none_sentinel_and_is_reported(monkeypatch, echo_read_tab):
    """A scrape failure must not masquerade as an empty roster: the writer
    receives None and run_update returns the failed player's name."""
    def boom(page, name):
        raise RuntimeError(f"down for {name}")
    monkeypatch.setattr(main, "scrape_roster", boom)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)

    received: list[dict] = []
    monkeypatch.setattr(
        main,
        "rewrite_sheet_sorted",
        lambda ws, sid, eligibility, ordered, player_rows, existing, svc: received.append(
            eligibility
        ),
    )

    failed, skipped = main.run_update(
        page=None,
        sheets_service=MagicMock(),
        spreadsheet_id="sid",
        tabs=echo_read_tab({"Hard (1700+)": (MagicMock(), [(3, "Alice"), (4, "Bob")], {})}),
        player_names=["Alice", "Bob"],
        overrides={},
        priority_players=[],
        single_player=False,
    )

    assert failed == ["Alice", "Bob"]
    assert skipped == []
    assert received[0] == {"Alice": None, "Bob": None}


def test_run_update_reads_each_worksheet_exactly_once(monkeypatch):
    """Writers get pre-read data; run_update's only access to a ws is one
    read_tab call just before writing it. A bare object() raises
    AttributeError on ANY attribute access, so this fails loudly if run_update
    sneaks another read back in (MagicMock would hide it)."""
    monkeypatch.setattr(main, "scrape_roster", lambda page, name: [make_char("A1", 1760)])
    reads: list[object] = []

    def read_once(ws):
        reads.append(ws)
        return [(3, "Alice")], {}

    monkeypatch.setattr(main, "read_tab", read_once)
    writes: list[object] = []
    monkeypatch.setattr(main, "rewrite_sheet_sorted", lambda ws, *a, **k: writes.append(ws))
    monkeypatch.setattr(main, "update_player_rows", lambda ws, *a, **k: writes.append(ws))
    hard, soft = object(), object()
    main.run_update(
        page=None, sheets_service=MagicMock(), spreadsheet_id="sid",
        tabs={
            "Hard (1700+)": (hard, [(3, "Alice")], {}),
            "Soft (1750+)": (soft, [(3, "Alice")], {}),
        },
        player_names=["Alice"], overrides={}, priority_players=[],
        single_player=False,
    )
    assert reads == [hard, soft]
    assert writes == [hard, soft]


@pytest.mark.parametrize("single_player", [False, True])
def test_changed_column_a_skips_the_tab(monkeypatch, capsys, single_player):
    """A row edited, inserted or deleted after the snapshot shifts the write
    range onto the run planner: the tab must be left untouched and reported."""
    monkeypatch.setattr(main, "scrape_roster", lambda page, name: [make_char("A1", 1760)])
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    ws_changed, ws_same = MagicMock(), MagicMock()
    current = {
        id(ws_changed): ([(3, "Alice"), (4, "Carol")], {}),  # Bob's row deleted mid-run
        id(ws_same): ([(3, "Alice")], {}),
    }
    monkeypatch.setattr(main, "read_tab", lambda ws: current[id(ws)])
    writes: list[object] = []
    monkeypatch.setattr(main, "rewrite_sheet_sorted", lambda ws, *a, **k: writes.append(ws))
    monkeypatch.setattr(main, "update_player_rows", lambda ws, *a, **k: writes.append(ws))

    failed, skipped = main.run_update(
        page=None, sheets_service=MagicMock(), spreadsheet_id="sid",
        tabs={
            "Hard (1700+)": (ws_changed, [(3, "Alice"), (4, "Bob"), (5, "Carol")], {}),
            "Soft (1750+)": (ws_same, [(3, "Alice")], {}),
        },
        player_names=["Alice"], overrides={}, priority_players=[],
        single_player=single_player,
    )

    assert writes == [ws_same]
    assert skipped == ["Hard (1700+)"]
    assert failed == []
    assert (
        "Skipping 'Hard (1700+)': column A changed during the run - re-run to update it."
        in capsys.readouterr().out
    )


def test_politeness_delay_between_players(monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr(main.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(main.random, "uniform", lambda a, b: 0.0)
    monkeypatch.setattr(main, "scrape_roster", lambda page, name: [])
    main._scrape_all_rosters(None, ["A", "B", "C"])
    assert sleeps == [main.SCRAPE_DELAY_S] * 2  # between players, not before the first


def _auth_ok(monkeypatch):
    creds_cls = MagicMock()
    monkeypatch.setattr(main.Credentials, "from_service_account_file", creds_cls)
    client = MagicMock()
    monkeypatch.setattr(main.gspread, "authorize", lambda creds: client)
    return creds_cls, client


def test_open_spreadsheet_mounts_retry_and_sets_timeout(monkeypatch):
    _, client = _auth_ok(monkeypatch)
    main._open_spreadsheet("My Sheet")
    prefix, adapter = client.http_client.session.mount.call_args.args
    assert prefix == "https://"
    retry = adapter.max_retries
    assert 503 in retry.status_forcelist
    assert retry.allowed_methods is None
    assert retry.raise_on_status is False
    client.set_timeout.assert_called_once_with((10, 60))


def test_open_by_id_uses_open_by_key_and_sheets_scope_only(monkeypatch):
    creds_cls, client = _auth_ok(monkeypatch)
    main._open_spreadsheet("ignored", spreadsheet_id="abc123")
    client.open_by_key.assert_called_once_with("abc123")
    client.open.assert_not_called()
    assert creds_cls.call_args.kwargs["scopes"] == ["https://www.googleapis.com/auth/spreadsheets"]


def test_open_by_id_unshared_sheet_is_friendly(monkeypatch, capsys):
    _, client = _auth_ok(monkeypatch)
    client.open_by_key.side_effect = PermissionError("403")
    with pytest.raises(SystemExit) as exc:
        main._open_spreadsheet("ignored", spreadsheet_id="abc123")
    assert exc.value.code == 1
    out = capsys.readouterr().out.lower()
    assert "share" in out and "client_email" in out


def test_open_by_name_still_uses_both_scopes(monkeypatch):
    creds_cls, client = _auth_ok(monkeypatch)
    main._open_spreadsheet("My Sheet")
    client.open.assert_called_once_with("My Sheet")
    assert "https://www.googleapis.com/auth/drive.readonly" in creds_cls.call_args.kwargs["scopes"]
