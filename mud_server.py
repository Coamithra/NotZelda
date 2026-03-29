"""
MUD Server — Zelda-style multiplayer online dungeon.

Run with: python mud_server.py
Then open http://localhost:8080 in your browser.
"""

import asyncio
import json
import os
import re
import time
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
from server.constants import DEBUG_MODE, STARTING_ROOM, PLAYER_MAX_HP
from server.models import Player
from server import log
from server.net import send_to, player_info
from server.rooms import load_room_files, load_dungeon_templates
from server.lifecycle import (
    on_player_enter_room, on_player_leave_room, send_room_enter,
    broadcast_dungeon_player_positions,
)
from server.combat import game_tick, flush_messages
from server.debug_monsters import auto_register_debug_monsters
from server.npc_chat import clear_player_history, register_town_guard, warmup_ollama
from server.dungeon_content import register_precreated_types, load_precreated_content
from server.dungeons import load_deprecation_timestamp, load_deprecated_sets, get_dungeon_for_room
from server.dungeon_types import DUNGEON_TYPES
from server.content_library import ContentLibrary, MONSTER_LIBRARY_CAPACITY, TILE_LIBRARY_CAPACITY, ROOM_LIBRARY_CAPACITY
from server.validation import register_monster_type, register_tile_type


# ---------------------------------------------------------------------------
# Stdout capture — safety net for stray print() from libraries/tracebacks.
# All intentional logging goes through server.log; this catches the rest.
# ---------------------------------------------------------------------------

_log_tasks = set()  # prevent GC of fire-and-forget log-broadcast tasks


async def _safe_log_send(ws, msg):
    """Send a log message to a single websocket, swallowing errors."""
    try:
        await ws.send(msg)
    except Exception:
        pass


class _LogBroadcaster:
    """Wraps sys.stdout to broadcast stray print() output to debug clients
    and write it to the server log file."""

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
                self._write_file(line)

    def _write_file(self, line):
        """Append stray stdout lines to the server log file."""
        try:
            log._write_file(f"[{log._timestamp()}] [STDOUT] {line}")
        except Exception:
            pass

    def _broadcast(self, line):
        if not game.players:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                msg = json.dumps({"type": "server_log", "text": line})
                for p in list(game.players.values()):
                    try:
                        task = asyncio.ensure_future(_safe_log_send(p.ws, msg))
                        _log_tasks.add(task)
                        task.add_done_callback(_log_tasks.discard)
                    except Exception:
                        pass
        except RuntimeError:
            pass

    def flush(self):
        self._original.flush()

    def __getattr__(self, name):
        return getattr(self._original, name)

if DEBUG_MODE:
    sys.stdout = _LogBroadcaster(sys.stdout)


# ---------------------------------------------------------------------------
# Login name validation
# ---------------------------------------------------------------------------

# Allow unicode letters, digits, underscores, spaces, hyphens, apostrophes.
# Reject control chars, HTML-special chars, emoji, and other symbols.
_VALID_NAME_RE = re.compile(r"^[\w '-]+$", re.UNICODE)
# \w matches [a-zA-Z0-9_] plus unicode letters/digits.
# We also allow space, apostrophe, and hyphen for names like "O'Brien" or "Mary Jane".

def _validate_login_name(name: str) -> str | None:
    """Return an error message if the name is invalid, or None if it's OK."""
    if not name:
        return "Name cannot be empty."
    if not _VALID_NAME_RE.match(name):
        return "Name can only contain letters, numbers, spaces, hyphens, apostrophes, and underscores."
    if name.startswith((" ", "-", "'")) or name.endswith((" ", "-", "'")):
        return "Name cannot start or end with a space, hyphen, or apostrophe."
    if "  " in name:
        return "Name cannot contain consecutive spaces."
    return None

# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------

async def handle_connection(websocket):
    player = None
    connect_time = time.time()
    remote = websocket.remote_address
    addr = f"{remote[0]}:{remote[1]}" if remote else "unknown"
    # Extract real IP and User-Agent from nginx proxy headers
    headers = websocket.request_headers if hasattr(websocket, 'request_headers') else {}
    real_ip = headers.get("X-Forwarded-For", addr)
    user_agent = headers.get("User-Agent", "unknown")
    ua_short = user_agent[:80]
    log.debug(f"[CONN] New connection from {real_ip} (UA: {ua_short})")
    try:
        raw = await websocket.recv()
        data = json.loads(raw)
        if data.get("type") != "login":
            log.debug(f"[CONN] {addr} sent non-login first message, dropping")
            return

        name = data.get("name", "").strip()[:20]
        desc = data.get("description", "").strip()[:80]

        name_error = _validate_login_name(name)
        if name_error:
            await websocket.send(json.dumps({"type": "error", "text": name_error}))
            return

        if any(p.name.lower() == name.lower() for p in game.players.values()):
            await websocket.send(json.dumps({"type": "error", "text": "That name is already taken."}))
            return

        color_index = game.next_color_index
        game.next_color_index = (game.next_color_index + 1) % 6

        player = Player(websocket, name, desc or "A mysterious stranger.", color_index)
        spawn = game.rooms[STARTING_ROOM]["spawn_points"]["default"]
        player.avatar.x, player.avatar.y = float(spawn[0]), float(spawn[1])
        player.avatar.last_reported_x = player.avatar.x
        player.avatar.last_reported_y = player.avatar.y
        game.players[websocket] = player
        log.event("JOIN", f"{name} ({player.description}) from {addr}")
        warmup_ollama()

        login_msg = {"type": "login_ok", "color_index": color_index, "hp": PLAYER_MAX_HP, "max_hp": PLAYER_MAX_HP}
        if DEBUG_MODE:
            login_msg["debug_mode"] = True
            player.grant_flag("has_sword")
            player.grant_flag("invulnerable")
        await send_to(player, login_msg)
        if DEBUG_MODE:
            await send_to(player, {"type": "item_obtained", "item_type": "sword", "item_name": "Sword"})

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
                elif msg_type in ("position_update", "face", "attack", "chat", "unlock_door", "respawn_request"):
                    player.command_queue.append((msg_type, data))
            except json.JSONDecodeError:
                log.debug(f"[WARN] {name}: bad JSON: {raw[:200]}")
            except websockets.ConnectionClosed:
                raise  # re-raise so the outer handler logs it
            except Exception as e:
                log.debug(f"[ERROR] {name}: message handler error: {type(e).__name__}: {e}")

    except websockets.ConnectionClosed as e:
        reason = f"code={e.code} reason='{e.reason}'" if e.code else "no close frame"
        who = player.name if player else addr
        duration = time.time() - connect_time
        log.event("DISCONNECT", f"{who} — {reason} — {duration:.0f}s (IP: {real_ip}, UA: {ua_short})")
    except Exception as e:
        who = player.name if player else addr
        duration = time.time() - connect_time
        log.event("ERROR", f"{who} — {type(e).__name__}: {e} — {duration:.0f}s")
    finally:
        if player and websocket in game.players:
            leaving_room = player.room
            del game.players[websocket]
            log.event("LEAVE", player.name)
            clear_player_history(player.name)
            disc_msgs = []

            # Clean up tombstone if this player had one
            if player.name in game.tombstones:
                ts = game.tombstones.pop(player.name)
                if ts.reviver:
                    disc_msgs.append(("send", ts.reviver, {"type": "revival_cancelled"}))
                disc_msgs.append(("broadcast", ts.room_id, {
                    "type": "tombstone_removed", "name": player.name,
                }, None))

            # Cancel any revival this player was channeling
            for ts in game.tombstones.values():
                if ts.reviver is player:
                    ts.reviver = None
                    ts.revival_start_time = 0.0
                    disc_msgs.append(("send", ts.player, {"type": "revival_cancelled"}))
                    disc_msgs.append(("broadcast", ts.room_id, {
                        "type": "revival_cancelled", "target": ts.name,
                    }, None))
                    break

            disc_msgs.append(("broadcast", leaving_room,
                              {"type": "player_left", "name": player.name}, None))
            on_player_leave_room(leaving_room, disc_msgs)
            # Update compass minimap for remaining dungeon players
            dungeon_inst = get_dungeon_for_room(leaving_room)
            if dungeon_inst:
                broadcast_dungeon_player_positions(dungeon_inst, player, disc_msgs)
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
    # Menu music
    "/music_menu.mp3":         ("music/other/menu.mp3", "audio/mpeg"),
    # Overworld music
    "/music.mp3":              ("music/overworld/village.mp3", "audio/mpeg"),
    "/music_tavern.mp3":       ("music/overworld/tavern.mp3", "audio/mpeg"),
    "/music_chapel.mp3":       ("music/overworld/chapel.mp3", "audio/mpeg"),
    "/music_overworld.mp3":    ("music/overworld/overworld.mp3", "audio/mpeg"),
    "/music_castle_ruins.mp3": ("music/overworld/castle_ruins.mp3", "audio/mpeg"),
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
                        log.debug(f"[LIBS] WARNING: Failed to register monster {entry.id}: {errors}")
        if tile_lib:
            for entry in tile_lib.real_entries:
                if not entry.permanent and entry.id not in game.custom_tile_recipes:
                    ok, errors = register_tile_type(entry.data)
                    if not ok:
                        log.debug(f"[LIBS] WARNING: Failed to register tile {entry.id}: {errors}")

    for type_id, libs in game.content_libraries.items():
        m = libs.get("monsters")
        t = libs.get("tiles")
        r = libs.get("rooms")
        log.debug(f"[LIBS] {type_id}: monster {m.real_count}/{m.capacity}, "
                  f"tile {t.real_count}/{t.capacity}, room {r.real_count}/{r.capacity}")

    from server.combat import _apply_damage
    behavior_engine.init(_apply_damage)
    port = int(os.environ.get("PORT", 8080))
    server = await websockets.serve(
        handle_connection, "0.0.0.0", port,
        process_request=process_request,
        compression=None,
        ping_interval=15,
        ping_timeout=120,
    )

    # TLS WebSocket on port 8443 — bypasses nginx to avoid iOS Safari 30s disconnect
    tls_port = 8443
    cert_path = Path("/etc/letsencrypt/live/notzelda.haraldmaassen.com")
    if cert_path.exists():
        import ssl
        ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_ctx.load_cert_chain(cert_path / "fullchain.pem", cert_path / "privkey.pem")
        tls_server = await websockets.serve(
            handle_connection, "0.0.0.0", tls_port,
            process_request=process_request,
            ssl=ssl_ctx,
            compression=None,
            ping_interval=15,
            ping_timeout=120,
        )
        log.debug(f"TLS WebSocket on port {tls_port}")
    else:
        log.debug(f"No TLS cert found at {cert_path} — TLS WebSocket disabled")

    asyncio.create_task(game_tick())
    load_deprecation_timestamp()
    load_deprecated_sets()
    log.debug("MUD server running!")
    log.debug(f"Local:  http://localhost:{port}")

    try:
        from pyngrok import ngrok
        tunnel = ngrok.connect(port, "http")
        log.debug(f"Public: {tunnel.public_url}")
        log.debug("Share the public URL with your friends!")
    except Exception as e:
        log.debug(f"ngrok not available ({e})")
        log.debug("Friends can still join on your local network.")

    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
