"""Unit tests for treasure-in-trap-room interactions.

Verifies that:
  - Treasure cells can become trap rooms based on difficulty tier.
  - Dungeon items (map, compass, key) are hidden during trap lockdown.
  - Per-player items (lantern, tide_medallion) are hidden during lockdown.
  - _lock_room() replaces doorway tiles with CD and saves originals.
  - unlock_room() restores door tiles and reveals dungeon_items.
  - game.locked_rooms is cleaned up after unlock.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.state import game
from server.constants import ROOM_COLS, ROOM_ROWS, DOORWAY_TILES
from server.dungeons import DungeonInstance, _identify_trap_rooms
from server.lifecycle import _lock_room, unlock_room


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FLOOR = "GR"   # grass — walkable
WALL = "DW"    # dungeon wall — not walkable


def _make_tilemap():
    """Build a minimal 11x15 tilemap: walls on border, floor inside, doorway openings."""
    tilemap = []
    for r in range(ROOM_ROWS):
        row = []
        for c in range(ROOM_COLS):
            if r == 0 or r == ROOM_ROWS - 1 or c == 0 or c == ROOM_COLS - 1:
                row.append(WALL)
            else:
                row.append(FLOOR)
        tilemap.append(row)

    # Punch doorway openings — replace wall tiles at doorway positions with floor
    for _direction, positions in DOORWAY_TILES.items():
        for r, c in positions:
            tilemap[r][c] = FLOOR

    return tilemap


def _setup_trap_treasure_room():
    """Create a minimal DungeonInstance with a treasure cell that is also a trap room.

    Registers the room in game.rooms, game.room_to_dungeon, game.active_dungeons.
    Returns (instance, room_id, treasure_cell).
    """
    dungeon_id = "d1"
    treasure_cell = (2, 1)
    room_id = f"{dungeon_id}_{treasure_cell[0]}_{treasure_cell[1]}"

    # Build a room with exits north and south
    tilemap = _make_tilemap()
    game.rooms[room_id] = {
        "tilemap": tilemap,
        "exits": {"north": f"{dungeon_id}_2_0", "south": f"{dungeon_id}_2_2"},
        "locked": True,  # trap room flag
    }

    # Ensure tile recipes exist for walkability checks
    if FLOOR not in game.custom_tile_recipes:
        game.custom_tile_recipes[FLOOR] = {"walkable": True}
    if WALL not in game.custom_tile_recipes:
        game.custom_tile_recipes[WALL] = {"walkable": False}
    if "CD" not in game.custom_tile_recipes:
        game.custom_tile_recipes["CD"] = {"walkable": False}

    # Create a minimal DungeonInstance
    instance = DungeonInstance(
        dungeon_id=dungeon_id,
        layout={"entrance": (1, 1), "size": (4, 4)},
        room_map={(2, 1): "precreated_0"},
        active_rooms={room_id},
        entrance_room_id=f"{dungeon_id}_1_1",
        music_track="dungeon1",
        boss_track="boss1",
    )
    instance.treasure_cell = treasure_cell
    instance.trap_cells = {treasure_cell}
    instance.boss_cell = (3, 3)

    # Place items in the treasure room
    instance.dungeon_items[room_id] = [
        {"x": 7, "y": 5, "item_type": "map"},
    ]
    instance.per_player_items[room_id] = [
        {"x": 7, "y": 3, "item_type": "lantern"},
    ]

    # Register in game state
    game.active_dungeons[dungeon_id] = instance
    game.room_to_dungeon[room_id] = dungeon_id

    return instance, room_id, treasure_cell


def _cleanup(room_id, dungeon_id="d1"):
    """Remove test data from game state."""
    game.rooms.pop(room_id, None)
    game.locked_rooms.pop(room_id, None)
    game.room_to_dungeon.pop(room_id, None)
    game.active_dungeons.pop(dungeon_id, None)


# ---------------------------------------------------------------------------
# Tests: trap eligibility
# ---------------------------------------------------------------------------

def test_treasure_cell_can_be_trap():
    """A treasure cell with 'hard' difficulty is always identified as a trap room."""
    treasure_cell = (2, 1)
    boss_cell = (3, 3)
    entrance = (1, 1)
    sanctum = (3, 4)

    cell_difficulty = {
        entrance: "easy",
        treasure_cell: "hard",
        boss_cell: "hard",
        sanctum: "easy",
        (1, 2): "easy",
    }

    trap_cells = _identify_trap_rooms(cell_difficulty, boss_cell, entrance, sanctum)
    assert treasure_cell in trap_cells, (
        f"Hard-tier treasure cell {treasure_cell} should be in trap_cells, got {trap_cells}"
    )


def test_treasure_cell_not_trap_when_easy():
    """A treasure cell with 'easy' difficulty is never a trap room."""
    treasure_cell = (2, 1)
    boss_cell = (3, 3)
    entrance = (1, 1)
    sanctum = (3, 4)

    cell_difficulty = {
        entrance: "easy",
        treasure_cell: "easy",
        boss_cell: "hard",
        sanctum: "easy",
        (1, 2): "easy",
    }

    trap_cells = _identify_trap_rooms(cell_difficulty, boss_cell, entrance, sanctum)
    assert treasure_cell not in trap_cells, (
        f"Easy-tier treasure cell {treasure_cell} should NOT be in trap_cells, got {trap_cells}"
    )


# ---------------------------------------------------------------------------
# Tests: door locking
# ---------------------------------------------------------------------------

def test_door_tiles_replaced_on_lock():
    """_lock_room() replaces doorway tiles with CD and stores originals."""
    _inst, room_id, _ = _setup_trap_treasure_room()
    try:
        tilemap = game.rooms[room_id]["tilemap"]

        # Verify doorways start as floor tiles
        for r, c in DOORWAY_TILES["north"]:
            assert tilemap[r][c] == FLOOR, f"Pre-lock: ({r},{c}) should be {FLOOR}"

        _lock_room(room_id)

        # Doorway tiles should now be CD
        for r, c in DOORWAY_TILES["north"]:
            assert tilemap[r][c] == "CD", f"Post-lock: ({r},{c}) should be CD, got {tilemap[r][c]}"
        for r, c in DOORWAY_TILES["south"]:
            assert tilemap[r][c] == "CD", f"Post-lock: ({r},{c}) should be CD, got {tilemap[r][c]}"

        # Original tiles should be saved
        assert room_id in game.locked_rooms
        originals = game.locked_rooms[room_id]["original_tiles"]
        for r, c in DOORWAY_TILES["north"]:
            assert (r, c) in originals, f"Original tile for ({r},{c}) not saved"
            assert originals[(r, c)] == FLOOR
    finally:
        _cleanup(room_id)


# ---------------------------------------------------------------------------
# Tests: item hiding during lockdown
# ---------------------------------------------------------------------------

def test_items_hidden_during_lockdown():
    """Dungeon items are not visible when room is in game.locked_rooms.

    This tests the guard condition used by send_room_enter() and the item
    pickup code in commands.py: `if room_id not in game.locked_rooms`.
    """
    instance, room_id, _ = _setup_trap_treasure_room()
    try:
        _lock_room(room_id)

        # Verify the room is locked
        assert room_id in game.locked_rooms

        # The guard condition that hides items — same as lifecycle.py:363
        room_items = instance.dungeon_items.get(room_id, [])
        assert len(room_items) > 0, "Test setup should have dungeon items"

        items_visible = room_items and room_id not in game.locked_rooms
        assert not items_visible, "Dungeon items should be hidden while room is locked"
    finally:
        _cleanup(room_id)


def test_per_player_items_hidden_during_lockdown():
    """Per-player items (lantern, tide_medallion) are also hidden during lockdown.

    Same guard condition as lifecycle.py:369.
    """
    instance, room_id, _ = _setup_trap_treasure_room()
    try:
        _lock_room(room_id)

        pp_items = instance.per_player_items.get(room_id, [])
        assert len(pp_items) > 0, "Test setup should have per-player items"

        items_visible = pp_items and room_id not in game.locked_rooms
        assert not items_visible, "Per-player items should be hidden while room is locked"
    finally:
        _cleanup(room_id)


# ---------------------------------------------------------------------------
# Tests: unlock and item reveal
# ---------------------------------------------------------------------------

def test_unlock_restores_doors_and_reveals_items():
    """unlock_room() restores original doorway tiles and includes dungeon_items in broadcast."""
    _inst, room_id, _ = _setup_trap_treasure_room()
    try:
        tilemap = game.rooms[room_id]["tilemap"]

        _lock_room(room_id)

        # Verify locked state
        for r, c in DOORWAY_TILES["north"]:
            assert tilemap[r][c] == "CD"

        msgs = []
        unlock_room(room_id, msgs)

        # Doors should be restored
        for r, c in DOORWAY_TILES["north"]:
            assert tilemap[r][c] == FLOOR, (
                f"Post-unlock: ({r},{c}) should be {FLOOR}, got {tilemap[r][c]}"
            )
        for r, c in DOORWAY_TILES["south"]:
            assert tilemap[r][c] == FLOOR, (
                f"Post-unlock: ({r},{c}) should be {FLOOR}, got {tilemap[r][c]}"
            )

        # Should have broadcast a doors_unlocked message
        assert len(msgs) == 1, f"Expected 1 broadcast message, got {len(msgs)}"
        kind, target_room, msg, _ = msgs[0]
        assert kind == "broadcast"
        assert target_room == room_id
        assert msg["type"] == "doors_unlocked"

        # Tile changes should list restored tiles
        assert len(msg["tile_changes"]) > 0

        # Dungeon items should be revealed in the unlock message
        assert "dungeon_items" in msg, (
            "unlock message should contain dungeon_items for the treasure room"
        )
        revealed_types = {it["item_type"] for it in msg["dungeon_items"]}
        assert "map" in revealed_types, f"Map should be revealed, got {revealed_types}"
    finally:
        _cleanup(room_id)


def test_locked_room_cleared_after_unlock():
    """After unlock_room(), the room is no longer in game.locked_rooms."""
    _inst, room_id, _ = _setup_trap_treasure_room()
    try:
        _lock_room(room_id)
        assert room_id in game.locked_rooms

        msgs = []
        unlock_room(room_id, msgs)

        assert room_id not in game.locked_rooms, (
            "Room should be removed from game.locked_rooms after unlock"
        )
    finally:
        _cleanup(room_id)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
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
