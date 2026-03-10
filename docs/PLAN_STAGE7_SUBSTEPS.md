# Stage 7 Implementation Sub-steps

Detailed implementation plan for **Stage 7: Library-Managed Dungeon Generation (Lazy)** from [PLAN_AI_GENERATION.md](PLAN_AI_GENERATION.md).

## Overview

Transform the dungeon system from "pick random templates and build all rooms instantly" to "assign library entries (precreated or custom) to cells, then lazily resolve custom rooms on player entry."

## Implementation Order

Steps are ordered by dependency — each builds on the previous.

---

### Step 1: Wire Content Libraries into GameState & Startup

**Files:** `server/state.py`, `mud_server.py`

- Add `monster_library`, `tile_library`, `room_library` fields to `GameState`
- In `main()`, create the 3 `ContentLibrary` instances, call
  `load_precreated_content()`, load custom entries from `data/*.json`
- Currently only `content_viewer.py` does this — move the same logic into
  the main server startup

**Test:** Server starts, logs library sizes
(e.g., `Libraries: monster 4/8, tile 7/14, room 64/96`).

---

### Step 2: Register All Precreated Content in Game Registries

**Files:** `server/dungeon_content.py`, possibly `server/validation.py`

- Extend `register_precreated_types()` to register **all 4 monsters**
  (including skeleton/bat sprites) and **all 7 tiles** into
  `game.custom_sprites`, `game.custom_tile_recipes`, etc.
- Library rooms use string tile codes (`"DW"`, `"DF"`) not numeric IDs,
  so tile recipes must be in `custom_tile_recipes` for `send_room_enter()`
  to send them to clients
- May need to relax tile ID validation regex to allow uppercase codes

**Why:** Stage 6.5 Option B says all dungeon content goes through the
custom registry pipeline. Skeleton/bat sprites and DW/DF/etc. tile recipes
need to be server-side data, not just hardcoded client rendering.

---

### Step 3: Refactor DungeonInstance Data Structure

**Files:** `server/dungeons.py`

- Add `cell_assignments` dict: `(col, row) → {source, entry, resolved}`
- Add `resolved_rooms` set
- Track which cells are precreated vs custom

---

### Step 4: Rewrite `create_dungeon()` — Instant, No API

**Files:** `server/dungeons.py`

1. Pick layout (existing logic)
2. Flag ~50% of cells as precreated, ~50% as custom
3. Precreated → random pick from permanent room library entries
4. Custom → pull from custom library slots (real entries or placeholders)
5. Only create `game.rooms[]` entry for the entrance room (others deferred)
6. Resolve entrance immediately (if placeholder, one blocking
   `generate_room()` call with fallback)
7. Player enters dungeon immediately

**Key change:** Current `create_dungeon()` builds all `game.rooms[]` entries
up front. New version only builds the entrance; the rest are deferred.

---

### Step 5: Implement `resolve_dungeon_room()`

**Files:** `server/dungeons.py`

New async function that materializes a library entry into a live
`game.rooms[]` entry:

- **Precreated rooms:** Apply tilemap, wall off unused exits, place stairs,
  register monsters from `monster_placements`
- **Custom rooms (real library entry):** Same, plus **late-bind** any
  expired monster/tile references via tag-overlap fallback
- **Custom rooms (placeholder):** Call `generate_room()`, add results to
  libraries. On API failure, fall back to a random permanent room
- Add a per-cell lock/flag to prevent double-resolution if two players
  enter simultaneously

---

### Step 6: Modify `do_room_transition()` for Lazy Resolution

**Files:** `server/lifecycle.py`

- When transitioning to a dungeon room not yet in `game.rooms`, call
  `resolve_dungeon_room()`
- Send `{"type": "room_generating"}` to the player before async generation
  starts (custom cells only)
- Precreated rooms resolve instantly — no loading screen

---

### Step 7: Add Expiry to `destroy_dungeon()`

**Files:** `server/dungeons.py`, `server/content_library.py`

- After cleaning up rooms, expire ~10% of oldest custom entries per library
  (skip permanent, 24h minimum age)
- Clean up expired monsters/tiles from game registries
  (`game.monster_stats`, `game.custom_sprites`, etc.)
- Save all libraries to disk
- Constants: `EXPIRY_RATE = 0.10`, `EXPIRY_MIN_AGE = 86400` (24h)
- Test overrides: `EXPIRY_RATE = 0.50`, `EXPIRY_MIN_AGE = 5`

---

### Step 8: Persist Libraries After Generation

**Files:** `server/dungeons.py`

- After any `generate_room()` produces new content, `.save()` all three
  libraries to `data/*.json`
- Ensures generated content survives server restarts

---

### Step 9: Client — "Conjuring" Loading Animation

**Files:** `client/net.js`, `client/renderer.js`, `client/game_state.js`,
`client/client.html`

- Handle `room_generating` message → set `G.conjuring` state
- Render dark overlay with flickering torchlight, drifting particles,
  atmospheric text ("The dungeon shifts..." / "Dark forces stir...")
- Minimum 1.5s duration — if `room_enter` arrives sooner, queue it until
  timer expires
- Only on first-visit custom rooms; precreated and revisited rooms use
  the normal slide transition

---

### Step 10: Client — Dungeon Debug Panel

**Files:** `client/renderer.js`, `client/net.js`, `client/game_state.js`

- Server attaches `dungeon_debug` object to `room_enter` for dungeon rooms:
  - `lib_rooms`: `"72/96"`, `lib_monsters`: `"6/8"`, `lib_tiles`: `"10/14"`
  - `room_source`: `"precreated"` / `"custom (library)"` /
    `"custom (generated)"` / `"fallback"`
  - `gen_time`, `gen_tokens` (if generated)
  - `api_calls_today`, `api_cost`
- Display in backtick debug overlay, only for dungeon rooms

---

### Step 11: Verbose `[GEN]` Server Logging

**Files:** Throughout `server/dungeons.py`, `server/lifecycle.py`

- Log layout choice, cell counts (precreated vs custom)
- Log each room resolution: source, timing, fallback usage
- Log expiry results per library
- Log library saves

---

## Known Risks & Mitigations

| Risk | Mitigation |
|---|---|
| **Race condition:** Two players enter same unresolved room simultaneously | Per-cell resolving lock/flag in `resolve_dungeon_room()` |
| **String vs numeric tile IDs:** Library rooms use strings; engine uses numeric | Bridge already works (`is_walkable_tile`, `send_room_enter`, `getTileCanvas`). May need to update `getExitDirs()` in `renderer.js` |
| **Entrance blocking:** Placeholder entrance requires synchronous generation | One unavoidable blocking call; falls back to permanent room on failure |
| **Tile ID validation:** Precreated tiles use uppercase codes (DW, DF) | Relax `validate_tile()` regex or register directly into registries |
| **Client tile cache:** Expired tiles stay in `customTiles` until page reload | Harmless — caches are additive, never cause errors |

## Flow Diagram

```
Player enters dungeon → layout assigned (instant)
  → entrance room: precreated → instant → player is in

Player walks north → first visit, precreated room
  → instant (precreated rooms never need generation)

Player walks east → first visit, custom room (real library entry)
  → conjuring animation (1.5s cosmetic) → instant resolution

Player walks south → first visit, custom room (placeholder)
  → conjuring animation → generate_room() API call (~1-2s)
  → room + any new monsters/tiles added to libraries → player is in

Player walks north back → already visited → normal slide transition

API is down? → custom placeholder falls back to one of 32 fallback rooms
```
