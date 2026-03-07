"""Combat system — player attacks, monster attacks, projectiles, damage, monster AI tick."""

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
        if monster.alive and monster.x == hit_x and monster.y == hit_y:
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
# Monster attack execution (Stage 5)
# ---------------------------------------------------------------------------

async def execute_monster_attack(monster, room_id, monster_idx):
    """Select and execute the best available attack for a monster."""
    behavior = getattr(monster, "behavior", None)
    if not behavior:
        return
    attacks = behavior.get("attacks", [])
    if not attacks:
        return

    cooldowns = monster._attack_cooldowns
    now = time.monotonic()
    player, player_dist = behavior_engine._nearest_player(monster, room_id)
    if player is None:
        return

    for i, atk in enumerate(attacks):
        last_used = cooldowns.get(i, 0)
        cd = atk.get("cooldown", 1.0)
        if now - last_used < cd:
            continue
        if player_dist > atk.get("range", 1):
            continue
        if atk.get("type") == "charge" and monster.x != player.x and monster.y != player.y:
            continue

        # This attack is usable — execute it
        monster._attack_cooldowns[i] = now
        atype = atk["type"]

        if atype == "melee":
            await attack_melee(monster, room_id, monster_idx, atk, player)
        elif atype == "projectile":
            await attack_projectile(monster, room_id, monster_idx, atk, player)
        elif atype == "charge":
            await attack_charge(monster, room_id, monster_idx, atk, player)
        elif atype == "teleport":
            await attack_teleport(monster, room_id, monster_idx, atk, player)
        elif atype == "area":
            await attack_area(monster, room_id, monster_idx, atk)
        return  # one attack per tick


async def attack_melee(monster, room_id, monster_idx, atk, target):
    """Enhanced melee — strike adjacent player without moving onto them."""
    damage = atk.get("damage", monster.damage)
    await broadcast_to_room(room_id, {
        "type": "monster_attack",
        "id": monster_idx,
        "attack_type": "melee",
        "target_x": target.x,
        "target_y": target.y,
    })
    await damage_player(target, damage, room_id)


async def attack_projectile(monster, room_id, monster_idx, atk, target):
    """Fire a projectile toward the nearest player in a cardinal direction."""
    dx_raw = target.x - monster.x
    dy_raw = target.y - monster.y
    if dx_raw == 0 and dy_raw == 0:
        return
    if abs(dx_raw) >= abs(dy_raw):
        dx, dy = (1 if dx_raw > 0 else -1), 0
    else:
        dx, dy = 0, (1 if dy_raw > 0 else -1)

    color = atk.get("sprite_color", "#ff0000")
    damage = atk.get("damage", 1)
    speed = atk.get("speed", 1)
    piercing = atk.get("piercing", False)

    # Projectile starts one tile away from monster
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


async def attack_charge(monster, room_id, monster_idx, atk, target):
    """Lock in charge direction and enter prep state. Actual dash happens next tick."""
    dx_raw = target.x - monster.x
    dy_raw = target.y - monster.y
    if dx_raw == 0 and dy_raw == 0:
        return
    if abs(dx_raw) >= abs(dy_raw):
        dx, dy = (1 if dx_raw > 0 else -1), 0
    else:
        dx, dy = 0, (1 if dy_raw > 0 else -1)

    # Store prep — direction is locked, charge fires next tick
    monster._charge_prep = {"dx": dx, "dy": dy, "atk": atk}

    # Build the preview lane
    max_range = atk.get("range", 3)
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


async def execute_charge_from_prep(monster, room_id, monster_idx, prep):
    """Execute the actual charge dash from a prepped direction."""
    dx = prep["dx"]
    dy = prep["dy"]
    atk = prep["atk"]
    max_range = atk.get("range", 3)
    damage = atk.get("damage", monster.damage)
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


async def attack_teleport(monster, room_id, monster_idx, atk, target):
    """Disappear, then reappear near the target player after a brief delay."""
    damage = atk.get("damage", monster.damage)
    delay = atk.get("delay", 0.5)

    # Find a walkable tile adjacent to the target
    target_pos = None
    candidates = [(1, 0), (-1, 0), (0, 1), (0, -1)]
    random.shuffle(candidates)
    for ddx, ddy in candidates:
        nx, ny = target.x + ddx, target.y + ddy
        if behavior_engine._is_walkable(nx, ny, room_id):
            target_pos = (nx, ny)
            break
    if target_pos is None:
        return

    monster._teleporting = True
    await broadcast_to_room(room_id, {
        "type": "teleport_start",
        "id": monster_idx,
        "target_x": target_pos[0],
        "target_y": target_pos[1],
        "delay": delay,
    })

    async def complete_teleport():
        await asyncio.sleep(delay)
        if not monster.alive:
            monster._teleporting = False
            return
        monster.x = target_pos[0]
        monster.y = target_pos[1]
        monster._teleporting = False
        await broadcast_to_room(room_id, {
            "type": "teleport_end",
            "id": monster_idx,
            "x": target_pos[0],
            "y": target_pos[1],
        })
        # Damage any adjacent player after landing
        for p in players_in_room(room_id):
            if p.hp > 0 and abs(p.x - monster.x) + abs(p.y - monster.y) <= 1:
                await damage_player(p, damage, room_id)

    asyncio.create_task(complete_teleport())


async def attack_area(monster, room_id, monster_idx, atk):
    """Ground slam — warning indicator, then damage all players within range."""
    damage = atk.get("damage", monster.damage)
    range_val = atk.get("range", 2)
    warning_duration = atk.get("warning_duration", 0.75)

    await broadcast_to_room(room_id, {
        "type": "area_warning",
        "id": monster_idx,
        "x": monster.x,
        "y": monster.y,
        "range": range_val,
        "duration": warning_duration,
    })

    async def execute_area():
        await asyncio.sleep(warning_duration)
        if not monster.alive:
            return
        await broadcast_to_room(room_id, {
            "type": "area_attack",
            "id": monster_idx,
            "x": monster.x,
            "y": monster.y,
            "range": range_val,
        })
        for p in players_in_room(room_id):
            if p.hp > 0:
                dist = abs(p.x - monster.x) + abs(p.y - monster.y)
                if dist <= range_val:
                    await damage_player(p, damage, room_id)

    asyncio.create_task(execute_area())


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
    """Background loop — hops alive monsters in rooms that have players."""
    while True:
        await asyncio.sleep(0.25)
        now = time.monotonic()
        for room_id, monster_list in list(game.room_monsters.items()):
            # Only simulate rooms with players
            if not players_in_room(room_id):
                continue
            for i, monster in enumerate(monster_list):
                if not monster.alive or monster._teleporting:
                    continue
                if now - monster.last_hop_time < monster.hop_interval:
                    continue
                monster.last_hop_time = now

                # Execute pending charge prep (locked direction from previous tick)
                if monster._charge_prep is not None:
                    prep = monster._charge_prep
                    monster._charge_prep = None
                    await execute_charge_from_prep(monster, room_id, i, prep)
                    continue

                # Evaluate behavior rules -> pick action -> execute
                action = behavior_engine.evaluate_rules(monster, room_id)

                if action == "attack":
                    await execute_monster_attack(monster, room_id, i)
                else:
                    result = behavior_engine.execute_action(action, monster, room_id)
                    if result is not None:
                        nx, ny = result
                        monster.x = nx
                        monster.y = ny
                        await broadcast_to_room(room_id, {
                            "type": "monster_moved",
                            "id": i,
                            "x": nx,
                            "y": ny,
                        })
                        # Check if monster landed on a player
                        for p in players_in_room(room_id):
                            if p.x == nx and p.y == ny and p.hp > 0:
                                await damage_player(p, monster.damage, room_id)
