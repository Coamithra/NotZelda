"""
MUD Server — Zelda-style multiplayer online dungeon.

Run with: python mud_server.py
Then open http://localhost:8080 in your browser.
"""

import asyncio
import json
import os
import sys
import time
from http import HTTPStatus
from pathlib import Path

# Load .env file if present (before any server imports that read env vars)
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            os.environ.setdefault(_key.strip(), _val.strip())

import websockets

from server import behavior_engine
from server.state import game
from server.constants import (
    DIRECTIONS, ROOM_COLS, ROOM_ROWS,
    WALK_TIME, CANCEL_TIME, LATENCY_COMP,
    STARTING_ROOM, PLAYER_MAX_HP,
)
from server.models import Player
from server.net import send_to, broadcast_to_room, players_in_room, player_info, log_event
from server.rooms import load_room_files, load_dungeon_templates
from server.lifecycle import (
    on_player_enter_room, on_player_leave_room,
    send_room_enter, do_room_transition,
)
from server.combat import handle_attack, game_tick
from server.debug_monsters import handle_debug_spawn, auto_register_debug_monsters
from server.npc_chat import find_adjacent_npc, handle_npc_chat, clear_player_history, register_town_guard
from server.dungeon_content import register_precreated_types, load_precreated_content
from server.dungeons import load_deprecation_timestamp, load_deprecated_sets, _run_content_deprecation, start_background_regen, get_dungeon_for_room
from server.dungeon_types import DUNGEON_TYPES
from server.content_library import ContentLibrary, MONSTER_LIBRARY_CAPACITY, TILE_LIBRARY_CAPACITY, ROOM_LIBRARY_CAPACITY
from server.validation import register_monster_type, register_tile_type


# ---------------------------------------------------------------------------
# Stdout capture — tees print() output to connected debug clients
# ---------------------------------------------------------------------------

class _LogBroadcaster:
    """Wraps sys.stdout to broadcast lines to debug-mode WebSocket clients."""

    def __init__(self, original):
        self._original = original
        self._buf = ""

    def write(self, text):
        self._original.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                self._broadcast(line)

    def _broadcast(self, line):
        if not game.players:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                msg = json.dumps({"type": "server_log", "text": line})
                for p in list(game.players.values()):
                    try:
                        asyncio.ensure_future(p.ws.send(msg))
                    except Exception:
                        pass
        except RuntimeError:
            pass

    def flush(self):
        self._original.flush()

    def __getattr__(self, name):
        return getattr(self._original, name)

if os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
    sys.stdout = _LogBroadcaster(sys.stdout)


# ---------------------------------------------------------------------------
# Movement
# ---------------------------------------------------------------------------

def check_edge_exit(player, new_x, new_y, room):
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


async def send_reconcile(player):
    """Send full state snapshot so client snaps to authoritative server state."""
    msg = {
        "type": "reconcile",
        "x": player.x,
        "y": player.y,
        "direction": player.direction,
    }
    if player.walk:
        elapsed = time.monotonic() - player.walk["start_time"]
        progress = min(elapsed / WALK_TIME, 1.0)
        msg["walking"] = True
        msg["walk_progress"] = progress
        msg["walk_from"] = {"x": player.walk["from_x"], "y": player.walk["from_y"]}
        msg["walk_to"] = {"x": player.walk["to_x"], "y": player.walk["to_y"]}
    else:
        msg["walking"] = False
    await send_to(player, msg)


async def handle_walk(player, direction: str, origin_x: int, origin_y: int):
    """Handle a walk request — validate and start a server-side walk."""
    if player.hp <= 0:
        return

    delta = DIRECTIONS.get(direction)
    if not delta:
        return
    dx, dy = delta
    now = time.monotonic()

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
            await send_reconcile(player)
            return

    # Origin validation — client and server must agree on position
    if origin_x != player.x or origin_y != player.y:
        await send_reconcile(player)
        return

    player.direction = direction
    player.dancing = False

    to_x = origin_x + dx
    to_y = origin_y + dy

    room = game.rooms[player.room]
    tilemap = room["tilemap"]

    # Off-grid — check room exit
    if to_x < 0 or to_x >= ROOM_COLS or to_y < 0 or to_y >= ROOM_ROWS:
        exit_dir = check_edge_exit(player, to_x, to_y, room)
        if exit_dir:
            player.walk = None
            await do_room_transition(player, exit_dir)
        else:
            await send_reconcile(player)
        return

    tile = tilemap[to_y][to_x]

    # Stairs
    if tile == "SU" and "up" in room["exits"]:
        player.walk = None
        await do_room_transition(player, "up")
        return
    if tile == "SD" and "down" in room["exits"]:
        player.walk = None
        await do_room_transition(player, "down")
        return

    # Not walkable
    if not game.is_walkable_tile(tile):
        await send_reconcile(player)
        return

    # Guard collision
    for guard in game.guards.get(player.room, []):
        if to_x == guard["x"] and to_y == guard["y"]:
            await send_reconcile(player)
            return

    # Start walk — use real start_time (dead reckoning offset only sent to other clients)
    player.walk = {
        "from_x": origin_x, "from_y": origin_y,
        "to_x": to_x, "to_y": to_y,
        "dir": direction,
        "start_time": now,
        "committed": False,
    }

    # Broadcast walk_started to other players with latency compensation offset
    initial_progress = LATENCY_COMP / WALK_TIME
    await broadcast_to_room(player.room, {
        "type": "walk_started",
        "name": player.name,
        "from_x": origin_x, "from_y": origin_y,
        "to_x": to_x, "to_y": to_y,
        "dir": direction,
        "progress": initial_progress,
    }, exclude=player.ws)


async def handle_cancel_walk(player):
    """Handle a cancel_walk request — validate timing and cancel or reject."""
    if player.walk is None:
        return

    now = time.monotonic()
    elapsed = now - player.walk["start_time"]

    if elapsed <= CANCEL_TIME + LATENCY_COMP:
        # Valid cancel — roll back to origin (even if midway committed)
        from_x = player.walk["from_x"]
        from_y = player.walk["from_y"]
        player.x = from_x
        player.y = from_y
        player.walk = None
        await broadcast_to_room(player.room, {
            "type": "walk_cancelled",
            "name": player.name,
            "x": from_x,
            "y": from_y,
        }, exclude=player.ws)
        # No reconcile needed — client already snapped back optimistically.
        # Sending one would interfere with any new walk the client started.
    else:
        # Too late to cancel — send reconcile with current walk state
        await send_reconcile(player)


# ---------------------------------------------------------------------------
# Chat commands
# ---------------------------------------------------------------------------

async def handle_chat(player, text: str):
    text = text.strip()
    if not text:
        return

    # Slash commands
    if text.startswith("/"):
        parts = text[1:].split(None, 1)
        cmd = parts[0].lower() if parts else ""
        if cmd == "who":
            lines = ["Players online:"]
            for p in game.players.values():
                room_name = game.rooms[p.room]["name"]
                lines.append(f"  {p.name} — {p.description} (in {room_name})")
            await send_to(player, {"type": "info", "text": "\n".join(lines)})
        elif cmd == "help":
            await send_to(player, {"type": "info", "text": (
                "Arrow keys / WASD — Move\n"
                "Space — Attack\n"
                "Enter — Open chat\n"
                "Escape — Close chat\n"
                "M — Toggle music\n"
                "/who — List online players\n"
                "/dance — Bust a move\n"
                "/help — Show this message"
            )})
        elif cmd == "dance":
            player.dancing = True
            await broadcast_to_room(player.room, {
                "type": "dance", "name": player.name,
            })
        elif cmd == "me":
            action = parts[1] if len(parts) > 1 else ""
            if action:
                await broadcast_to_room(player.room, {
                    "type": "chat", "from": player.name, "text": f"*{action}*",
                })
        elif cmd == "cheat" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
            if player.has_flag("invulnerable"):
                player.flags.discard("invulnerable")
                await send_to(player, {"type": "info", "text": "Cheat mode off: vulnerable again"})
            else:
                player.grant_flag("has_sword")
                player.grant_flag("invulnerable")
                player.hp = player.max_hp
                await send_to(player, {"type": "sword_obtained"})
                await send_to(player, {"type": "hp_update", "hp": player.hp, "max_hp": player.max_hp})
                await send_to(player, {"type": "info", "text": "Cheat mode: sword + invulnerability"})
        elif cmd == "debug_spawn" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
            await handle_debug_spawn(player, parts[1] if len(parts) > 1 else "")
        elif cmd == "deprecate" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
            for _tid in list(game.content_libraries.keys()):
                _run_content_deprecation(_tid)
            await send_to(player, {"type": "info", "text": "Forced deprecation pass — see ~ debug log"})
        elif cmd == "regen" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
            regen_inst = get_dungeon_for_room(player.room)
            regen_type = regen_inst.dungeon_id if regen_inst else "d1"
            regen_libs = game.content_libraries.get(regen_type, {})
            regen_room_lib = regen_libs.get("rooms")
            count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else (regen_room_lib.placeholder_count if regen_room_lib else 0)
            if count <= 0:
                await send_to(player, {"type": "info", "text": f"No {regen_type} room library slots to fill"})
            else:
                start_background_regen(count, regen_type)
                await send_to(player, {"type": "info", "text": f"Regen started: {count} {regen_type} room(s) — see ~ debug log"})
        elif cmd == "choir" and os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
            debug_on = getattr(player, '_debug_choir', False)
            choir_inst = get_dungeon_for_room(player.room)
            if debug_on:
                player._debug_choir = False
                if choir_inst:
                    choir_inst.boss_engaged = False
                await send_to(player, {"type": "boss_choir_stop"})
                await send_to(player, {"type": "info", "text": "Choir overlay OFF"})
            else:
                dist = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2
                player._debug_choir = True
                if choir_inst:
                    choir_inst.boss_engaged = True
                await send_to(player, {"type": "boss_choir_start", "distance": dist})
                await send_to(player, {"type": "info", "text": f"Choir overlay ON (distance={dist})"})
        else:
            await send_to(player, {"type": "info", "text": "Unknown command. Try /help"})
        return

    # Normal chat — broadcast to room
    room_name = game.rooms[player.room]["name"]
    log_event("CHAT", f"{player.name} ({room_name}): {text}")
    await broadcast_to_room(player.room, {
        "type": "chat",
        "from": player.name,
        "text": text,
    })

    # Check if player is adjacent to an NPC — trigger LLM conversation
    guard = find_adjacent_npc(player)
    if guard:
        await handle_npc_chat(player, guard, text)


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------

async def handle_connection(websocket):
    player = None
    remote = websocket.remote_address
    addr = f"{remote[0]}:{remote[1]}" if remote else "unknown"
    print(f"[CONN] New connection from {addr}")
    try:
        raw = await websocket.recv()
        data = json.loads(raw)
        if data.get("type") != "login":
            print(f"[CONN] {addr} sent non-login first message, dropping")
            return

        name = data.get("name", "").strip()[:20]
        desc = data.get("description", "").strip()[:80]

        if not name:
            await websocket.send(json.dumps({"type": "error", "text": "Name cannot be empty."}))
            return

        if any(p.name.lower() == name.lower() for p in game.players.values()):
            await websocket.send(json.dumps({"type": "error", "text": "That name is already taken."}))
            return

        color_index = game.next_color_index
        game.next_color_index = (game.next_color_index + 1) % 6

        player = Player(websocket, name, desc or "A mysterious stranger.", color_index)
        spawn = game.rooms[STARTING_ROOM]["spawn_points"]["default"]
        player.x, player.y = spawn
        game.players[websocket] = player
        log_event("JOIN", f"{name} ({player.description})")
        print(f"[JOIN] {name} from {addr}")

        login_msg = {"type": "login_ok", "color_index": color_index, "hp": PLAYER_MAX_HP, "max_hp": PLAYER_MAX_HP}
        if os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
            login_msg["debug_mode"] = True
            player.grant_flag("has_sword")
            player.grant_flag("invulnerable")
        await send_to(player, login_msg)
        if os.environ.get("DEBUG_MODE", "").lower() in ("1", "true"):
            await send_to(player, {"type": "sword_obtained"})
        await on_player_enter_room(player.room)
        await send_room_enter(player)
        await broadcast_to_room(
            player.room,
            {"type": "player_entered", **player_info(player)},
            exclude=websocket,
        )

        async for raw in websocket:
            try:
                data = json.loads(raw)
                msg_type = data.get("type")
                if msg_type == "walk":
                    origin = data.get("origin", {})
                    await handle_walk(player, data.get("direction", ""),
                                      origin.get("x", player.x), origin.get("y", player.y))
                elif msg_type == "cancel_walk":
                    await handle_cancel_walk(player)
                elif msg_type == "face":
                    direction = data.get("direction", "")
                    if direction in DIRECTIONS:
                        player.walk = None
                        player.direction = direction
                        player.dancing = False
                        await broadcast_to_room(player.room, {
                            "type": "player_faced",
                            "name": player.name,
                            "direction": direction,
                        }, exclude=player.ws)
                elif msg_type == "attack":
                    await handle_attack(player)
                elif msg_type == "chat":
                    await handle_chat(player, data.get("text", ""))
                elif msg_type == "ping":
                    await player.ws.send(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                print(f"[WARN] {name}: bad JSON: {raw[:200]}")
            except websockets.ConnectionClosed:
                raise  # re-raise so the outer handler logs it
            except Exception as e:
                print(f"[ERROR] {name}: message handler error: {type(e).__name__}: {e}")

    except websockets.ConnectionClosed as e:
        reason = f"code={e.code} reason='{e.reason}'" if e.code else "no close frame"
        who = player.name if player else addr
        print(f"[DISC] {who} disconnected: {reason}")
        log_event("DISCONNECT", f"{who} — {reason}")
    except Exception as e:
        who = player.name if player else addr
        print(f"[ERROR] {who} error: {type(e).__name__}: {e}")
        log_event("ERROR", f"{who} — {type(e).__name__}: {e}")
    finally:
        if player and websocket in game.players:
            leaving_room = player.room
            del game.players[websocket]
            log_event("LEAVE", player.name)
            print(f"[LEAVE] {player.name}")
            clear_player_history(player.name)
            await broadcast_to_room(
                leaving_room,
                {"type": "player_left", "name": player.name},
            )
            await on_player_leave_room(leaving_room)


# ---------------------------------------------------------------------------
# HTTP server for client files
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).parent

STATIC_FILES = {
    "/":            ("client/client.html", "text/html; charset=utf-8"),
    "/index.html":  ("client/client.html", "text/html; charset=utf-8"),
    "/game_state.js": ("client/game_state.js", "application/javascript; charset=utf-8"),
    "/sprite_data.js": ("client/sprite_data.js", "application/javascript; charset=utf-8"),
    "/sprites.js":  ("client/sprites.js",  "application/javascript; charset=utf-8"),
    "/tiles.js":    ("client/tiles.js",    "application/javascript; charset=utf-8"),
    "/music.js":    ("client/music.js",    "application/javascript; charset=utf-8"),
    "/renderer.js": ("client/renderer.js", "application/javascript; charset=utf-8"),
    "/net.js":      ("client/net.js",      "application/javascript; charset=utf-8"),
    "/input.js":    ("client/input.js",    "application/javascript; charset=utf-8"),
    # Overworld music
    "/music.mp3":              ("music/overworld/village.mp3", "audio/mpeg"),
    "/music_tavern.mp3":       ("music/overworld/tavern.mp3", "audio/mpeg"),
    "/music_chapel.mp3":       ("music/overworld/chapel.mp3", "audio/mpeg"),
    "/music_overworld.mp3":    ("music/overworld/overworld.mp3", "audio/mpeg"),
    # Dungeon 1 music
    "/music_dungeon1.mp3":     ("music/dungeon1/dungeon_a.mp3", "audio/mpeg"),
    "/music_dungeon2.mp3":     ("music/dungeon1/dungeon_b.mp3", "audio/mpeg"),
    "/music_dungeon3.mp3":     ("music/dungeon1/dungeon_c.mp3", "audio/mpeg"),
    "/music_dungeon4.mp3":     ("music/dungeon1/dungeon_d.mp3", "audio/mpeg"),
    "/music_dungeon5.mp3":     ("music/dungeon1/dungeon_e.mp3", "audio/mpeg"),
    "/music_dungeon6.mp3":     ("music/dungeon1/dungeon_f.mp3", "audio/mpeg"),
    "/music_boss1.mp3":        ("music/dungeon1/boss1.mp3", "audio/mpeg"),
    "/music_boss1_choir.mp3":  ("music/dungeon1/boss1_choir.mp3", "audio/mpeg"),
    "/music_boss2.mp3":        ("music/dungeon1/boss2.mp3", "audio/mpeg"),
    "/music_boss2_choir.mp3":  ("music/dungeon1/boss2_choir.mp3", "audio/mpeg"),
    "/music_boss3.mp3":        ("music/dungeon1/boss3.mp3", "audio/mpeg"),
    "/music_boss3_choir.mp3":  ("music/dungeon1/boss3_choir.mp3", "audio/mpeg"),
    # Dungeon 2 (water temple) music
    "/music_watertemple1.mp3":       ("music/dungeon2/watertemple_a.mp3", "audio/mpeg"),
    "/music_watertemple2.mp3":       ("music/dungeon2/watertemple_b.mp3", "audio/mpeg"),
    "/music_watertemple_boss1.mp3":  ("music/dungeon2/watertemple_boss1.mp3", "audio/mpeg"),
    "/music_watertemple_boss1_choir.mp3": ("music/dungeon2/watertemple_boss1_choir.mp3", "audio/mpeg"),
}


async def process_request(path, request_headers):
    path = path.split("?")[0]  # strip query string for cache-busting support
    if path == "/ws":
        return None
    if path == "/get-log":
        body = game.log_file.read_bytes() if game.log_file.exists() else b""
        return HTTPStatus.OK, [("Content-Type", "text/plain; charset=utf-8")], body
    if path == "/clear-log":
        game.log_file.write_text("", encoding="utf-8")
        return HTTPStatus.OK, [("Content-Type", "text/plain; charset=utf-8")], b"Log cleared."
    if path in STATIC_FILES:
        filename, content_type = STATIC_FILES[path]
        body = (ROOT_DIR / filename).read_bytes()
        return HTTPStatus.OK, [("Content-Type", content_type)], body
    return HTTPStatus.NOT_FOUND, [], b"Not Found"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    game.load_builtin_tiles()
    game.load_builtin_monsters()
    game.load_npc_sprites()
    load_room_files()
    register_precreated_types()
    register_town_guard()
    auto_register_debug_monsters()

    # Initialize per-type dungeon templates and content libraries
    data_dir = ROOT_DIR / "data"

    for type_id, type_config in DUNGEON_TYPES.items():
        # Load dungeon room templates for this type
        load_dungeon_templates(type_config["template_dir"], type_id)

        # Create content libraries (use per-type capacities if defined)
        m_cap = type_config.get("monster_capacity", MONSTER_LIBRARY_CAPACITY)
        t_cap = type_config.get("tile_capacity", TILE_LIBRARY_CAPACITY)
        r_cap = type_config.get("room_capacity", ROOM_LIBRARY_CAPACITY)
        monster_lib = ContentLibrary("monster", m_cap)
        tile_lib = ContentLibrary("tile", t_cap)
        room_lib = ContentLibrary("room", r_cap)

        # Load precreated content into libraries
        templates = game.dungeon_templates.get(type_id, {})
        special_rooms = {type_config["boss_template"], type_config["treasure_template"]}
        load_precreated_content(monster_lib, tile_lib, room_lib, templates,
                                special_rooms=special_rooms, type_id=type_id)

        # Load custom (AI-generated) entries from disk
        # Try new per-type path first, fall back to old path for d1 backward compat
        for lib_name, lib, old_name in [
            ("monster", monster_lib, "monster_library.json"),
            ("tile", tile_lib, "tile_library.json"),
            ("room", room_lib, "room_library.json"),
        ]:
            new_path = data_dir / f"{type_id}_{old_name}"
            old_path = data_dir / old_name
            if new_path.exists():
                lib.load_custom(new_path)
            elif old_path.exists() and type_id == "d1":
                lib.load_custom(old_path)

        game.content_libraries[type_id] = {
            "rooms": room_lib,
            "monsters": monster_lib,
            "tiles": tile_lib,
        }
        game.deprecated_content.setdefault(type_id, {"monsters": set(), "tiles": set()})

    # Register custom library entries into game registries so send_room_enter()
    # can send sprites/tile recipes and monsters can spawn correctly
    for type_id, libs in game.content_libraries.items():
        monster_lib = libs.get("monsters")
        tile_lib = libs.get("tiles")
        if monster_lib:
            for entry in monster_lib.real_entries:
                if not entry.permanent and entry.id not in game.custom_sprites:
                    ok, errors = register_monster_type(entry.data)
                    if not ok:
                        print(f"[LIBS] WARNING: Failed to register monster {entry.id}: {errors}")
        if tile_lib:
            for entry in tile_lib.real_entries:
                if not entry.permanent and entry.id not in game.custom_tile_recipes:
                    ok, errors = register_tile_type(entry.data)
                    if not ok:
                        print(f"[LIBS] WARNING: Failed to register tile {entry.id}: {errors}")

    for type_id, libs in game.content_libraries.items():
        m = libs.get("monsters")
        t = libs.get("tiles")
        r = libs.get("rooms")
        print(f"[LIBS] {type_id}: monster {m.real_count}/{m.capacity}, "
              f"tile {t.real_count}/{t.capacity}, room {r.real_count}/{r.capacity}")

    behavior_engine.init(players_in_room, ROOM_COLS, ROOM_ROWS, game.is_walkable_tile, game.guards, game.rooms)
    port = 8080
    server = await websockets.serve(
        handle_connection, "0.0.0.0", port,
        process_request=process_request,
        ping_interval=30,
        ping_timeout=60,
    )
    asyncio.create_task(game_tick())
    load_deprecation_timestamp()
    load_deprecated_sets()
    print("MUD server running!")
    print(f"Local:  http://localhost:{port}")

    try:
        from pyngrok import ngrok
        tunnel = ngrok.connect(port, "http")
        print(f"Public: {tunnel.public_url}")
        print("\nShare the public URL with your friends!")
    except Exception as e:
        print(f"\nngrok not available ({e})")
        print("Friends can still join on your local network.")

    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
