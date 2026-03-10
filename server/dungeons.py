"""Dungeon instance system — procedurally generated dungeon layouts."""

import asyncio
import random

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


def create_dungeon() -> DungeonInstance | None:
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
    # Split: ~50% precreated, ~50% custom (placeholder or real custom)
    permanent_entries = [e for e in game.room_library.real_entries if e.permanent]
    custom_entries = [e for e in game.room_library.real_entries if not e.permanent]
    has_placeholders = game.room_library.placeholder_count > 0

    random.shuffle(permanent_entries)
    random.shuffle(custom_entries)

    # Decide per-cell: entrance always gets a precreated room
    perm_idx = 0
    custom_idx = 0
    for cell in active_cells:
        room_id = f"d1_{cell[0]}_{cell[1]}"
        active_rooms.add(room_id)
        room_map[cell] = room_id  # legacy compat — now maps cell to room_id

        is_entrance = (cell[0] == entrance_col and cell[1] == entrance_row)

        if is_entrance or not custom_entries and not has_placeholders:
            # Use precreated
            entry = permanent_entries[perm_idx % len(permanent_entries)]
            perm_idx += 1
            cell_assignments[cell] = {"source": "precreated", "entry": entry, "resolved": False}
        elif random.random() < 0.5 and custom_entries:
            # Use existing custom entry
            entry = custom_entries[custom_idx % len(custom_entries)]
            custom_idx += 1
            cell_assignments[cell] = {"source": "custom", "entry": entry, "resolved": False}
        elif has_placeholders:
            # Placeholder — will need generation later
            cell_assignments[cell] = {"source": "custom", "entry": None, "resolved": False}
        else:
            # Fallback to precreated
            entry = permanent_entries[perm_idx % len(permanent_entries)]
            perm_idx += 1
            cell_assignments[cell] = {"source": "precreated", "entry": entry, "resolved": False}

    instance = DungeonInstance(
        dungeon_id="d1",
        layout=layout,
        room_map=room_map,
        active_rooms=active_rooms,
        entrance_room_id=entrance_room_id,
        music_track=music_track,
    )
    instance.cell_assignments = cell_assignments
    game.active_dungeon = instance

    # Count sources for logging
    precreated_count = sum(1 for a in cell_assignments.values() if a["source"] == "precreated")
    custom_real = sum(1 for a in cell_assignments.values() if a["source"] == "custom" and a["entry"] is not None)
    custom_placeholder = sum(1 for a in cell_assignments.values() if a["source"] == "custom" and a["entry"] is None)

    print(f"[DUNGEON] Created instance: layout={layout['name']}, "
          f"rooms={len(active_rooms)} ({precreated_count}p/{custom_real}c/{custom_placeholder}g), "
          f"entrance={entrance_room_id}, music={music_track}")

    # Resolve the entrance room immediately
    resolve_dungeon_room(instance, (entrance_col, entrance_row))

    return instance


def resolve_dungeon_room(instance: DungeonInstance, cell: tuple) -> bool:
    """Materialize a library entry into a live game.rooms[] entry.

    For precreated or real custom entries, this is instant.
    For placeholders (entry is None), falls back to a random permanent room.
    Returns True if successfully resolved.
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

    entry = assignment["entry"]
    if entry is not None:
        # Real entry (precreated or custom) — use its data
        entry_data = entry.data
        source_label = f"{assignment['source']}:{entry.id}"
    else:
        # Placeholder — fall back to a random permanent room for now
        # (async generation will be added in a later step)
        fallback = game.room_library.get_random_real()
        if fallback is None:
            print(f"[DUNGEON] ERROR: No fallback room for {room_id}")
            return False
        entry_data = fallback.data
        assignment["entry"] = fallback
        source_label = f"fallback:{fallback.id}"

    _resolve_room_from_entry(room_id, entry_data, exits, cell, instance.music_track, is_entrance)

    assignment["resolved"] = True
    instance.resolved_rooms.add(room_id)
    print(f"[DUNGEON] Resolved {room_id} ({source_label})")
    return True


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

    # Expire oldest custom entries from libraries (skip permanent, respect min age)
    expired = {}
    for lib_name, lib in [("monster", game.monster_library),
                          ("tile", game.tile_library),
                          ("room", game.room_library)]:
        if lib:
            ids = lib.expire_oldest()
            if ids:
                expired[lib_name] = ids
                # Clean up game registries for expired monsters/tiles
                if lib_name == "monster":
                    for mid in ids:
                        game.monster_stats.pop(mid, None)
                        game.custom_sprites.pop(mid, None)
                        game.custom_death_sprites.pop(mid, None)
                        game.monster_behaviors.pop(mid, None)
                elif lib_name == "tile":
                    for tid in ids:
                        game.custom_tile_recipes.pop(tid, None)
                        game.custom_walkable_tiles.discard(tid)

    if expired:
        parts = [f"{k}: {v}" for k, v in expired.items()]
        print(f"[DUNGEON] Expired: {', '.join(parts)}")

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
