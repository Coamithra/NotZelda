"""Combat system — damage, projectiles, monster AI tick, game loop."""

import asyncio
import time
import traceback

from server import behavior_engine, log
from server.state import game
from server.constants import (
    DEBUG_MODE,
    ROOM_COLS, ROOM_ROWS, DIRECTIONS, DIRECTION_OPPOSITES,
    INVINCIBILITY_DURATION, PLAYER_RESPAWN_DELAY, STARTING_ROOM,
    PROJECTILE_TICK_RATE, SWORD_ACTIVE_DURATION,
    GUARD_DESPAWN_TIMEOUT, GUARD_DESPAWN_DISTANCE, GUARD_DESPAWN_GRACE,
    TICK_INTERVAL, COLLISION_GRACE_PERIOD,
    REVIVAL_DURATION, REVIVAL_PROXIMITY, REVIVAL_HP,
)
from server.net import send_to, broadcast_to_room, avatars_in_room, player_info


# ---------------------------------------------------------------------------
# Message batching — all game state changes are synchronous, messages are
# collected in a list and flushed after the entire tick completes.
#
# Tuple format:
#   ("broadcast", room_id, msg_dict, exclude_ws_or_None)
#   ("send", player, msg_dict)
#   ("death", player, old_room_id, death_x, death_y)
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
        # Cancel any revival this player is channeling
        for ts in game.tombstones.values():
            if ts.reviver is player:
                _cancel_revival(ts, msgs)
                break
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
        msgs.append(("death", player, room_id, a.x, a.y))


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
            _, player, old_room_id, dx, dy = entry
            player.dead = True
            player.death_time = time.monotonic()
            player.death_room = old_room_id
            player.death_x = dx
            player.death_y = dy
            player.avatar = None  # destroy physical presence — tombstone takes over
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
    player.death_x = 0.0
    player.death_y = 0.0
    player.chose_respawn = False
    player.hp = player.max_hp
    player.room = STARTING_ROOM
    spawn = game.rooms[STARTING_ROOM]["spawn_points"]["default"]
    player.avatar = Avatar(float(spawn[0]), float(spawn[1]), "down")
    player.command_queue.clear()
    player.active_attack = None

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
# Background tick loops
# ---------------------------------------------------------------------------

def _has_potential_revivers(player) -> bool:
    """Check if any alive player is in the same area (dungeon instance or overworld)."""
    from server.dungeons import get_dungeon_for_room, is_dungeon_room
    death_room = player.death_room
    inst = get_dungeon_for_room(death_room)
    for p in game.players.values():
        if p is player or p.dead:
            continue
        if inst:
            if p.room in inst.active_rooms:
                return True
        else:
            if not is_dungeon_room(p.room):
                return True
    return False


def _place_tombstone(player, now, msgs):
    """Create a Tombstone game object for a dead player."""
    from server.models import Tombstone
    ts = Tombstone(player, player.death_room, player.death_x, player.death_y)
    ts.created_time = now
    game.tombstones[player.name] = ts
    msgs.append(("broadcast", player.death_room, {
        "type": "tombstone_placed",
        "name": player.name, "x": ts.x, "y": ts.y, "color_index": ts.color_index,
    }, None))
    msgs.append(("send", player, {"type": "waiting_for_revival"}))
    log.event("TOMBSTONE", f"{player.name} tombstone placed in {player.death_room}")


def _remove_tombstone(name, msgs):
    """Remove a tombstone and broadcast its removal."""
    ts = game.tombstones.pop(name, None)
    if ts:
        if ts.reviver:
            msgs.append(("send", ts.reviver, {"type": "revival_cancelled"}))
        msgs.append(("broadcast", ts.room_id, {
            "type": "tombstone_removed", "name": name,
        }, None))


def _cancel_revival(ts, msgs):
    """Cancel an in-progress revival channel."""
    if ts.reviver:
        msgs.append(("send", ts.reviver, {"type": "revival_cancelled"}))
    msgs.append(("send", ts.player, {"type": "revival_cancelled"}))
    msgs.append(("broadcast", ts.room_id, {
        "type": "revival_cancelled", "target": ts.name,
    }, None))
    ts.reviver = None
    ts.revival_start_time = 0.0


def _complete_revival(ts, now, msgs):
    """Revive a dead player at their tombstone position."""
    from server.lifecycle import on_player_enter_room, send_room_enter
    from server.models import Avatar

    player = ts.player
    reviver = ts.reviver
    room_id = ts.room_id

    player.dead = False
    player.death_time = 0.0
    player.death_room = None
    player.death_x = 0.0
    player.death_y = 0.0
    player.chose_respawn = False
    player.hp = min(REVIVAL_HP, player.max_hp)
    player.avatar = Avatar(ts.x, ts.y, "down")
    player.command_queue.clear()
    player.active_attack = None
    player.last_damage_time = now  # brief invincibility after revival

    game.tombstones.pop(player.name, None)

    msgs.append(("broadcast", room_id, {
        "type": "tombstone_removed", "name": player.name,
    }, None))
    msgs.append(("broadcast", room_id, {
        "type": "revival_complete",
        "reviver": reviver.name, "target": player.name,
        "x": ts.x, "y": ts.y,
    }, None))
    msgs.append(("send", player, {"type": "you_revived", "reviver": reviver.name}))

    on_player_enter_room(room_id)
    send_room_enter(player, msgs)
    msgs.append(("broadcast", room_id,
                  {"type": "player_entered", **player_info(player)}, player.ws))
    log.event("REVIVE", f"{reviver.name} revived {player.name} in {room_id}")


def _spirit_jar_revive(player, now, msgs):
    """Auto-revive a dead player using their spirit jar."""
    from server.lifecycle import on_player_enter_room, send_room_enter
    from server.models import Avatar

    room_id = player.death_room
    x, y = player.death_x, player.death_y

    # Consume the spirit jar
    player.flags.discard("has_spirit_jar")
    # Clear gift tracking flag so the Ghost NPC can re-gift
    for flag in list(player.flags):
        if flag.startswith("gift_") and flag.endswith("_spirit_jar"):
            player.flags.discard(flag)
    # Reset death state
    player.dead = False
    player.death_time = 0.0
    player.death_room = None
    player.death_x = 0.0
    player.death_y = 0.0
    player.chose_respawn = False
    player.hp = min(REVIVAL_HP, player.max_hp)
    player.avatar = Avatar(x, y, "down")
    player.command_queue.clear()
    player.active_attack = None
    # Invincibility must cover the 2.5s client animation — shift time forward
    # so INVINCIBILITY_DURATION (1.5s) doesn't expire until animation ends.
    player.last_damage_time = now + 1.0

    # Notify client — spirit jar animation, then room data
    msgs.append(("send", player, {
        "type": "spirit_jar_revive",
        "hp": player.hp,
        "max_hp": player.max_hp,
    }))
    on_player_enter_room(room_id)
    send_room_enter(player, msgs)
    msgs.append(("broadcast", room_id,
                  {"type": "player_entered", **player_info(player)}, player.ws))
    log.event("SPIRIT_JAR", f"{player.name} auto-revived via spirit jar in {room_id}")


def _tick_players(now, msgs):
    """Two-phase death handling: death animation → tombstone or auto-respawn."""
    for player in list(game.players.values()):
        if not player.dead:
            continue
        if player.name in game.tombstones:
            # Phase 2: has tombstone — check manual respawn or orphan
            if player.chose_respawn:
                _remove_tombstone(player.name, msgs)
                _respawn_player(player, msgs)
            elif not _has_potential_revivers(player):
                _remove_tombstone(player.name, msgs)
                _respawn_player(player, msgs)
        elif now - player.death_time >= PLAYER_RESPAWN_DELAY:
            # Phase 1: death animation done — spirit jar / tombstone / auto-respawn
            # Gauntlet: death = wave failed, advance to next room
            if player.death_room and player.death_room.startswith("gauntlet_"):
                from server.gauntlet import on_gauntlet_death
                on_gauntlet_death(player, now, msgs)
            elif player.has_flag("has_spirit_jar"):
                _spirit_jar_revive(player, now, msgs)
            elif player.chose_respawn:
                _respawn_player(player, msgs)
            elif _has_potential_revivers(player):
                _place_tombstone(player, now, msgs)
            else:
                _respawn_player(player, msgs)


def _tick_revivals(now, msgs):
    """Check revival proximity, start/cancel/complete revival channels."""
    for name, ts in list(game.tombstones.items()):
        # Skip revival checks during room pickup freeze
        freeze_info = game.room_pickup_freeze.get(ts.room_id)
        if freeze_info and now < freeze_info["end"]:
            if ts.reviver and ts.revival_start_time > 0:
                # Shift revival start forward so freeze doesn't count as channel time
                ts.revival_start_time = now
            continue
        if ts.reviver:
            r = ts.reviver
            # Validate reviver is still valid
            if r.dead or r.avatar is None or r.room != ts.room_id:
                _cancel_revival(ts, msgs)
                continue
            dx = r.avatar.x - ts.x
            dy = r.avatar.y - ts.y
            if (dx * dx + dy * dy) > REVIVAL_PROXIMITY * REVIVAL_PROXIMITY:
                _cancel_revival(ts, msgs)
                continue
            # Check completion
            if now - ts.revival_start_time >= REVIVAL_DURATION:
                _complete_revival(ts, now, msgs)
        else:
            # Look for a new reviver among alive players in the room
            for p, a in avatars_in_room(ts.room_id):
                if p.dead or p is ts.player:
                    continue
                dx = a.x - ts.x
                dy = a.y - ts.y
                if (dx * dx + dy * dy) <= REVIVAL_PROXIMITY * REVIVAL_PROXIMITY:
                    ts.reviver = p
                    ts.revival_start_time = now
                    # Broadcast covers both reviver and dead player
                    msgs.append(("broadcast", ts.room_id, {
                        "type": "revival_started",
                        "reviver": p.name, "target": ts.name,
                        "duration": REVIVAL_DURATION,
                    }, None))
                    break


def _tick_active_attacks(now, msgs):
    """Continue hit-scanning for players with an active sword swing."""
    from server.commands import sword_hit_scan
    for player in list(game.players.values()):
        atk = player.active_attack
        if atk is None:
            continue
        # Expire if duration elapsed, player died, or left the room
        if (now - atk["start_time"] >= SWORD_ACTIVE_DURATION
                or player.hp <= 0
                or player.avatar is None
                or player.room != atk["room"]):
            player.active_attack = None
            continue
        sword_hit_scan(player, atk["direction"], atk["room"],
                       atk["hit_monsters"], now, msgs,
                       anchor_x=atk.get("anchor_x"), anchor_y=atk.get("anchor_y"))


def _tick_all_monsters(now, msgs):
    """Tick all monsters — walks, state machine, guard despawns."""
    for room_id, monster_list in list(game.room_monsters.items()):
        if room_id not in game.rooms:
            continue
        if not avatars_in_room(room_id):
            continue
        # Item-pickup freeze — skip room while active, shift timers on thaw
        freeze_info = game.room_pickup_freeze.get(room_id)
        if freeze_info:
            if now < freeze_info["end"]:
                continue
            # Freeze just expired — shift all monster timers so they resume smoothly
            freeze_dur = freeze_info["end"] - freeze_info["start"]
            freeze_start = freeze_info["start"]
            for m in monster_list:
                if not m.alive:
                    continue
                # Only shift timers set before freeze; timers set during freeze
                # (e.g. by player attacks) restart from thaw instead
                if m.last_action_time < freeze_start:
                    m.last_action_time += freeze_dur
                else:
                    m.last_action_time = freeze_info["end"]
                if m.state == "walking" and m.state_data.start_time < freeze_start:
                    m.state_data.start_time += freeze_dur
                elif m.state in ("charging", "teleporting", "area"):
                    m.state_data["end_time"] += freeze_dur
            del game.room_pickup_freeze[room_id]
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
                    elapsed = now - sd.start_time
                    progress = min(elapsed / monster.walk_time, 1.0)
                    # At 50%: move hitbox to midpoint between origin and destination
                    if progress >= 0.5 and not sd.midpoint_checked:
                        sd.midpoint_checked = True
                        monster.x = (sd.from_x + sd.to_x) / 2
                        monster.y = (sd.from_y + sd.to_y) / 2
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
                                            "prev_source_x": sd.from_x, "prev_source_y": sd.from_y,
                                        }
                    # At 100%: commit to destination, check collision, complete walk
                    if progress >= 1.0:
                        monster.x = sd.to_x
                        monster.y = sd.to_y
                        if not monster.intangible:
                            mid_src_x = (sd.from_x + sd.to_x) / 2
                            mid_src_y = (sd.from_y + sd.to_y) / 2
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
                        remaining = sd.remaining_distance
                        walk_dir = sd.direction
                        walk_seq = sd.seq
                        monster.state = "idle"
                        monster.state_data = {}
                        msgs.append(("broadcast", room_id, {
                            "type": "monster_walk_complete",
                            "id": i,
                            "seq": walk_seq,
                        }, None))
                        # Chain next walk if distance remains
                        if remaining > 0 and monster.alive:
                            next_move = behavior_engine.engine.resolve_move(
                                {"direction": walk_dir}, monster, room_id)
                            if next_move:
                                next_move["distance"] = remaining
                                next_move["direction"] = walk_dir
                                behavior_engine.engine.start_walk(monster, room_id, i, next_move, msgs, now)
                # State machine (behavior eval, warmup countdown)
                behavior_engine.engine.tick_monster_state(monster, room_id, i, now, msgs)
            except Exception as e:
                log.debug(f"[MONSTER TICK ERROR] monster {i} ({monster.kind}) in {room_id} "
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
                if DEBUG_MODE:
                    # Re-raises past the per-monster loop — skips remaining
                    # monsters/rooms for this tick. Acceptable for dev only.
                    raise


def _tick_projectiles(msgs):
    """Move projectiles and check collisions (sync — appends to msgs batch)."""
    for room_id in list(game.room_projectiles.keys()):
        if room_id not in game.rooms:
            del game.room_projectiles[room_id]
            continue
        # Freeze projectiles during item pickup
        if room_id in game.room_pickup_freeze:
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
        # Skip contact damage while room is frozen for item pickup
        if player.room in game.room_pickup_freeze:
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
    from server.commands import sword_hitbox
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
        # Active sword hitboxes
        swords = []
        for p, a in avatars_in_room(room_id):
            atk = p.active_attack
            if atk is None:
                continue
            d = atk["direction"]
            px = atk.get("anchor_x", a.x)
            py = atk.get("anchor_y", a.y)
            sx, sy, sw, sh = sword_hitbox(px, py, d)
            swords.append({"x": sx, "y": sy, "w": sw, "h": sh})
        await send_to(player, {
            "type": "debug_state",
            "players": players,
            "monsters": monsters,
            "projectiles": projectiles,
            "hearts": hearts,
            "items": items,
            "swords": swords,
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
                    # Allow respawn_request while dead
                    if player.dead:
                        while player.command_queue:
                            cmd_type, _ = player.command_queue.popleft()
                            if cmd_type == "respawn_request":
                                player.chose_respawn = True
                    continue
                try:
                    process_player_commands(player, now, msgs)
                except Exception:
                    traceback.print_exc()
            _tick_players(now, msgs)
            _tick_revivals(now, msgs)
            _tick_active_attacks(now, msgs)
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


def _despawn_guards(guards, room_id, msgs):
    """Kill all guards and broadcast their deaths."""
    for i, m in guards:
        m.alive = False
        msgs.append(("broadcast", room_id, {
            "type": "monster_killed", "id": i, "x": m.x, "y": m.y,
        }, None))


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
        _despawn_guards(guards, room_id, msgs)
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
        _despawn_guards(guards, room_id, msgs)
        return

    # Despawn if target is beyond distance from ALL guards
    nearest = min(abs(target_avatar.x - m.x) + abs(target_avatar.y - m.y) for _, m in guards)
    if nearest > GUARD_DESPAWN_DISTANCE:
        _despawn_guards(guards, room_id, msgs)


