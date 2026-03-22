"""
MUD Server — Zelda-style multiplayer online dungeon.

Run with: python mud_server.py
Then open http://localhost:8080 in your browser.
"""

import asyncio
import json
import os
import sys
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
from server.constants import STARTING_ROOM, PLAYER_MAX_HP, ROOM_COLS, ROOM_ROWS
from server.models import Player
from server.net import send_to, players_in_room, player_info, log_event
from server.rooms import load_room_files, load_dungeon_templates
from server.lifecycle import on_player_enter_room, on_player_leave_room, send_room_enter
from server.combat import game_tick, flush_messages
from server.debug_monsters import auto_register_debug_monsters
from server.npc_chat import clear_player_history, register_town_guard
from server.dungeon_content import register_precreated_types, load_precreated_content
from server.dungeons import load_deprecation_timestamp, load_deprecated_sets
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
        player.x, player.y = float(spawn[0]), float(spawn[1])
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

        # Room entry — use sync lifecycle with message batching
        on_player_enter_room(player.room)
        login_msgs = []
        send_room_enter(player, login_msgs)
        login_msgs.append(("broadcast", player.room,
                           {"type": "player_entered", **player_info(player)}, websocket))
        await flush_messages(login_msgs)

        # Message loop — all game logic is queued for the tick loop
        async for raw in websocket:
            try:
                data = json.loads(raw)
                msg_type = data.get("type")
                if msg_type == "ping":
                    await player.ws.send(json.dumps({"type": "pong"}))
                elif msg_type in ("position_update", "face", "attack", "chat"):
                    player.command_queue.append((msg_type, data))
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
            disc_msgs = []
            disc_msgs.append(("broadcast", leaving_room,
                              {"type": "player_left", "name": player.name}, None))
            on_player_leave_room(leaving_room, disc_msgs)
            await flush_messages(disc_msgs)


# ---------------------------------------------------------------------------
# HTTP server for client files
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).parent

STATIC_FILES = {
    "/":            ("client/client.html", "text/html; charset=utf-8"),
    "/index.html":  ("client/client.html", "text/html; charset=utf-8"),
    "/game_state.js": ("client/game_state.js", "application/javascript; charset=utf-8"),
    "/title.js":    ("client/title.js",    "application/javascript; charset=utf-8"),
    "/sprite_data.js": ("client/sprite_data.js", "application/javascript; charset=utf-8"),
    "/sprites.js":  ("client/sprites.js",  "application/javascript; charset=utf-8"),
    "/tiles.js":    ("client/tiles.js",    "application/javascript; charset=utf-8"),
    "/music.js":    ("client/music.js",    "application/javascript; charset=utf-8"),
    "/renderer.js": ("client/renderer.js", "application/javascript; charset=utf-8"),
    "/fx.js":       ("client/fx.js",       "application/javascript; charset=utf-8"),
    "/net.js":      ("client/net.js",      "application/javascript; charset=utf-8"),
    "/input.js":    ("client/input.js",    "application/javascript; charset=utf-8"),
    # Overworld music
    "/music.mp3":              ("music/overworld/village.mp3", "audio/mpeg"),
    "/music_tavern.mp3":       ("music/overworld/tavern.mp3", "audio/mpeg"),
    "/music_chapel.mp3":       ("music/overworld/chapel.mp3", "audio/mpeg"),
    "/music_overworld.mp3":    ("music/overworld/overworld.mp3", "audio/mpeg"),
    # Dungeon 1 music
    "/music_dungeon2.mp3":     ("music/dungeon1/dungeon_b.mp3", "audio/mpeg"),
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
    "/music_watertemple3.mp3":       ("music/dungeon2/watertemple_c.mp3", "audio/mpeg"),
    "/music_watertemple_boss1.mp3":  ("music/dungeon2/watertemple_boss1.mp3", "audio/mpeg"),
    "/music_watertemple_boss1_choir.mp3": ("music/dungeon2/watertemple_boss1_choir.mp3", "audio/mpeg"),
    "/music_watertemple_boss2.mp3":  ("music/dungeon2/watertemple_boss2.mp3", "audio/mpeg"),
    "/music_watertemple_boss2_choir.mp3": ("music/dungeon2/watertemple_boss2_choir.mp3", "audio/mpeg"),
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
    game.load_tiles()
    game.load_monsters()
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
