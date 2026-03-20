"""Command processing — drains player command queues during game_tick."""

import os
import random
import time

from server.state import game
from server.constants import (
    DIRECTIONS, ROOM_COLS, ROOM_ROWS,
    WALK_TIME, CANCEL_TIME, LATENCY_COMP,
    ATTACK_COOLDOWN, HEART_DROP_CHANCE,
)
from server.net import players_in_room, log_event
from server.lifecycle import (
    do_room_transition, get_room_monsters,
    broadcast_choir_start, broadcast_choir_stop,
)
from server.dungeons import get_dungeon_for_room, _run_content_deprecation, start_background_regen
from server.npc_chat import find_adjacent_npc


def process_player_commands(player, now, msgs):
    """Drain and process all queued commands for a player."""
    while player.command_queue:
        cmd_type, data = player.command_queue.popleft()
        if cmd_type == "walk":
            _process_walk(player, data, now, msgs)
        elif cmd_type == "cancel_walk":
            _process_cancel_walk(player, now, msgs)
        elif cmd_type == "face":
            _process_face(player, data, msgs)
        elif cmd_type == "attack":
            _process_attack(player, now, msgs)
        elif cmd_type == "chat":
            _process_chat(player, data, msgs)


# ---------------------------------------------------------------------------
# Reconcile helper
# ---------------------------------------------------------------------------

def _send_reconcile(player, now, msgs):
    """Append a reconcile message for the player."""
    msg = {
        "type": "reconcile",
        "x": player.x,
        "y": player.y,
        "direction": player.direction,
    }
    if player.walk:
        elapsed = now - player.walk["start_time"]
        progress = min(elapsed / WALK_TIME, 1.0)
        msg["walking"] = True
        msg["walk_progress"] = progress
        msg["walk_from"] = {"x": player.walk["from_x"], "y": player.walk["from_y"]}
        msg["walk_to"] = {"x": player.walk["to_x"], "y": player.walk["to_y"]}
    else:
        msg["walking"] = False
    msgs.append(("send", player, msg))


# ---------------------------------------------------------------------------
# Movement
# ---------------------------------------------------------------------------

def _check_edge_exit(player, new_x, new_y, room):
    """Check if walking off-edge corresponds to a room exit."""
    exits = room["exits"]
    if new_y < 0 and "north" in exits and 6 <= player.x <= 8:
        return "north"
    if new_y > 10 and "south" in exits and 6 <= player.x <= 8:
        return "south"
    if new_x < 0 and "west" in exits and 4 <= player.y <= 6:
        return "west"
    if new_x > 14 and "east" in exits and 4 <= player.y <= 6:
        return "east"
    return None


def _process_face(player, data, msgs):
    """Handle face direction change."""
    direction = data.get("direction", "")
    if direction in DIRECTIONS:
        player.walk = None
        player.direction = direction
        player.dancing = False
        msgs.append(("broadcast", player.room, {
            "type": "player_faced",
            "name": player.name,
            "direction": direction,
        }, player.ws))


def _process_walk(player, data, now, msgs):
    """Handle a walk request — validate and start a server-side walk."""
    direction = data.get("direction", "")
    origin = data.get("origin", {})
    origin_x = origin.get("x", player.x)
    origin_y = origin.get("y", player.y)

    if player.hp <= 0:
        return

    delta = DIRECTIONS.get(direction)
    if not delta:
        return
    dx, dy = delta

    # If already walking, check for chained walk acceptance
    if player.walk:
        elapsed = now - player.walk["start_time"]
        progress = min(elapsed / WALK_TIME, 1.0)
        if progress >= 1.0 - LATENCY_COMP / WALK_TIME:
            # Near completion — accept chain. Complete current walk immediately.
            if not player.walk["committed"]:
                player.x = player.walk["to_x"]
                player.y = player.walk["to_y"]
            player.walk = None
            # Use the completed walk's target as origin for the new walk
            origin_x = player.x
            origin_y = player.y
        else:
            # Not near completion — reject, send reconcile
            _send_reconcile(player, now, msgs)
            return

    # Origin validation — client and server must agree on position
    if origin_x != player.x or origin_y != player.y:
        _send_reconcile(player, now, msgs)
        return

    player.direction = direction
    player.dancing = False

    to_x = origin_x + dx
    to_y = origin_y + dy

    room = game.rooms[player.room]
    tilemap = room["tilemap"]

    # Off-grid — check room exit
    if to_x < 0 or to_x >= ROOM_COLS or to_y < 0 or to_y >= ROOM_ROWS:
        exit_dir = _check_edge_exit(player, to_x, to_y, room)
        if exit_dir:
            player.walk = None
            do_room_transition(player, exit_dir, msgs)
        else:
            _send_reconcile(player, now, msgs)
        return

    tile = tilemap[to_y][to_x]

    # Stairs
    if tile == "SU" and "up" in room["exits"]:
        player.walk = None
        do_room_transition(player, "up", msgs)
        return
    if tile == "SD" and "down" in room["exits"]:
        player.walk = None
        do_room_transition(player, "down", msgs)
        return

    # Not walkable
    if not game.is_walkable_tile(tile):
        _send_reconcile(player, now, msgs)
        return

    # Guard collision
    for guard in game.guards.get(player.room, []):
        if to_x == guard["x"] and to_y == guard["y"]:
            _send_reconcile(player, now, msgs)
            return

    # Start walk
    player.walk = {
        "from_x": origin_x, "from_y": origin_y,
        "to_x": to_x, "to_y": to_y,
        "dir": direction,
        "start_time": now,
        "committed": False,
    }

    # Broadcast walk_started to other players with latency compensation offset
    initial_progress = LATENCY_COMP / WALK_TIME
    msgs.append(("broadcast", player.room, {
        "type": "walk_started",
        "name": player.name,
        "from_x": origin_x, "from_y": origin_y,
        "to_x": to_x, "to_y": to_y,
        "dir": direction,
        "progress": initial_progress,
    }, player.ws))


def _process_cancel_walk(player, now, msgs):
    """Handle a cancel_walk request — validate timing and cancel or reject."""
    if player.walk is None:
        return

    elapsed = now - player.walk["start_time"]

    if elapsed <= CANCEL_TIME + LATENCY_COMP:
        # Valid cancel — roll back to origin (even if midway committed)
        from_x = player.walk["from_x"]
        from_y = player.walk["from_y"]
        player.x = from_x
        player.y = from_y
        player.walk = None
        msgs.append(("broadcast", player.room, {
            "type": "walk_cancelled",
            "name": player.name,
            "x": from_x,
            "y": from_y,
        }, player.ws))
        # No reconcile needed — client already snapped back optimistically.
        # Sending one would interfere with any new walk the client started.
    else:
        # Too late to cancel — send reconcile with current walk state
        _send_reconcile(player, now, msgs)


# ---------------------------------------------------------------------------
# Attack
# ---------------------------------------------------------------------------

def _process_attack(player, now, msgs):
    """Handle a player's sword attack."""
    if player.hp <= 0:
        return
    if not player.has_flag("has_sword"):
        msgs.append(("send", player, {"type": "info", "text": "You don't have a weapon."}))
        return
    if now - player.last_attack_time < ATTACK_COOLDOWN:
        return
    player.last_attack_time = now
    player.dancing = False
    player.walk = None

    msgs.append(("broadcast", player.room, {
        "type": "attack",
        "name": player.name,
        "direction": player.direction,
    }, None))

    # Hit detection — check if sword hits a monster (supports multi-tile monsters)
    dx, dy = DIRECTIONS.get(player.direction, (0, 0))
    hit_x = player.x + dx
    hit_y = player.y + dy
    for i, monster in enumerate(get_room_monsters(player.room)):
        if monster.alive and not monster.intangible and monster.occupies(hit_x, hit_y):
            monster.hp -= 1
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
                monster.alive = False
                monster.state = "idle"
                monster.state_data = {}
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
                if dinst:
                    alive = [m for m in game.room_monsters[player.room] if m.alive]
                    if not alive:
                        dinst.cleared_rooms.add(player.room)
                        # Boss defeated — silence music + stop choir
                        if is_boss:
                            print(f"[BOSS] Boss defeated in {player.room}, silencing music")
                            dinst.boss_engaged = False
                            msgs.append(("broadcast", player.room, {
                                "type": "music_change", "music": None,
                            }, None))
                            broadcast_choir_stop(player.room, msgs)
            else:
                msgs.append(("broadcast", player.room, {
                    "type": "monster_hit",
                    "id": i,
                    "x": monster.x,
                    "y": monster.y,
                    "hp": monster.hp,
                }, None))


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
    guard = find_adjacent_npc(player)
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
        player.dancing = True
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
            msgs.append(("send", player, {"type": "sword_obtained"}))
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

    else:
        msgs.append(("send", player, {"type": "info", "text": "Unknown command. Try /help"}))
