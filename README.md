# LostArk Bible Roster Updater

Scrapes character rosters from [lostark.bible](https://lostark.bible) and writes each player's eligible characters to the **BOZO BOZONGOS** Google Sheet. Run it once before each raid week to keep everyone's roster current.

---

## How it all works together

```
lostark.bible  →  scraper.py  →  sheets.py  →  BOZO BOZONGOS (Google Sheet)
                                                        ↓
                                              "Serca (1740+)" tab
                                              Roster table + Run planner
```

**Step by step:**

1. The tool reads the player list from **column A** of the target sheet tab (rows 3+, stops at the "Run" row)
2. For each player, it visits their lostark.bible roster page and pulls all characters
3. Characters are filtered by the iLvl threshold (and optional cap) — derived from the tab name (e.g. `Serca (1740+)` → 1740 minimum) or overridden in `config.json`
4. Each player's eligible characters are sorted by iLvl descending, then combat power descending, capped at 6
5. Results are written to columns B–G, one character per cell, formatted as:
   ```
   CharName | iLvl
   ClassName | CP
   ```
6. Players are sorted top-to-bottom by most eligible characters; ties broken by total combat power (higher investment = higher placement). Priority players (Valslayer, Mabi, Remi) always appear first regardless of count.

---

## First-time setup

**1. Install Python dependencies**
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

---

## Running the tool

**Double-click** `LostArk Roster Updater.bat` — opens PowerShell with the venv activated and shows help automatically.

Or from a terminal with the venv active:

```
# One player, one tab  (no confirmation prompt)
python main.py --player Valslayer --sheet "Serca (1740+)"

# All players, one tab
python main.py --sheet "Serca (1740+)"

# One player, all tabs
python main.py --player Valslayer

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
- The tool stops reading column A when it hits a cell containing "Run"

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
  "overrides": {
    "Serca (1740+)": 1750,
    "Hard Serca (1730+)": { "threshold": 1730 },
    "Hard Serca (1730+)": { "threshold": 1730, "cap": 1739 }
  }
}
```

| Form | Effect |
|------|--------|
| `1750` (plain number) | Threshold = 1750, no cap |
| `{ "threshold": 1750 }` | Same as above, object form |
| `{ "threshold": 1730, "cap": 1739 }` | Threshold = 1730 **and** cap = 1739 — only characters with iLvl in [1730, 1739] are included |

The `cap` field is useful when a raid tier has both a hard floor and a ceiling — for example a "Hard" mode that only accepts characters who have not yet hit the next tier's minimum.

---

## Project structure

```
main.py               CLI entry point — argument parsing, confirmation prompts, orchestration
scraper.py            Playwright browser scraping + filter/sort logic
sheets.py             Google Sheets read/write + rich text formatting
class_map.py          KR internal class name → global NA class name (29 classes)
config.py             Tab name threshold parsing + config.json loader
models.py             Character dataclass
tests/                Unit tests (36 passing)
config.json           Optional threshold overrides (empty by default)
credentials.json      Google service account key (gitignored)
LostArk Roster Updater.bat   Windows launcher — opens PowerShell with venv activated
```
