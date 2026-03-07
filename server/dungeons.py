"""Dungeon instance system — procedurally generated dungeon layouts."""

import copy
import random

from server.state import game
from server.constants import (
    DUNGEON_WALL, STAIRS_UP,
    EDGE_SPAWN_POINTS, DEFAULT_SPAWN, DUNGEON_MUSIC_TRACKS,
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


def create_dungeon() -> DungeonInstance | None:
    """Create a new dungeon instance from random layout + templates."""
    layout = random.choice(DUNGEON_LAYOUTS)
    music_track = random.choice(DUNGEON_MUSIC_TRACKS)

    # Find all active cells in layout
    active_cells = []
    for row_idx, row_str in enumerate(layout["grid"]):
        for col_idx, ch in enumerate(row_str):
            if ch == "X":
                active_cells.append((col_idx, row_idx))

    # Assign templates to cells
    template_keys = list(game.dungeon_templates.keys())
    if not template_keys:
        print("[DUNGEON] No dungeon templates loaded, cannot create dungeon")
        return None
    random.shuffle(template_keys)
    # Cycle through templates if we have more cells than templates
    room_map = {}
    for i, cell in enumerate(active_cells):
        room_map[cell] = template_keys[i % len(template_keys)]

    entrance_col, entrance_row = layout["entrance"]
    entrance_room_id = f"d1_{entrance_col}_{entrance_row}"
    active_rooms = set()

    for (col, row), template_id in room_map.items():
        room_id = f"d1_{col}_{row}"
        active_rooms.add(room_id)
        tmpl = game.dungeon_templates[template_id]

        # Deep-copy tilemap
        tilemap = [list(r) for r in tmpl["tilemap"]]

        # Auto-generate exits from layout adjacency
        exits = {}
        if (col, row - 1) in room_map:
            exits["north"] = f"d1_{col}_{row - 1}"
        if (col, row + 1) in room_map:
            exits["south"] = f"d1_{col}_{row + 1}"
        if (col - 1, row) in room_map:
            exits["west"] = f"d1_{col - 1}_{row}"
        if (col + 1, row) in room_map:
            exits["east"] = f"d1_{col + 1}_{row}"

        # Wall off unused exits
        if "north" not in exits:
            for c in (6, 7, 8):
                tilemap[0][c] = DUNGEON_WALL
        if "south" not in exits:
            for c in (6, 7, 8):
                tilemap[10][c] = DUNGEON_WALL
        if "west" not in exits:
            for r in (4, 5, 6):
                tilemap[r][0] = DUNGEON_WALL
        if "east" not in exits:
            for r in (4, 5, 6):
                tilemap[r][14] = DUNGEON_WALL

        # Entrance cell gets stairs up to clearing
        if col == entrance_col and row == entrance_row:
            exits["up"] = "clearing"
            tilemap[9][7] = STAIRS_UP

        # Build spawn points
        spawn_points = {"default": DEFAULT_SPAWN}
        for direction, pos in EDGE_SPAWN_POINTS.items():
            if direction in exits:
                spawn_points[direction] = pos
        # Scan for stairs
        for ry, trow in enumerate(tilemap):
            for rx, tile in enumerate(trow):
                if tile == STAIRS_UP:
                    spawn_points["down"] = (rx, ry)

        game.rooms[room_id] = {
            "name": tmpl["name"],
            "exits": exits,
            "tilemap": tilemap,
            "spawn_points": spawn_points,
            "biome": "dungeon",
            "music": music_track,
        }
        if tmpl["guards"]:
            game.guards[room_id] = copy.deepcopy(tmpl["guards"])
        if tmpl["monsters"]:
            game.monster_templates[room_id] = copy.deepcopy(tmpl["monsters"])

    instance = DungeonInstance(
        dungeon_id="d1",
        layout=layout,
        room_map=room_map,
        active_rooms=active_rooms,
        entrance_room_id=entrance_room_id,
        music_track=music_track,
    )
    game.active_dungeon = instance
    print(f"[DUNGEON] Created instance: layout={layout['name']}, rooms={len(active_rooms)}, entrance={entrance_room_id}, music={music_track}")
    return instance


def destroy_dungeon():
    """Tear down the active dungeon instance."""
    if game.active_dungeon is None:
        return

    for room_id in game.active_dungeon.active_rooms:
        game.rooms.pop(room_id, None)
        game.guards.pop(room_id, None)
        game.monster_templates.pop(room_id, None)
        game.room_monsters.pop(room_id, None)
        game.room_cooldowns.pop(room_id, None)
        game.room_hearts.pop(room_id, None)

    print(f"[DUNGEON] Destroyed instance: layout={game.active_dungeon.layout['name']}")
    game.active_dungeon = None


def is_dungeon_room(room_id: str) -> bool:
    return game.active_dungeon is not None and room_id in game.active_dungeon.active_rooms


def dungeon_player_count() -> int:
    if game.active_dungeon is None:
        return 0
    return sum(1 for p in game.players.values() if p.room in game.active_dungeon.active_rooms)
