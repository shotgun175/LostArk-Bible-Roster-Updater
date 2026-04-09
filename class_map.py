"""Maps KR internal class names to English global (NA) class names.

KR names come from the ``class`` field in lostark.bible's embedded page JSON
(the ``roster`` array inside the ``kit.start`` data argument in each page's
inline ``<script>`` tag).  These are stable internal identifiers used by the
game server and are independent of the Svelte build.
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

    Returns 'Unknown' if the name is not in the map.
    """
    return CLASS_MAP.get(kr_name, "Unknown")
