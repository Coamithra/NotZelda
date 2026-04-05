"""
MUD Server — Zelda-style multiplayer online dungeon.

Run with: python mud_server.py
Then open http://localhost:8080 in your browser.
"""

import asyncio
import base64
import hmac
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
from websockets.legacy.http import read_headers, read_line
from websockets.legacy.server import WebSocketServerProtocol

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
from server.ai_generator import rate_limiter, usage_tracker, AI_BACKEND, ANTHROPIC_MODEL


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

        # Debug auto-login: assign debugN name if none provided
        if DEBUG_MODE and not name:
            existing = {p.name for p in game.players.values()}
            n = 1
            while f"debug{n}" in existing:
                n += 1
            name = f"debug{n}"

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

        login_msg = {"type": "login_ok", "name": name, "color_index": color_index, "hp": PLAYER_MAX_HP, "max_hp": PLAYER_MAX_HP}
        if DEBUG_MODE:
            login_msg["debug_mode"] = True
            player.grant_flag("has_sword")
            player.grant_flag("has_lantern")
            player.grant_flag("invulnerable")
        await send_to(player, login_msg)
        if DEBUG_MODE:
            await send_to(player, {"type": "item_obtained", "item_type": "sword", "item_name": "Sword"})
            await send_to(player, {"type": "item_obtained", "item_type": "lantern", "item_name": "Magic Lantern"})

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
                    pong = {"type": "pong"}
                    if "ct" in data:
                        pong["ct"] = data["ct"]  # echo client timestamp for RTT measurement
                    await player.ws.send(json.dumps(pong))
                elif msg_type in ("player_input", "player_state", "chat", "unlock_door", "respawn_request"):
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

            # Clean up gauntlet session if player was in one
            if leaving_room.startswith("gauntlet_"):
                from server.gauntlet import on_gauntlet_exit
                on_gauntlet_exit(player.name)

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
    "/ost":         ("client/ost.html",    "text/html; charset=utf-8"),
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
    "/music_menu.mp3":         ("audio/music/other/menu.mp3", "audio/mpeg"),
    # Overworld music
    "/music.mp3":              ("audio/music/overworld/village.mp3", "audio/mpeg"),
    "/music_tavern.mp3":       ("audio/music/overworld/tavern.mp3", "audio/mpeg"),
    "/music_chapel.mp3":       ("audio/music/overworld/chapel.mp3", "audio/mpeg"),
    "/music_overworld.mp3":    ("audio/music/overworld/overworld.mp3", "audio/mpeg"),
    "/music_castle_ruins.mp3": ("audio/music/overworld/castle_ruins.mp3", "audio/mpeg"),
    # Dungeon 1 music
    "/music_dungeon2.mp3":     ("audio/music/dungeon1/dungeon_b.mp3", "audio/mpeg"),
    "/music_dungeon4.mp3":     ("audio/music/dungeon1/dungeon_d.mp3", "audio/mpeg"),
    "/music_dungeon5.mp3":     ("audio/music/dungeon1/dungeon_e.mp3", "audio/mpeg"),
    "/music_dungeon6.mp3":     ("audio/music/dungeon1/dungeon_f.mp3", "audio/mpeg"),
    "/music_boss1.mp3":        ("audio/music/dungeon1/boss1.mp3", "audio/mpeg"),
    "/music_boss1_choir.mp3":  ("audio/music/dungeon1/boss1_choir.mp3", "audio/mpeg"),
    "/music_boss2.mp3":        ("audio/music/dungeon1/boss2.mp3", "audio/mpeg"),
    "/music_boss2_choir.mp3":  ("audio/music/dungeon1/boss2_choir.mp3", "audio/mpeg"),
    "/music_boss3.mp3":        ("audio/music/dungeon1/boss3.mp3", "audio/mpeg"),
    "/music_boss3_choir.mp3":  ("audio/music/dungeon1/boss3_choir.mp3", "audio/mpeg"),
    # Dungeon 2 (water temple) music
    "/music_watertemple1.mp3":       ("audio/music/dungeon2/watertemple_a.mp3", "audio/mpeg"),
    "/music_watertemple2.mp3":       ("audio/music/dungeon2/watertemple_b.mp3", "audio/mpeg"),
    "/music_watertemple3.mp3":       ("audio/music/dungeon2/watertemple_c.mp3", "audio/mpeg"),
    "/music_watertemple_boss1.mp3":  ("audio/music/dungeon2/watertemple_boss1.mp3", "audio/mpeg"),
    "/music_watertemple_boss1_choir.mp3": ("audio/music/dungeon2/watertemple_boss1_choir.mp3", "audio/mpeg"),
    "/music_watertemple_boss2.mp3":  ("audio/music/dungeon2/watertemple_boss2.mp3", "audio/mpeg"),
    "/music_watertemple_boss2_choir.mp3": ("audio/music/dungeon2/watertemple_boss2_choir.mp3", "audio/mpeg"),
    # Dungeon 3 (desert tomb) music
    "/music_desert_a.mp3":     ("audio/music/dungeon3/desert_a.mp3", "audio/mpeg"),
    "/music_desert_b.mp3":     ("audio/music/dungeon3/desert_b.mp3", "audio/mpeg"),
    "/music_desert_c.mp3":     ("audio/music/dungeon3/desert_c.mp3", "audio/mpeg"),
    "/music_desert_boss1.mp3":       ("audio/music/dungeon3/desert_boss1.mp3", "audio/mpeg"),
    "/music_desert_boss1_choir.mp3": ("audio/music/dungeon3/desert_boss1_choir.mp3", "audio/mpeg"),
    "/music_desert_boss2.mp3":       ("audio/music/dungeon3/desert_boss2.mp3", "audio/mpeg"),
    "/music_desert_boss2_choir.mp3": ("audio/music/dungeon3/desert_boss2_choir.mp3", "audio/mpeg"),
    # Sound effects (AI-generated WAV)
    "/sfx_sword_slash.wav":     ("audio/sfx/combat/sword_slash.wav", "audio/wav"),
    "/sfx_sword_hit.wav":       ("audio/sfx/combat/sword_hit.wav", "audio/wav"),
    "/sfx_sword_hit_flesh.wav": ("audio/sfx/combat/sword_hit_flesh.wav", "audio/wav"),
    "/sfx_player_hurt.wav":     ("audio/sfx/combat/player_hurt.wav", "audio/wav"),
    "/sfx_monster_death.wav":   ("audio/sfx/combat/monster_death.wav", "audio/wav"),
    "/sfx_boss_roar.wav":       ("audio/sfx/combat/boss_roar.wav", "audio/wav"),
    "/sfx_player_death.wav":    ("audio/sfx/combat/player_death.wav", "audio/wav"),
    "/sfx_revival_success.wav": ("audio/sfx/combat/revival_success.wav", "audio/wav"),
    "/sfx_door_open.wav":       ("audio/sfx/environment/door_open.wav", "audio/wav"),
    "/sfx_door_locked.wav":     ("audio/sfx/environment/door_locked.wav", "audio/wav"),
    "/sfx_footstep_grass.wav":  ("audio/sfx/environment/footstep_grass.wav", "audio/wav"),
    "/sfx_footstep_stone.wav":  ("audio/sfx/environment/footstep_stone.wav", "audio/wav"),
    "/sfx_water_splash.wav":    ("audio/sfx/environment/water_splash.wav", "audio/wav"),
    "/sfx_portal_enter.wav":    ("audio/sfx/environment/portal_enter.wav", "audio/wav"),
    "/sfx_chest_open.wav":      ("audio/sfx/items/chest_open.wav", "audio/wav"),
    "/sfx_key_pickup.wav":      ("audio/sfx/items/key_pickup.wav", "audio/wav"),
    "/sfx_item_pickup.wav":     ("audio/sfx/items/item_pickup.wav", "audio/wav"),
    "/sfx_npc_chat_open.wav":   ("audio/sfx/ui/npc_chat_open.wav", "audio/wav"),
    "/sfx_stairs_up.wav":       ("audio/sfx/environment/stairs_up.wav", "audio/wav"),
    "/sfx_stairs_down.wav":     ("audio/sfx/environment/stairs_down.wav", "audio/wav"),
}


# Captured at module load — slightly earlier than actual server listen, but close enough for debug
_server_start_time = time.time()


def _build_library_stats() -> dict:
    """Assemble a JSON-serializable snapshot of library composition and API usage."""
    # -- Server info --
    server_info = {
        "uptime_seconds": round(time.time() - _server_start_time),
        "players_online": len(game.players),
        "active_dungeons": sorted(game.active_dungeons.keys()),
        "debug_mode": DEBUG_MODE,
    }

    # -- Per-dungeon library composition --
    libraries = {}
    for type_id, libs in sorted(game.content_libraries.items()):
        type_libs = {}
        for lib_name in ("rooms", "monsters", "tiles"):
            lib = libs.get(lib_name)
            if lib:
                type_libs[lib_name] = {
                    "capacity": lib.capacity,
                    "real": lib.real_count,
                    "permanent": lib.permanent_count,
                    "custom": lib.custom_count,
                    "placeholders": lib.placeholder_count,
                }
        libraries[type_id] = type_libs

    # -- Deprecated content counts --
    deprecated = {}
    for type_id, dep in sorted(game.deprecated_content.items()):
        deprecated[type_id] = {
            "monsters": len(dep.get("monsters", set())),
            "tiles": len(dep.get("tiles", set())),
        }

    # -- API usage --
    api_usage = {
        "backend": AI_BACKEND,
        "model": ANTHROPIC_MODEL,
        "rate_limit": {
            "per_minute": rate_limiter.per_minute,
            "per_day": rate_limiter.per_day,
            "daily_calls_used": rate_limiter.daily_calls,
        },
        "tokens": {
            "total_input": usage_tracker.total_input_tokens,
            "total_output": usage_tracker.total_output_tokens,
            "total_cache_write": usage_tracker.total_cache_write_tokens,
            "total_cache_read": usage_tracker.total_cache_read_tokens,
            "total_calls": usage_tracker.total_calls,
            "estimated_cost_usd": round(usage_tracker.estimated_cost(), 4),
        },
        "session": {
            "input": usage_tracker.session_input_tokens,
            "output": usage_tracker.session_output_tokens,
            "cache_write": usage_tracker.session_cache_write_tokens,
            "cache_read": usage_tracker.session_cache_read_tokens,
            "calls": usage_tracker.session_calls,
            "estimated_cost_usd": round(usage_tracker.session_cost(), 4),
        },
    }

    return {
        "server": server_info,
        "libraries": libraries,
        "deprecated": deprecated,
        "api_usage": api_usage,
    }


def _check_admin_auth(request_headers):
    """Validate Basic Auth against ADMIN_PASSWORD. Returns None on success, or HTTP error response tuple."""
    admin_pw = os.environ.get("ADMIN_PASSWORD", "")
    if not admin_pw:
        return HTTPStatus.NOT_FOUND, [], b"Not Found"
    auth = request_headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return HTTPStatus.UNAUTHORIZED, [("WWW-Authenticate", 'Basic realm="Admin"')], b"Unauthorized"
    try:
        provided = base64.b64decode(auth[6:]).decode()
    except Exception:
        return HTTPStatus.UNAUTHORIZED, [("WWW-Authenticate", 'Basic realm="Admin"')], b"Unauthorized"
    if not hmac.compare_digest(provided, f"admin:{admin_pw}"):
        return HTTPStatus.UNAUTHORIZED, [("WWW-Authenticate", 'Basic realm="Admin"')], b"Unauthorized"
    return None


class _GameServerProtocol(WebSocketServerProtocol):
    """Extend WebSocket protocol to accept POST for admin endpoints.

    websockets 12.0 only accepts GET requests. This subclass overrides
    read_http_request() to also accept POST, storing the method so
    process_request() can enforce POST-only on destructive endpoints.
    """

    async def read_http_request(self):
        """Read HTTP request line, accepting both GET and POST methods."""
        try:
            request_line = await read_line(self.reader)
        except EOFError as exc:
            raise websockets.exceptions.InvalidMessage(
                "connection closed while reading HTTP request line"
            ) from exc

        try:
            method, raw_path, version = request_line.split(b" ", 2)
        except ValueError:
            raise websockets.exceptions.InvalidMessage(
                "invalid HTTP request line"
            ) from None

        if method not in (b"GET", b"POST"):
            raise websockets.exceptions.InvalidMessage(
                f"unsupported HTTP method: {method.decode(errors='backslashreplace')}"
            )
        if version != b"HTTP/1.1":
            raise websockets.exceptions.InvalidMessage(
                f"unsupported HTTP version: {version.decode(errors='backslashreplace')}"
            )

        path = raw_path.decode("ascii", "surrogateescape")
        headers = await read_headers(self.reader)

        self.path = path
        self.request_headers = headers
        self._http_method = method.decode()

        if self.debug:
            self.logger.debug("< %s %s HTTP/1.1", self._http_method, path)
            for key, value in headers.raw_items():
                self.logger.debug("< %s: %s", key, value)

        return path, headers

    async def process_request(self, path, request_headers):
        """Route HTTP requests. Overrides the parent method (not the callback)."""
        path = path.split("?")[0]  # strip query string for cache-busting support
        method = getattr(self, "_http_method", "GET")
        if path == "/ws":
            return None
        if path == "/get-log":
            auth_err = _check_admin_auth(request_headers)
            if auth_err:
                return auth_err
            body = game.log_file.read_bytes() if game.log_file.exists() else b""
            return HTTPStatus.OK, [("Content-Type", "text/plain; charset=utf-8")], body
        if path == "/clear-log":
            if method != "POST":
                return HTTPStatus.METHOD_NOT_ALLOWED, [("Allow", "POST")], b"Use POST for /clear-log"
            auth_err = _check_admin_auth(request_headers)
            if auth_err:
                return auth_err
            game.log_file.write_text("", encoding="utf-8")
            return HTTPStatus.OK, [("Content-Type", "text/plain; charset=utf-8")], b"Log cleared."
        if path == "/admin/library-stats":
            auth_err = _check_admin_auth(request_headers)
            if auth_err:
                return auth_err
            try:
                body = json.dumps(_build_library_stats(), indent=2).encode()
            except Exception as e:
                body = json.dumps({"error": str(e)}).encode()
            return HTTPStatus.OK, [("Content-Type", "application/json")], body
        if path in STATIC_FILES:
            filename, content_type = STATIC_FILES[path]
            body = (ROOT_DIR / filename).read_bytes()
            # Inject debug flag into HTML so client can auto-login
            if DEBUG_MODE and filename.endswith(".html"):
                body = body.replace(b"</head>", b"<script>window.SERVER_DEBUG=true</script></head>")
            # Support Range requests for audio seeking
            range_header = request_headers.get("Range", "")
            if range_header.startswith("bytes=") and content_type.startswith("audio/"):
                total = len(body)
                range_spec = range_header[6:]  # strip "bytes="
                start_str, _, end_str = range_spec.partition("-")
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else total - 1
                end = min(end, total - 1)
                if start > end or start >= total:
                    return HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE, [
                        ("Content-Range", f"bytes */{total}"),
                    ], b""
                chunk = body[start:end + 1]
                return HTTPStatus.PARTIAL_CONTENT, [
                    ("Content-Type", content_type),
                    ("Accept-Ranges", "bytes"),
                    ("Content-Range", f"bytes {start}-{end}/{total}"),
                    ("Content-Length", str(len(chunk))),
                ], chunk
            headers = [("Content-Type", content_type)]
            if content_type.startswith("audio/"):
                headers.append(("Accept-Ranges", "bytes"))
            return HTTPStatus.OK, headers, body
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
        create_protocol=_GameServerProtocol,
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
            create_protocol=_GameServerProtocol,
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
