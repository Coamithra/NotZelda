"""Combat system — player attacks, monster actions, projectiles, damage, monster AI tick."""

import asyncio
import random
import time

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


async def damage_player(player, damage: int, room_id: str):
    """Apply contact damage to a player from a monster."""
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
        room = game.rooms[room_id]
        tilemap = room["tilemap"]
        guards = game.guards.get(room_id, [])
        if 0 <= kx < ROOM_COLS and 0 <= ky < ROOM_ROWS and game.is_walkable_tile(tilemap[ky][kx]):
            if not any(g["x"] == kx and g["y"] == ky for g in guards):
                player.x, player.y = kx, ky
                knocked = True

        await broadcast_to_room(room_id, {
            "type": "player_hurt",
            "name": player.name,
            "hp": player.hp,
            "max_hp": player.max_hp,
            "x": player.x,
            "y": player.y,
            "knockback": knocked,
        })
    else:
        # Player died
        await broadcast_to_room(room_id, {
            "type": "player_died",
            "name": player.name,
            "x": player.x,
            "y": player.y,
            "color_index": player.color_index,
        }, exclude=player.ws)
        await send_to(player, {
            "type": "you_died",
            "x": player.x,
            "y": player.y,
        })

        # Respawn after delay (match client death animation duration)
        await asyncio.sleep(PLAYER_RESPAWN_DELAY)
        old_room = player.room
        player.hp = player.max_hp
        player.room = STARTING_ROOM
        spawn = game.rooms[STARTING_ROOM]["spawn_points"]["default"]
        player.x, player.y = spawn
        player.direction = "down"
        player.dancing = False

        # Import here to avoid circular dependency (lifecycle -> combat -> lifecycle)
        from server.lifecycle import on_player_enter_room, on_player_leave_room, send_room_enter

        await broadcast_to_room(old_room, {
            "type": "player_left", "name": player.name,
        })
        await on_player_leave_room(old_room)
        await on_player_enter_room(STARTING_ROOM)
        await send_room_enter(player)
        await broadcast_to_room(
            STARTING_ROOM,
            {"type": "player_entered", **player_info(player)},
            exclude=player.ws,
        )


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

    await broadcast_to_room(player.room, {
        "type": "attack",
        "name": player.name,
        "direction": player.direction,
    })

    # Hit detection — check if sword hits a monster
    from server.lifecycle import get_room_monsters
    dx, dy = DIRECTIONS.get(player.direction, (0, 0))
    hit_x = player.x + dx
    hit_y = player.y + dy
    for i, monster in enumerate(get_room_monsters(player.room)):
        if monster.alive and not monster.intangible and monster.x == hit_x and monster.y == hit_y:
            monster.hp -= 1
            if monster.hp <= 0:
                monster.alive = False
                await broadcast_to_room(player.room, {
                    "type": "monster_killed",
                    "id": i,
                    "x": monster.x,
                    "y": monster.y,
                })
                # Heart drop
                if random.random() < HEART_DROP_CHANCE:
                    hid = game.next_heart_id
                    game.next_heart_id += 1
                    heart = {"x": monster.x, "y": monster.y, "id": hid}
                    game.room_hearts.setdefault(player.room, []).append(heart)
                    await broadcast_to_room(player.room, {
                        "type": "heart_spawned",
                        "id": hid,
                        "x": monster.x,
                        "y": monster.y,
                    })
                # Mark dungeon room as cleared if all monsters dead
                if is_dungeon_room(player.room):
                    alive = [m for m in game.room_monsters[player.room] if m.alive]
                    if not alive:
                        game.active_dungeon.cleared_rooms.add(player.room)
            else:
                await broadcast_to_room(player.room, {
                    "type": "monster_hit",
                    "id": i,
                    "x": monster.x,
                    "y": monster.y,
                    "hp": monster.hp,
                })


# ---------------------------------------------------------------------------
# Action execution — called by monster_tick when behavior engine returns
# ---------------------------------------------------------------------------

async def exec_move(monster, room_id, monster_idx, action):
    """Move the monster and check for contact damage."""
    nx, ny = action["x"], action["y"]
    monster.x = nx
    monster.y = ny
    await broadcast_to_room(room_id, {
        "type": "monster_moved",
        "id": monster_idx,
        "x": nx,
        "y": ny,
    })
    # Contact damage — monster landed on a player
    for p in players_in_room(room_id):
        if p.x == nx and p.y == ny and p.hp > 0:
            await damage_player(p, monster.damage, room_id)


async def exec_projectile(monster, room_id, monster_idx, action):
    """Spawn a projectile from the monster in the resolved direction."""
    dx, dy = action["dx"], action["dy"]
    damage = action.get("damage", 1)
    color = action.get("sprite_color", "#ff0000")
    speed = action.get("speed", 1)
    piercing = action.get("piercing", False)

    start_x = monster.x + dx
    start_y = monster.y + dy
    if start_x < 0 or start_x >= ROOM_COLS or start_y < 0 or start_y >= ROOM_ROWS:
        return
    if not game.is_walkable_tile(game.rooms[room_id]["tilemap"][start_y][start_x]):
        return

    proj_id = game.next_projectile_id
    game.next_projectile_id += 1
    proj = Projectile(start_x, start_y, dx, dy, damage, color, room_id, speed, piercing)

    if room_id not in game.room_projectiles:
        game.room_projectiles[room_id] = {}
    game.room_projectiles[room_id][proj_id] = proj

    await broadcast_to_room(room_id, {
        "type": "projectile_spawned",
        "id": proj_id,
        "x": start_x,
        "y": start_y,
        "dx": dx,
        "dy": dy,
        "color": color,
    })

    # Check if a player is already at the spawn tile
    for p in players_in_room(room_id):
        if p.hp > 0 and p.x == start_x and p.y == start_y:
            await broadcast_to_room(room_id, {"type": "projectile_hit", "id": proj_id, "x": start_x, "y": start_y})
            await damage_player(p, damage, room_id)
            game.room_projectiles.get(room_id, {}).pop(proj_id, None)
            return


async def warmup_charge(monster, room_id, monster_idx, action):
    """Send charge prep visuals when warmup starts."""
    dx, dy = action["dx"], action["dy"]
    max_range = action.get("range", 3)

    lane = []
    nx, ny = monster.x, monster.y
    for _ in range(max_range):
        nx += dx
        ny += dy
        if not behavior_engine._is_walkable(nx, ny, room_id):
            break
        lane.append([nx, ny])

    await broadcast_to_room(room_id, {
        "type": "charge_prep",
        "id": monster_idx,
        "dx": dx,
        "dy": dy,
        "lane": lane,
    })


async def exec_charge(monster, room_id, monster_idx, action):
    """Execute the charge dash with locked-in direction."""
    dx, dy = action["dx"], action["dy"]
    max_range = action.get("range", 3)
    damage = action.get("damage", monster.damage)
    path = []

    nx, ny = monster.x, monster.y
    for _ in range(max_range):
        nx += dx
        ny += dy
        if not behavior_engine._is_walkable(nx, ny, room_id):
            break
        path.append([nx, ny])

    if not path:
        return

    end_x, end_y = path[-1]
    monster.x = end_x
    monster.y = end_y

    await broadcast_to_room(room_id, {
        "type": "monster_charged",
        "id": monster_idx,
        "path": path,
        "x": end_x,
        "y": end_y,
    })

    for p in players_in_room(room_id):
        if p.hp > 0 and any(p.x == px and p.y == py for px, py in path):
            await damage_player(p, damage, room_id)


async def warmup_teleport(monster, room_id, monster_idx, action):
    """Send teleport start visuals when warmup starts (monster fades out)."""
    await broadcast_to_room(room_id, {
        "type": "teleport_start",
        "id": monster_idx,
        "target_x": action["target_x"],
        "target_y": action["target_y"],
        "delay": action.get("ticks", 1) * monster.tick_interval,
        "damage_radius": action.get("damage_radius", 1),
    })


async def exec_teleport(monster, room_id, monster_idx, action):
    """Execute teleport — move monster to target and deal damage."""
    target_x = action["target_x"]
    target_y = action["target_y"]
    damage = action.get("damage", monster.damage)

    monster.x = target_x
    monster.y = target_y

    await broadcast_to_room(room_id, {
        "type": "teleport_end",
        "id": monster_idx,
        "x": target_x,
        "y": target_y,
    })

    # Damage players within damage_radius of landing position
    damage_radius = action.get("damage_radius", 1)
    if damage > 0 and damage_radius >= 0:
        for p in players_in_room(room_id):
            if p.hp > 0 and abs(p.x - monster.x) + abs(p.y - monster.y) <= damage_radius:
                await damage_player(p, damage, room_id)


async def warmup_area(monster, room_id, monster_idx, action):
    """Send area warning visuals when warmup starts."""
    await broadcast_to_room(room_id, {
        "type": "area_warning",
        "id": monster_idx,
        "x": action["x"],
        "y": action["y"],
        "range": action["range"],
        "duration": action.get("ticks", 1) * monster.tick_interval,
    })


async def exec_area(monster, room_id, monster_idx, action):
    """Execute area attack — damage all players within range."""
    damage = action.get("damage", monster.damage)
    range_val = action.get("range", 2)
    # Use locked-in position from warmup
    ax = action.get("x", monster.x)
    ay = action.get("y", monster.y)

    await broadcast_to_room(room_id, {
        "type": "area_attack",
        "id": monster_idx,
        "x": ax,
        "y": ay,
        "range": range_val,
    })

    for p in players_in_room(room_id):
        if p.hp > 0:
            dist = abs(p.x - ax) + abs(p.y - ay)
            if dist <= range_val:
                await damage_player(p, damage, room_id)


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
        for room_id in list(game.room_projectiles.keys()):
            projs = game.room_projectiles[room_id]
            to_remove = []
            for proj_id, proj in list(projs.items()):
                # Move by speed tiles per tick
                for _ in range(proj.speed):
                    proj.x += proj.dx
                    proj.y += proj.dy

                    # Out of bounds or hit a wall
                    if (proj.x < 0 or proj.x >= ROOM_COLS or
                            proj.y < 0 or proj.y >= ROOM_ROWS or
                            not game.is_walkable_tile(game.rooms[room_id]["tilemap"][proj.y][proj.x])):
                        to_remove.append(proj_id)
                        await broadcast_to_room(room_id, {"type": "projectile_gone", "id": proj_id})
                        break

                    # Check player collision
                    hit_player = False
                    for p in players_in_room(room_id):
                        if p.hp > 0 and p.x == proj.x and p.y == proj.y:
                            await broadcast_to_room(room_id, {
                                "type": "projectile_hit", "id": proj_id,
                                "x": proj.x, "y": proj.y,
                            })
                            await damage_player(p, proj.damage, room_id)
                            hit_player = True
                            if not proj.piercing:
                                to_remove.append(proj_id)
                                break
                    if hit_player and not proj.piercing:
                        break
                else:
                    # No wall hit during multi-step move — send position update
                    if proj_id not in to_remove:
                        await broadcast_to_room(room_id, {
                            "type": "projectile_moved", "id": proj_id,
                            "x": proj.x, "y": proj.y,
                        })

            for pid in to_remove:
                projs.pop(pid, None)
            if not projs:
                game.room_projectiles.pop(room_id, None)


async def monster_tick():
    """Background loop — ticks alive monsters in rooms that have players."""
    while True:
        await asyncio.sleep(0.25)
        now = time.monotonic()
        for room_id, monster_list in list(game.room_monsters.items()):
            if not players_in_room(room_id):
                continue
            for i, monster in enumerate(monster_list):
                if not monster.alive:
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
                        await handler(monster, room_id, i, result)

                elif phase == "execute":
                    handler = EXEC_HANDLERS.get(action_name)
                    if handler:
                        await handler(monster, room_id, i, result)
