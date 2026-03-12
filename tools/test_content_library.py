"""Unit tests for content_library.py — Stage 1 of AI generation plan."""

import json
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.content_library import (
    ContentLibrary, LibraryEntry, PLACEHOLDER_ID,
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
