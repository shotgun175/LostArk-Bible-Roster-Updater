from dataclasses import dataclass, field


@dataclass
class Character:
    """A single scraped character entry from lostark.bible."""
    name: str
    ilvl: int        # item level (e.g. 1755)
    cp: float        # combat power score (e.g. 5915.7)
    char_class: str


@dataclass
class PlayerRoster:
    """A player's full roster, grouped under their nickname."""
    nickname: str
    characters: list[Character] = field(default_factory=list)
