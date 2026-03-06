"""
Content Library — Tag-based storage, querying, and expiry for AI-generated content.

Manages rooms, monsters, and tiles in fixed-capacity libraries with placeholder
slots. Supports late binding via semantic tags: preferred → role+tags → role → generate.
Tags are free-form strings (normalized on ingestion). Fuzzy tag matching bridges
synonyms when exact matches fail. Persists to JSON files in data/.
"""

import json
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Reference roles (soft guidance for AI prompts, not enforced)
# ---------------------------------------------------------------------------

MONSTER_ROLES = frozenset({
    "fodder", "light_melee", "medium_melee", "heavy_melee",
    "ranged", "tank", "boss", "swarm",
})

TILE_ROLES = frozenset({
    "floor_base", "floor_variant", "wall_base", "wall_variant",
    "pillar", "structural", "light_source", "decoration", "hazard",
    "container", "furniture",
})

ROOM_ROLES = frozenset({
    "combat", "puzzle", "treasure", "corridor", "hub", "boss_room",
    "ambush", "rest",
})


# ---------------------------------------------------------------------------
# Tag normalization & fuzzy matching
# ---------------------------------------------------------------------------

def normalize_tag(tag: str) -> str:
    """Normalize a tag: lowercase, strip, collapse whitespace to underscores."""
    return re.sub(r'\s+', '_', tag.strip().lower())


def normalize_tags(tags: list[str]) -> list[str]:
    """Normalize a list of tags, dropping empty results."""
    return [t for raw in tags if (t := normalize_tag(raw))]


# Fuzzy similarity threshold for partial tag matching (0.0 to 1.0).
# A query tag is considered a fuzzy match if it scores above this.
FUZZY_TAG_THRESHOLD = 0.5


def _tag_similarity(a: str, b: str) -> float:
    """Score similarity between two normalized tags. Returns 0.0-1.0.

    Uses substring containment (strong signal) with bigram Jaccard as tiebreaker.
    """
    if a == b:
        return 1.0
    # Substring containment — one tag fully inside the other
    if a in b or b in a:
        return 0.9
    # Bigram Jaccard similarity
    if len(a) < 2 or len(b) < 2:
        return 0.0
    bigrams_a = {a[i:i+2] for i in range(len(a) - 1)}
    bigrams_b = {b[i:i+2] for i in range(len(b) - 1)}
    intersection = len(bigrams_a & bigrams_b)
    union = len(bigrams_a | bigrams_b)
    return intersection / union if union else 0.0


def tags_match_fuzzy(query_tags: list[str], entry_tags: list[str],
                     threshold: float = FUZZY_TAG_THRESHOLD) -> float:
    """Check if all query tags have a fuzzy match in entry tags.

    Returns the average best-match score (0.0 if any query tag has no match
    above threshold). Higher is better.
    """
    if not query_tags:
        return 0.0
    total = 0.0
    for qt in query_tags:
        best = max((_tag_similarity(qt, et) for et in entry_tags), default=0.0)
        if best < threshold:
            return 0.0
        total += best
    return total / len(query_tags)

# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------

ROOM_LIBRARY_CAPACITY = 50
MONSTER_LIBRARY_CAPACITY = 40
TILE_LIBRARY_CAPACITY = 30

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
    role: str                            # semantic role (e.g. "medium_melee")
    tags: list[str] = field(default_factory=list)
    created_at: float = 0.0             # time.time() when created
    data: dict[str, Any] = field(default_factory=dict)  # full payload

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
            role=d["role"],
            tags=d.get("tags", []),
            created_at=d.get("created_at", 0.0),
            data=d.get("data", {}),
        )

    @classmethod
    def placeholder(cls, content_type: str) -> "LibraryEntry":
        return cls(id=PLACEHOLDER_ID, content_type=content_type, role="", tags=[])


# ---------------------------------------------------------------------------
# Resolution result
# ---------------------------------------------------------------------------

@dataclass
class ResolutionResult:
    """Result of resolving a content reference."""
    entry: Optional[LibraryEntry]
    method: str   # "preferred", "role_tags", "role_only", "generate", "none"


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
    def is_full(self) -> bool:
        return self.placeholder_count == 0

    def get_by_id(self, entry_id: str) -> Optional[LibraryEntry]:
        for e in self._entries:
            if e.id == entry_id and not e.is_placeholder:
                return e
        return None

    def query_by_role_and_tags(self, role: str, tags: list[str]) -> list[LibraryEntry]:
        """Find real entries matching the given role AND all given tags (exact)."""
        results = []
        normed = normalize_tags(tags)
        tag_set = set(normed)
        for e in self._entries:
            if e.is_placeholder:
                continue
            if e.role == role and tag_set.issubset(set(e.tags)):
                results.append(e)
        return results

    def query_by_role_and_tags_fuzzy(self, role: str, tags: list[str],
                                     threshold: float = FUZZY_TAG_THRESHOLD) -> list[LibraryEntry]:
        """Find real entries matching role, with fuzzy tag matching.

        Returns entries sorted by descending match score.
        """
        normed = normalize_tags(tags)
        if not normed:
            return []
        scored = []
        for e in self._entries:
            if e.is_placeholder or e.role != role:
                continue
            score = tags_match_fuzzy(normed, e.tags, threshold)
            if score > 0:
                scored.append((score, e))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored]

    def query_by_role(self, role: str) -> list[LibraryEntry]:
        """Find real entries matching the given role (ignoring tags)."""
        return [e for e in self._entries if not e.is_placeholder and e.role == role]

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
        """Remove an entry by ID, replacing it with a placeholder."""
        for i, e in enumerate(self._entries):
            if e.id == entry_id and not e.is_placeholder:
                self._entries[i] = LibraryEntry.placeholder(self.content_type)
                return True
        return False

    def expire_oldest(self, rate: float = EXPIRY_RATE, min_age: float = EXPIRY_MIN_AGE) -> list[str]:
        """Expire the oldest N% of entries that exceed min_age. Returns IDs of expired entries."""
        now = time.time()
        # Collect eligible entries with their indices
        eligible = []
        for i, e in enumerate(self._entries):
            if not e.is_placeholder and (now - e.created_at) >= min_age:
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

    def resolve(self, preferred_id: Optional[str], role: str, tags: list[str]) -> ResolutionResult:
        """
        Resolve a content reference using the fallback chain:
        1. preferred ID exists in library → use it
        2. role + exact tags match → pick one
        3. role + fuzzy tags match → pick best
        4. role only match → pick one
        5. nothing found → signal that generation is needed
        """
        import random

        # Step 1: preferred
        if preferred_id:
            entry = self.get_by_id(preferred_id)
            if entry is not None:
                return ResolutionResult(entry=entry, method="preferred")

        # Step 2: role + exact tags
        if tags:
            matches = self.query_by_role_and_tags(role, tags)
            if matches:
                return ResolutionResult(entry=random.choice(matches), method="role_tags")

        # Step 3: role + fuzzy tags
        if tags:
            matches = self.query_by_role_and_tags_fuzzy(role, tags)
            if matches:
                return ResolutionResult(entry=matches[0], method="role_tags_fuzzy")

        # Step 4: role only
        if role:
            matches = self.query_by_role(role)
            if matches:
                return ResolutionResult(entry=random.choice(matches), method="role_only")

        # Step 5: nothing — generation needed
        return ResolutionResult(entry=None, method="generate")

    # -- Persistence --

    def to_json(self) -> list[dict]:
        """Serialize real entries only (placeholders are reconstructed on load)."""
        return [e.to_dict() for e in self._entries if not e.is_placeholder]

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
                f"{self.real_count}/{self.capacity} real, "
                f"{self.placeholder_count} placeholders)")
