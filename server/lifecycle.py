"""Room lifecycle — monster spawning, room enter/leave, room transitions."""

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


async def on_player_leave_room(room_id: str):
    """Called after a player leaves a room. Cleans up if room is now empty."""
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
    if game.active_dungeon and room_id in game.active_dungeon.active_rooms:
        if dungeon_player_count() == 0:
            destroy_dungeon()


async def send_room_enter(player, exit_direction: str = None):
    """Build and send the room_enter message with all room data."""
    room = game.rooms[player.room]
    others = [player_info(p) for p in players_in_room(player.room, exclude=player.ws)]
    guards = game.guards.get(player.room, [])
    monsters = [
        {"id": i, "kind": m.kind, "x": m.x, "y": m.y}
        for i, m in enumerate(get_room_monsters(player.room))
        if m.alive
    ]
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

    # Attach custom sprite/tile data for any AI-generated content in this room
    custom_sprites = {}
    custom_death_sprites = {}
    for m in monsters:
        kind = m["kind"]
        if kind in game.custom_sprites:
            custom_sprites[kind] = game.custom_sprites[kind]
        if kind in game.custom_death_sprites:
            custom_death_sprites[kind] = game.custom_death_sprites[kind]
    custom_tiles = {}
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
        debug = {}
        if game.monster_library:
            debug["lib_monsters"] = f"{game.monster_library.real_count}/{game.monster_library.capacity}"
        if game.tile_library:
            debug["lib_tiles"] = f"{game.tile_library.real_count}/{game.tile_library.capacity}"
        if game.room_library:
            debug["lib_rooms"] = f"{game.room_library.real_count}/{game.room_library.capacity}"
        # Find source for this room
        for cell, assignment in game.active_dungeon.cell_assignments.items():
            room_id_check = f"d1_{cell[0]}_{cell[1]}"
            if room_id_check == player.room:
                entry = assignment.get("entry")
                source = assignment["source"]
                if entry is None:
                    debug["room_source"] = "custom (generated)"
                elif source == "precreated":
                    debug["room_source"] = f"precreated ({entry.id})"
                else:
                    debug["room_source"] = f"custom ({entry.id})"
                break
        msg["dungeon_debug"] = debug

    await send_to(player, msg)


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

    # Lazy resolution — if this is an unresolved dungeon room, resolve it now
    if game.active_dungeon and new_room_id in game.active_dungeon.active_rooms:
        if new_room_id not in game.rooms:
            # Find the cell for this room_id
            for cell, assignment in game.active_dungeon.cell_assignments.items():
                room_id_check = f"d1_{cell[0]}_{cell[1]}"
                if room_id_check == new_room_id and not assignment["resolved"]:
                    # Send conjuring animation for custom rooms (placeholder or library)
                    if assignment["source"] == "custom":
                        await send_to(player, {"type": "room_generating"})
                    if not await resolve_dungeon_room(game.active_dungeon, cell):
                        await send_to(player, {"type": "info", "text": "The way is blocked."})
                        return
                    break

    new_room = game.rooms[new_room_id]

    # Broadcast departure
    await broadcast_to_room(old_room, {"type": "player_left", "name": player.name}, exclude=player.ws)

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
    await on_player_leave_room(old_room)
    await on_player_enter_room(new_room_id)

    # Send new room to player
    await send_room_enter(player, exit_direction=exit_direction)

    # Broadcast arrival
    await broadcast_to_room(
        new_room_id,
        {"type": "player_entered", **player_info(player)},
        exclude=player.ws,
    )
