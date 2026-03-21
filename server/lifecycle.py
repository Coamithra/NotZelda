"""Room lifecycle — monster spawning, room enter/leave, room transitions."""

import os
import random
import time

from server.state import game
from server.constants import ROOM_RESET_COOLDOWN, ENTRY_DIR, EDGE_SPAWN_POINTS, DEFAULT_SPAWN
from server.models import Monster
from server.net import players_in_room, player_info
from server.dungeons import (
    create_dungeon, destroy_dungeon, dungeon_player_count, resolve_dungeon_room,
    is_dungeon_room, get_boss_distances, get_dungeon_for_room,
)


def spawn_monsters(room_id: str) -> list[Monster]:
    """Create fresh Monster instances from templates for a room."""
    templates = game.monster_templates.get(room_id, [])
    now = time.monotonic()
    monsters = []
    for t in templates:
        m = Monster(t["x"], t["y"], t["kind"])
        # Stagger first tick by 0-4 intervals so monsters don't move in sync
        m.last_action_time = now + random.randint(0, 4) * 0.25
        monsters.append(m)
    return monsters


def get_room_monsters(room_id: str) -> list[Monster]:
    """Get the live monster list for a room (may be empty list)."""
    return game.room_monsters.get(room_id, [])


def on_player_enter_room(room_id: str):
    """Called when a player enters a room. Spawns monsters if needed."""
    # Dungeon cleared rooms stay empty (no respawn)
    inst = get_dungeon_for_room(room_id)
    if inst and room_id in inst.cleared_rooms:
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


def on_player_leave_room(room_id: str, msgs: list, skip_dungeon_teardown: bool = False):
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

    # Boss disengagement — if boss room emptied and boss was engaged (not killed), reset
    inst = get_dungeon_for_room(room_id)
    if inst and inst.boss_engaged:
        boss_room = f"{inst.dungeon_id}_{inst.boss_cell[0]}_{inst.boss_cell[1]}"
        if room_id == boss_room and room_id not in inst.cleared_rooms:
            inst.boss_engaged = False
            for p in list(game.players.values()):
                if p.room in inst.active_rooms:
                    msgs.append(("send", p, {"type": "boss_choir_stop"}))

    # Dungeon cleanup — destroy instance when all players have left
    if not skip_dungeon_teardown and inst:
        if dungeon_player_count(inst) == 0:
            destroy_dungeon(inst)


def send_room_enter(player, msgs: list, exit_direction: str = None):
    """Build and append the room_enter message with all room data."""
    room = game.rooms[player.room]
    others = [player_info(p) for p in players_in_room(player.room, exclude=player.ws)]
    guards = game.guards.get(player.room, [])
    monsters = []
    now = time.monotonic()
    for i, m in enumerate(get_room_monsters(player.room)):
        if m.alive:
            mdata = {"id": i, "kind": m.kind, "x": m.x, "y": m.y,
                     "walk_time": m.walk_time}
            if m.width > 1:
                mdata["width"] = m.width
            if m.height > 1:
                mdata["height"] = m.height
            # Include walk state if mid-walk so client can interpolate
            if m.state == "walking":
                sd = m.state_data
                elapsed = now - sd["start_time"]
                progress = min(elapsed / m.walk_time, 1.0)
                mdata["walking"] = True
                mdata["walk_from"] = {"x": sd["from_x"], "y": sd["from_y"]}
                mdata["walk_to"] = {"x": sd["to_x"], "y": sd["to_y"]}
                mdata["walk_progress"] = progress
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
                if tid in game.custom_tile_recipes:
                    custom_tiles[tid] = game.custom_tile_recipes[tid]

    if custom_sprites:
        msg["custom_sprites"] = custom_sprites
    if custom_death_sprites:
        msg["custom_death_sprites"] = custom_death_sprites
    if custom_tiles:
        msg["custom_tiles"] = custom_tiles

    # Send NPC sprites for guards in this room
    npc_sprites = {}
    for g in guards:
        sprite_key = g.get("sprite", "guard")
        if sprite_key in game.npc_sprites and sprite_key not in npc_sprites:
            npc_sprites[sprite_key] = game.npc_sprites[sprite_key]
    if npc_sprites:
        msg["npc_sprites"] = npc_sprites

    # Attach dungeon item data for dungeon rooms
    inst = get_dungeon_for_room(player.room) if is_dungeon else None
    if inst:
        msg["dungeon_collected"] = sorted(inst.collected_items)
        msg["dungeon_boss_cell"] = list(inst.boss_cell) if inst.boss_cell else None
        room_items = inst.dungeon_items.get(player.room, [])
        if room_items:
            msg["dungeon_items"] = [{"x": it["x"], "y": it["y"], "item_type": it["item_type"]} for it in room_items]

    # Attach dungeon debug info for dungeon rooms
    if inst:
        dungeon_id = inst.dungeon_id
        libs = game.content_libraries.get(dungeon_id, {})
        debug = {}
        if libs.get("monsters"):
            debug["lib_monsters"] = f"{libs['monsters'].real_count}/{libs['monsters'].capacity}"
        if libs.get("tiles"):
            debug["lib_tiles"] = f"{libs['tiles'].real_count}/{libs['tiles'].capacity}"
        if libs.get("rooms"):
            debug["lib_rooms"] = f"{libs['rooms'].real_count}/{libs['rooms'].capacity}"
        # Find source for this room
        for cell, assignment in inst.cell_assignments.items():
            room_id_check = f"{dungeon_id}_{cell[0]}_{cell[1]}"
            if room_id_check == player.room:
                source = assignment["source"]
                entry = assignment.get("entry")
                if entry:
                    debug["room_source"] = f"{source} ({entry.id})"
                else:
                    debug["room_source"] = source
                break

        # Minimap data — always sent (simplified for non-debug)
        entrance_col, entrance_row = inst.layout["entrance"]
        is_debug = os.environ.get("DEBUG_MODE", "").lower() in ("1", "true")
        cells = []
        for (c, r), asn in inst.cell_assignments.items():
            cell_info = {"c": c, "r": r, "res": asn["resolved"]}
            if is_debug:
                cell_info["src"] = asn["source"]
                cell_info["gen"] = asn.get("entry") is not None
                if (c, r) == inst.boss_cell:
                    cell_info["boss"] = True
                if (c, r) == inst.treasure_cell:
                    cell_info["treasure"] = True
            cell_info["ent"] = c == entrance_col and r == entrance_row
            cells.append(cell_info)
        # Find which cell the player is in
        player_cell = None
        for (c, r) in inst.cell_assignments:
            if f"{dungeon_id}_{c}_{r}" == player.room:
                player_cell = [c, r]
                break
        debug["minimap"] = {
            "cells": cells,
            "player": player_cell,
        }
        if is_debug:
            # Serialize connections as [[c1,r1,c2,r2], ...]
            conn_list = []
            for edge in inst.connections:
                a, b = tuple(edge)
                conn_list.append([a[0], a[1], b[0], b[1]])
            debug["minimap"]["layout"] = inst.layout["name"]
            debug["minimap"]["connections"] = conn_list
            debug["libraries"] = _build_library_icons(dungeon_id)

        msg["dungeon_debug"] = debug

    msgs.append(("send", player, msg))

    # Choir overlay — always update after sending room data so any code path
    # that calls send_room_enter() automatically gets correct choir state.
    _send_choir_update(player, msgs)


def _build_library_icons(type_id):
    """Build compact library summary for the conjuring screen debug overlay."""
    libs = game.content_libraries.get(type_id, {})
    dep = game.deprecated_content.get(type_id, {})
    dep_monsters = dep.get("monsters", set())
    dep_tiles = dep.get("tiles", set())

    def _primary_color(colors_dict):
        """Extract the first color value from a colors dict."""
        if isinstance(colors_dict, dict):
            for v in colors_dict.values():
                if isinstance(v, str) and v.startswith("#"):
                    return v
        return "#888"

    monsters = []
    monster_empty = 0
    monster_lib = libs.get("monsters")
    if monster_lib:
        for e in monster_lib.real_entries:
            color = _primary_color(game.custom_sprites.get(e.id, {}).get("colors", {}))
            if e.id in dep_monsters:
                status = "dep"
            elif e.permanent:
                status = "pre"
            else:
                status = "cus"
            monsters.append({"id": e.id, "s": status, "color": color})
        monster_empty = monster_lib.placeholder_count

    tiles = []
    tile_empty = 0
    tile_lib = libs.get("tiles")
    if tile_lib:
        for e in tile_lib.real_entries:
            color = _primary_color(game.custom_tile_recipes.get(e.id, {}).get("colors", {}))
            if e.id in dep_tiles:
                status = "dep"
            elif e.permanent:
                status = "pre"
            else:
                status = "cus"
            tiles.append({"id": e.id, "s": status, "color": color})
        tile_empty = tile_lib.placeholder_count

    return {"monsters": monsters, "tiles": tiles,
            "monster_empty": monster_empty, "tile_empty": tile_empty}


def _send_choir_update(player, msgs: list):
    """If boss is engaged, send choir start/stop based on player's current room."""
    inst = get_dungeon_for_room(player.room)
    if not inst or not inst.boss_engaged:
        # Not in a dungeon or boss not engaged — stop any active choir
        msgs.append(("send", player, {"type": "boss_choir_stop"}))
        return
    boss_room = f"{inst.dungeon_id}_{inst.boss_cell[0]}_{inst.boss_cell[1]}"
    if player.room not in inst.active_rooms or player.room == boss_room:
        msgs.append(("send", player, {"type": "boss_choir_stop"}))
    else:
        distances = get_boss_distances(inst)
        dist = distances.get(player.room, 5)
        choir_track = f"music_{inst.boss_track}_choir.mp3"
        msgs.append(("send", player, {"type": "boss_choir_start", "distance": dist, "choir_track": choir_track}))


def broadcast_choir_start(boss_room, msgs: list):
    """Send boss_choir_start to all dungeon players not in the boss room."""
    instance = get_dungeon_for_room(boss_room)
    if not instance:
        return
    distances = get_boss_distances(instance)
    choir_track = f"music_{instance.boss_track}_choir.mp3"
    for p in list(game.players.values()):
        if p.room in instance.active_rooms and p.room != boss_room:
            dist = distances.get(p.room, 5)
            msgs.append(("send", p, {"type": "boss_choir_start", "distance": dist, "choir_track": choir_track}))


def broadcast_choir_stop(room_id, msgs: list):
    """Send boss_choir_stop to all dungeon players."""
    instance = get_dungeon_for_room(room_id)
    if not instance:
        return
    for p in list(game.players.values()):
        if p.room in instance.active_rooms:
            msgs.append(("send", p, {"type": "boss_choir_stop"}))


def do_room_transition(player, exit_direction: str, msgs: list):
    """Move a player from their current room to an adjacent room via an exit."""
    old_room = player.room
    new_room_id = game.rooms[old_room]["exits"][exit_direction]

    # Dungeon entrance — create instance on demand
    from server.dungeon_types import ENTRANCE_TO_TYPE
    entrance_type = ENTRANCE_TO_TYPE.get(new_room_id)
    if entrance_type is not None:
        if entrance_type not in game.active_dungeons:
            instance = create_dungeon(entrance_type)
            if instance is None:
                msgs.append(("send", player, {"type": "info", "text": "The dungeon entrance is sealed."}))
                return
        new_room_id = game.active_dungeons[entrance_type].entrance_room_id
        # Show conjuring animation when first entering the dungeon
        msgs.append(("send", player, {"type": "room_generating"}))

    # Lazy resolution — if this is an unresolved dungeon room, resolve it now
    dungeon_inst = get_dungeon_for_room(new_room_id)
    if dungeon_inst and new_room_id not in game.rooms:
        # Find the cell for this room_id
        did = dungeon_inst.dungeon_id
        for cell, assignment in dungeon_inst.cell_assignments.items():
            room_id_check = f"{did}_{cell[0]}_{cell[1]}"
            if room_id_check == new_room_id and not assignment["resolved"]:
                resolved = resolve_dungeon_room(dungeon_inst, cell)
                if not resolved:
                    msgs.append(("send", player, {"type": "info", "text": "The way is blocked."}))
                    return
                break

    new_room = game.rooms[new_room_id]

    # Remove player from game during the transition so monster ticks / projectiles
    # can't target them while they're between rooms.
    game.players.pop(player.ws, None)
    try:
        # Broadcast departure (player already removed, so exclude isn't needed
        # but other players in old room still see the message)
        msgs.append(("broadcast", old_room, {"type": "player_left", "name": player.name}, None))

        # Move player — preserve column/row through the doorway
        old_x, old_y = player.x, player.y
        player.room = new_room_id
        entry = ENTRY_DIR.get(exit_direction, "default")
        spawn = new_room["spawn_points"].get(entry, new_room["spawn_points"]["default"])
        player.x, player.y = float(spawn[0]), float(spawn[1])
        if exit_direction in ("north", "south"):
            player.x = float(old_x)  # keep column
        elif exit_direction in ("east", "west"):
            player.y = float(old_y)  # keep row

        # Monster lifecycle — leave old room, enter new room
        # Skip dungeon teardown if the player is moving to another dungeon room
        # (they're removed from game.players so dungeon_player_count would be wrong)
        entering_dungeon = is_dungeon_room(new_room_id)
        on_player_leave_room(old_room, msgs, skip_dungeon_teardown=entering_dungeon)
        on_player_enter_room(new_room_id)

        # Send new room data and broadcast arrival while still removed,
        # so game_tick can't target us before the client has loaded.
        send_room_enter(player, msgs, exit_direction=exit_direction)
        msgs.append(("broadcast", new_room_id,
                      {"type": "player_entered", **player_info(player)}, None))
    finally:
        game.players[player.ws] = player
