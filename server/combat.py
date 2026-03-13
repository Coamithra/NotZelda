"""Combat system — player attacks, monster actions, projectiles, damage, monster AI tick."""

import asyncio
import random
import time
import traceback

from server import behavior_engine
from server.state import game
from server.constants import (
    ROOM_COLS, ROOM_ROWS, DIRECTIONS, DIRECTION_OPPOSITES,
    INVINCIBILITY_DURATION, PLAYER_RESPAWN_DELAY, STARTING_ROOM,
    HEART_DROP_CHANCE, ATTACK_COOLDOWN, PROJECTILE_TICK_RATE,
)
from server.models import Projectile
from server.net import send_to, broadcast_to_room, players_in_room, player_info
from server.dungeons import is_dungeon_room


# ---------------------------------------------------------------------------
# Message batching — all game state changes are synchronous, messages are
# collected in a list and flushed after the entire tick completes.
#
# Tuple format:
#   ("broadcast", room_id, msg_dict, exclude_ws_or_None)
#   ("send", player, msg_dict)
#   ("death", player, old_room_id)
# ---------------------------------------------------------------------------

def _apply_damage(player, damage: int, room_id: str, msgs: list):
    """Synchronously apply damage to a player and append messages to the batch."""
    if player.has_flag("invulnerable"):
        return
    now = time.monotonic()
    if now - player.last_damage_time < INVINCIBILITY_DURATION:
        return
    player.hp = max(0, player.hp - damage)
    player.last_damage_time = now

    if player.hp > 0:
        # Calculate knockback — push player away from facing direction
        opp = DIRECTION_OPPOSITES.get(player.direction, "down")
        kdx, kdy = DIRECTIONS[opp]
        kx, ky = player.x + kdx, player.y + kdy
        knocked = False
        room = game.rooms.get(room_id)
        if room:
            tilemap = room["tilemap"]
            guards = game.guards.get(room_id, [])
            if 0 <= kx < ROOM_COLS and 0 <= ky < ROOM_ROWS and game.is_walkable_tile(tilemap[ky][kx]):
                if not any(g["x"] == kx and g["y"] == ky for g in guards):
                    player.x, player.y = kx, ky
                    knocked = True

        msgs.append(("broadcast", room_id, {
            "type": "player_hurt",
            "name": player.name,
            "hp": player.hp,
            "max_hp": player.max_hp,
            "x": player.x,
            "y": player.y,
            "knockback": knocked,
        }, None))
    else:
        # Player died
        msgs.append(("broadcast", room_id, {
            "type": "player_died",
            "name": player.name,
            "x": player.x,
            "y": player.y,
            "color_index": player.color_index,
        }, player.ws))
        msgs.append(("send", player, {
            "type": "you_died",
            "x": player.x,
            "y": player.y,
        }))
        msgs.append(("death", player, room_id))


async def _flush_messages(msgs: list):
    """Send all batched messages and schedule death respawns."""
    for entry in msgs:
        kind = entry[0]
        if kind == "broadcast":
            _, room_id, msg, exclude = entry
            await broadcast_to_room(room_id, msg, exclude=exclude)
        elif kind == "send":
            _, player, msg = entry
            await send_to(player, msg)
        elif kind == "death":
            _, player, old_room_id = entry
            asyncio.ensure_future(_death_respawn(player, old_room_id))
    msgs.clear()


async def _death_respawn(player, old_room_id):
    """Background task — wait for death animation, then respawn the player."""
    await asyncio.sleep(PLAYER_RESPAWN_DELAY)

    # If player disconnected during death animation, skip respawn
    if player.ws not in game.players:
        return

    # Remove from game during respawn so ticks/projectiles can't target us
    game.players.pop(player.ws, None)
    try:
        player.hp = player.max_hp
        player.room = STARTING_ROOM
        spawn = game.rooms[STARTING_ROOM]["spawn_points"]["default"]
        player.x, player.y = spawn
        player.direction = "down"
        player.dancing = False

        # Import here to avoid circular dependency (lifecycle -> combat -> lifecycle)
        from server.lifecycle import on_player_enter_room, on_player_leave_room, send_room_enter

        await broadcast_to_room(old_room_id, {
            "type": "player_left", "name": player.name,
        })
        await on_player_leave_room(old_room_id)
        await on_player_enter_room(STARTING_ROOM)
        await send_room_enter(player)
        await broadcast_to_room(
            STARTING_ROOM,
            {"type": "player_entered", **player_info(player)},
        )
    finally:
        # Only re-add if player didn't disconnect during respawn
        if player.ws not in game.players:
            game.players[player.ws] = player


async def damage_player(player, damage: int, room_id: str):
    """Apply contact damage to a player from a monster.

    Async wrapper around _apply_damage for callers outside the tick loop
    (e.g. handle_move contact damage).
    """
    msgs = []
    _apply_damage(player, damage, room_id, msgs)
    await _flush_messages(msgs)


async def handle_attack(player):
    """Handle a player's sword attack."""
    if player.hp <= 0:
        return
    if not player.has_flag("has_sword"):
        await send_to(player, {"type": "info", "text": "You don't have a weapon."})
        return
    now = time.monotonic()
    if now - player.last_attack_time < ATTACK_COOLDOWN:
        return
    player.last_attack_time = now
    player.dancing = False

    msgs = []
    msgs.append(("broadcast", player.room, {
        "type": "attack",
        "name": player.name,
        "direction": player.direction,
    }, None))

    # Hit detection — check if sword hits a monster (supports multi-tile monsters)
    from server.lifecycle import get_room_monsters
    dx, dy = DIRECTIONS.get(player.direction, (0, 0))
    hit_x = player.x + dx
    hit_y = player.y + dy
    for i, monster in enumerate(get_room_monsters(player.room)):
        if monster.alive and not monster.intangible and monster.occupies(hit_x, hit_y):
            monster.hp -= 1
            if monster.hp <= 0:
                monster.alive = False
                monster._pending_warmup = None
                msgs.append(("broadcast", player.room, {
                    "type": "monster_killed",
                    "id": i,
                    "x": monster.x,
                    "y": monster.y,
                }, None))
                # Heart drop
                if random.random() < HEART_DROP_CHANCE:
                    hid = game.next_heart_id
                    game.next_heart_id += 1
                    heart = {"x": monster.x, "y": monster.y, "id": hid}
                    game.room_hearts.setdefault(player.room, []).append(heart)
                    msgs.append(("broadcast", player.room, {
                        "type": "heart_spawned",
                        "id": hid,
                        "x": monster.x,
                        "y": monster.y,
                    }, None))
                # Mark dungeon room as cleared if all monsters dead
                if is_dungeon_room(player.room):
                    alive = [m for m in game.room_monsters[player.room] if m.alive]
                    if not alive:
                        game.active_dungeon.cleared_rooms.add(player.room)
                        # Boss defeated — silence music in the dungeon
                        if monster.kind == "dungeon_warden":
                            msgs.append(("broadcast", player.room, {
                                "type": "music_change", "music": None,
                            }, None))
            else:
                msgs.append(("broadcast", player.room, {
                    "type": "monster_hit",
                    "id": i,
                    "x": monster.x,
                    "y": monster.y,
                    "hp": monster.hp,
                }, None))

    await _flush_messages(msgs)


# ---------------------------------------------------------------------------
# Action execution — called by monster_tick when behavior engine returns.
# All sync — append messages to the batch instead of awaiting sends.
# ---------------------------------------------------------------------------

def exec_move(monster, room_id, monster_idx, action, msgs):
    """Move the monster and check for contact damage."""
    nx, ny = action["x"], action["y"]
    monster.x = nx
    monster.y = ny
    msgs.append(("broadcast", room_id, {
        "type": "monster_moved",
        "id": monster_idx,
        "x": nx,
        "y": ny,
    }, None))
    # Contact damage — monster landed on a player (supports multi-tile monsters)
    for p in players_in_room(room_id):
        if p.hp > 0 and monster.occupies(p.x, p.y):
            _apply_damage(p, monster.damage, room_id, msgs)


def exec_projectile(monster, room_id, monster_idx, action, msgs):
    """Spawn a projectile from the monster in the resolved direction."""
    dx, dy = action["dx"], action["dy"]
    damage = action.get("damage", 1)
    color = action.get("sprite_color", "#ff0000")
    speed = action.get("speed", 1)
    piercing = action.get("piercing", False)

    # For multi-tile monsters, spawn from the edge tile closest to the direction
    w, h = monster.width, monster.height
    if dx > 0:
        spawn_col = monster.x + w - 1  # rightmost column
    elif dx < 0:
        spawn_col = monster.x           # leftmost column
    else:
        spawn_col = monster.x + w // 2  # center
    if dy > 0:
        spawn_row = monster.y + h - 1   # bottom row
    elif dy < 0:
        spawn_row = monster.y            # top row
    else:
        spawn_row = monster.y + h // 2   # center
    start_x = spawn_col + dx
    start_y = spawn_row + dy
    if start_x < 0 or start_x >= ROOM_COLS or start_y < 0 or start_y >= ROOM_ROWS:
        return
    room = game.rooms.get(room_id)
    if not room:
        return
    if not game.is_walkable_tile(room["tilemap"][start_y][start_x]):
        return

    proj_id = game.next_projectile_id
    game.next_projectile_id += 1
    proj = Projectile(start_x, start_y, dx, dy, damage, color, room_id, speed, piercing)

    if room_id not in game.room_projectiles:
        game.room_projectiles[room_id] = {}
    game.room_projectiles[room_id][proj_id] = proj

    msgs.append(("broadcast", room_id, {
        "type": "projectile_spawned",
        "id": proj_id,
        "x": start_x,
        "y": start_y,
        "dx": dx,
        "dy": dy,
        "color": color,
    }, None))

    # Check if a player is already at the spawn tile
    for p in players_in_room(room_id):
        if p.hp > 0 and p.x == start_x and p.y == start_y:
            msgs.append(("broadcast", room_id, {
                "type": "projectile_hit", "id": proj_id,
                "x": start_x, "y": start_y,
            }, None))
            _apply_damage(p, damage, room_id, msgs)
            game.room_projectiles.get(room_id, {}).pop(proj_id, None)
            return


def warmup_charge(monster, room_id, monster_idx, action, msgs):
    """Send charge prep visuals when warmup starts."""
    dx, dy = action["dx"], action["dy"]
    max_range = action.get("range", 3)

    lane = []
    nx, ny = monster.x, monster.y
    for _ in range(max_range):
        nx += dx
        ny += dy
        if not behavior_engine._can_move_to(monster, nx, ny, room_id):
            break
        lane.append([nx, ny])

    msgs.append(("broadcast", room_id, {
        "type": "charge_prep",
        "id": monster_idx,
        "dx": dx,
        "dy": dy,
        "lane": lane,
    }, None))


def exec_charge(monster, room_id, monster_idx, action, msgs):
    """Execute the charge dash with locked-in direction."""
    dx, dy = action["dx"], action["dy"]
    max_range = action.get("range", 3)
    damage = action.get("damage", monster.damage)
    path = []

    nx, ny = monster.x, monster.y
    for _ in range(max_range):
        nx += dx
        ny += dy
        if not behavior_engine._can_move_to(monster, nx, ny, room_id):
            break
        path.append([nx, ny])

    if not path:
        return

    end_x, end_y = path[-1]
    monster.x = end_x
    monster.y = end_y

    msgs.append(("broadcast", room_id, {
        "type": "monster_charged",
        "id": monster_idx,
        "path": path,
        "x": end_x,
        "y": end_y,
    }, None))

    # Check if player was hit — for multi-tile monsters, expand each path
    # position to the monster's full footprint
    w, h = monster.width, monster.height
    for p in players_in_room(room_id):
        if p.hp > 0 and any(
            px <= p.x < px + w and py <= p.y < py + h
            for px, py in path
        ):
            _apply_damage(p, damage, room_id, msgs)


def warmup_teleport(monster, room_id, monster_idx, action, msgs):
    """Send teleport start visuals when warmup starts (monster fades out)."""
    msgs.append(("broadcast", room_id, {
        "type": "teleport_start",
        "id": monster_idx,
        "target_x": action["target_x"],
        "target_y": action["target_y"],
        "delay": action.get("ticks", 1) * monster.tick_interval,
        "damage_radius": action.get("damage_radius", 1),
    }, None))


def exec_teleport(monster, room_id, monster_idx, action, msgs):
    """Execute teleport — move monster to target and deal damage."""
    target_x = action["target_x"]
    target_y = action["target_y"]
    damage = action.get("damage", monster.damage)

    monster.x = target_x
    monster.y = target_y

    msgs.append(("broadcast", room_id, {
        "type": "teleport_end",
        "id": monster_idx,
        "x": target_x,
        "y": target_y,
    }, None))

    # Damage players within damage_radius of landing position
    damage_radius = action.get("damage_radius", 1)
    if damage > 0 and damage_radius >= 0:
        for p in players_in_room(room_id):
            if p.hp > 0 and abs(p.x - monster.x) + abs(p.y - monster.y) <= damage_radius:
                _apply_damage(p, damage, room_id, msgs)


def warmup_area(monster, room_id, monster_idx, action, msgs):
    """Send area warning visuals when warmup starts."""
    msgs.append(("broadcast", room_id, {
        "type": "area_warning",
        "id": monster_idx,
        "x": action["x"],
        "y": action["y"],
        "range": action["range"],
        "duration": action.get("ticks", 1) * monster.tick_interval,
    }, None))


def exec_area(monster, room_id, monster_idx, action, msgs):
    """Execute area attack — damage all players within range."""
    damage = action.get("damage", monster.damage)
    range_val = action.get("range", 2)
    # Use locked-in position from warmup
    ax = action.get("x", monster.x)
    ay = action.get("y", monster.y)

    msgs.append(("broadcast", room_id, {
        "type": "area_attack",
        "id": monster_idx,
        "x": ax,
        "y": ay,
        "range": range_val,
    }, None))

    for p in players_in_room(room_id):
        if p.hp > 0:
            dist = abs(p.x - ax) + abs(p.y - ay)
            if dist <= range_val:
                _apply_damage(p, damage, room_id, msgs)


# Dispatch tables for warmup visuals and execution
WARMUP_HANDLERS = {
    "charge": warmup_charge,
    "teleport": warmup_teleport,
    "area": warmup_area,
}

EXEC_HANDLERS = {
    "move": exec_move,
    "projectile": exec_projectile,
    "charge": exec_charge,
    "teleport": exec_teleport,
    "area": exec_area,
}


# ---------------------------------------------------------------------------
# Background tick loops
# ---------------------------------------------------------------------------

async def projectile_tick():
    """Background loop — moves projectiles and checks collisions."""
    while True:
        await asyncio.sleep(PROJECTILE_TICK_RATE)
        msgs = []
        for room_id in list(game.room_projectiles.keys()):
            if room_id not in game.rooms:
                del game.room_projectiles[room_id]
                continue
            projs = game.room_projectiles[room_id]
            to_remove = []
            for proj_id, proj in list(projs.items()):
                try:
                    # Move by speed tiles per tick
                    for _ in range(proj.speed):
                        proj.x += proj.dx
                        proj.y += proj.dy

                        # Out of bounds or hit a wall
                        if (proj.x < 0 or proj.x >= ROOM_COLS or
                                proj.y < 0 or proj.y >= ROOM_ROWS or
                                not game.is_walkable_tile(game.rooms[room_id]["tilemap"][proj.y][proj.x])):
                            to_remove.append(proj_id)
                            msgs.append(("broadcast", room_id, {
                                "type": "projectile_gone", "id": proj_id,
                            }, None))
                            break

                        # Check player collision
                        hit_player = False
                        for p in players_in_room(room_id):
                            if p.hp > 0 and p.x == proj.x and p.y == proj.y:
                                msgs.append(("broadcast", room_id, {
                                    "type": "projectile_hit", "id": proj_id,
                                    "x": proj.x, "y": proj.y,
                                }, None))
                                _apply_damage(p, proj.damage, room_id, msgs)
                                hit_player = True
                                if not proj.piercing:
                                    to_remove.append(proj_id)
                                    break
                        if hit_player and not proj.piercing:
                            break
                    else:
                        # No wall hit during multi-step move — send position update
                        if proj_id not in to_remove:
                            msgs.append(("broadcast", room_id, {
                                "type": "projectile_moved", "id": proj_id,
                                "x": proj.x, "y": proj.y,
                            }, None))
                except Exception:
                    traceback.print_exc()
                    to_remove.append(proj_id)

            for pid in to_remove:
                projs.pop(pid, None)
            if not projs:
                game.room_projectiles.pop(room_id, None)

        await _flush_messages(msgs)


async def monster_tick():
    """Background loop — ticks alive monsters in rooms that have players."""
    while True:
        await asyncio.sleep(0.25)
        now = time.monotonic()
        msgs = []
        for room_id, monster_list in list(game.room_monsters.items()):
            if room_id not in game.rooms:
                continue
            if not players_in_room(room_id):
                continue
            for i, monster in enumerate(monster_list):
                try:
                    if not monster.alive:
                        monster._pending_warmup = None
                        continue
                    # Intangible monsters (mid-teleport) still tick for warmup countdown
                    # but non-warmup ticks are skipped
                    if monster.intangible and monster._pending_warmup is None:
                        continue
                    if now - monster.last_tick_time < monster.tick_interval:
                        continue
                    monster.last_tick_time = now

                    result = behavior_engine.monster_tick(monster, room_id)
                    if result is None:
                        continue

                    phase = result.get("phase")
                    action_name = result.get("action")

                    if phase == "warmup":
                        handler = WARMUP_HANDLERS.get(action_name)
                        if handler:
                            handler(monster, room_id, i, result, msgs)

                    elif phase == "execute":
                        handler = EXEC_HANDLERS.get(action_name)
                        if handler:
                            handler(monster, room_id, i, result, msgs)
                except Exception:
                    traceback.print_exc()

        await _flush_messages(msgs)
