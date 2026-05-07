from models import Character


def test_character_fields():
    char = Character(name="Valslayer", ilvl=1755, cp=5915.7, char_class="Slayer")
    assert char.name == "Valslayer"
    assert char.ilvl == 1755
    assert char.cp == 5915.7
    assert char.char_class == "Slayer"
