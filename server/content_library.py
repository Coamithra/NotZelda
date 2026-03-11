"""
Content Library — Tag-based storage, querying, and expiry for AI-generated content.

Manages rooms, monsters, and tiles in fixed-capacity libraries with placeholder
slots. Supports late binding via semantic tags: preferred → best tag overlap → generate.
Tags are free-form strings (normalized on ingestion). Tag-overlap scoring ranks
candidates when exact matches fail. Persists to JSON files in data/.
"""

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Tag normalization & fuzzy matching
# ---------------------------------------------------------------------------

def normalize_tag(tag: str) -> str:
    """Normalize a tag: lowercase, strip, collapse whitespace to underscores."""
    return re.sub(r'\s+', '_', tag.strip().lower())


def normalize_tags(tags: list[str]) -> list[str]:
    """Normalize a list of tags, dropping empty results."""
    return [t for raw in tags if (t := normalize_tag(raw))]



# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

ROOM_LIBRARY_CAPACITY = 79      # 64 permanent + 15 custom
MONSTER_LIBRARY_CAPACITY = 8    # 4 permanent + 4 custom
TILE_LIBRARY_CAPACITY = 14      # 7 permanent + 7 custom

EXPIRY_RATE = 0.10          # expire 10% of library per teardown
EXPIRY_MIN_AGE = 86400      # 24 hours

# ---------------------------------------------------------------------------
# Library entry
# ---------------------------------------------------------------------------

PLACEHOLDER_ID = "__placeholder__"


@dataclass
class LibraryEntry:
    """A single item in a content library (room, monster, or tile)."""
    id: str                              # unique identifier (e.g. "flame_wyrm")
    content_type: str                    # "room", "monster", or "tile"
    tags: list[str] = field(default_factory=list)
    created_at: float = 0.0             # time.time() when created
    data: dict[str, Any] = field(default_factory=dict)  # full payload
    permanent: bool = False             # permanent entries never expire or get deleted

    @property
    def is_placeholder(self) -> bool:
        return self.id == PLACEHOLDER_ID

    def to_dict(self) -> dict:
        return asdict(self)

    def __post_init__(self):
        self.tags = normalize_tags(self.tags)

    @classmethod
    def from_dict(cls, d: dict) -> "LibraryEntry":
        return cls(
            id=d["id"],
            content_type=d["content_type"],
            tags=d.get("tags", []),
            created_at=d.get("created_at", 0.0),
            data=d.get("data", {}),
            permanent=d.get("permanent", False),
        )

    @classmethod
    def placeholder(cls, content_type: str) -> "LibraryEntry":
        return cls(id=PLACEHOLDER_ID, content_type=content_type, tags=[])


# ---------------------------------------------------------------------------
# Resolution result
# ---------------------------------------------------------------------------

@dataclass
class ResolutionResult:
    """Result of resolving a content reference."""
    entry: Optional[LibraryEntry]
    method: str   # "preferred", "tag_match", "any", "generate"


# ---------------------------------------------------------------------------
# Content library
# ---------------------------------------------------------------------------

class ContentLibrary:
    """Fixed-capacity library with placeholder slots, tag-based queries, and expiry."""

    def __init__(self, content_type: str, capacity: int):
        self.content_type = content_type
        self.capacity = capacity
        self._entries: list[LibraryEntry] = []
        # Fill with placeholders
        for _ in range(capacity):
            self._entries.append(LibraryEntry.placeholder(content_type))

    # -- Queries --

    @property
    def real_entries(self) -> list[LibraryEntry]:
        return [e for e in self._entries if not e.is_placeholder]

    @property
    def placeholder_count(self) -> int:
        return sum(1 for e in self._entries if e.is_placeholder)

    @property
    def real_count(self) -> int:
        return len(self._entries) - self.placeholder_count

    @property
    def permanent_count(self) -> int:
        return sum(1 for e in self._entries if e.permanent)

    @property
    def custom_count(self) -> int:
        return sum(1 for e in self._entries if not e.is_placeholder and not e.permanent)

    @property
    def is_full(self) -> bool:
        return self.placeholder_count == 0

    def get_by_id(self, entry_id: str) -> Optional[LibraryEntry]:
        for e in self._entries:
            if e.id == entry_id and not e.is_placeholder:
                return e
        return None

    def query_by_tags(self, tags: list[str]) -> list[LibraryEntry]:
        """Find real entries matching ALL given tags (exact)."""
        normed = normalize_tags(tags)
        tag_set = set(normed)
        return [e for e in self._entries
                if not e.is_placeholder and tag_set.issubset(set(e.tags))]

    def query_by_tag_overlap(self, tags: list[str],
                              min_overlap: int = 1) -> list[tuple[float, LibraryEntry]]:
        """Find real entries ranked by tag overlap score.

        Score = number of shared tags / total unique tags across both sets.
        Returns (score, entry) pairs sorted by descending score,
        filtered to entries with at least min_overlap shared tags.
        """
        normed = set(normalize_tags(tags))
        if not normed:
            return []
        scored = []
        for e in self._entries:
            if e.is_placeholder:
                continue
            entry_tags = set(e.tags)
            shared = len(normed & entry_tags)
            if shared < min_overlap:
                continue
            union = len(normed | entry_tags)
            score = shared / union if union else 0.0
            scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def get_random_real(self) -> Optional[LibraryEntry]:
        """Return a random real entry, or None if library is empty."""
        import random
        real = self.real_entries
        return random.choice(real) if real else None

    def all_tags(self) -> set[str]:
        """Return the set of all tags currently used by real entries.

        Useful for including in AI prompts so the AI reuses existing tags.
        """
        tags: set[str] = set()
        for e in self._entries:
            if not e.is_placeholder:
                tags.update(e.tags)
        return tags

    # -- Mutations --

    def add(self, entry: LibraryEntry) -> bool:
        """Add an entry, replacing a placeholder slot. Returns False if no room."""
        if entry.is_placeholder:
            return False
        # Don't add duplicates
        if self.get_by_id(entry.id) is not None:
            return False
        # Find a placeholder to replace
        for i, e in enumerate(self._entries):
            if e.is_placeholder:
                if entry.created_at == 0.0:
                    entry.created_at = time.time()
                self._entries[i] = entry
                return True
        return False  # library full, no placeholders

    def remove(self, entry_id: str) -> bool:
        """Remove an entry by ID, replacing it with a placeholder.
        Permanent entries cannot be removed."""
        for i, e in enumerate(self._entries):
            if e.id == entry_id and not e.is_placeholder:
                if e.permanent:
                    return False
                self._entries[i] = LibraryEntry.placeholder(self.content_type)
                return True
        return False

    def expire_oldest(self, rate: float = EXPIRY_RATE, min_age: float = EXPIRY_MIN_AGE) -> list[str]:
        """Expire the oldest N% of entries that exceed min_age. Returns IDs of expired entries.
        Permanent entries are never expired."""
        now = time.time()
        # Collect eligible entries with their indices (skip permanent)
        eligible = []
        for i, e in enumerate(self._entries):
            if not e.is_placeholder and not e.permanent and (now - e.created_at) >= min_age:
                eligible.append((i, e))

        if not eligible:
            return []

        # Sort by created_at ascending (oldest first)
        eligible.sort(key=lambda x: x[1].created_at)

        # Expire up to rate * capacity entries
        count = max(1, int(self.capacity * rate))
        count = min(count, len(eligible))

        expired_ids = []
        for idx in range(count):
            i, e = eligible[idx]
            expired_ids.append(e.id)
            self._entries[i] = LibraryEntry.placeholder(self.content_type)

        return expired_ids

    # -- Resolution (late binding) --

    def resolve(self, preferred_id: Optional[str], tags: list[str],
                walkable: Optional[bool] = None) -> ResolutionResult:
        """
        Resolve a content reference using the fallback chain:
        1. preferred ID exists in library → use it
        2. best tag overlap match → pick highest scoring
        3. any real entry (respecting walkability constraint) → pick random
        4. nothing found → signal that generation is needed

        For tiles, walkable is a hard constraint: a walkable tile can only be
        substituted with another walkable tile, and vice versa.
        """
        import random

        def _walkability_ok(entry: LibraryEntry) -> bool:
            if walkable is None:
                return True
            return entry.data.get("walkable", False) == walkable

        # Step 1: preferred
        if preferred_id:
            entry = self.get_by_id(preferred_id)
            if entry is not None and _walkability_ok(entry):
                return ResolutionResult(entry=entry, method="preferred")

        # Step 2: best tag overlap
        if tags:
            matches = self.query_by_tag_overlap(tags)
            # Filter by walkability
            matches = [(s, e) for s, e in matches if _walkability_ok(e)]
            if matches:
                return ResolutionResult(entry=matches[0][1], method="tag_match")

        # Step 3: any real entry
        candidates = [e for e in self.real_entries if _walkability_ok(e)]
        if candidates:
            return ResolutionResult(entry=random.choice(candidates), method="any")

        # Step 4: nothing — generation needed
        return ResolutionResult(entry=None, method="generate")

    # -- Persistence --

    def to_json(self) -> list[dict]:
        """Serialize custom (non-permanent) real entries only.
        Placeholders are reconstructed on load; permanent entries are loaded from source."""
        return [e.to_dict() for e in self._entries
                if not e.is_placeholder and not e.permanent]

    @classmethod
    def from_json(cls, content_type: str, capacity: int, data: list[dict]) -> "ContentLibrary":
        """Load a library from saved JSON data, filling remaining slots with placeholders."""
        lib = cls(content_type, capacity)
        # Replace placeholders with loaded entries
        for i, d in enumerate(data):
            if i >= capacity:
                break
            lib._entries[i] = LibraryEntry.from_dict(d)
        return lib

    def load_custom(self, filepath: Path) -> int:
        """Load custom (non-permanent) entries from a JSON file into remaining placeholder slots.
        Call this AFTER permanent entries have been added. Returns count loaded."""
        if not filepath.exists():
            return 0
        data = json.loads(filepath.read_text(encoding="utf-8"))
        count = 0
        for d in data:
            entry = LibraryEntry.from_dict(d)
            if self.add(entry):
                count += 1
        return count

    def save(self, filepath: Path) -> None:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, content_type: str, capacity: int, filepath: Path) -> "ContentLibrary":
        if filepath.exists():
            data = json.loads(filepath.read_text(encoding="utf-8"))
            return cls.from_json(content_type, capacity, data)
        return cls(content_type, capacity)

    def __repr__(self) -> str:
        return (f"ContentLibrary({self.content_type}, "
                f"{self.real_count}/{self.capacity} real "
                f"[{self.permanent_count}p+{self.custom_count}c], "
                f"{self.placeholder_count} placeholders)")
