"""Room lifecycle — monster spawning, room enter/leave, room transitions."""

import os
import random
import time

from server.state import game
from server.constants import (
    ROOM_RESET_COOLDOWN, ENTRY_DIR, EDGE_SPAWN_POINTS, DEFAULT_SPAWN,
    ROOM_COLS, ROOM_ROWS, DOORWAY_TILES, STARTING_ROOM,
)
from server.models import Monster
from server.net import avatars_in_room, player_info
from server.dungeons import (
    create_dungeon, destroy_dungeon, dungeon_player_count, resolve_dungeon_room,
    is_dungeon_room, get_boss_distances, get_dungeon_for_room,
)


def _on_state_exited(monster, old_state, room_id, monster_idx, msgs):
    """Broadcast cleanup messages when a monster exits a non-idle state."""
    if old_state in ("charging", "area"):
        msgs.append(("broadcast", room_id, {
            "type": "warmup_cancel", "id": monster_idx,
        }, None))
    elif old_state == "teleporting":
        msgs.append(("broadcast", room_id, {
            "type": "monster_fade_in", "id": monster_idx,
        }, None))


def set_monster_idle(monster, room_id, monster_idx, msgs):
    """Transition a monster to idle with proper state exit cleanup."""
    old_state = monster.state
    if old_state != "idle":
        _on_state_exited(monster, old_state, room_id, monster_idx, msgs)
    monster.state = "idle"
    monster.state_data = {}
    monster.last_action_time = time.monotonic()


def _lock_room(room_id: str):
    """Close all doorways in a trap room by replacing doorway tiles with CD."""
    room = game.rooms.get(room_id)
    if not room:
        return
    tilemap = room["tilemap"]
    exits = room["exits"]
    original_tiles = {}
    for direction in exits:
        if direction not in DOORWAY_TILES:
            continue
        for r, c in DOORWAY_TILES[direction]:
            original_tiles[(r, c)] = tilemap[r][c]
            tilemap[r][c] = "CD"
    game.locked_rooms[room_id] = {"original_tiles": original_tiles}


def unlock_room(room_id: str, msgs: list):
    """Open doorways in a trap room by restoring original tiles."""
    lock_data = game.locked_rooms.pop(room_id, None)
    if not lock_data:
        return
    room = game.rooms.get(room_id)
    if not room:
        return
    tilemap = room["tilemap"]
    tile_changes = []
    for (r, c), tile in lock_data["original_tiles"].items():
        tilemap[r][c] = tile
        tile_changes.append([r, c, tile])
    unlock_msg = {
        "type": "doors_unlocked",
        "tile_changes": tile_changes,
    }
    # Reveal hidden dungeon items now that the room is cleared
    inst = get_dungeon_for_room(room_id)
    if inst:
        room_items = inst.dungeon_items.get(room_id, [])
        if room_items:
            unlock_msg["dungeon_items"] = [
                {"x": it["x"], "y": it["y"], "item_type": it["item_type"]}
                for it in room_items
            ]
    msgs.append(("broadcast", room_id, unlock_msg, None))


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

    # Lock doors in trap rooms
    room = game.rooms.get(room_id)
    if room and room.get("locked") and monsters and room_id not in game.locked_rooms:
        _lock_room(room_id)


def on_player_leave_room(room_id: str, msgs: list, skip_dungeon_teardown: bool = False):
    """Called after a player leaves a room. Cleans up if room is now empty.

    skip_dungeon_teardown: set True when the player is transitioning to another
    dungeon room (their avatar is detached mid-transition so avatars_in_room
    would show 0, but dungeon_player_count uses player.room which is already
    updated to the new room).
    """
    if avatars_in_room(room_id):
        return  # still has players with physical presence

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


def _dungeon_room_to_cell(inst):
    """Build a room_id -> (col, row) lookup for a dungeon instance."""
    did = inst.dungeon_id
    return {f"{did}_{c}_{r}": (c, r) for (c, r) in inst.cell_assignments}


def _dungeon_other_players(inst, exclude_player=None):
    """Build list of other players in a dungeon for the compass minimap."""
    room_to_cell = _dungeon_room_to_cell(inst)
    players = []
    for p in game.players.values():
        if p is exclude_player:
            continue
        cell = room_to_cell.get(p.room)
        if cell:
            players.append({"c": cell[0], "r": cell[1],
                            "color_index": p.color_index, "name": p.name})
    return players


def broadcast_dungeon_player_positions(inst, moved_player, msgs):
    """Notify all players in a dungeon about updated player positions (for compass)."""
    room_to_cell = _dungeon_room_to_cell(inst)
    # Build full list of all players in the dungeon
    all_players = []
    for p in game.players.values():
        cell = room_to_cell.get(p.room)
        if cell:
            all_players.append({"c": cell[0], "r": cell[1],
                                "color_index": p.color_index, "name": p.name})
    # Send each player a list excluding themselves
    for p in game.players.values():
        if p is moved_player:
            continue  # moved player already got updated data via send_room_enter
        cell = room_to_cell.get(p.room)
        if cell:
            others = [dp for dp in all_players if dp["name"] != p.name]
            msgs.append(("send", p, {
                "type": "dungeon_player_positions",
                "players": others,
            }))


def send_room_enter(player, msgs: list, exit_direction: str = None):
    """Build and append the room_enter message with all room data."""
    room = game.rooms.get(player.room)
    if not room:
        print(f"[BUG] send_room_enter: room {player.room} missing for {player.name}! Redirecting to spawn.")
        assert os.environ.get("DEBUG_MODE", "").lower() not in ("1", "true"), \
            f"send_room_enter called with destroyed room {player.room} — this should never happen"
        player.room = STARTING_ROOM
        spawn = game.rooms[STARTING_ROOM]["spawn_points"]["default"]
        a = player.avatar
        a.x, a.y = float(spawn[0]), float(spawn[1])
        room = game.rooms[STARTING_ROOM]
        exit_direction = None
    a = player.avatar
    others = [player_info(p) for p, _a in avatars_in_room(player.room, exclude=player.ws)]
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
        "your_pos": {"x": a.x, "y": a.y},
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

    # Trap room — tell client doors are locked
    if player.room in game.locked_rooms:
        msg["locked"] = True

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
        # Hide items in locked trap rooms — they appear when doors unlock
        if room_items and player.room not in game.locked_rooms:
            msg["dungeon_items"] = [{"x": it["x"], "y": it["y"], "item_type": it["item_type"]} for it in room_items]

    # Attach dungeon type for client-side ambient effects
    if inst:
        msg["dungeon_type"] = inst.dungeon_id

    # Attach key count and locked door edges for minimap
    if inst:
        msg["keys"] = player.keys
        still_locked = inst.locked_doors - inst.unlocked_doors
        if still_locked:
            msg["locked_edges"] = [[list(c) for c in edge] for edge in still_locked]

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
            "other_players": _dungeon_other_players(inst, exclude_player=player),
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
    if not inst or not inst.boss_engaged or not inst.boss_cell:
        # Not in a dungeon, boss not engaged, or no boss cell — stop any active choir
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
    from server.models import Avatar

    # Detach avatar — character vanishes from the world.  Monster ticks /
    # projectiles can't target a player with no avatar.
    old_avatar = player.avatar
    old_x, old_y = old_avatar.x, old_avatar.y
    player.avatar = None

    try:
        # Broadcast departure (avatar is gone so player is excluded from
        # avatars_in_room, but we add explicit exclude for broadcast_to_room
        # which checks player.room)
        msgs.append(("broadcast", old_room, {"type": "player_left", "name": player.name}, player.ws))

        # Update which room the player is in
        player.room = new_room_id
        entry = ENTRY_DIR.get(exit_direction, "default")
        spawn = new_room["spawn_points"].get(entry, new_room["spawn_points"]["default"])
        spawn_x, spawn_y = float(spawn[0]), float(spawn[1])
        if exit_direction in ("north", "south"):
            spawn_x = float(old_x)  # keep column through doorway
        elif exit_direction in ("east", "west"):
            spawn_y = float(old_y)  # keep row through doorway

        # Monster lifecycle — leave old room, enter new room
        # Skip dungeon teardown if moving to another dungeon room
        entering_dungeon = is_dungeon_room(new_room_id)
        on_player_leave_room(old_room, msgs, skip_dungeon_teardown=entering_dungeon)

        # Defensive: verify destination room wasn't destroyed by dungeon teardown.
        if new_room_id not in game.rooms:
            print(f"[BUG] Room {new_room_id} destroyed mid-transition for {player.name}! Redirecting to spawn.")
            assert os.environ.get("DEBUG_MODE", "").lower() not in ("1", "true"), \
                f"Room {new_room_id} destroyed during do_room_transition — this should never happen"
            new_room_id = STARTING_ROOM
            player.room = STARTING_ROOM
            spawn = game.rooms[STARTING_ROOM]["spawn_points"]["default"]
            spawn_x, spawn_y = float(spawn[0]), float(spawn[1])
            exit_direction = None

        on_player_enter_room(new_room_id)

        # Adjust spawn position for locked trap rooms — spawn 1 tile inward
        if new_room_id in game.locked_rooms:
            if entry == "south":
                spawn_y = min(spawn_y, 9.0)
            elif entry == "north":
                spawn_y = max(spawn_y, 1.0)
            elif entry == "east":
                spawn_x = min(spawn_x, 13.0)
            elif entry == "west":
                spawn_x = max(spawn_x, 1.0)

        # Create new avatar at the spawn position
        player.avatar = Avatar(spawn_x, spawn_y, old_avatar.direction)

        # Send new room data and broadcast arrival (exclude self from broadcast
        # since player.room is already new_room_id)
        send_room_enter(player, msgs, exit_direction=exit_direction)
        msgs.append(("broadcast", new_room_id,
                      {"type": "player_entered", **player_info(player)}, player.ws))

        # Update compass minimap for other players in the dungeon
        new_inst = get_dungeon_for_room(new_room_id)
        old_inst = get_dungeon_for_room(old_room)
        # Player moved within or entered a dungeon — notify others
        if new_inst:
            broadcast_dungeon_player_positions(new_inst, player, msgs)
        # Player left a dungeon for a different area — notify remaining
        if old_inst and old_inst is not new_inst:
            broadcast_dungeon_player_positions(old_inst, player, msgs)
    except Exception:
        # If anything fails mid-transition, restore avatar at spawn so the
        # player isn't permanently stuck as a ghost.
        if player.avatar is None:
            player.room = STARTING_ROOM
            fallback = game.rooms[STARTING_ROOM]["spawn_points"]["default"]
            player.avatar = Avatar(float(fallback[0]), float(fallback[1]))
        raise
