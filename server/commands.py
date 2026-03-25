"""Command processing — drains player command queues during game_tick."""

import math
import os
import random
import time

from server.state import game
from server.constants import (
    DIRECTIONS, ROOM_COLS, ROOM_ROWS, DOORWAY_TILES,
    ATTACK_COOLDOWN, HEART_DROP_CHANCE, HEART_RESTORE_HP,
    POSITION_UPDATE_RATE, MAX_MOVE_PER_UPDATE, GUARD_COOLDOWN,
    COLLISION_GRACE_PERIOD,
)
from server.net import log_event
from server.lifecycle import (
    do_room_transition, get_room_monsters,
    broadcast_choir_start, broadcast_choir_stop,
    unlock_room, set_monster_idle,
)
from server.dungeons import get_dungeon_for_room, _run_content_deprecation, start_background_regen, broadcast_to_dungeon
from server.npc_chat import find_adjacent_npc


def process_player_commands(player, now, msgs):
    """Drain and process all queued commands for a player."""
    while player.command_queue:
        cmd_type, data = player.command_queue.popleft()
        if cmd_type == "position_update":
            _process_position_update(player, data, now, msgs)
        elif cmd_type == "face":
            _process_face(player, data, msgs)
        elif cmd_type == "attack":
            _process_attack(player, data, now, msgs)
        elif cmd_type == "chat":
            _process_chat(player, data, msgs)
        elif cmd_type == "unlock_door":
            _process_unlock_door(player, data, msgs)


# ---------------------------------------------------------------------------
# Reconcile helper
# ---------------------------------------------------------------------------

def _send_reconcile(player, msgs, reason=""):
    """Append a reconcile message for the player."""
    a = player.avatar
    if reason:
        print(f"[RECONCILE] {player.name}: {reason} -> snap to ({a.x}, {a.y})")
    msgs.append(("send", player, {
        "type": "reconcile",
        "x": a.x,
        "y": a.y,
        "direction": a.direction,
    }))


# ---------------------------------------------------------------------------
# Movement — half-tile free movement
# ---------------------------------------------------------------------------

# Exit zone ranges derived from DOORWAY_TILES (± 0.5 for hitbox overlap margin).
# North/south share columns; west/east share rows (standard room layout).
_ns_cols = [c for _, c in DOORWAY_TILES["north"]]
_ew_rows = [r for r, _ in DOORWAY_TILES["west"]]
_EXIT_X_MIN, _EXIT_X_MAX = min(_ns_cols) - 0.5, max(_ns_cols) + 0.5
_EXIT_Y_MIN, _EXIT_Y_MAX = min(_ew_rows) - 0.5, max(_ew_rows) + 0.5


def _check_edge_exit_float(x, y, direction, room):
    """Check if a float position at room edge corresponds to an exit."""
    exits = room["exits"]
    if direction == "up" and y < 0 and "north" in exits and _EXIT_X_MIN <= x <= _EXIT_X_MAX:
        return "north"
    if direction == "down" and y > ROOM_ROWS - 1 and "south" in exits and _EXIT_X_MIN <= x <= _EXIT_X_MAX:
        return "south"
    if direction == "left" and x < 0 and "west" in exits and _EXIT_Y_MIN <= y <= _EXIT_Y_MAX:
        return "west"
    if direction == "right" and x > ROOM_COLS - 1 and "east" in exits and _EXIT_Y_MIN <= y <= _EXIT_Y_MAX:
        return "east"
    return None


def _is_position_walkable(x, y, room):
    """Check if a 1x1 hitbox at (x,y) is walkable.
    Only checks the bottom half (y+0.5 to y+1) so the sprite's top half
    can overlap walls — NES Zelda style, regardless of direction."""
    tilemap = room["tilemap"]
    check_y_start = y + 0.5

    min_tx = int(math.floor(x + 0.001))
    max_tx = int(math.floor(x + 1.0 - 0.001))
    min_ty = int(math.floor(check_y_start + 0.001))
    max_ty = int(math.floor(y + 1.0 - 0.001))

    for ty in range(min_ty, max_ty + 1):
        for tx in range(min_tx, max_tx + 1):
            if tx < 0 or tx >= ROOM_COLS or ty < 0 or ty >= ROOM_ROWS:
                continue  # off-grid handled by edge detection
            if not game.is_walkable_tile(tilemap[ty][tx]):
                return False
    return True


def _process_position_update(player, data, now, msgs):
    """Validate a client position update and relay to other players."""
    a = player.avatar
    new_x = data.get("x")
    new_y = data.get("y")
    direction = data.get("direction", a.direction)

    if player.hp <= 0:
        return
    if not isinstance(new_x, (int, float)) or not isinstance(new_y, (int, float)):
        return

    new_x = float(new_x)
    new_y = float(new_y)

    # Validate half-tile snapped
    if round(new_x * 2) / 2 != new_x or round(new_y * 2) / 2 != new_y:
        _send_reconcile(player, msgs, f"not half-tile snapped: ({new_x}, {new_y})")
        return

    # Anti-cheat: rate limit
    dt = now - player.last_pos_update_time
    if dt < POSITION_UPDATE_RATE * 0.5:
        return  # silently drop (too fast)

    # Anti-cheat: distance check
    dist = abs(new_x - a.x) + abs(new_y - a.y)
    if dist > MAX_MOVE_PER_UPDATE:
        _send_reconcile(player, msgs, f"too far: dist={dist:.2f} from ({a.x},{a.y}) to ({new_x},{new_y})")
        return

    # Direction
    if direction in DIRECTIONS:
        a.direction = direction
    a.dancing = False

    # Edge detection (room transition)
    room = game.rooms[player.room]
    exit_dir = _check_edge_exit_float(new_x, new_y, direction, room)
    if exit_dir:
        do_room_transition(player, exit_dir, msgs)
        return

    # Stairs
    center_tx, center_ty = int(round(new_x)), int(round(new_y))
    if 0 <= center_tx < ROOM_COLS and 0 <= center_ty < ROOM_ROWS:
        tile = room["tilemap"][center_ty][center_tx]
        if tile == "SU" and "up" in room["exits"]:
            do_room_transition(player, "up", msgs)
            return
        if tile == "SD" and "down" in room["exits"]:
            do_room_transition(player, "down", msgs)
            return

    # Walkability — check all tiles the 1x1 hitbox overlaps
    if not _is_position_walkable(new_x, new_y, room):
        _send_reconcile(player, msgs, f"unwalkable at ({new_x}, {new_y})")
        return

    # Guard collision (AABB)
    for guard in game.guards.get(player.room, []):
        if (new_x < guard["x"] + 1 and new_x + 1 > guard["x"] and
            new_y < guard["y"] + 1 and new_y + 1 > guard["y"]):
            _send_reconcile(player, msgs, f"guard collision at ({new_x}, {new_y}) vs guard ({guard['x']}, {guard['y']})")
            return

    # Accept — update position
    prev_x, prev_y = a.x, a.y
    a.x = new_x
    a.y = new_y
    player.last_pos_update_time = now

    # Relay to other players
    if new_x != a.last_reported_x or new_y != a.last_reported_y:
        msgs.append(("broadcast", player.room, {
            "type": "player_walk_half",
            "name": player.name,
            "x": new_x, "y": new_y,
            "direction": a.direction,
        }, player.ws))
        a.last_reported_x = new_x
        a.last_reported_y = new_y

    # Collision checks (monster contact, hearts, dungeon items, guard proximity)
    _check_position_collisions(player, now, msgs, prev_x, prev_y)


def _get_monster_visual_pos(monster, now):
    """Get interpolated monster position during walks, actual position otherwise."""
    if monster.state == "walking":
        sd = monster.state_data
        elapsed = now - sd["start_time"]
        progress = min(elapsed / monster.walk_time, 1.0)
        fx = sd["from_x"]
        fy = sd["from_y"]
        return fx + (sd["to_x"] - fx) * progress, fy + (sd["to_y"] - fy) * progress
    return monster.x, monster.y


def _check_position_collisions(player, now, msgs, prev_player_x=None, prev_player_y=None):
    """Check monster contact, heart pickup, dungeon items at player position."""
    a = player.avatar
    if prev_player_x is None:
        prev_player_x = a.x
    if prev_player_y is None:
        prev_player_y = a.y
    # Monster contact damage (AABB: player 1x1 at float pos vs monster footprint)
    # Records pending collisions with a grace period for corner-scrape forgiveness
    if player.hp > 0:
        overlapping = set()
        for monster in get_room_monsters(player.room):
            if monster.alive and not monster.intangible:
                mx, my = _get_monster_visual_pos(monster, now)
                if (a.x < mx + monster.width and a.x + 1 > mx and
                    a.y < my + monster.height and a.y + 1 > my):
                    mid = id(monster)
                    overlapping.add(mid)
                    if mid not in a.pending_collisions:
                        prev_mx, prev_my = monster.x, monster.y
                        if monster.state == "walking":
                            prev_mx = monster.state_data.get("from_x", monster.x)
                            prev_my = monster.state_data.get("from_y", monster.y)
                        a.pending_collisions[mid] = {
                            "monster": monster, "room_id": player.room, "time": now,
                            "prev_player_x": prev_player_x, "prev_player_y": prev_player_y,
                            "prev_source_x": prev_mx, "prev_source_y": prev_my,
                        }
        # Clear pending for monsters no longer overlapping
        for mid in list(a.pending_collisions):
            if mid not in overlapping:
                del a.pending_collisions[mid]

    # Heart pickup (proximity)
    if player.hp > 0:
        hearts = game.room_hearts.get(player.room, [])
        for heart in hearts:
            if (abs(a.x - heart["x"]) < 0.75 and
                abs(a.y - heart["y"]) < 0.75 and player.hp < player.max_hp):
                player.hp = min(player.max_hp, player.hp + HEART_RESTORE_HP)
                hearts.remove(heart)
                msgs.append(("send", player, {"type": "hp_update", "hp": player.hp, "max_hp": player.max_hp}))
                msgs.append(("broadcast", player.room, {"type": "heart_collected", "id": heart["id"]}, None))
                break

    # Dungeon item pickup (proximity) — hidden during trap room lockdown
    if player.hp > 0:
        dinst = get_dungeon_for_room(player.room)
        if dinst and player.room not in game.locked_rooms:
            items = dinst.dungeon_items.get(player.room, [])
            for item in list(items):
                if abs(a.x - item["x"]) < 0.75 and abs(a.y - item["y"]) < 0.75:
                    item_type = item["item_type"]
                    items.remove(item)
                    if item_type == "key":
                        # Keys go to the player, not to collected_items
                        player.keys += 1
                        item_name = "Small Key"
                    else:
                        dinst.collected_items.add(item_type)
                        item_name = {"map": "Dungeon Map", "compass": "Compass"}.get(item_type, item_type)
                    msgs.append(("send", player, {
                        "type": "item_obtained",
                        "item_type": item_type,
                        "item_name": item_name,
                    }))
                    msgs.append(("broadcast", player.room, {
                        "type": "item_effect",
                        "item_type": item_type,
                        "name": player.name,
                    }, player.ws))
                    collect_msg = {
                        "type": "dungeon_item_collected",
                        "item_type": item_type,
                        "collected_by": player.name,
                    }
                    # Include position for keys (multiple can exist, need precise removal)
                    if item_type == "key":
                        collect_msg["x"] = item["x"]
                        collect_msg["y"] = item["y"]
                        collect_msg["room_id"] = player.room
                    broadcast_to_dungeon(dinst, collect_msg, msgs)
                    break

    # Guard proximity chat (float-aware)
    if player.hp > 0:
        _check_guard_proximity_sync(player, now, msgs)


def _check_guard_proximity_sync(player, now, msgs):
    """If near a guard and cooldown has passed, queue guard dialog."""
    a = player.avatar
    for guard in game.guards.get(player.room, []):
        dx = abs(a.x - guard["x"])
        dy = abs(a.y - guard["y"])
        if dx + dy <= 1.5:
            key = f"{player.room}:{guard['name']}:{guard['x']},{guard['y']}"
            last = player.guard_cooldowns.get(key, 0)
            if now - last >= GUARD_COOLDOWN:
                player.guard_cooldowns[key] = now
                msgs.append(("guard_chat", player, guard))


def _process_face(player, data, msgs):
    """Handle face direction change."""
    a = player.avatar
    direction = data.get("direction", "")
    if direction in DIRECTIONS:
        a.direction = direction
        a.dancing = False
        msgs.append(("broadcast", player.room, {
            "type": "player_faced",
            "name": player.name,
            "direction": direction,
        }, player.ws))


# ---------------------------------------------------------------------------
# Attack
# ---------------------------------------------------------------------------

def _process_attack(player, data, now, msgs):
    """Handle a player's sword attack."""
    if player.hp <= 0:
        return
    if not player.has_flag("has_sword"):
        msgs.append(("send", player, {"type": "info", "text": "You don't have a weapon."}))
        return
    if now - player.last_attack_time < ATTACK_COOLDOWN:
        return
    player.last_attack_time = now
    a = player.avatar
    a.dancing = False

    # Use client-supplied direction so quick turn+attack works without waiting
    # for the server to process the direction change first
    direction = data.get("direction")
    if direction in DIRECTIONS:
        a.direction = direction

    msgs.append(("broadcast", player.room, {
        "type": "attack",
        "name": player.name,
        "direction": a.direction,
    }, None))

    # Hit detection — AABB overlap, 1.5 tiles in attack dir (covers half player tile + full sword tile)
    dx, dy = DIRECTIONS.get(a.direction, (0, 0))
    sword_x = a.x + (0.5 if dx > 0 else -1.0 if dx < 0 else 0)
    sword_y = a.y + (0.5 if dy > 0 else -1.0 if dy < 0 else 0)
    sword_w = 1.5 if dx != 0 else 1.0
    sword_h = 1.5 if dy != 0 else 1.0
    for i, monster in enumerate(get_room_monsters(player.room)):
        if monster.alive and not monster.intangible and (
            sword_x < monster.x + monster.width and sword_x + sword_w > monster.x and
            sword_y < monster.y + monster.height and sword_y + sword_h > monster.y):
            monster.hp -= 1
            # Knockback: push surviving non-boss monster 1 tile in attack direction
            knock_x = None
            knock_y = None
            if monster.hp > 0 and not monster.is_boss:
                room = game.rooms.get(player.room)
                if room:
                    kx = round(monster.x + dx)
                    ky = round(monster.y + dy)
                    can_knock = True
                    for oy in range(monster.height):
                        for ox in range(monster.width):
                            cx, cy = kx + ox, ky + oy
                            if cx < 0 or cx + 1 > ROOM_COLS or cy < 0 or cy + 1 > ROOM_ROWS:
                                can_knock = False
                            elif not _is_position_walkable(cx, cy, room):
                                can_knock = False
                    if can_knock:
                        monster.x = kx
                        monster.y = ky
                        knock_x = kx
                        knock_y = ky
                        # Reset to idle so the monster doesn't continue its interrupted action
                        if monster.state != "idle":
                            set_monster_idle(monster, player.room, i, msgs)
            # Boss engagement — start choir overlay if boss survives this hit
            dinst = get_dungeon_for_room(player.room)
            is_boss = monster.is_boss and dinst is not None
            if (monster.hp > 0
                    and is_boss
                    and dinst
                    and not dinst.boss_engaged):
                dinst.boss_engaged = True
                broadcast_choir_start(player.room, msgs)
            if monster.hp <= 0:
                set_monster_idle(monster, player.room, i, msgs)
                monster.alive = False
                msg_killed = {
                    "type": "monster_killed",
                    "id": i,
                    "x": monster.x,
                    "y": monster.y,
                }
                if knock_x is not None:
                    msg_killed["knock_x"] = knock_x
                    msg_killed["knock_y"] = knock_y
                msgs.append(("broadcast", player.room, msg_killed, None))
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
                if dinst:
                    alive = [m for m in game.room_monsters[player.room] if m.alive]
                    if not alive:
                        dinst.cleared_rooms.add(player.room)
                        # Unlock trap room doors
                        if player.room in game.locked_rooms:
                            unlock_room(player.room, msgs)
                        # Boss defeated — silence music + stop choir
                        if is_boss:
                            print(f"[BOSS] Boss defeated in {player.room}, silencing music")
                            dinst.boss_engaged = False
                            msgs.append(("broadcast", player.room, {
                                "type": "music_change", "music": None,
                            }, None))
                            broadcast_choir_stop(player.room, msgs)
            else:
                msg_hit = {
                    "type": "monster_hit",
                    "id": i,
                    "x": monster.x,
                    "y": monster.y,
                    "hp": monster.hp,
                }
                if knock_x is not None:
                    msg_hit["knock_x"] = knock_x
                    msg_hit["knock_y"] = knock_y
                msgs.append(("broadcast", player.room, msg_hit, None))


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def _process_chat(player, data, msgs):
    """Handle chat message — slash commands and normal chat."""
    text = data.get("text", "").strip()
    if not text:
        return

    if text.startswith("/"):
        _process_slash_command(player, text, msgs)
        return

    # Normal chat — broadcast to room
    room_name = game.rooms[player.room]["name"]
    log_event("CHAT", f"{player.name} ({room_name}): {text}")
    msgs.append(("broadcast", player.room, {
        "type": "chat",
        "from": player.name,
        "text": text,
    }, None))

    # Check if player is adjacent to an NPC — trigger LLM conversation
    guard = find_adjacent_npc(player.room, player.avatar)
    if guard:
        msgs.append(("npc_chat", player, guard, text))


def _process_slash_command(player, text, msgs):
    """Handle a slash command."""
    parts = text[1:].split(None, 1)
    cmd = parts[0].lower() if parts else ""

    if cmd == "who":
        lines = ["Players online:"]
        for p in game.players.values():
            room_name = game.rooms[p.room]["name"]
            lines.append(f"  {p.name} — {p.description} (in {room_name})")
        msgs.append(("send", player, {"type": "info", "text": "\n".join(lines)}))

    elif cmd == "help":
        msgs.append(("send", player, {"type": "info", "text": (
            "Arrow keys / WASD — Move\n"
            "Space — Attack\n"
            "Enter — Open chat\n"
            "Escape — Close chat\n"
            "M — Toggle music\n"
            "/who — List online players\n"
            "/dance — Bust a move\n"
            "/help — Show this message"
        )}))

    elif cmd == "dance":
        player.avatar.dancing = True
        msgs.append(("broadcast", player.room, {
            "type": "dance", "name": player.name,
        }, None))

    elif cmd == "me":
        action = parts[1] if len(parts) > 1 else ""
        if action:
            msgs.append(("broadcast", player.room, {
                "type": "chat", "from": player.name, "text": f"*{action}*",
            }, None))

    elif cmd == "cheat" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
        if player.has_flag("invulnerable"):
            player.flags.discard("invulnerable")
            msgs.append(("send", player, {"type": "info", "text": "Cheat mode off: vulnerable again"}))
        else:
            player.grant_flag("has_sword")
            player.grant_flag("invulnerable")
            player.hp = player.max_hp
            msgs.append(("send", player, {"type": "item_obtained", "item_type": "sword", "item_name": "Sword"}))
            msgs.append(("send", player, {"type": "hp_update", "hp": player.hp, "max_hp": player.max_hp}))
            msgs.append(("send", player, {"type": "info", "text": "Cheat mode: sword + invulnerability"}))

    elif cmd == "debug_spawn" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
        msgs.append(("debug_spawn", player, parts[1] if len(parts) > 1 else ""))

    elif cmd == "deprecate" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
        for _tid in list(game.content_libraries.keys()):
            _run_content_deprecation(_tid)
        msgs.append(("send", player, {"type": "info", "text": "Forced deprecation pass — see ~ debug log"}))

    elif cmd == "regen" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
        regen_inst = get_dungeon_for_room(player.room)
        regen_type = regen_inst.dungeon_id if regen_inst else "d1"
        regen_libs = game.content_libraries.get(regen_type, {})
        regen_room_lib = regen_libs.get("rooms")
        count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else (regen_room_lib.placeholder_count if regen_room_lib else 0)
        if count <= 0:
            msgs.append(("send", player, {"type": "info", "text": f"No {regen_type} room library slots to fill"}))
        else:
            start_background_regen(count, regen_type)
            msgs.append(("send", player, {"type": "info", "text": f"Regen started: {count} {regen_type} room(s) — see ~ debug log"}))

    elif cmd == "viewserver" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
        enabled = not getattr(player, '_viewserver', False)
        player._viewserver = enabled
        msgs.append(("send", player, {"type": "viewserver_toggle", "enabled": enabled}))

    elif cmd == "choir" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
        debug_on = getattr(player, '_debug_choir', False)
        choir_inst = get_dungeon_for_room(player.room)
        if debug_on:
            player._debug_choir = False
            if choir_inst:
                choir_inst.boss_engaged = False
            msgs.append(("send", player, {"type": "boss_choir_stop"}))
            msgs.append(("send", player, {"type": "info", "text": "Choir overlay OFF"}))
        else:
            dist = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2
            player._debug_choir = True
            if choir_inst:
                choir_inst.boss_engaged = True
            msgs.append(("send", player, {"type": "boss_choir_start", "distance": dist}))
            msgs.append(("send", player, {"type": "info", "text": f"Choir overlay ON (distance={dist})"}))

    elif cmd == "key" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
        player.keys += 1
        msgs.append(("send", player, {"type": "key_update", "keys": player.keys}))
        msgs.append(("send", player, {"type": "info", "text": f"Granted key (total: {player.keys})"}))

    elif cmd == "keylayout" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
        dinst = get_dungeon_for_room(player.room)
        if not dinst or not dinst.zone_cells:
            msgs.append(("send", player, {"type": "info", "text": "Not in a dungeon with locked doors"}))
        else:
            from collections import Counter
            key_counts = Counter(dinst.key_cells)
            zone_data = []
            for zid, cells in dinst.zone_cells.items():
                keys_in_zone = sum(key_counts.get(c, 0) for c in cells)
                zone_data.append({
                    "zone_id": zid,
                    "cells": [[c[0], c[1]] for c in cells],
                    "keys": keys_in_zone,
                })
            msgs.append(("send", player, {
                "type": "keylayout",
                "zones": zone_data,
            }))
            msgs.append(("send", player, {"type": "info",
                "text": f"Key layout: {len(dinst.zone_cells)} zones, "
                        f"{len(dinst.locked_doors)} doors, {len(dinst.key_cells)} keys"}))

    else:
        msgs.append(("send", player, {"type": "info", "text": "Unknown command. Try /help"}))


# ---------------------------------------------------------------------------
# Locked door unlock
# ---------------------------------------------------------------------------

_UNLOCK_DIR_OFFSETS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
_OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}


def _process_unlock_door(player, data, msgs):
    """Handle player walking into a locked door — consume key and open it."""
    if player.keys <= 0 or player.hp <= 0:
        return
    direction = data.get("direction")
    if direction not in DOORWAY_TILES:
        return

    dinst = get_dungeon_for_room(player.room)
    if not dinst:
        return

    # Map room_id back to cell
    cell = _room_id_to_cell(player.room, dinst)
    if not cell:
        return

    # Check if there's a locked door in this direction
    dc, dr = _UNLOCK_DIR_OFFSETS[direction]
    neighbor = (cell[0] + dc, cell[1] + dr)
    edge = frozenset((cell, neighbor))
    if edge not in dinst.locked_doors or edge in dinst.unlocked_doors:
        return

    # Consume key and unlock
    player.keys -= 1
    dinst.unlocked_doors.add(edge)

    # Edge data for client minimap update
    unlocked_edge = [list(cell), list(neighbor)]

    # Restore tiles in this room
    _unlock_locked_door(player.room, direction, dinst, msgs, unlocked_edge)

    # Restore tiles in neighbor room (if resolved)
    neighbor_room_id = f"{dinst.dungeon_id}_{neighbor[0]}_{neighbor[1]}"
    opposite = _OPPOSITE[direction]
    if neighbor_room_id in game.rooms:
        _unlock_locked_door(neighbor_room_id, opposite, dinst, msgs, unlocked_edge)

    # Send key count update
    msgs.append(("send", player, {"type": "key_update", "keys": player.keys}))
    msgs.append(("send", player, {"type": "info", "text": "Used a Small Key!"}))

    print(f"[DUNGEON] {player.name} unlocked door {direction} in {player.room} "
          f"(keys remaining: {player.keys})")


def _room_id_to_cell(room_id, dinst):
    """Convert a room_id like 'd1_3_2' back to a (col, row) cell tuple."""
    for cell, rid in dinst.room_map.items():
        if rid == room_id:
            return cell
    return None


def _unlock_locked_door(room_id, direction, dinst, msgs, unlocked_edge=None):
    """Restore original tiles for a locked doorway in one room."""
    room = game.rooms.get(room_id)
    if not room:
        return
    tilemap = room["tilemap"]
    originals = dinst.locked_door_originals.get(room_id, {})
    tile_changes = []
    for r, c in DOORWAY_TILES[direction]:
        original = originals.get((r, c), "DF")
        tilemap[r][c] = original
        tile_changes.append([r, c, original])
    if tile_changes:
        unlock_msg = {
            "type": "doors_unlocked",
            "tile_changes": tile_changes,
        }
        if unlocked_edge:
            unlock_msg["unlocked_edge"] = unlocked_edge
        msgs.append(("broadcast", room_id, unlock_msg, None))
