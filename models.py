"""Data models for scraped Lost Ark characters."""
from dataclasses import dataclass

# Display cap: characters shown per player (sheet columns B.. derive from it).
MAX_CHARS_PER_PLAYER = 6


@dataclass
class Character:
    """A single scraped character entry from lostark.bible."""
    name: str
    ilvl: int        # item level (e.g. 1755)
    cp: float        # combat power score (e.g. 5915.7)
    char_class: str
