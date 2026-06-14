"""Maps KR internal class names to English global (NA) class names.

KR names come from the ``class`` field in lostark.bible's embedded page JSON
(the ``roster`` array inside the ``kit.start`` data argument in each page's
inline ``<script>`` tag).  These are stable internal identifiers used by the
game server and are independent of the Svelte build.

Last verified against live lostark.bible pages: 2026-06-11. To re-derive
after a new class releases: open any roster page containing the new class,
find its ``class`` value in the inline hydration script, and add the mapping
here (the console warning below names the unmapped value when it appears).
"""

CLASS_MAP: dict[str, str] = {
    "alchemist":          "Wildsoul",
    "arcana":             "Arcanist",
    "bard":               "Bard",
    "battle_master":      "Wardancer",
    "battle_master_male": "Striker",
    "berserker":          "Berserker",
    "berserker_female":   "Slayer",
    "blade":              "Deathblade",
    "blaster":            "Artillerist",
    "demonic":            "Shadowhunter",
    "destroyer":          "Destroyer",
    "devil_hunter":       "Deadeye",
    "devil_hunter_female": "Gunslinger",
    "dragon_knight":      "Guardianknight",
    "elemental_master":   "Sorceress",
    "force_master":       "Soulfist",
    "hawk_eye":           "Sharpshooter",
    "holyknight":         "Paladin",
    "holyknight_female":  "Valkyrie",
    "infighter":          "Scrapper",
    "infighter_male":     "Breaker",
    "lance_master":       "Glaivier",
    "reaper":             "Reaper",
    "scouter":            "Machinist",
    "soul_eater":         "Souleater",
    "summoner":           "Summoner",
    "warlord":            "Gunlancer",
    "weather_artist":     "Aeromancer",
    "yinyangshi":         "Artist",
}


def get_class_from_name(kr_name: str) -> str:
    """Return the English class name for the given KR internal class string.

    Returns 'Unknown' (with a console warning) if the name is not in the map,
    so a newly released class is visible to the operator instead of silently
    writing 'Unknown' rows to the sheet.
    """
    eng_name = CLASS_MAP.get(kr_name)
    if eng_name is None:
        print(
            f"Warning: unmapped class '{kr_name}' from lostark.bible — writing "
            "'Unknown'. A new class may have released; add it to class_map.py."
        )
        return "Unknown"
    return eng_name
