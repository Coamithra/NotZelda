"""Combat system — damage, projectiles, monster AI tick, game loop."""

import asyncio
import math
import os
import time
import traceback

from server import behavior_engine
from server.state import game
from server.constants import (
    ROOM_COLS, ROOM_ROWS, DIRECTIONS, DIRECTION_OPPOSITES,
    INVINCIBILITY_DURATION, PLAYER_RESPAWN_DELAY, STARTING_ROOM,
    PROJECTILE_TICK_RATE,
    WALK_TIME, GUARD_COOLDOWN,
    HEART_RESTORE_HP, TICK_INTERVAL, COLLISION_GRACE_PERIOD,
)
from server.models import Projectile
from server.net import send_to, broadcast_to_room, avatars_in_room, player_info
from server.lifecycle import set_monster_idle

_debug = os.environ.get("DEBUG_MODE", "").lower() in ("1", "true")


# ---------------------------------------------------------------------------
# Message batching — all game state changes are synchronous, messages are
# collected in a list and flushed after the entire tick completes.
#
# Tuple format:
#   ("broadcast", room_id, msg_dict, exclude_ws_or_None)
#   ("send", player, msg_dict)
#   ("death", player, old_room_id)
#   ("guard_chat", player, guard)
#   ("npc_chat", player, guard, text)
#   ("debug_spawn", player, args)
# ---------------------------------------------------------------------------

def _apply_damage(player, damage: int, room_id: str, msgs: list,
                   source_x: float = None, source_y: float = None,
                   prev_player_x: float = None, prev_player_y: float = None,
                   prev_source_x: float = None, prev_source_y: float = None,
                   source_w: float = 1, source_h: float = 1):
    """Synchronously apply damage to a player and append messages to the batch."""
    if player.has_flag("invulnerable"):
        return
    now = time.monotonic()
    if now - player.last_damage_time < INVINCIBILITY_DURATION:
        return
    player.hp = max(0, player.hp - damage)
    player.last_damage_time = now
    a = player.avatar

    if player.hp > 0:
        # Calculate knockback direction from previous positions (before overlap)
        pre_x, pre_y = a.x, a.y
        if prev_player_x is not None and prev_source_x is not None:
            dx = prev_player_x - prev_source_x
            dy = prev_player_y - prev_source_y
        elif source_x is not None and source_y is not None:
            dx = a.x - source_x
            dy = a.y - source_y
        else:
            dx, dy = 0, 0
        # Determine knockback axis and sign
        if dx == 0 and dy == 0:
            opp = DIRECTION_OPPOSITES.get(a.direction, "down")
            knock_dx, knock_dy = DIRECTIONS[opp]
        elif abs(dx) >= abs(dy):
            knock_dx = 1 if dx >= 0 else -1
            knock_dy = 0
        else:
            knock_dx = 0
            knock_dy = 1 if dy >= 0 else -1
        # Target: fixed 1 tile knockback, snapped to nearest half-tile
        kx = round((a.x + knock_dx) * 2) / 2
        ky = round((a.y + knock_dy) * 2) / 2
        knocked = False
        room = game.rooms.get(room_id)
        if room:
            from server.commands import _is_position_walkable
            guards = game.guards.get(room_id, [])
            if 0 <= kx < ROOM_COLS and 0 <= ky < ROOM_ROWS and _is_position_walkable(kx, ky, room):
                guard_blocked = any(
                    kx < g["x"] + 1 and kx + 1 > g["x"] and
                    ky < g["y"] + 1 and ky + 1 > g["y"]
                    for g in guards
                )
                if not guard_blocked:
                    a.x, a.y = kx, ky
                    knocked = True

        msgs.append(("broadcast", room_id, {
            "type": "player_hurt",
            "name": player.name,
            "hp": player.hp,
            "max_hp": player.max_hp,
            "x": a.x,
            "y": a.y,
            "knockback": knocked,
            "debug_pre_x": pre_x,
            "debug_pre_y": pre_y,
            "debug_source_x": source_x,
            "debug_source_y": source_y,
            "debug_prev_player_x": prev_player_x,
            "debug_prev_player_y": prev_player_y,
            "debug_prev_source_x": prev_source_x,
            "debug_prev_source_y": prev_source_y,
            "debug_source_w": source_w,
            "debug_source_h": source_h,
        }, None))
    else:
        # Player died
        msgs.append(("broadcast", room_id, {
            "type": "player_died",
            "name": player.name,
            "x": a.x,
            "y": a.y,
            "color_index": player.color_index,
        }, player.ws))
        msgs.append(("send", player, {
            "type": "you_died",
            "x": a.x,
            "y": a.y,
        }))
        msgs.append(("death", player, room_id))


async def flush_messages(msgs: list):
    """Send all batched messages and schedule background tasks."""
    from server.quests import handle_quest_npc
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
            player.dead = True
            player.death_time = time.monotonic()
            player.death_room = old_room_id
        elif kind == "guard_chat":
            _, player, guard = entry
            asyncio.ensure_future(handle_quest_npc(player, guard))
        elif kind == "npc_chat":
            from server.npc_chat import handle_npc_chat
            _, player, guard, text = entry
            asyncio.ensure_future(handle_npc_chat(player, guard, text))
        elif kind == "debug_spawn":
            from server.debug_monsters import handle_debug_spawn
            _, player, args = entry
            asyncio.ensure_future(handle_debug_spawn(player, args))
    msgs.clear()


def _respawn_player(player, msgs):
    """Synchronous respawn — called from _tick_players when delay has elapsed."""
    from server.lifecycle import on_player_enter_room, on_player_leave_room, send_room_enter
    from server.models import Avatar

    old_room_id = player.death_room
    player.dead = False
    player.death_time = 0.0
    player.death_room = None
    player.hp = player.max_hp
    player.room = STARTING_ROOM
    spawn = game.rooms[STARTING_ROOM]["spawn_points"]["default"]
    player.avatar = Avatar(float(spawn[0]), float(spawn[1]), "down")
    player.command_queue.clear()

    # Despawn summoned town guards — their job is done
    if old_room_id in game.room_monsters:
        for i, m in enumerate(game.room_monsters[old_room_id]):
            if m.kind == "town_guard" and m.alive:
                m.alive = False
                msgs.append(("broadcast", old_room_id, {
                    "type": "monster_killed",
                    "id": i, "x": m.x, "y": m.y,
                }, None))

    msgs.append(("broadcast", old_room_id, {
        "type": "player_left", "name": player.name,
    }, None))
    on_player_leave_room(old_room_id, msgs)
    # Update compass minimap for remaining dungeon players
    from server.dungeons import get_dungeon_for_room
    from server.lifecycle import broadcast_dungeon_player_positions
    dungeon_inst = get_dungeon_for_room(old_room_id)
    if dungeon_inst:
        broadcast_dungeon_player_positions(dungeon_inst, player, msgs)
    on_player_enter_room(STARTING_ROOM)
    send_room_enter(player, msgs)
    msgs.append(("broadcast", STARTING_ROOM,
                  {"type": "player_entered", **player_info(player)}, player.ws))


# ---------------------------------------------------------------------------
# Action execution — called by monster_tick when behavior engine returns.
# All sync — append messages to the batch instead of awaiting sends.
# ---------------------------------------------------------------------------

def start_walk(monster, room_id, monster_idx, action, msgs, now):
    """Start a smooth walk — set monster state and broadcast walk_started."""
    nx, ny = action["x"], action["y"]
    remaining = action.get("distance", 1) - 1  # distance includes this step
    monster.state = "walking"
    monster.move_seq += 1
    monster.state_data = {
        "from_x": monster.x, "from_y": monster.y,
        "to_x": nx, "to_y": ny,
        "start_time": now,
        "midpoint_checked": False,
        "room_id": room_id,
        "monster_idx": monster_idx,
        "remaining_distance": remaining,
        "direction": action.get("direction", "random"),
        "seq": monster.move_seq,
    }
    msgs.append(("broadcast", room_id, {
        "type": "monster_walk_started",
        "id": monster_idx,
        "from_x": monster.x, "from_y": monster.y,
        "to_x": nx, "to_y": ny,
        "walk_time": monster.walk_time,
        "seq": monster.move_seq,
    }, None))


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

    # Check if a player is already at the spawn tile (AABB overlap)
    for p, a in avatars_in_room(room_id):
        if p.hp > 0 and a.x < start_x + 1 and a.x + 1 > start_x and a.y < start_y + 1 and a.y + 1 > start_y:
            msgs.append(("broadcast", room_id, {
                "type": "projectile_hit", "id": proj_id,
                "x": start_x, "y": start_y,
            }, None))
            _apply_damage(p, damage, room_id, msgs, start_x, start_y)
            proj.hit_entities.add(id(p))
            if not piercing:
                game.room_projectiles.get(room_id, {}).pop(proj_id, None)
                return


def warmup_charge(monster, room_id, monster_idx, action, msgs):
    """Send charge prep visuals when warmup starts.

    Does NOT increment move_seq — charge_prep is visual-only (no position
    change).  The seq sent here lets the client detect staleness without
    advancing the counter past the preceding walk/idle state."""
    dx, dy = action["dx"], action["dy"]
    max_range = action.get("range", 3)

    lane = []
    seen = set()
    nx, ny = monster.x, monster.y
    for _ in range(max_range):
        nx += dx
        ny += dy
        if not behavior_engine._can_move_to(monster, nx, ny, room_id):
            break
        # Expand to full footprint for multi-tile monsters
        for ox in range(monster.width):
            for oy in range(monster.height):
                tile = (nx + ox, ny + oy)
                if tile not in seen:
                    seen.add(tile)
                    lane.append([nx + ox, ny + oy])

    msgs.append(("broadcast", room_id, {
        "type": "charge_prep",
        "id": monster_idx,
        "dx": dx,
        "dy": dy,
        "lane": lane,
        "seq": monster.move_seq,
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
    monster.move_seq += 1

    # Expand path to full footprint for the visual charge trail
    w, h = monster.width, monster.height
    trail = []
    if w == 1 and h == 1:
        trail = path
    else:
        seen = set()
        for px, py in path:
            for ox in range(w):
                for oy in range(h):
                    tile = (px + ox, py + oy)
                    if tile not in seen:
                        seen.add(tile)
                        trail.append([px + ox, py + oy])

    msgs.append(("broadcast", room_id, {
        "type": "monster_charged",
        "id": monster_idx,
        "path": trail,
        "x": end_x,
        "y": end_y,
        "seq": monster.move_seq,
    }, None))

    # Check if player was hit — AABB overlap with charge path
    for p, a in avatars_in_room(room_id):
        if p.hp > 0 and any(
            a.x < px + w and a.x + 1 > px and a.y < py + h and a.y + 1 > py
            for px, py in path
        ):
            _apply_damage(p, damage, room_id, msgs, monster.x, monster.y)


def warmup_teleport(monster, room_id, monster_idx, action, msgs):
    """Send teleport start visuals when warmup starts (monster fades out)."""
    msgs.append(("broadcast", room_id, {
        "type": "teleport_start",
        "id": monster_idx,
        "target_x": action["target_x"],
        "target_y": action["target_y"],
        "delay": action.get("ticks", 1) * monster.decision_time,
        "damage_radius": action.get("damage_radius", 1),
    }, None))


def exec_teleport(monster, room_id, monster_idx, action, msgs):
    """Execute teleport — move monster to target and deal damage."""
    target_x = action["target_x"]
    target_y = action["target_y"]
    damage = action.get("damage", monster.damage)

    monster.x = target_x
    monster.y = target_y
    monster.move_seq += 1

    msgs.append(("broadcast", room_id, {
        "type": "teleport_end",
        "id": monster_idx,
        "x": target_x,
        "y": target_y,
        "seq": monster.move_seq,
    }, None))

    # Damage players within damage_radius of landing position
    damage_radius = action.get("damage_radius", 1)
    if damage > 0 and damage_radius >= 0:
        w, h = monster.width, monster.height
        for p, a in avatars_in_room(room_id):
            if p.hp > 0:
                nearest_x = max(monster.x, min(a.x, monster.x + w - 1))
                nearest_y = max(monster.y, min(a.y, monster.y + h - 1))
                if abs(a.x - nearest_x) + abs(a.y - nearest_y) <= damage_radius:
                    _apply_damage(p, damage, room_id, msgs, monster.x, monster.y)


def warmup_area(monster, room_id, monster_idx, action, msgs):
    """Send area warning visuals when warmup starts."""
    msg = {
        "type": "area_warning",
        "id": monster_idx,
        "x": action["x"],
        "y": action["y"],
        "range": action["range"],
        "duration": action.get("ticks", 1) * monster.decision_time,
    }
    if action.get("width", 1) > 1:
        msg["width"] = action["width"]
    if action.get("height", 1) > 1:
        msg["height"] = action["height"]
    msgs.append(("broadcast", room_id, msg, None))


def exec_area(monster, room_id, monster_idx, action, msgs):
    """Execute area attack — damage all players within range."""
    damage = action.get("damage", monster.damage)
    range_val = action.get("range", 2)
    # Use locked-in position from warmup
    ax = action.get("x", monster.x)
    ay = action.get("y", monster.y)
    aw = action.get("width", 1)
    ah = action.get("height", 1)

    atk_msg = {
        "type": "area_attack",
        "id": monster_idx,
        "x": ax,
        "y": ay,
        "range": range_val,
    }
    if aw > 1:
        atk_msg["width"] = aw
    if ah > 1:
        atk_msg["height"] = ah
    msgs.append(("broadcast", room_id, atk_msg, None))

    for p, a in avatars_in_room(room_id):
        if p.hp > 0:
            # Manhattan distance from nearest tile in the boss footprint
            nearest_x = max(ax, min(a.x, ax + aw - 1))
            nearest_y = max(ay, min(a.y, ay + ah - 1))
            dist = abs(a.x - nearest_x) + abs(a.y - nearest_y)
            if dist <= range_val:
                _apply_damage(p, damage, room_id, msgs, ax, ay)


# Dispatch tables for warmup visuals and execution
WARMUP_HANDLERS = {
    "charge": warmup_charge,
    "teleport": warmup_teleport,
    "area": warmup_area,
}

EXEC_HANDLERS = {
    "projectile": exec_projectile,
    "charge": exec_charge,
    "teleport": exec_teleport,
    "area": exec_area,
}


# ---------------------------------------------------------------------------
# Background tick loops
# ---------------------------------------------------------------------------

def _tick_players(now, msgs):
    """Check dead players for respawn after death animation delay."""
    for player in list(game.players.values()):
        if player.dead and now - player.death_time >= PLAYER_RESPAWN_DELAY:
            _respawn_player(player, msgs)


def _tick_all_monsters(now, msgs):
    """Tick all monsters — walks, state machine, guard despawns."""
    for room_id, monster_list in list(game.room_monsters.items()):
        if room_id not in game.rooms:
            continue
        if not avatars_in_room(room_id):
            continue
        _check_guard_despawn(room_id, monster_list, now, msgs)
        for i, monster in enumerate(monster_list):
            try:
                if not monster.alive:
                    if monster.state != "idle":
                        monster.state = "idle"
                        monster.state_data = {}
                    continue
                # Walk progression — midpoint position at 50%, destination + collision at 100%
                if monster.state == "walking":
                    sd = monster.state_data
                    elapsed = now - sd["start_time"]
                    progress = min(elapsed / monster.walk_time, 1.0)
                    # At 50%: move hitbox to midpoint between origin and destination
                    if progress >= 0.5 and not sd["midpoint_checked"]:
                        sd["midpoint_checked"] = True
                        monster.x = (sd["from_x"] + sd["to_x"]) / 2
                        monster.y = (sd["from_y"] + sd["to_y"]) / 2
                        if not monster.intangible:
                            for p, pa in avatars_in_room(room_id):
                                if p.hp > 0 and (
                                    pa.x < monster.x + monster.width and pa.x + 1 > monster.x and
                                    pa.y < monster.y + monster.height and pa.y + 1 > monster.y):
                                    mid = id(monster)
                                    if mid not in pa.pending_collisions:
                                        pa.pending_collisions[mid] = {
                                            "monster": monster, "room_id": room_id, "time": now,
                                            "prev_player_x": pa.x, "prev_player_y": pa.y,
                                            "prev_source_x": sd["from_x"], "prev_source_y": sd["from_y"],
                                        }
                    # At 100%: commit to destination, check collision, complete walk
                    if progress >= 1.0:
                        monster.x = sd["to_x"]
                        monster.y = sd["to_y"]
                        if not monster.intangible:
                            mid_src_x = (sd["from_x"] + sd["to_x"]) / 2
                            mid_src_y = (sd["from_y"] + sd["to_y"]) / 2
                            for p, pa in avatars_in_room(room_id):
                                if p.hp > 0 and (
                                    pa.x < monster.x + monster.width and pa.x + 1 > monster.x and
                                    pa.y < monster.y + monster.height and pa.y + 1 > monster.y):
                                    mid = id(monster)
                                    if mid not in pa.pending_collisions:
                                        pa.pending_collisions[mid] = {
                                            "monster": monster, "room_id": room_id, "time": now,
                                            "prev_player_x": pa.x, "prev_player_y": pa.y,
                                            "prev_source_x": mid_src_x, "prev_source_y": mid_src_y,
                                        }
                        remaining = sd.get("remaining_distance", 0)
                        walk_dir = sd.get("direction", "random")
                        walk_seq = sd.get("seq", monster.move_seq)
                        monster.state = "idle"
                        monster.state_data = {}
                        msgs.append(("broadcast", room_id, {
                            "type": "monster_walk_complete",
                            "id": i,
                            "seq": walk_seq,
                        }, None))
                        # Chain next walk if distance remains
                        if remaining > 0 and monster.alive:
                            next_move = behavior_engine._resolve_move(
                                {"direction": walk_dir}, monster, room_id)
                            if next_move:
                                next_move["distance"] = remaining
                                next_move["direction"] = walk_dir
                                start_walk(monster, room_id, i, next_move, msgs, now)
                # State machine (behavior eval, warmup countdown)
                _tick_monster_state(monster, room_id, i, now, msgs)
            except Exception as e:
                print(f"[MONSTER TICK ERROR] monster {i} ({monster.kind}) in {room_id} "
                      f"state={monster.state}: {e}")
                traceback.print_exc()
                # Reset to safe state so the monster doesn't stay corrupted.
                # Snap position to nearest tile in case we crashed mid-walk
                # at a fractional coordinate.
                was_walking = monster.state == "walking"
                monster.x = round(monster.x)
                monster.y = round(monster.y)
                monster.state = "idle"
                monster.state_data = {}
                if was_walking:
                    msgs.append(("broadcast", room_id, {
                        "type": "monster_walk_complete", "id": i,
                        "seq": monster.move_seq,
                    }, None))
                if _debug:
                    # Re-raises past the per-monster loop — skips remaining
                    # monsters/rooms for this tick. Acceptable for dev only.
                    raise


def _tick_projectiles(msgs):
    """Move projectiles and check collisions (sync — appends to msgs batch)."""
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

                    # Check player collision (AABB overlap)
                    hit_player = False
                    for p, pa in avatars_in_room(room_id):
                        if id(p) in proj.hit_entities:
                            continue
                        if p.hp > 0 and pa.x < proj.x + 1 and pa.x + 1 > proj.x and pa.y < proj.y + 1 and pa.y + 1 > proj.y:
                            msgs.append(("broadcast", room_id, {
                                "type": "projectile_hit", "id": proj_id,
                                "x": proj.x, "y": proj.y,
                            }, None))
                            _apply_damage(p, proj.damage, room_id, msgs, proj.x, proj.y)
                            proj.hit_entities.add(id(p))
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


def _resolve_pending_collisions(now, msgs):
    """Check pending contact collisions — apply damage if grace period elapsed and still valid."""
    from server.commands import _get_monster_visual_pos
    from server.lifecycle import get_room_monsters
    for player in list(game.players.values()):
        a = player.avatar
        if a is None or not a.pending_collisions:
            continue
        for mid in list(a.pending_collisions):
            pc = a.pending_collisions[mid]
            monster = pc["monster"]
            room_id = pc["room_id"]
            # Stale check: player moved rooms, or monster/player dead
            if player.room != room_id or player.hp <= 0 or not monster.alive or monster.intangible:
                del a.pending_collisions[mid]
                continue
            # Check monster still in room
            if monster not in get_room_monsters(room_id):
                del a.pending_collisions[mid]
                continue
            # Re-check AABB overlap
            mx, my = _get_monster_visual_pos(monster, now)
            if not (a.x < mx + monster.width and a.x + 1 > mx and
                    a.y < my + monster.height and a.y + 1 > my):
                del a.pending_collisions[mid]
                continue
            # Grace period not yet elapsed
            if now - pc["time"] < COLLISION_GRACE_PERIOD:
                continue
            # All checks passed — apply damage
            del a.pending_collisions[mid]
            _apply_damage(player, monster.damage, room_id, msgs, mx, my,
                          pc["prev_player_x"], pc["prev_player_y"],
                          pc["prev_source_x"], pc["prev_source_y"],
                          source_w=monster.width, source_h=monster.height)
            break  # one hit per tick per player


async def _send_debug_state_snapshots():
    """Send full room state to players with /viewserver active."""
    from server.dungeons import get_dungeon_for_room
    for player in list(game.players.values()):
        if not getattr(player, '_viewserver', False):
            continue
        room_id = player.room
        # Players in this room (need name from player, position from avatar)
        players = []
        for p, a in avatars_in_room(room_id):
            players.append({"name": p.name, "x": a.x, "y": a.y})
        # Monsters
        monsters = []
        for m in game.room_monsters.get(room_id, []):
            monsters.append({
                "x": m.x, "y": m.y, "w": m.width, "h": m.height,
                "alive": m.alive, "kind": m.kind,
            })
        # Projectiles
        projectiles = []
        for proj in game.room_projectiles.get(room_id, {}).values():
            projectiles.append({"x": proj.x, "y": proj.y})
        # Hearts
        hearts = []
        for h in game.room_hearts.get(room_id, []):
            hearts.append({"x": h["x"], "y": h["y"]})
        # Dungeon ground items
        items = []
        dinst = get_dungeon_for_room(room_id)
        if dinst:
            for it in dinst.dungeon_items.get(room_id, []):
                items.append({"x": it["x"], "y": it["y"]})
        await send_to(player, {
            "type": "debug_state",
            "players": players,
            "monsters": monsters,
            "projectiles": projectiles,
            "hearts": hearts,
            "items": items,
        })


async def game_tick():
    """Unified game loop — processes commands, ticks players/monsters/projectiles at ~30Hz."""
    from server.commands import process_player_commands
    last_projectile_tick = time.monotonic()
    while True:
        await asyncio.sleep(TICK_INTERVAL)
        now = time.monotonic()
        msgs = []
        try:
            # Drain queued commands from all connected players
            for player in list(game.players.values()):
                if player.dead or player.avatar is None:
                    continue
                try:
                    process_player_commands(player, now, msgs)
                except Exception:
                    traceback.print_exc()
            _tick_players(now, msgs)
            _tick_all_monsters(now, msgs)
            _resolve_pending_collisions(now, msgs)
            if now - last_projectile_tick >= PROJECTILE_TICK_RATE:
                last_projectile_tick = now
                _tick_projectiles(msgs)
        except Exception:
            traceback.print_exc()
        await flush_messages(msgs)
        # Send debug state snapshots to /viewserver subscribers
        await _send_debug_state_snapshots()


GUARD_DESPAWN_TIMEOUT = 30.0   # seconds before summoned guards vanish
GUARD_DESPAWN_DISTANCE = 4     # Manhattan tiles — target escapes if beyond this
GUARD_DESPAWN_GRACE = 3.0      # seconds before distance check kicks in


def _check_guard_despawn(room_id, monster_list, now, msgs):
    """Despawn summoned town guards if timed out or target player escaped."""
    guards = [(i, m) for i, m in enumerate(monster_list)
              if m.kind == "town_guard" and m.alive]
    if not guards:
        return

    first = guards[0][1]
    spawn_time = getattr(first, '_guard_spawn_time', now)
    age = now - spawn_time

    # 30s hard timeout
    if age >= GUARD_DESPAWN_TIMEOUT:
        for i, m in guards:
            m.alive = False
            msgs.append(("broadcast", room_id, {
                "type": "monster_killed", "id": i, "x": m.x, "y": m.y,
            }, None))
        return

    # After grace period, check if target player escaped
    if age < GUARD_DESPAWN_GRACE:
        return
    target_name = getattr(first, '_guard_target', None)
    if not target_name:
        return

    # Find target in room (need avatar for distance check)
    target_avatar = None
    for p, a in avatars_in_room(room_id):
        if p.name == target_name:
            target_avatar = a
            break

    if target_avatar is None:
        # Target left the room or has no avatar — despawn
        for i, m in guards:
            m.alive = False
            msgs.append(("broadcast", room_id, {
                "type": "monster_killed", "id": i, "x": m.x, "y": m.y,
            }, None))
        return

    # Despawn if target is beyond distance from ALL guards
    nearest = min(abs(target_avatar.x - m.x) + abs(target_avatar.y - m.y) for _, m in guards)
    if nearest > GUARD_DESPAWN_DISTANCE:
        for i, m in guards:
            m.alive = False
            msgs.append(("broadcast", room_id, {
                "type": "monster_killed", "id": i, "x": m.x, "y": m.y,
            }, None))


def _tick_monster_state(monster, room_id, i, now, msgs):
    """Process one monster's state machine tick (called from 33ms loop)."""
    state = monster.state

    if state == "walking":
        # Walk progression handled by _tick_monster_walks
        return

    if state in ("charging", "teleporting", "area"):
        # Warmup — time-based end
        sd = monster.state_data
        if now >= sd["end_time"]:
            action_name = sd["action_name"]
            action = sd["action"]
            handler = EXEC_HANDLERS.get(action_name)
            if handler:
                handler(monster, room_id, i, action, msgs)
            set_monster_idle(monster, room_id, i, msgs)
        return

    # state == "idle" — decision timer runs continuously (even during other states)
    # so if walk/warmup took longer than decision_time, we evaluate immediately
    if now - monster.last_action_time < monster.decision_time:
        return  # not time to decide yet

    # Decision point — reset timer regardless of outcome
    monster.last_action_time = now

    result = behavior_engine.monster_tick(monster, room_id)
    if result is None:
        return

    action_name = result.get("action")
    warmup = result.get("warmup", 0)

    if action_name == "move":
        start_walk(monster, room_id, i, result, msgs, now)
        return

    if action_name == "hold":
        return

    # Projectile — instant, no state change
    if action_name == "projectile":
        handler = EXEC_HANDLERS.get("projectile")
        if handler:
            handler(monster, room_id, i, result, msgs)
        return

    # Warmup actions: charge, teleport, area
    if warmup > 0 and action_name in WARMUP_HANDLERS:
        state_name = {"charge": "charging", "teleport": "teleporting", "area": "area"}
        monster.state = state_name.get(action_name, "idle")
        monster.state_data = {
            "end_time": now + warmup * monster.decision_time,
            "action_name": action_name,
            "action": result,
        }
        handler = WARMUP_HANDLERS.get(action_name)
        if handler:
            handler(monster, room_id, i, result, msgs)
        return

    # No warmup — execute immediately
    handler = EXEC_HANDLERS.get(action_name)
    if handler:
        handler(monster, room_id, i, result, msgs)
