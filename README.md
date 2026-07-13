# LostArk Bible Roster Updater

Scrapes character rosters from [lostark.bible](https://lostark.bible) and writes each player's eligible characters to your roster Google Sheet. Run it once before each raid week to keep everyone's roster current.

Part of [Lost Ark Tools](https://shotgun175.github.io/) — see all tools.

---

## How it all works together

```
lostark.bible  →  scraper.py  →  sheets.py  →  Your roster sheet (Google Sheet)  →  "Serca (1740+)" tab  →  Roster table + Run planner
```

**Step by step:**

1. The tool reads the player list from **column A** of the target sheet tab (rows 3+, stops at the "Run" row)
2. Each player's lostark.bible roster page is scraped **once** up front — even when running `--all`, every player is fetched a single time
3. For each target tab, the cached rosters are filtered by the iLvl threshold (and optional cap) — derived from the tab name (e.g. `Serca (1740+)` → 1740 minimum) or overridden in `config.json`
4. Each player's eligible characters are sorted by iLvl descending, then combat power descending, capped at 6
5. Results are written to columns B–G, one character per cell, formatted as:
   ```
   CharName | iLvl
   ClassName | CP
   ```
6. Players are sorted top-to-bottom by most eligible characters; ties broken by total combat power (higher investment = higher placement). Priority players (configured via `priority_players` in `config.json`) always appear first regardless of count.

---

## First-time setup

**0. Create the virtual environment** — the launcher (`LostArk Bible Roster Updater.bat`)
hard-requires a venv at `.\venv`, so create it there (not `.venv`):
```
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**1. Install Python dependencies** (inside the venv)
```
pip install -r requirements.txt
```

**2. Install the browser (one-time, or after a Playwright update)**
```
playwright install chromium
```

**3. Set up Google API access** — the tool needs a service account key to read and write your Google Sheet. Follow these steps once:

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a new project (any name)
2. In the left menu go to **APIs & Services → Library**, search for and enable both:
   - **Google Sheets API**
   - **Google Drive API**
3. Go to **APIs & Services → Credentials**, click **Create Credentials → Service account**
   - Give it any name, click through the remaining steps, and hit **Done**
4. Click your new service account in the list, go to the **Keys** tab, click **Add Key → Create new key → JSON**
   - A `credentials.json` file will download — move it to the project root
5. Open the JSON file and copy the `client_email` value (looks like `name@project.iam.gserviceaccount.com`)
6. Open your Google Sheet, click **Share**, and share the spreadsheet with that email address — give it **Editor** access

`credentials.json` is gitignored and never committed.

**4. Create your config file** — copy `config.example.json` to `config.json` and edit the values to match your spreadsheet:

```
copy config.example.json config.json
```

Set `spreadsheet_name` to your Google Sheet name, list any `priority_players` who should always sort to the top, and add `overrides` for tabs whose iLvl threshold doesn't match the tab name. `config.json` is gitignored — your personal config never gets committed.

---

## Running the tool

**Double-click** `LostArk Bible Roster Updater.bat` — opens PowerShell with the venv activated and shows help automatically.

Or from a terminal with the venv active:

```
# One player, one tab  (no confirmation prompt)
python main.py --player PlayerOne --sheet "Serca (1740+)"

# All players, one tab
python main.py --sheet "Serca (1740+)"

# One player, all tabs
python main.py --player PlayerOne

# Everyone, everything
python main.py --all
```

`--player` is case-insensitive. Any run involving multiple players or multiple tabs will ask for confirmation before writing.

---

## The Google Sheet — "Serca (1740+)" tab

### Roster table (rows 3+)

| Column A | Columns B–G |
|----------|-------------|
| Player name | Up to 6 eligible characters (one per cell) |

- Column A is the source of truth for the player list — edit it directly to add/remove players
- Player names must match exactly as they appear on lostark.bible
- The tool stops reading column A at the run-planner marker: a cell that is "Run" or starts with "Run " (e.g. "Run Planner"). Everything below it is never touched.

### Run planner (below the roster)

Below the "Run" row, there are 6 run slots for scheduling raid groups within the week. Each slot has two rows:

| Row | Columns B–I | Columns J–L |
|-----|-------------|-------------|
| Name row | Player names (or "Pug" for fill-ins) | Pug count / Supp status / Supp helper |
| Char row | Characters being played | Discord paste formula |

**Filling in a run:**
1. Enter player names (or "Pug") in the name row (B–I)
2. Enter the character each person is playing in the char row directly below
3. `J` (name row) auto-calculates how many DPS pugs are still needed
4. `K` (name row) shows supp status — warns if over- or under-supplied
5. `J` (char row) generates a Discord-ready paste with everyone's name and character

### 4-man raid checkbox (B15)

The label **"4-man raid?"** in B14 and checkbox in **B15** control whether the run planner operates in 4-man or 8-man mode.

- **Unchecked (default):** full 8-player mode — all columns B–I are active
- **Checked:** 4-man mode — columns F–I are visually grayed out and automatically excluded from all calculations (pug count, supp count, Discord paste)

You do not need to delete or hide columns when switching modes — just toggle the checkbox.

---

## Managing players

Edit **column A** of the target tab directly (rows 3 and below, above the "Run" row). The tool reads this list fresh on every run. No code or config changes needed.

---

## Sheet tab naming

Tabs must follow the pattern `Name (iLvl+)` for the iLvl threshold to be detected automatically.

Examples: `Serca (1740+)`, `Kazeros (1620+)`

To override a threshold without renaming a tab, add an entry to `config.json`. Three forms are supported:

```json
{
  "spreadsheet_name": "Your Spreadsheet Name",
  "priority_players": ["PlayerOne", "PlayerTwo"],
  "overrides": {
    "Serca (1740+)": 1750,
    "Hard Serca (1730+)": { "threshold": 1730 },
    "Hard Brel (1670+)": { "threshold": 1670, "cap": 1699 }
  }
}
```

`spreadsheet_name` and `priority_players` are also read from `config.json`. Both fall back to sensible defaults if absent (the default priority list is empty — i.e. no priority).

| Form | Effect |
|------|--------|
| `1750` (plain number) | Threshold = 1750, no cap |
| `{ "threshold": 1750 }` | Same as above, object form |
| `{ "threshold": 1730, "cap": 1739 }` | Threshold = 1730 **and** cap = 1739 — only characters with iLvl in [1730, 1739] are included |

The `cap` field is useful when a raid tier has both a hard floor and a ceiling — for example a "Hard" mode that only accepts characters who have not yet hit the next tier's minimum.

---

## Assumptions, scope & open questions

> Unofficial community tool — not affiliated with or endorsed by lostark.bible, Smilegate, or Amazon Games.

### Confirmed assumptions

- **Data source is lostark.bible's inline page data, not an API.** Each roster is read from the SvelteKit hydration payload embedded in an inline `<script>` tag on the player's roster page. `scraper.py` extracts the `roster: [ ... ]` array from the raw HTML in Python (a string-aware bracket scan, then converted for JSON parsing) — no JS is executed, and the extraction is unit-tested against saved real pages. There is no public/documented API to call.
- **Region is hard-coded to NA.** The scrape URL is `https://lostark.bible/character/NA/{name}/roster` (`scraper.py`). Region is *not* configurable.
- **Player names come from the Google Sheet, not config.** The list is read live from column A of the target tab (rows 3+, stopping at the first "Run" cell). Names must match how they appear on lostark.bible exactly.
- **`config.json` covers the sheet name, priority players, and iLvl threshold/cap** — `spreadsheet_name`, `priority_players`, and per-tab `overrides`. A tab's threshold otherwise comes from its name (`Name (iLvl+)`).
- **Auth is a Google service account.** `credentials.json` is a service-account key; the spreadsheet must be shared with that account's email as Editor. Scopes used are Sheets (read/write) and Drive (read-only).
- **Output shape is fixed:** up to 6 characters per player, each cell formatted as `Name | iLvl` / `Class | CP`, written to columns A–G.

### Open questions / known fragility

- **KEY RISK — scraping is brittle.** Extraction depends on string-matching `roster: [` and bracket-scanning lostark.bible's inline hydration script. There is no versioned contract to depend on — treat this as the primary maintenance risk. Failure modes are at least distinct now: a page with no roster key reports "check the character name", while a roster that exists but cannot be parsed reports a scraper/site-layout problem.
- **Class names map to a fixed set.** `class_map.py` translates KR internal class names to NA names for a known set of classes; a new or renamed class shows as `Unknown` until the map is updated.
- **No region support beyond NA** (see above) without a code change.
- **No retry/backoff.** A timeout or load error for one player is logged and that player is skipped (treated as an empty roster) for the run.
- **Dependencies are version-pinned but not fully locked.** `requirements.txt` pins direct dependencies to known-good versions; transitive dependencies are not captured in a lockfile.

### Scope (out)

- Regions other than NA.
- Reading the player list from anywhere other than the sheet's column A.
- A stable API client (none is published by lostark.bible).
- Unattended scheduling/automation — the tool is run manually before each raid week.
- The sheet's run-planner formulas and layout — the tool only writes the roster table (columns A–G); everything below the "Run" row is owned by the spreadsheet itself.

---

## Project structure

```
main.py               CLI entry point — owns auth, Playwright lifetime, orchestration
scraper.py            Roster scraping (takes a Page) + filter/sort/count logic
sheets.py             Google Sheets read/write + rich text formatting
class_map.py          KR internal class name → global NA class name (29 classes)
config.py             config.json loader + tab name threshold parsing
models.py             Character dataclass
tests/                Unit tests
config.example.json   Template config — copy to config.json and edit
config.json           Spreadsheet name, priority players, threshold overrides (gitignored)
credentials.json      Google service account key (gitignored)
LostArk Bible Roster Updater.bat   Windows launcher — opens PowerShell with venv activated
```
