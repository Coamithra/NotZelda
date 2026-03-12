"""Dungeon instance system — procedurally generated dungeon layouts."""

import asyncio
import os
import random
import time

from server.state import game
from server.constants import (
    STAIRS_UP, EDGE_SPAWN_POINTS, DEFAULT_SPAWN, DUNGEON_MUSIC_TRACKS,
)
from server.dungeon_layouts import DUNGEON_LAYOUTS
from server.net import players_in_room, broadcast_debug


class DungeonInstance:
    def __init__(self, dungeon_id, layout, room_map, active_rooms, entrance_room_id, music_track):
        self.dungeon_id = dungeon_id
        self.layout = layout
        self.room_map = room_map           # (col, row) -> template_id
        self.active_rooms = active_rooms   # set of room_id strings
        self.cleared_rooms = set()         # room_ids where all monsters killed
        self.entrance_room_id = entrance_room_id
        self.music_track = music_track

        # Stage 7: Library-managed cell tracking
        # (col, row) -> {"source": "precreated"|"custom", "entry": LibraryEntry|None, "resolved": bool}
        self.cell_assignments = {}
        self.resolved_rooms = set()        # room_ids that have been materialized into game.rooms

        # Custom slot pool — shared pool of room content for custom cells.
        # Each slot: {"data": dict, "entry": LibraryEntry} or None (needs generation).
        # Custom cells pick a random slot at resolution time.
        self.custom_slots = []


def _get_cell_exits(cell, room_map, layout, entrance_col, entrance_row):
    """Compute exits for a cell based on layout adjacency."""
    col, row = cell
    exits = {}
    if (col, row - 1) in room_map:
        exits["north"] = f"d1_{col}_{row - 1}"
    if (col, row + 1) in room_map:
        exits["south"] = f"d1_{col}_{row + 1}"
    if (col - 1, row) in room_map:
        exits["west"] = f"d1_{col - 1}_{row}"
    if (col + 1, row) in room_map:
        exits["east"] = f"d1_{col + 1}_{row}"
    if col == entrance_col and row == entrance_row:
        exits["up"] = "clearing"
    return exits


def _resolve_room_from_entry(room_id, entry_data, exits, cell, music_track, is_entrance):
    """Materialize a library entry's data into a live game.rooms[] entry.

    entry_data: dict with 'name', 'tilemap' (list[list[str]]), 'monster_placements'
    """
    # Deep-copy tilemap (string tile codes)
    tilemap = [list(r) for r in entry_data["tilemap"]]
    col, row = cell

    # Wall off unused exits (use string tile code "DW")
    wall_tile = "DW"
    if "north" not in exits:
        for c in (6, 7, 8):
            tilemap[0][c] = wall_tile
    if "south" not in exits:
        for c in (6, 7, 8):
            tilemap[10][c] = wall_tile
    if "west" not in exits:
        for r in (4, 5, 6):
            tilemap[r][0] = wall_tile
    if "east" not in exits:
        for r in (4, 5, 6):
            tilemap[r][14] = wall_tile

    # Entrance gets stairs up (use numeric constant — client knows how to render it)
    if is_entrance:
        tilemap[9][7] = STAIRS_UP

    # Build spawn points
    spawn_points = {"default": DEFAULT_SPAWN}
    for direction, pos in EDGE_SPAWN_POINTS.items():
        if direction in exits:
            spawn_points[direction] = pos
    # Scan for stairs (numeric or string)
    for ry, trow in enumerate(tilemap):
        for rx, tile in enumerate(trow):
            if tile == STAIRS_UP or tile == "SU":
                spawn_points["down"] = (rx, ry)

    game.rooms[room_id] = {
        "name": entry_data.get("name", "Dungeon Room"),
        "exits": exits,
        "tilemap": tilemap,
        "spawn_points": spawn_points,
        "biome": "dungeon",
        "music": music_track,
    }

    # Register monster templates from placements
    placements = entry_data.get("monster_placements", [])
    if placements:
        game.monster_templates[room_id] = [
            {"kind": p["kind"], "x": p["x"], "y": p["y"]}
            for p in placements
        ]


async def create_dungeon() -> DungeonInstance | None:
    """Create a new dungeon instance using library-managed content.

    Picks a random layout, assigns library entries to each cell (~50% precreated,
    ~50% custom), but only resolves the entrance room immediately. Other rooms
    are resolved lazily when a player enters them.
    """
    layout = random.choice(DUNGEON_LAYOUTS)
    music_track = random.choice(DUNGEON_MUSIC_TRACKS)

    # Find all active cells in layout
    active_cells = []
    for row_idx, row_str in enumerate(layout["grid"]):
        for col_idx, ch in enumerate(row_str):
            if ch == "X":
                active_cells.append((col_idx, row_idx))

    if not game.room_library or game.room_library.real_count == 0:
        print("[DUNGEON] No room library entries, cannot create dungeon")
        return None

    entrance_col, entrance_row = layout["entrance"]
    entrance_room_id = f"d1_{entrance_col}_{entrance_row}"
    active_rooms = set()
    room_map = {}
    cell_assignments = {}

    # Assign library entries to cells
    permanent_entries = [e for e in game.room_library.real_entries if e.permanent]
    custom_entries = [e for e in game.room_library.real_entries if not e.permanent]
    has_placeholders = game.room_library.placeholder_count > 0
    max_custom_slots = 15

    random.shuffle(permanent_entries)
    random.shuffle(custom_entries)

    # Shuffle cells so precreated/custom rooms are spatially distributed
    random.shuffle(active_cells)

    # Split: entrance always precreated, ~50% of rest are custom
    non_entrance = [c for c in active_cells if not (c[0] == entrance_col and c[1] == entrance_row)]
    if custom_entries or has_placeholders:
        num_custom = len(non_entrance) // 2
    else:
        num_custom = 0
    custom_cell_set = set(non_entrance[:num_custom])

    perm_idx = 0
    for cell in active_cells:
        room_id = f"d1_{cell[0]}_{cell[1]}"
        active_rooms.add(room_id)
        room_map[cell] = room_id

        if cell in custom_cell_set:
            cell_assignments[cell] = {"source": "custom", "resolved": False}
        else:
            entry = permanent_entries[perm_idx % len(permanent_entries)]
            perm_idx += 1
            cell_assignments[cell] = {"source": "precreated", "entry": entry, "resolved": False}

    # Build custom slot pool: pre-fill with existing custom library entries, rest need generation
    if has_placeholders:
        num_slots = max_custom_slots
    else:
        num_slots = min(len(custom_entries), max_custom_slots)
    custom_slots = []
    for i in range(num_slots):
        if i < len(custom_entries):
            custom_slots.append({"data": custom_entries[i].data, "entry": custom_entries[i]})
        else:
            custom_slots.append(None)
    random.shuffle(custom_slots)

    instance = DungeonInstance(
        dungeon_id="d1",
        layout=layout,
        room_map=room_map,
        active_rooms=active_rooms,
        entrance_room_id=entrance_room_id,
        music_track=music_track,
    )
    instance.cell_assignments = cell_assignments
    instance.custom_slots = custom_slots
    game.active_dungeon = instance

    # Logging
    precreated_count = sum(1 for a in cell_assignments.values() if a["source"] == "precreated")
    custom_count = sum(1 for a in cell_assignments.values() if a["source"] == "custom")
    filled_slots = sum(1 for s in custom_slots if s is not None)
    empty_slots = num_slots - filled_slots

    print(f"[DUNGEON] Created instance: layout={layout['name']}, "
          f"rooms={len(active_rooms)} ({precreated_count}p/{custom_count}c), "
          f"slots={num_slots} ({filled_slots}filled/{empty_slots}empty), "
          f"entrance={entrance_room_id}, music={music_track}")
    broadcast_debug(f"Dungeon created: {layout['name']} ({len(active_rooms)} rooms, {precreated_count}p/{custom_count}c)")

    # Resolve the entrance room immediately (always precreated, so instant)
    resolve_dungeon_room(instance, (entrance_col, entrance_row))

    return instance


def resolve_dungeon_room(instance: DungeonInstance, cell: tuple) -> bool:
    """Materialize a library entry into a live game.rooms[] entry.

    For precreated entries, uses the pre-assigned library entry.
    For custom entries, picks from the shared pool; falls back to precreated
    if the pool is exhausted or the slot was a placeholder.
    Fully synchronous — no AI generation, no awaits.
    """
    assignment = instance.cell_assignments.get(cell)
    if not assignment or assignment["resolved"]:
        return True  # already resolved

    col, row = cell
    room_id = f"d1_{col}_{row}"
    entrance_col, entrance_row = instance.layout["entrance"]
    is_entrance = (col == entrance_col and row == entrance_row)

    exits = _get_cell_exits(cell, {c: True for c in instance.cell_assignments},
                            instance.layout, entrance_col, entrance_row)

    if assignment["source"] == "precreated":
        entry_data = assignment["entry"].data
        source_label = f"precreated:{assignment['entry'].id}"
    else:
        # Custom cell — pick a random slot from the shared pool
        entry_data, source_label = _resolve_custom_slot(
            instance, assignment, room_id)
        if entry_data is None:
            return False

    _resolve_room_from_entry(room_id, entry_data, exits, cell, instance.music_track, is_entrance)

    assignment["resolved"] = True
    instance.resolved_rooms.add(room_id)
    print(f"[DUNGEON] Resolved {room_id} ({source_label})")
    return True


def _resolve_custom_slot(instance, assignment, room_id):
    """Pop a slot from the custom pool and use its content.

    Each cell gets a unique slot (popped, not shared).
    Falls back to a precreated room if the pool is exhausted or the slot
    was a placeholder (empty). Background regen fills placeholders later.
    Returns (entry_data, source_label) on success, or (None, None) on failure.
    """
    # Pop a slot from the pool (already shuffled at dungeon creation)
    if instance.custom_slots:
        slot = instance.custom_slots.pop()
    else:
        slot = None  # pool exhausted

    # Slot has existing content — use it directly
    if slot is not None and slot.get("data") is not None:
        entry = slot.get("entry")
        entry_id = entry.id if entry else "unknown"
        assignment["entry"] = entry
        return slot["data"], f"custom:{entry_id}"

    # Pool exhausted or empty slot — fall back to a precreated room
    reason = "pool exhausted" if slot is None else "empty slot"
    if game.room_library:
        used_ids = {a.get("entry").id for a in instance.cell_assignments.values()
                    if a.get("entry") is not None}
        available = [e for e in game.room_library.real_entries
                     if e.permanent and e.id not in used_ids]
        if not available:
            # All permanent rooms used — allow duplicates as last resort
            available = [e for e in game.room_library.real_entries if e.permanent]
        if available:
            pick = random.choice(available)
            assignment["entry"] = pick
            print(f"[DUNGEON] {reason} for {room_id}, using precreated '{pick.id}'")
            return pick.data, f"precreated-overflow:{pick.id}"

    return None, None


def _save_libraries():
    """Persist all content libraries and deprecated sets to disk."""
    from pathlib import Path
    data_dir = Path(__file__).parent.parent / "data"
    if game.monster_library:
        game.monster_library.save(data_dir / "monster_library.json")
    if game.tile_library:
        game.tile_library.save(data_dir / "tile_library.json")
    if game.room_library:
        game.room_library.save(data_dir / "room_library.json")
    _save_deprecated_sets()
    print("[DUNGEON] Libraries saved to disk")


def _save_deprecation_timestamp():
    """Persist the last deprecation timestamp to disk."""
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "data" / "deprecation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_deprecation_time": game.last_deprecation_time}), encoding="utf-8")


def load_deprecation_timestamp():
    """Load the last deprecation timestamp from disk (call at startup)."""
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "data" / "deprecation.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        game.last_deprecation_time = data.get("last_deprecation_time", 0.0)
        print(f"[DEPRECATION] Last deprecation: {time.strftime('%Y-%m-%d %H:%M', time.localtime(game.last_deprecation_time))}")


def _save_deprecated_sets():
    """Persist deprecated monster/tile IDs to disk."""
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "data" / "deprecated.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "monsters": sorted(game.deprecated_monsters),
        "tiles": sorted(game.deprecated_tiles),
    }), encoding="utf-8")


def load_deprecated_sets():
    """Load deprecated monster/tile IDs from disk (call at startup)."""
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "data" / "deprecated.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        game.deprecated_monsters = set(data.get("monsters", []))
        game.deprecated_tiles = set(data.get("tiles", []))
        if game.deprecated_monsters or game.deprecated_tiles:
            print(f"[DEPRECATION] Loaded deprecated: {len(game.deprecated_monsters)} monsters, {len(game.deprecated_tiles)} tiles")


def get_active_content_lists():
    """Build monster/tile lists for AI prompts, excluding deprecated entries."""
    monsters = []
    if game.monster_library:
        for e in game.monster_library.real_entries:
            if e.id not in game.deprecated_monsters:
                monsters.append({"kind": e.id, "tags": e.tags})
    tiles = []
    if game.tile_library:
        for e in game.tile_library.real_entries:
            if e.id not in game.deprecated_tiles:
                tiles.append({"id": e.id, "walkable": e.data.get("walkable", False), "tags": e.tags})
    return monsters, tiles


def _get_referenced_ids(room_library):
    """Scan all rooms in the library for referenced monster kinds and tile IDs."""
    referenced_monsters = set()
    referenced_tiles = set()
    if not room_library:
        return referenced_monsters, referenced_tiles
    for entry in room_library.real_entries:
        data = entry.data
        for p in data.get("monster_placements", []):
            referenced_monsters.add(p["kind"])
        for row in data.get("tilemap", []):
            for tid in row:
                if isinstance(tid, str):
                    referenced_tiles.add(tid)
    return referenced_monsters, referenced_tiles


def _cleanup_monster(mid):
    """Fully remove a monster from game registries."""
    game.monster_stats.pop(mid, None)
    game.custom_sprites.pop(mid, None)
    game.custom_death_sprites.pop(mid, None)
    game.monster_behaviors.pop(mid, None)
    game.deprecated_monsters.discard(mid)


def _cleanup_tile(tid):
    """Fully remove a tile from game registries."""
    game.custom_tile_recipes.pop(tid, None)
    game.custom_walkable_tiles.discard(tid)
    game.deprecated_tiles.discard(tid)


def destroy_dungeon():
    """Tear down the active dungeon instance. Content deprecation is handled by the daily task."""
    if game.active_dungeon is None:
        return

    for room_id in game.active_dungeon.active_rooms:
        game.rooms.pop(room_id, None)
        game.guards.pop(room_id, None)
        game.monster_templates.pop(room_id, None)
        game.room_monsters.pop(room_id, None)
        game.room_cooldowns.pop(room_id, None)
        game.room_hearts.pop(room_id, None)
        game.room_projectiles.pop(room_id, None)

    layout_name = game.active_dungeon.layout['name']
    print(f"[DUNGEON] Destroyed instance: layout={layout_name}")
    broadcast_debug(f"Dungeon destroyed ({layout_name})")
    game.active_dungeon = None

    # Run daily content deprecation if enough time has passed
    _maybe_run_deprecation()


DEPRECATION_INTERVAL = 86400  # 24 hours between deprecation passes


def _maybe_run_deprecation():
    """Run content deprecation if at least 24 hours have passed since the last run."""
    now = time.time()
    if now - game.last_deprecation_time < DEPRECATION_INTERVAL:
        elapsed = now - game.last_deprecation_time
        remaining = DEPRECATION_INTERVAL - elapsed
        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        print(f"[DEPRECATION] Skipped — next pass in {hours}h{mins}m")
        broadcast_debug(f"Deprecation: next pass in {hours}h{mins}m")
        return
    broadcast_debug("Deprecation: starting pass...")
    num_expired = _run_content_deprecation()
    game.last_deprecation_time = now
    _save_deprecation_timestamp()

    # Start background regen to refill expired slots (skip in debug mode — use /regen)
    is_debug = os.environ.get("DEBUG_MODE", "").lower() in ("1", "true")
    if num_expired > 0:
        if is_debug:
            broadcast_debug(f"Regen: skipped (debug mode) — use /regen {num_expired}")
        else:
            start_background_regen(num_expired)


def _deprecate_oldest(library, deprecated_set):
    """Mark the oldest 10% of non-deprecated custom entries as deprecated.

    Entries stay in the library and game registries — they're just excluded
    from AI prompts via get_active_content_lists(). Returns newly deprecated IDs.
    """
    import math
    if not library:
        return []
    candidates = [
        (e.created_at, e.id) for e in library.real_entries
        if not e.permanent and e.id not in deprecated_set
    ]
    if not candidates:
        return []
    candidates.sort()
    count = max(1, math.ceil(len(candidates) * 0.10))
    count = min(count, len(candidates))
    newly = [cid for _, cid in candidates[:count]]
    deprecated_set.update(newly)
    return newly


def _run_content_deprecation():
    """Execute one round of content deprecation. Returns count of expired rooms.

    Rooms: oldest 10% are expired (removed from library).
    Monsters/tiles: oldest 10% are deprecated (kept in library + registries,
      but excluded from AI prompts). They're only fully removed once no room
      in the library references them anymore.
    """
    # Step 1: Expire oldest 10% of custom rooms
    expired_rooms = []
    if game.room_library:
        expired_rooms = game.room_library.expire_oldest()
        if expired_rooms:
            print(f"[DEPRECATION] Expired rooms: {expired_rooms}")
            broadcast_debug(f"Expired {len(expired_rooms)} room(s): {', '.join(expired_rooms)}")

    # Step 2: Deprecate oldest 10% of custom monsters/tiles
    #   Marked as deprecated (excluded from AI prompts) but kept in library
    #   and registries so existing rooms still work.
    newly_dep_m = _deprecate_oldest(game.monster_library, game.deprecated_monsters)
    newly_dep_t = _deprecate_oldest(game.tile_library, game.deprecated_tiles)
    for mid in newly_dep_m:
        print(f"[DEPRECATION] Deprecated monster '{mid}'")
        broadcast_debug(f"Monster '{mid}' deprecated")
    for tid in newly_dep_t:
        print(f"[DEPRECATION] Deprecated tile '{tid}'")
        broadcast_debug(f"Tile '{tid}' deprecated")

    # Step 3: Scan remaining rooms for referenced monster/tile IDs
    ref_monsters, ref_tiles = _get_referenced_ids(game.room_library)

    # Step 4: Fully remove unreferenced custom monsters/tiles
    #   (from both library and game registries)
    removed_monsters = []
    if game.monster_library:
        for entry in list(game.monster_library.real_entries):
            if not entry.permanent and entry.id not in ref_monsters:
                game.monster_library.remove(entry.id)
                _cleanup_monster(entry.id)
                removed_monsters.append(entry.id)
                print(f"[DEPRECATION] Removed monster '{entry.id}' (unreferenced)")
                broadcast_debug(f"Monster '{entry.id}' removed")

    removed_tiles = []
    if game.tile_library:
        for entry in list(game.tile_library.real_entries):
            if not entry.permanent and entry.id not in ref_tiles:
                game.tile_library.remove(entry.id)
                _cleanup_tile(entry.id)
                removed_tiles.append(entry.id)
                print(f"[DEPRECATION] Removed tile '{entry.id}' (unreferenced)")
                broadcast_debug(f"Tile '{entry.id}' removed")

    # Also clean up deprecated IDs that aren't in the library at all
    # (edge case: entry was in deprecated set but already removed from library)
    stale_m = {mid for mid in game.deprecated_monsters if mid not in ref_monsters}
    for mid in stale_m:
        _cleanup_monster(mid)
    stale_t = {tid for tid in game.deprecated_tiles if tid not in ref_tiles}
    for tid in stale_t:
        _cleanup_tile(tid)

    # Save libraries to disk
    _save_libraries()

    # Summary
    removed_count = len(removed_monsters) + len(removed_tiles) + len(stale_m) + len(stale_t)
    dep_count = len(newly_dep_m) + len(newly_dep_t)
    if expired_rooms or dep_count > 0 or removed_count > 0:
        print(f"[DEPRECATION] Complete: {len(expired_rooms)} rooms expired, "
              f"{len(newly_dep_m)}M {len(newly_dep_t)}T deprecated, "
              f"{removed_count} removed")
        broadcast_debug(f"Deprecation done: {len(expired_rooms)}R expired, "
                        f"{len(newly_dep_m)}M {len(newly_dep_t)}T deprecated, "
                        f"{removed_count} removed")
    else:
        print("[DEPRECATION] Nothing to deprecate")
        broadcast_debug("Deprecation: nothing to expire")

    return len(expired_rooms)


def start_background_regen(num_rooms):
    """Start background content generation to refill libraries.

    Takes a snapshot of library state synchronously (before any await),
    then hands it to the async task. The task never reads from game.* —
    it only writes at the very end via _apply_staged_content().
    """
    if game.regen_task is not None and not game.regen_task.done():
        print("[REGEN] Already in progress, skipping")
        broadcast_debug("Regen: already in progress")
        return
    if num_rooms <= 0:
        return

    # Snapshot everything synchronously before launching the task
    existing_monsters, existing_tiles = get_active_content_lists()
    existing_room_names = [
        e.data.get("name", e.id) for e in game.room_library.real_entries
    ]
    snapshot = {
        "existing_monsters": existing_monsters,
        "existing_tiles": existing_tiles,
        "existing_room_names": existing_room_names,
        "monster_count": game.monster_library.real_count if game.monster_library else 0,
        "monster_cap": game.monster_library.capacity if game.monster_library else 0,
        "tile_count": game.tile_library.real_count if game.tile_library else 0,
        "tile_cap": game.tile_library.capacity if game.tile_library else 0,
    }

    game.regen_task = asyncio.create_task(_background_regen(num_rooms, snapshot))


async def _background_regen(num_rooms, snapshot):
    """Generate rooms in the background to refill libraries after deprecation.

    Uses only the provided snapshot — never reads from game.* directly.
    Applies all results at the end via _apply_staged_content().
    """
    from server import ai_generator

    print(f"[REGEN] Starting background generation of {num_rooms} room(s)...")
    broadcast_debug(f"Regen: generating {num_rooms} room(s)...")
    staged = []

    # Progress callback — sends each AI step to the debug panel
    async def on_progress(step, detail=""):
        broadcast_debug(f"  {detail}" if detail else f"  {step}")

    # Unpack snapshot into local working copies
    existing_monsters = snapshot["existing_monsters"]
    existing_tiles = snapshot["existing_tiles"]
    existing_room_names = snapshot["existing_room_names"]
    monster_count = snapshot["monster_count"]
    monster_cap = snapshot["monster_cap"]
    tile_count = snapshot["tile_count"]
    tile_cap = snapshot["tile_cap"]

    for i in range(num_rooms):
        broadcast_debug(f"Regen: room {i+1}/{num_rooms}...")
        try:
            result = await ai_generator.generate_room(
                theme="dungeon",
                difficulty=random.randint(3, 7),
                existing_monsters=existing_monsters,
                existing_tiles=existing_tiles,
                monster_library_full=(monster_count >= monster_cap),
                tile_library_full=(tile_count >= tile_cap),
                existing_room_names=existing_room_names,
                monster_library_count=monster_count,
                monster_library_capacity=monster_cap,
                tile_library_count=tile_count,
                tile_library_capacity=tile_cap,
                progress=on_progress,
            )
        except Exception as e:
            print(f"[REGEN] Room {i+1}/{num_rooms} failed: {type(e).__name__}: {e}")
            broadcast_debug(f"Regen {i+1}/{num_rooms}: FAILED ({type(e).__name__})")
            continue

        if result is None:
            print(f"[REGEN] Room {i+1}/{num_rooms} returned None, skipping")
            broadcast_debug(f"Regen {i+1}/{num_rooms}: empty result, skipped")
            continue

        staged.append(result)

        # Update snapshot so next room sees what we've generated
        for m in result.get("new_monsters", []):
            existing_monsters.append({"kind": m["kind"], "tags": m.get("tags", [])})
            monster_count += 1
        for t in result.get("new_tiles", []):
            existing_tiles.append({
                "id": t["id"], "walkable": t.get("walkable", False),
                "tags": t.get("tags", []),
            })
            tile_count += 1
        existing_room_names.append(result.get("name", "Unknown"))

        # Summarize what this room produced
        new_m = [m["kind"] for m in result.get("new_monsters", [])]
        new_t = [t["id"] for t in result.get("new_tiles", [])]
        detail = result.get("name", "?")
        if new_m:
            detail += f" +{','.join(new_m)}"
        if new_t:
            detail += f" +{','.join(new_t)}"
        print(f"[REGEN] Room {i+1}/{num_rooms} generated: \"{result.get('name', '?')}\"")
        broadcast_debug(f"Regen {i+1}/{num_rooms}: {detail}")

    if staged:
        _apply_staged_content(staged)
    else:
        print("[REGEN] No rooms generated successfully")
        broadcast_debug("Regen: no rooms generated")

    game.regen_task = None


def _apply_staged_content(results):
    """Register staged content into game registries and libraries.

    Fully synchronous — no awaits — so no interleaving with other coroutines.
    """
    from server.validation import register_monster_type, register_tile_type
    from server.content_library import LibraryEntry

    total_monsters = 0
    total_tiles = 0
    total_rooms = 0

    for result in results:
        # Register new monsters
        for m in result.get("new_monsters", []):
            ok, errors = register_monster_type(m)
            if ok:
                added = game.monster_library.add(LibraryEntry(
                    id=m["kind"], content_type="monster",
                    tags=m.get("tags", []), created_at=time.time(), data=m,
                ))
                if added:
                    total_monsters += 1
            else:
                print(f"[REGEN] Monster registration failed for {m.get('kind')}: {errors}")

        # Register new tiles
        for t in result.get("new_tiles", []):
            ok, errors = register_tile_type(t)
            if ok:
                added = game.tile_library.add(LibraryEntry(
                    id=t["id"], content_type="tile",
                    tags=t.get("tags", []), created_at=time.time(), data=t,
                ))
                if added:
                    total_tiles += 1
            else:
                print(f"[REGEN] Tile registration failed for {t.get('id')}: {errors}")

        # Add room to library (deduplicate ID)
        room_name = result.get("name", "Unknown Room")
        lib_id = room_name.lower().replace(" ", "_")
        base_id = lib_id
        counter = 1
        while game.room_library.get_by_id(lib_id):
            counter += 1
            lib_id = f"{base_id}_{counter}"

        added = game.room_library.add(LibraryEntry(
            id=lib_id, content_type="room",
            tags=[], created_at=time.time(), data=result,
        ))
        if added:
            total_rooms += 1

    _save_libraries()
    print(f"[REGEN] Applied staged content: {total_rooms} rooms, "
          f"{total_monsters} monsters, {total_tiles} tiles")
    broadcast_debug(f"Regen done: {total_rooms}R {total_monsters}M {total_tiles}T added")


def is_dungeon_room(room_id: str) -> bool:
    return game.active_dungeon is not None and room_id in game.active_dungeon.active_rooms


def dungeon_player_count() -> int:
    if game.active_dungeon is None:
        return 0
    return sum(1 for p in game.players.values() if p.room in game.active_dungeon.active_rooms)
