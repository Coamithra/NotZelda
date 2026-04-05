# Plan: Scary Boss Doorway Tile

**Card:** Scary boss doorway tile (Trello #69c9077b)
**Branch:** `feat-scary-boss-doorway-tile`

## Context

Dungeons currently give players no visual warning before they walk into the boss room. This feature adds a new decorative tile (`BD`) with a menacing monster face that appears at doorways leading to the boss room. It serves as a classic Zelda-style "danger ahead" signal, giving players a moment to prepare before entering.

## Approach

### 1. New tile definition — `data/tiles.json`

Add a `"BD"` (boss door) tile entry:
- `"walkable": true` — decorative, doesn't block movement
- Dark stone base color with a menacing face sprite rendered via rect layers
- The face: glowing red eyes, fanged mouth, carved into dark stone
- 16×16 pixel grid using `[colorKey, x, y, w, h]` rect layers

### 2. Placement logic — `server/dungeons.py` → `resolve_dungeon_room()`

After `_resolve_room_from_entry()` returns (tilemap is materialized, traps applied, locked doors placed), add a new block that:

1. Iterates each exit direction for the current cell using `_DIR_OFFSETS`
2. Checks if the neighbor cell in that direction is `instance.boss_cell`
3. If yes, places `BD` at the **center** doorway tile position (`DOORWAY_TILES[direction][1]`) — but only if:
   - The current tile at that position is walkable (not CD, LD, KD, or wall)
   - The direction exists in the room's exits

For **locked doorways** leading to the boss: the center doorway position will have `KD` (non-walkable). Instead, place `BD` one row/column inward from the center position:
- North: `(1, 7)` instead of `(0, 7)`
- South: `(9, 7)` instead of `(10, 7)`
- West: `(5, 1)` instead of `(5, 0)`
- East: `(5, 13)` instead of `(5, 14)`

This puts the menacing face tile right in front of the locked door — visible and walkable.

For **trap rooms** (boss room always traps): the doorway tiles become `CD` (closed door). Since the BD tile goes on the *approach side* (the room BEFORE the boss, not the boss room itself), this is usually not an issue. But if the approach room is also a trap room, the doorway tiles there also become CD. In that case, use the inward placement (same as locked doors) so BD appears in front of the closed door.

### 3. No client changes needed

The client's `runTileRecipe()` in `tiles.js` automatically renders any tile from its JSON recipe. The tile recipes are sent to the client on room enter via `custom_tiles` in the `room_enter` message. No client-side code changes required.

## Edge Cases

1. **Boss doorway is also locked**: Place BD inward, not on the locked door tiles themselves.
2. **Approach room is a trap room**: Doorway gets CD tiles during trap setup. Place BD inward.
3. **Boss room itself**: The boss room is always a trap room. We do NOT place BD inside the boss room — only on the approach side (the room before the boss).
4. **Entrance room leads to boss**: Unlikely with current topology (boss is placed far from entrance), but handle gracefully — place BD normally.
5. **Multiple exits lead to boss**: A room could theoretically have 2+ exits toward the boss cell (different cells adjacent to boss). Place BD at each.
6. **Sanctum room**: The room between boss and sanctum should NOT get a BD tile (the boss is already defeated when heading to the sanctum). Only place BD when looking FROM a non-boss cell TOWARD the boss cell.
7. **Re-resolution**: If a room is re-resolved (corrupted state recovery), BD gets placed again — this is fine since it's idempotent.

## Files Changed

| File | Change |
|------|--------|
| `data/tiles.json` | New `"BD"` tile entry with menacing face sprite |
| `server/dungeons.py` | BD placement logic in `resolve_dungeon_room()` |
