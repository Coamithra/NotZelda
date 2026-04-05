# Plan: Test — Treasure in Trap Room

## Context

Dungeon treasure chests (containing the lantern in d1, tide medallion in d2) are placed in the room furthest from boss + entrance. That room can receive a hard or challenging difficulty tier, making it a trap room. Trap rooms lock the player in (doors replaced with CD tiles) and hide all dungeon items until every monster is killed.

This interaction is critical to get right — if items aren't hidden during lockdown, players can grab the lantern/medallion before clearing the room, skipping the combat challenge. If items aren't revealed after clearing, the treasure is permanently lost.

There are currently no tests for this code path. This card adds a focused test file that exercises the lock/unlock/item-hide/item-reveal cycle specifically for treasure rooms.

## Approach

### New file: `tools/test_treasure_trap.py`

A single test file following the existing pattern (`tools/test_content_library.py`): plain `test_*()` functions, assertion-based, no external test framework.

**Setup helper** — `_make_trap_treasure_room()`:
- Creates a minimal `DungeonInstance` with a treasure cell marked as trapped
- Builds a simple 11x15 tilemap with walkable floor + wall borders + doorway tiles
- Registers it in `game.rooms`, `game.room_to_dungeon`, `game.active_dungeons`
- Places a lantern in `instance.per_player_items` and a map in `instance.dungeon_items`
- Returns `(instance, room_id)` for test use

**Teardown helper** — `_cleanup(room_id)`:
- Removes room from `game.rooms`, `game.locked_rooms`, `game.room_monsters`, etc.
- Resets `game.active_dungeons` and `game.room_to_dungeon`

**Tests:**

1. `test_treasure_cell_can_be_trap()` — Calls `_identify_trap_rooms()` with treasure cell at "hard" difficulty. Asserts treasure cell is in the returned trap set.

2. `test_treasure_cell_not_trap_when_easy()` — Calls `_identify_trap_rooms()` with treasure cell at "easy". Asserts treasure cell is NOT in the trap set.

3. `test_items_hidden_during_lockdown()` — Locks the room via `_lock_room()`. Builds a mock `send_room_enter()` message (or directly checks `game.locked_rooms` membership). Asserts that when `room_id in game.locked_rooms`, the items would be omitted from the message.

4. `test_door_tiles_replaced_on_lock()` — After `_lock_room()`, asserts doorway tiles in the tilemap are "CD". Asserts `game.locked_rooms[room_id]` contains the original tiles.

5. `test_unlock_restores_doors_and_reveals_items()` — Calls `_lock_room()` then `unlock_room()`. Asserts doorway tiles are restored. Asserts the broadcast message contains `dungeon_items` with the correct item data.

6. `test_unlock_includes_per_player_items()` — Verifies that `unlock_room()` also includes per-player items (lantern/tide_medallion) in the reveal — or documents that it doesn't (current code only reveals `dungeon_items` in `unlock_room`, not `per_player_items`).

7. `test_locked_room_cleared_after_unlock()` — After `unlock_room()`, asserts `room_id not in game.locked_rooms`.

## Edge Cases

- **Per-player items in unlock message**: `unlock_room()` currently only attaches `dungeon_items`, not `per_player_items`. The test should document this behavior. Per-player items (lantern) become visible on the next `room_enter` message after unlock, not in the `doors_unlocked` broadcast itself. This is correct because per-player visibility depends on the player's flags.

- **Empty trap room (no monsters)**: Not tested here — trap rooms always have monsters by design (hard/challenging tiers guarantee monster templates).

- **Treasure cell as entrance/sanctum**: Not possible — entrance and sanctum are hard-excluded from both treasure placement and trap assignment.

- **Re-resolve after clear**: If a room is re-resolved after being cleared, items are re-placed but `cleared_rooms` prevents re-locking. Not tested here (separate concern).

## Files Changed

| File | Change |
|------|--------|
| `tools/test_treasure_trap.py` | **NEW** — all tests |
| (no other files) | Test-only card, no game logic changes |
