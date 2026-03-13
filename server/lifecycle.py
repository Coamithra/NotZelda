"""Room lifecycle — monster spawning, room enter/leave, room transitions."""

import os
import random
import time

from server.state import game
from server.constants import ROOM_RESET_COOLDOWN, ENTRY_DIR, EDGE_SPAWN_POINTS, DEFAULT_SPAWN
from server.models import Monster
from server.net import send_to, broadcast_to_room, players_in_room, player_info
from server.dungeons import create_dungeon, destroy_dungeon, dungeon_player_count, resolve_dungeon_room, is_dungeon_room


def spawn_monsters(room_id: str) -> list[Monster]:
    """Create fresh Monster instances from templates for a room."""
    templates = game.monster_templates.get(room_id, [])
    now = time.monotonic()
    monsters = []
    for t in templates:
        m = Monster(t["x"], t["y"], t["kind"])
        # Stagger first tick by 0-4 intervals so monsters don't move in sync
        m.last_tick_time = now + random.randint(0, 4) * 0.25
        monsters.append(m)
    return monsters


def get_room_monsters(room_id: str) -> list[Monster]:
    """Get the live monster list for a room (may be empty list)."""
    return game.room_monsters.get(room_id, [])


async def on_player_enter_room(room_id: str):
    """Called when a player enters a room. Spawns monsters if needed."""
    # Dungeon cleared rooms stay empty (no respawn)
    if game.active_dungeon and room_id in game.active_dungeon.cleared_rooms:
        game.room_monsters[room_id] = []
        return
    if room_id not in game.monster_templates:
        return
    if room_id in game.room_monsters:
        return  # already active (other players present)

    # Check cooldown
    if room_id in game.room_cooldowns:
        elapsed = time.monotonic() - game.room_cooldowns[room_id]
        if elapsed < ROOM_RESET_COOLDOWN:
            # Still on cooldown — room stays empty, reset timer
            game.room_cooldowns[room_id] = time.monotonic()
            game.room_monsters[room_id] = []
            return
        else:
            del game.room_cooldowns[room_id]

    # Spawn fresh monsters
    monsters = spawn_monsters(room_id)
    game.room_monsters[room_id] = monsters


async def on_player_leave_room(room_id: str, skip_dungeon_teardown: bool = False):
    """Called after a player leaves a room. Cleans up if room is now empty.

    skip_dungeon_teardown: set True when the player is transitioning to another
    dungeon room (they're temporarily removed from game.players so the count
    would incorrectly hit 0).
    """
    if players_in_room(room_id):
        return  # still has players

    game.room_hearts.pop(room_id, None)
    game.room_projectiles.pop(room_id, None)

    if room_id in game.room_monsters:
        monster_list = game.room_monsters[room_id]
        all_killed = len(monster_list) > 0 and all(not m.alive for m in monster_list)
        empty_list = len(monster_list) == 0
        del game.room_monsters[room_id]

        if all_killed:
            game.room_cooldowns[room_id] = time.monotonic()
        elif empty_list and room_id in game.room_cooldowns:
            game.room_cooldowns[room_id] = time.monotonic()

    # Dungeon cleanup — destroy instance when all players have left
    if not skip_dungeon_teardown:
        if game.active_dungeon and room_id in game.active_dungeon.active_rooms:
            if dungeon_player_count() == 0:
                destroy_dungeon()


async def send_room_enter(player, exit_direction: str = None):
    """Build and send the room_enter message with all room data."""
    room = game.rooms[player.room]
    others = [player_info(p) for p in players_in_room(player.room, exclude=player.ws)]
    guards = game.guards.get(player.room, [])
    monsters = []
    for i, m in enumerate(get_room_monsters(player.room)):
        if m.alive:
            mdata = {"id": i, "kind": m.kind, "x": m.x, "y": m.y}
            if m.width > 1:
                mdata["width"] = m.width
            if m.height > 1:
                mdata["height"] = m.height
            monsters.append(mdata)
    exits = room["exits"]
    msg = {
        "type": "room_enter",
        "room_id": player.room,
        "name": room["name"],
        "tilemap": room["tilemap"],
        "your_pos": {"x": player.x, "y": player.y},
        "players": others,
        "guards": [{"name": g["name"], "x": g["x"], "y": g["y"], "sprite": g.get("sprite", "guard")} for g in guards],
        "monsters": monsters,
        "exits": {d: exits[d] for d in exits},
        "biome": room.get("biome", "town"),
        "music": room.get("music", "overworld"),
        "exit_direction": exit_direction,
        "hp": player.hp,
        "max_hp": player.max_hp,
    }

    # Attach custom sprite/tile data so the client can render them.
    # For dungeon rooms, send ALL registered custom content (the player may
    # encounter any of it as they explore). For overworld rooms, send only
    # what's present in the current room.
    is_dungeon = is_dungeon_room(player.room)
    custom_sprites = {}
    custom_death_sprites = {}
    if is_dungeon:
        custom_sprites = dict(game.custom_sprites)
        custom_death_sprites = dict(game.custom_death_sprites)
    else:
        for m in monsters:
            kind = m["kind"]
            if kind in game.custom_sprites:
                custom_sprites[kind] = game.custom_sprites[kind]
            if kind in game.custom_death_sprites:
                custom_death_sprites[kind] = game.custom_death_sprites[kind]
    custom_tiles = {}
    if is_dungeon:
        custom_tiles = dict(game.custom_tile_recipes)
    else:
        tilemap = room["tilemap"]
        for row in tilemap:
            for tid in row:
                if isinstance(tid, str) and tid in game.custom_tile_recipes:
                    custom_tiles[tid] = game.custom_tile_recipes[tid]

    if custom_sprites:
        msg["custom_sprites"] = custom_sprites
    if custom_death_sprites:
        msg["custom_death_sprites"] = custom_death_sprites
    if custom_tiles:
        msg["custom_tiles"] = custom_tiles

    # Attach dungeon debug info for dungeon rooms
    if is_dungeon_room(player.room) and game.active_dungeon:
        inst = game.active_dungeon
        debug = {}
        if game.monster_library:
            debug["lib_monsters"] = f"{game.monster_library.real_count}/{game.monster_library.capacity}"
        if game.tile_library:
            debug["lib_tiles"] = f"{game.tile_library.real_count}/{game.tile_library.capacity}"
        if game.room_library:
            debug["lib_rooms"] = f"{game.room_library.real_count}/{game.room_library.capacity}"
        # Find source for this room
        for cell, assignment in inst.cell_assignments.items():
            room_id_check = f"d1_{cell[0]}_{cell[1]}"
            if room_id_check == player.room:
                source = assignment["source"]
                entry = assignment.get("entry")
                if entry:
                    debug["room_source"] = f"{source} ({entry.id})"
                else:
                    debug["room_source"] = source
                break

        # Minimap + library debug (DEBUG_MODE only)
        if os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
            entrance_col, entrance_row = inst.layout["entrance"]
            cells = []
            for (c, r), asn in inst.cell_assignments.items():
                cell_info = {
                    "c": c, "r": r,
                    "src": asn["source"],           # "precreated", "custom", or "special"
                    "res": asn["resolved"],          # True/False
                    "gen": asn.get("entry") is not None,  # has content assigned
                    "ent": c == entrance_col and r == entrance_row,
                }
                if (c, r) == inst.boss_cell:
                    cell_info["boss"] = True
                if (c, r) == inst.treasure_cell:
                    cell_info["treasure"] = True
                cells.append(cell_info)
            # Find which cell the player is in
            player_cell = None
            for (c, r) in inst.cell_assignments:
                if f"d1_{c}_{r}" == player.room:
                    player_cell = [c, r]
                    break
            # Serialize connections as [[c1,r1,c2,r2], ...]
            conn_list = []
            for edge in inst.connections:
                a, b = tuple(edge)
                conn_list.append([a[0], a[1], b[0], b[1]])
            debug["minimap"] = {
                "cells": cells,
                "player": player_cell,
                "layout": inst.layout["name"],
                "connections": conn_list,
            }
            debug["libraries"] = _build_library_icons()

        msg["dungeon_debug"] = debug

    await send_to(player, msg)


def _build_library_icons():
    """Build compact library summary for the conjuring screen debug overlay."""
    def _primary_color(colors_dict):
        """Extract the first color value from a colors dict."""
        if isinstance(colors_dict, dict):
            for v in colors_dict.values():
                if isinstance(v, str) and v.startswith("#"):
                    return v
        return "#888"

    monsters = []
    monster_empty = 0
    if game.monster_library:
        for e in game.monster_library.real_entries:
            color = _primary_color(game.custom_sprites.get(e.id, {}).get("colors", {}))
            if e.id in game.deprecated_monsters:
                status = "dep"
            elif e.permanent:
                status = "pre"
            else:
                status = "cus"
            monsters.append({"id": e.id, "s": status, "color": color})
        monster_empty = game.monster_library.placeholder_count

    tiles = []
    tile_empty = 0
    if game.tile_library:
        for e in game.tile_library.real_entries:
            color = _primary_color(game.custom_tile_recipes.get(e.id, {}).get("colors", {}))
            if e.id in game.deprecated_tiles:
                status = "dep"
            elif e.permanent:
                status = "pre"
            else:
                status = "cus"
            tiles.append({"id": e.id, "s": status, "color": color})
        tile_empty = game.tile_library.placeholder_count

    return {"monsters": monsters, "tiles": tiles,
            "monster_empty": monster_empty, "tile_empty": tile_empty}


async def do_room_transition(player, exit_direction: str):
    """Move a player from their current room to an adjacent room via an exit."""
    old_room = player.room
    new_room_id = game.rooms[old_room]["exits"][exit_direction]

    # Dungeon entrance — create instance on demand
    if new_room_id == "d1_entrance":
        if game.active_dungeon is None:
            if await create_dungeon() is None:
                await send_to(player, {"type": "info", "text": "The dungeon entrance is sealed."})
                return
        new_room_id = game.active_dungeon.entrance_room_id
        # Show conjuring animation when first entering the dungeon
        await send_to(player, {"type": "room_generating"})

    # Lazy resolution — if this is an unresolved dungeon room, resolve it now
    if game.active_dungeon and new_room_id in game.active_dungeon.active_rooms:
        if new_room_id not in game.rooms:
            # Find the cell for this room_id
            for cell, assignment in game.active_dungeon.cell_assignments.items():
                room_id_check = f"d1_{cell[0]}_{cell[1]}"
                if room_id_check == new_room_id and not assignment["resolved"]:
                    resolved = resolve_dungeon_room(game.active_dungeon, cell)
                    if not resolved:
                        await send_to(player, {"type": "info", "text": "The way is blocked."})
                        return
                    break

    new_room = game.rooms[new_room_id]

    # Remove player from game during the transition so monster ticks / projectiles
    # can't target them while they're between rooms.
    game.players.pop(player.ws, None)
    try:
        # Broadcast departure (player already removed, so exclude isn't needed
        # but other players in old room still see the message)
        await broadcast_to_room(old_room, {"type": "player_left", "name": player.name})

        # Move player — preserve column/row through the doorway
        old_x, old_y = player.x, player.y
        player.room = new_room_id
        entry = ENTRY_DIR.get(exit_direction, "default")
        spawn = new_room["spawn_points"].get(entry, new_room["spawn_points"]["default"])
        player.x, player.y = spawn
        if exit_direction in ("north", "south"):
            player.x = old_x  # keep column
        elif exit_direction in ("east", "west"):
            player.y = old_y  # keep row

        # Monster lifecycle — leave old room, enter new room
        # Skip dungeon teardown if the player is moving to another dungeon room
        # (they're removed from game.players so dungeon_player_count would be wrong)
        entering_dungeon = is_dungeon_room(new_room_id)
        await on_player_leave_room(old_room, skip_dungeon_teardown=entering_dungeon)
        await on_player_enter_room(new_room_id)

        # Send new room data and broadcast arrival while still removed,
        # so monster_tick can't target us before the client has loaded.
        await send_room_enter(player, exit_direction=exit_direction)
        await broadcast_to_room(
            new_room_id,
            {"type": "player_entered", **player_info(player)},
        )
    finally:
        game.players[player.ws] = player
