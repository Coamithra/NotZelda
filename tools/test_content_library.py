"""Unit tests for content_library.py — Stage 1 of AI generation plan."""

import json
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.content_library import (
    ContentLibrary, LibraryEntry, ResolutionResult, PLACEHOLDER_ID,
    normalize_tag, normalize_tags,
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
        id="flame_wyrm", content_type="monster",
        tags=["fire", "dungeon"], created_at=1000.0,
        data={"hp": 3, "damage": 2},
    )
    assert not e.is_placeholder
    assert "fire" in e.tags

def test_serialization_roundtrip():
    e = LibraryEntry(
        id="lava_crack", content_type="tile",
        tags=["fire"], created_at=12345.0,
        data={"colors": {"base": "#3a2020"}, "walkable": True},
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
    e = LibraryEntry(id="slime", content_type="monster", tags=["beast"])
    assert lib.add(e)
    assert lib.real_count == 1
    assert lib.placeholder_count == 4

def test_add_duplicate_rejected():
    lib = ContentLibrary("monster", 5)
    e = LibraryEntry(id="slime", content_type="monster", tags=["beast"])
    assert lib.add(e)
    assert not lib.add(e)  # duplicate
    assert lib.real_count == 1

def test_add_to_full_library_fails():
    lib = ContentLibrary("monster", 2)
    lib.add(LibraryEntry(id="a", content_type="monster"))
    lib.add(LibraryEntry(id="b", content_type="monster"))
    assert lib.is_full
    ok = lib.add(LibraryEntry(id="c", content_type="monster"))
    assert not ok
    assert lib.real_count == 2

def test_add_sets_created_at():
    lib = ContentLibrary("tile", 5)
    e = LibraryEntry(id="brick", content_type="tile")
    before = time.time()
    lib.add(e)
    after = time.time()
    stored = lib.get_by_id("brick")
    assert stored is not None
    assert before <= stored.created_at <= after

def test_remove_entry():
    lib = ContentLibrary("monster", 5)
    lib.add(LibraryEntry(id="bat", content_type="monster"))
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
    lib.add(LibraryEntry(id="skeleton", content_type="monster", tags=["undead"]))
    assert lib.get_by_id("skeleton") is not None
    assert lib.get_by_id("nonexistent") is None

def test_query_by_tags():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="fire_bat", content_type="monster", tags=["fire", "flying"]))
    lib.add(LibraryEntry(id="ice_bat", content_type="monster", tags=["ice", "flying"]))
    lib.add(LibraryEntry(id="fire_golem", content_type="monster", tags=["fire"]))

    # Match all given tags
    results = lib.query_by_tags(["fire"])
    assert len(results) == 2
    assert {r.id for r in results} == {"fire_bat", "fire_golem"}

    # Match subset of tags
    results = lib.query_by_tags(["flying"])
    assert len(results) == 2

    # Match multiple tags (intersection)
    results = lib.query_by_tags(["fire", "flying"])
    assert len(results) == 1
    assert results[0].id == "fire_bat"

    # No match
    results = lib.query_by_tags(["shadow"])
    assert len(results) == 0

def test_query_by_tag_overlap():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="fire_bat", content_type="monster", tags=["fire", "flying", "dungeon"]))
    lib.add(LibraryEntry(id="ice_bat", content_type="monster", tags=["ice", "flying"]))
    lib.add(LibraryEntry(id="fire_golem", content_type="monster", tags=["fire"]))

    # Query with ["fire", "flying"] — fire_bat has 2 overlap, others have 1
    results = lib.query_by_tag_overlap(["fire", "flying"])
    assert len(results) == 3
    assert results[0][1].id == "fire_bat"  # best overlap

    # min_overlap filters
    results = lib.query_by_tag_overlap(["fire", "flying"], min_overlap=2)
    assert len(results) == 1
    assert results[0][1].id == "fire_bat"


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

def test_expire_oldest():
    lib = ContentLibrary("monster", 10)
    now = time.time()
    for i in range(10):
        lib.add(LibraryEntry(
            id=f"m{i}", content_type="monster",
            created_at=now - 200000 + i * 1000,
        ))
    assert lib.is_full

    expired = lib.expire_oldest(rate=0.3, min_age=1.0)
    assert len(expired) == 3
    assert expired == ["m0", "m1", "m2"]
    assert lib.real_count == 7
    assert lib.placeholder_count == 3

def test_expire_respects_min_age():
    lib = ContentLibrary("monster", 10)
    now = time.time()
    for i in range(10):
        lib.add(LibraryEntry(
            id=f"m{i}", content_type="monster",
            created_at=now,
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
    lib.add(LibraryEntry(id="old", content_type="monster", created_at=now - 100000))
    expired = lib.expire_oldest(rate=0.01, min_age=1.0)
    assert len(expired) == 1


# ---------------------------------------------------------------------------
# Resolution (late binding fallback chain)
# ---------------------------------------------------------------------------

def test_resolve_preferred():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="flame_wyrm", content_type="monster", tags=["fire"]))
    result = lib.resolve("flame_wyrm", ["fire"])
    assert result.method == "preferred"
    assert result.entry.id == "flame_wyrm"

def test_resolve_fallback_tag_match():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="fire_golem", content_type="monster", tags=["fire"]))
    # preferred is gone, but tags overlap
    result = lib.resolve("flame_wyrm", ["fire"])
    assert result.method == "tag_match"
    assert result.entry.id == "fire_golem"

def test_resolve_fallback_any():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="stone_golem", content_type="monster", tags=["stone"]))
    # preferred gone, no fire tags, but there's something in the library
    result = lib.resolve("flame_wyrm", ["fire"])
    assert result.method == "any"
    assert result.entry.id == "stone_golem"

def test_resolve_fallback_generate():
    lib = ContentLibrary("monster", 10)
    # Empty library — nothing to resolve
    result = lib.resolve("flame_wyrm", ["fire"])
    assert result.method == "generate"
    assert result.entry is None

def test_resolve_no_preferred_skips_to_tags():
    lib = ContentLibrary("tile", 10)
    lib.add(LibraryEntry(id="brazier", content_type="tile", tags=["fire", "wall_mounted"]))
    result = lib.resolve(None, ["fire"])
    assert result.method == "tag_match"
    assert result.entry.id == "brazier"

def test_resolve_empty_tags_falls_to_any():
    lib = ContentLibrary("tile", 10)
    lib.add(LibraryEntry(id="lamp", content_type="tile", tags=["metal"]))
    result = lib.resolve(None, [])
    assert result.method == "any"
    assert result.entry.id == "lamp"

def test_resolve_walkability_constraint():
    """Walkable tiles can only be substituted with walkable tiles."""
    lib = ContentLibrary("tile", 10)
    lib.add(LibraryEntry(id="lava_floor", content_type="tile", tags=["fire"],
                         data={"walkable": True}))
    lib.add(LibraryEntry(id="fire_wall", content_type="tile", tags=["fire"],
                         data={"walkable": False}))

    # Looking for a walkable fire tile — should get lava_floor
    result = lib.resolve(None, ["fire"], walkable=True)
    assert result.entry.id == "lava_floor"

    # Looking for a non-walkable fire tile — should get fire_wall
    result = lib.resolve(None, ["fire"], walkable=False)
    assert result.entry.id == "fire_wall"

def test_resolve_walkability_blocks_wrong_type():
    """If only non-walkable tiles exist, walkable resolve should fall through."""
    lib = ContentLibrary("tile", 10)
    lib.add(LibraryEntry(id="fire_wall", content_type="tile", tags=["fire"],
                         data={"walkable": False}))

    result = lib.resolve(None, ["fire"], walkable=True)
    assert result.method == "generate"
    assert result.entry is None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_save_and_load():
    lib = ContentLibrary("monster", 5)
    lib.add(LibraryEntry(
        id="slime", content_type="monster",
        tags=["beast"], created_at=1000.0,
        data={"hp": 1, "damage": 1},
    ))
    lib.add(LibraryEntry(
        id="bat", content_type="monster",
        tags=["flying", "cave"], created_at=2000.0,
        data={"hp": 1, "damage": 1},
    ))

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_lib.json"
        lib.save(path)

        raw = json.loads(path.read_text())
        assert len(raw) == 2

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
        {"id": f"m{i}", "content_type": "monster", "tags": [], "created_at": 1000.0, "data": {}}
        for i in range(20)
    ]
    lib = ContentLibrary.from_json("monster", 5, data)
    assert lib.real_count == 5
    assert lib.placeholder_count == 0


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
    e = LibraryEntry(id="test", content_type="monster",
                     tags=["Fire", " ICE ", "Shadow Beast"])
    assert e.tags == ["fire", "ice", "shadow_beast"]

def test_tags_normalized_on_from_dict():
    e = LibraryEntry.from_dict({
        "id": "test", "content_type": "tile",
        "tags": ["STONE", "Dark Dungeon"],
    })
    assert e.tags == ["stone", "dark_dungeon"]


# ---------------------------------------------------------------------------
# all_tags (prompt-side inventory)
# ---------------------------------------------------------------------------

def test_all_tags():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="a", content_type="monster", tags=["fire", "beast"]))
    lib.add(LibraryEntry(id="b", content_type="monster", tags=["ice", "beast"]))
    assert lib.all_tags() == {"fire", "beast", "ice"}

def test_all_tags_empty():
    lib = ContentLibrary("monster", 10)
    assert lib.all_tags() == set()


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------

def test_repr():
    lib = ContentLibrary("monster", 10)
    lib.add(LibraryEntry(id="slime", content_type="monster"))
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
