"""Unit tests for content_library.py — Stage 1 of AI generation plan."""

import json
import time
import tempfile
from pathlib import Path

from content_library import (
    ContentLibrary, LibraryEntry, ResolutionResult, PLACEHOLDER_ID,
    MONSTER_ROLES, TILE_ROLES, ROOM_ROLES,
    normalize_tag, normalize_tags, _tag_similarity, tags_match_fuzzy,
)


# ---------------------------------------------------------------------------
# LibraryEntry basics
# ---------------------------------------------------------------------------

def test_placeholder_creation():
    p = LibraryEntry.placeholder("monster")
    assert p.is_placeholder
    assert p.id == PLACEHOLDER_ID
    assert p.content_type == "monster"

def test_real_entry():
    e = LibraryEntry(
        id="flame_wyrm", content_type="monster", role="medium_melee",
        tags=["fire", "dungeon"], created_at=1000.0,
        data={"hp": 3, "damage": 2},
    )
    assert not e.is_placeholder
    assert e.role == "medium_melee"
    assert "fire" in e.tags

def test_serialization_roundtrip():
    e = LibraryEntry(
        id="lava_crack", content_type="tile", role="floor_variant",
        tags=["fire", "walkable"], created_at=12345.0,
        data={"colors": {"base": "#3a2020"}},
    )
    d = e.to_dict()
    e2 = LibraryEntry.from_dict(d)
    assert e2.id == e.id
    assert e2.tags == e.tags
    assert e2.data == e.data
    assert e2.created_at == e.created_at


# ---------------------------------------------------------------------------
# ContentLibrary — capacity and placeholders
# ---------------------------------------------------------------------------

def test_library_starts_with_placeholders():
    lib = ContentLibrary("monster", 10)
    assert lib.real_count == 0
    assert lib.placeholder_count == 10
    assert not lib.is_full

def test_add_entry():
    lib = ContentLibrary("monster", 5)
    e = LibraryEntry(id="slime", content_type="monster", role="fodder", tags=["beast"])
    assert lib.add(e)
    assert lib.real_count == 1
    assert lib.placeholder_count == 4

def test_add_duplicate_rejected():
    lib = ContentLibrary("monster", 5)
    e = LibraryEntry(id="slime", content_type="monster", role="fodder", tags=["beast"])
    assert lib.add(e)
    assert not lib.add(e)  # duplicate
    assert lib.real_count == 1

def test_add_to_full_library_fails():
    lib = ContentLibrary("monster", 2)
    lib.add(LibraryEntry(id="a", content_type="monster", role="fodder"))
    lib.add(LibraryEntry(id="b", content_type="monster", role="fodder"))
    assert lib.is_full
    ok = lib.add(LibraryEntry(id="c", content_type="monster", role="fodder"))
    assert not ok
    assert lib.real_count == 2

def test_add_sets_created_at():
    lib = ContentLibrary("tile", 5)
    e = LibraryEntry(id="brick", content_type="tile", role="wall_base")
    before = time.time()
    lib.add(e)
    after = time.time()
    stored = lib.get_by_id("brick")
    assert stored is not None
    assert before <= stored.created_at <= after

def test_remove_entry():
    lib = ContentLibrary("monster", 5)
    lib.add(LibraryEntry(id="bat", content_type="monster", role="fodder"))
    assert lib.real_count == 1
    assert lib.remove("bat")
    assert lib.real_count == 0
    assert lib.placeholder_count == 5

def test_remove_nonexistent():
    lib = ContentLibrary("monster", 5)
    assert not lib.remove("ghost")


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def test_get_by_id():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="skeleton", content_type="monster", role="medium_melee", tags=["undead"]))
    assert lib.get_by_id("skeleton") is not None
    assert lib.get_by_id("nonexistent") is None

def test_query_by_role_and_tags():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="fire_bat", content_type="monster", role="fodder", tags=["fire", "flying"]))
    lib.add(LibraryEntry(id="ice_bat", content_type="monster", role="fodder", tags=["ice", "flying"]))
    lib.add(LibraryEntry(id="fire_golem", content_type="monster", role="tank", tags=["fire"]))

    # Match role + all tags
    results = lib.query_by_role_and_tags("fodder", ["fire"])
    assert len(results) == 1
    assert results[0].id == "fire_bat"

    # Match role + subset of tags
    results = lib.query_by_role_and_tags("fodder", ["flying"])
    assert len(results) == 2

    # No match: wrong role
    results = lib.query_by_role_and_tags("boss", ["fire"])
    assert len(results) == 0

    # No match: tag not present
    results = lib.query_by_role_and_tags("fodder", ["shadow"])
    assert len(results) == 0

def test_query_by_role():
    lib = ContentLibrary("tile", 10)
    lib.add(LibraryEntry(id="torch", content_type="tile", role="light_source", tags=["fire"]))
    lib.add(LibraryEntry(id="lamp", content_type="tile", role="light_source", tags=["metal"]))
    lib.add(LibraryEntry(id="brick", content_type="tile", role="wall_base", tags=["stone"]))

    results = lib.query_by_role("light_source")
    assert len(results) == 2
    assert {r.id for r in results} == {"torch", "lamp"}


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

def test_expire_oldest():
    lib = ContentLibrary("monster", 10)
    # Add entries with staggered timestamps in the past
    now = time.time()
    for i in range(10):
        lib.add(LibraryEntry(
            id=f"m{i}", content_type="monster", role="fodder",
            created_at=now - 200000 + i * 1000,  # all well past min_age
        ))
    assert lib.is_full

    expired = lib.expire_oldest(rate=0.3, min_age=1.0)
    assert len(expired) == 3  # 30% of 10
    assert expired == ["m0", "m1", "m2"]  # oldest first
    assert lib.real_count == 7
    assert lib.placeholder_count == 3

def test_expire_respects_min_age():
    lib = ContentLibrary("monster", 10)
    now = time.time()
    for i in range(10):
        lib.add(LibraryEntry(
            id=f"m{i}", content_type="monster", role="fodder",
            created_at=now,  # just created — too young
        ))
    expired = lib.expire_oldest(rate=0.5, min_age=86400)
    assert len(expired) == 0
    assert lib.real_count == 10

def test_expire_empty_library():
    lib = ContentLibrary("monster", 10)
    expired = lib.expire_oldest()
    assert len(expired) == 0

def test_expire_at_least_one():
    """Even with tiny rate, expire at least 1 entry."""
    lib = ContentLibrary("monster", 5)
    now = time.time()
    lib.add(LibraryEntry(id="old", content_type="monster", role="fodder", created_at=now - 100000))
    expired = lib.expire_oldest(rate=0.01, min_age=1.0)
    assert len(expired) == 1


# ---------------------------------------------------------------------------
# Resolution (late binding fallback chain)
# ---------------------------------------------------------------------------

def test_resolve_preferred():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="flame_wyrm", content_type="monster", role="medium_melee", tags=["fire"]))
    result = lib.resolve("flame_wyrm", "medium_melee", ["fire"])
    assert result.method == "preferred"
    assert result.entry.id == "flame_wyrm"

def test_resolve_fallback_role_tags():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="fire_golem", content_type="monster", role="medium_melee", tags=["fire"]))
    # preferred is gone, but role+tags match
    result = lib.resolve("flame_wyrm", "medium_melee", ["fire"])
    assert result.method == "role_tags"
    assert result.entry.id == "fire_golem"

def test_resolve_fallback_role_only():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="stone_golem", content_type="monster", role="medium_melee", tags=["stone"]))
    # preferred gone, no fire tags, but role matches
    result = lib.resolve("flame_wyrm", "medium_melee", ["fire"])
    assert result.method == "role_only"
    assert result.entry.id == "stone_golem"

def test_resolve_fallback_generate():
    lib = ContentLibrary("monster", 10)
    # Empty library — nothing to resolve
    result = lib.resolve("flame_wyrm", "medium_melee", ["fire"])
    assert result.method == "generate"
    assert result.entry is None

def test_resolve_no_preferred_skips_to_tags():
    lib = ContentLibrary("tile", 10)
    lib.add(LibraryEntry(id="brazier", content_type="tile", role="light_source", tags=["fire", "wall_mounted"]))
    result = lib.resolve(None, "light_source", ["fire"])
    assert result.method == "role_tags"
    assert result.entry.id == "brazier"

def test_resolve_fuzzy_tags():
    """'flame' query tag should fuzzy-match an entry tagged 'fire_elemental'."""
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="fire_imp", content_type="monster", role="fodder",
                         tags=["fire_elemental", "dungeon"]))
    # "fire" is a substring of "fire_elemental" → fuzzy match
    result = lib.resolve(None, "fodder", ["fire"])
    assert result.method in ("role_tags", "role_tags_fuzzy")
    assert result.entry.id == "fire_imp"

def test_resolve_fuzzy_falls_through_to_role():
    """If fuzzy matching also fails, fall through to role-only."""
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="golem", content_type="monster", role="tank", tags=["stone"]))
    result = lib.resolve(None, "tank", ["zzzzz"])
    assert result.method == "role_only"
    assert result.entry.id == "golem"

def test_resolve_empty_tags_skips_to_role():
    lib = ContentLibrary("tile", 10)
    lib.add(LibraryEntry(id="lamp", content_type="tile", role="light_source", tags=["metal"]))
    result = lib.resolve(None, "light_source", [])
    assert result.method == "role_only"
    assert result.entry.id == "lamp"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_save_and_load():
    lib = ContentLibrary("monster", 5)
    lib.add(LibraryEntry(
        id="slime", content_type="monster", role="fodder",
        tags=["beast"], created_at=1000.0,
        data={"hp": 1, "damage": 1},
    ))
    lib.add(LibraryEntry(
        id="bat", content_type="monster", role="fodder",
        tags=["flying", "cave"], created_at=2000.0,
        data={"hp": 1, "damage": 1},
    ))

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_lib.json"
        lib.save(path)

        # Verify JSON on disk
        raw = json.loads(path.read_text())
        assert len(raw) == 2  # only real entries saved

        # Load back
        lib2 = ContentLibrary.load("monster", 5, path)
        assert lib2.real_count == 2
        assert lib2.placeholder_count == 3
        assert lib2.get_by_id("slime") is not None
        assert lib2.get_by_id("bat") is not None
        assert lib2.get_by_id("slime").data == {"hp": 1, "damage": 1}

def test_load_nonexistent_file():
    lib = ContentLibrary.load("tile", 10, Path("/nonexistent/path.json"))
    assert lib.real_count == 0
    assert lib.placeholder_count == 10

def test_load_more_entries_than_capacity():
    """If saved data has more entries than current capacity, extras are ignored."""
    data = [
        {"id": f"m{i}", "content_type": "monster", "role": "fodder", "tags": [], "created_at": 1000.0, "data": {}}
        for i in range(20)
    ]
    lib = ContentLibrary.from_json("monster", 5, data)
    assert lib.real_count == 5
    assert lib.placeholder_count == 0


# ---------------------------------------------------------------------------
# Reference roles sanity check
# ---------------------------------------------------------------------------

def test_reference_roles_nonempty():
    assert len(MONSTER_ROLES) > 0
    assert len(TILE_ROLES) > 0
    assert len(ROOM_ROLES) > 0


# ---------------------------------------------------------------------------
# Tag normalization
# ---------------------------------------------------------------------------

def test_normalize_tag_basic():
    assert normalize_tag("Fire") == "fire"
    assert normalize_tag("  ICE  ") == "ice"
    assert normalize_tag("wall mounted") == "wall_mounted"
    assert normalize_tag("DARK  shadow") == "dark_shadow"

def test_normalize_tags_list():
    result = normalize_tags(["Fire", " Ice ", "", "  ", "Shadow Beast"])
    assert result == ["fire", "ice", "shadow_beast"]

def test_tags_normalized_on_entry_creation():
    e = LibraryEntry(id="test", content_type="monster", role="fodder",
                     tags=["Fire", " ICE ", "Shadow Beast"])
    assert e.tags == ["fire", "ice", "shadow_beast"]

def test_tags_normalized_on_from_dict():
    e = LibraryEntry.from_dict({
        "id": "test", "content_type": "tile", "role": "floor_base",
        "tags": ["STONE", "Dark Dungeon"],
    })
    assert e.tags == ["stone", "dark_dungeon"]


# ---------------------------------------------------------------------------
# Tag similarity
# ---------------------------------------------------------------------------

def test_similarity_exact():
    assert _tag_similarity("fire", "fire") == 1.0

def test_similarity_substring():
    assert _tag_similarity("fire", "fire_elemental") == 0.9
    assert _tag_similarity("flame", "flame") == 1.0

def test_similarity_bigram():
    # "fire" and "dire" share some bigrams but aren't substrings
    score = _tag_similarity("fire", "dire")
    assert 0.0 < score < 0.9  # related but not substring

def test_similarity_unrelated():
    score = _tag_similarity("fire", "ice")
    assert score < 0.5  # should be low

def test_similarity_short():
    assert _tag_similarity("a", "b") == 0.0  # too short for bigrams

def test_fuzzy_match_all_query_tags():
    # "flame" should fuzzy-match "fire_elemental" via substring
    score = tags_match_fuzzy(["flame"], ["flame_wyrm", "dungeon"])
    assert score > 0

def test_fuzzy_match_fails_if_any_tag_unmatched():
    score = tags_match_fuzzy(["fire", "zzzzz"], ["fire", "ice"])
    assert score == 0.0


# ---------------------------------------------------------------------------
# all_tags (prompt-side inventory)
# ---------------------------------------------------------------------------

def test_all_tags():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="a", content_type="monster", role="fodder", tags=["fire", "beast"]))
    lib.add(LibraryEntry(id="b", content_type="monster", role="tank", tags=["ice", "beast"]))
    assert lib.all_tags() == {"fire", "beast", "ice"}

def test_all_tags_empty():
    lib = ContentLibrary("monster", 10)
    assert lib.all_tags() == set()


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------

def test_repr():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="slime", content_type="monster", role="fodder"))
    s = repr(lib)
    assert "monster" in s
    assert "1/10" in s


if __name__ == "__main__":
    import sys
    test_funcs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    failed = 0
    for fn in test_funcs:
        try:
            fn()
            passed += 1
            print(f"  PASS  {fn.__name__}")
        except Exception as ex:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {ex}")
    print(f"\n{passed} passed, {failed} failed out of {len(test_funcs)} tests")
    sys.exit(1 if failed else 0)
