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
from server.net import players_in_room


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

    # Resolve the entrance room immediately (always precreated, so instant)
    await resolve_dungeon_room(instance, (entrance_col, entrance_row))

    return instance


async def resolve_dungeon_room(instance: DungeonInstance, cell: tuple, player=None) -> bool:
    """Materialize a library entry into a live game.rooms[] entry.

    For precreated entries, uses the pre-assigned library entry (instant).
    For custom entries, picks a random slot from the shared pool — generates if needed.
    player: optional Player object for sending progress updates (DEBUG_GENERATION).
    Returns True if successfully resolved.
    """
    assignment = instance.cell_assignments.get(cell)
    if not assignment or assignment["resolved"]:
        return True  # already resolved

    # Concurrency: if another coroutine is already resolving this cell, wait
    resolve_event = assignment.get("_resolve_event")
    if resolve_event is not None:
        await resolve_event.wait()
        return assignment["resolved"]

    # Mark cell as being resolved
    event = asyncio.Event()
    assignment["_resolve_event"] = event

    try:
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
            entry_data, source_label = await _resolve_custom_slot(
                instance, assignment, room_id, player)
            if entry_data is None:
                return False

        _resolve_room_from_entry(room_id, entry_data, exits, cell, instance.music_track, is_entrance)

        assignment["resolved"] = True
        instance.resolved_rooms.add(room_id)
        print(f"[DUNGEON] Resolved {room_id} ({source_label})")
        return True
    finally:
        event.set()


async def _resolve_custom_slot(instance, assignment, room_id, player=None):
    """Pop a slot from the custom pool and use/generate its content.

    Each cell gets a unique slot (popped, not shared).
    Returns (entry_data, source_label) on success, or (None, None) on failure.
    """
    # Pop a slot from the pool (already shuffled at dungeon creation)
    if instance.custom_slots:
        slot = instance.custom_slots.pop()
    else:
        slot = None  # pool exhausted — will generate fresh content

    # Slot has existing content — use it directly
    if slot is not None and slot.get("data") is not None:
        entry = slot.get("entry")
        entry_id = entry.id if entry else "unknown"
        assignment["entry"] = entry
        return slot["data"], f"custom:{entry_id}"

    # Empty slot or pool exhausted — generate new content
    entry_data, source_label = await _generate_slot_content(
        instance, room_id, player)

    if entry_data is not None:
        assignment["entry"] = instance._last_generated_entry
        return entry_data, source_label

    return None, None


async def _generate_slot_content(instance, room_id, player=None):
    """Generate a room via AI, with permanent fallback.

    On success, stores the resulting LibraryEntry on instance._last_generated_entry.
    Returns (entry_data, source_label) on success, or (None, None) on hard failure.
    """
    instance._last_generated_entry = None
    from server import ai_generator
    from server.validation import register_monster_type, register_tile_type
    from server.content_library import LibraryEntry
    from server.net import send_to

    # Progress callback — sends updates to the waiting player if DEBUG_MODE is on
    progress_cb = None
    if player and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
        async def progress_cb(step, detail):
            try:
                await send_to(player, {
                    "type": "room_generating_progress",
                    "step": step,
                    "detail": detail,
                })
            except Exception:
                pass  # player may have disconnected

        # Send backend info as first progress message
        backend = ai_generator.AI_BACKEND
        model = ai_generator.ANTHROPIC_MODEL
        label = f"{model} via {backend}" + (" (subscription)" if backend == "cli" else " (API)")
        await progress_cb("init", label)

    existing_monsters, existing_tiles = get_active_content_lists()
    existing_room_names = [
        e.data.get("name", e.id) for e in game.room_library.real_entries
    ]

    print(f"[DUNGEON] Generating room for {room_id} via AI...")
    result = await ai_generator.generate_room(
        theme="dungeon",
        difficulty=random.randint(3, 7),
        existing_monsters=existing_monsters,
        existing_tiles=existing_tiles,
        monster_library_full=game.monster_library.is_full,
        tile_library_full=game.tile_library.is_full,
        existing_room_names=existing_room_names,
        monster_library_count=game.monster_library.real_count,
        monster_library_capacity=game.monster_library.capacity,
        tile_library_count=game.tile_library.real_count,
        tile_library_capacity=game.tile_library.capacity,
        progress=progress_cb,
    )

    # Check if dungeon was destroyed while we were awaiting AI
    if game.active_dungeon is not instance:
        print(f"[DUNGEON] Dungeon destroyed during generation of {room_id}")
        return None, None

    if result is None:
        # AI generation failed — fall back to a random permanent room
        print(f"[DUNGEON] AI generation failed for {room_id}, using fallback")
        fallback = game.room_library.get_random_real()
        if fallback is None:
            print(f"[DUNGEON] ERROR: No fallback room for {room_id}")
            return None, None
        instance._last_generated_entry = fallback
        return fallback.data, f"fallback:{fallback.id}"

    # Register new monsters into game registries + library
    for m in result.get("new_monsters", []):
        ok, errors = register_monster_type(m)
        if ok:
            game.monster_library.add(LibraryEntry(
                id=m["kind"],
                content_type="monster",
                tags=m.get("tags", []),
                created_at=time.time(),
                data=m,
            ))
        else:
            print(f"[DUNGEON] Monster registration failed for {m.get('kind')}: {errors}")

    # Register new tiles into game registries + library
    for t in result.get("new_tiles", []):
        ok, errors = register_tile_type(t)
        if ok:
            game.tile_library.add(LibraryEntry(
                id=t["id"],
                content_type="tile",
                tags=t.get("tags", []),
                created_at=time.time(),
                data=t,
            ))
        else:
            print(f"[DUNGEON] Tile registration failed for {t.get('id')}: {errors}")

    # Add room to library (deduplicate ID)
    room_name = result.get("name", "Unknown Room")
    lib_id = room_name.lower().replace(" ", "_")
    base_id = lib_id
    counter = 1
    while game.room_library.get_by_id(lib_id):
        counter += 1
        lib_id = f"{base_id}_{counter}"

    room_entry = LibraryEntry(
        id=lib_id,
        content_type="room",
        tags=[],
        created_at=time.time(),
        data=result,
    )
    game.room_library.add(room_entry)
    instance._last_generated_entry = room_entry

    _save_libraries()

    new_m = [m["kind"] for m in result.get("new_monsters", [])]
    new_t = [t["id"] for t in result.get("new_tiles", [])]
    print(f"[DUNGEON] Generated {room_id}: \"{room_name}\" "
          f"(monsters={new_m}, tiles={new_t})")
    return result, f"generated:{lib_id}"


def _save_libraries():
    """Persist all content libraries to disk."""
    from pathlib import Path
    data_dir = Path(__file__).parent.parent / "data"
    if game.monster_library:
        game.monster_library.save(data_dir / "monster_library.json")
    if game.tile_library:
        game.tile_library.save(data_dir / "tile_library.json")
    if game.room_library:
        game.room_library.save(data_dir / "room_library.json")
    print("[DUNGEON] Libraries saved to disk")


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
    """Tear down the active dungeon instance and expire old custom content."""
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

    # Expire oldest custom rooms from the room library
    expired_rooms = []
    if game.room_library:
        expired_rooms = game.room_library.expire_oldest()
        if expired_rooms:
            print(f"[DUNGEON] Expired rooms: {expired_rooms}")

    # Expire oldest custom monsters/tiles from their libraries
    expired_monsters = []
    expired_tiles = []
    if game.monster_library:
        expired_monsters = game.monster_library.expire_oldest()
    if game.tile_library:
        expired_tiles = game.tile_library.expire_oldest()

    # Scan remaining rooms for referenced monster/tile IDs
    ref_monsters, ref_tiles = _get_referenced_ids(game.room_library)

    # Handle expired monsters: deprecate if still referenced, remove if not
    for mid in expired_monsters:
        if mid in ref_monsters:
            game.deprecated_monsters.add(mid)
            print(f"[DUNGEON] Deprecated monster '{mid}' (still referenced)")
        else:
            _cleanup_monster(mid)
            print(f"[DUNGEON] Removed monster '{mid}'")

    # Handle expired tiles: deprecate if still referenced, remove if not
    for tid in expired_tiles:
        if tid in ref_tiles:
            game.deprecated_tiles.add(tid)
            print(f"[DUNGEON] Deprecated tile '{tid}' (still referenced)")
        else:
            _cleanup_tile(tid)
            print(f"[DUNGEON] Removed tile '{tid}'")

    # Clean up previously deprecated entries that are no longer referenced
    stale_monsters = game.deprecated_monsters - ref_monsters
    for mid in stale_monsters:
        _cleanup_monster(mid)
        print(f"[DUNGEON] Cleaned up deprecated monster '{mid}'")

    stale_tiles = game.deprecated_tiles - ref_tiles
    for tid in stale_tiles:
        _cleanup_tile(tid)
        print(f"[DUNGEON] Cleaned up deprecated tile '{tid}'")

    # Save libraries to disk
    _save_libraries()

    print(f"[DUNGEON] Destroyed instance: layout={layout_name}")
    game.active_dungeon = None


def is_dungeon_room(room_id: str) -> bool:
    return game.active_dungeon is not None and room_id in game.active_dungeon.active_rooms


def dungeon_player_count() -> int:
    if game.active_dungeon is None:
        return 0
    return sum(1 for p in game.players.values() if p.room in game.active_dungeon.active_rooms)
