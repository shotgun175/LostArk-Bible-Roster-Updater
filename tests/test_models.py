from models import Character, PlayerRoster


def test_character_fields():
    char = Character(name="Valslayer", ilvl=1755, cp=5915.7, char_class="Slayer")
    assert char.name == "Valslayer"
    assert char.ilvl == 1755
    assert char.cp == 5915.7
    assert char.char_class == "Slayer"


def test_player_roster_defaults_to_empty_characters():
    roster = PlayerRoster(nickname="Valluru")
    assert roster.nickname == "Valluru"
    assert roster.characters == []


def test_player_roster_with_characters():
    char = Character(name="Valslayer", ilvl=1755, cp=5915.7, char_class="Slayer")
    roster = PlayerRoster(nickname="Valluru", characters=[char])
    assert len(roster.characters) == 1
    assert roster.characters[0].name == "Valslayer"
