"""
Content Viewer — Standalone dev tool for browsing/generating AI dungeon content.

Lightweight async HTTP server on port 8081. Serves a single-page app that can:
- Browse monster, tile, and room libraries as rendered thumbnails
- Inspect items (tags, stats, behavior, sprite data)
- Generate new rooms on demand with theme/difficulty controls
- Delete library items

Usage: python content_viewer.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Load .env file if present
_env_path = _PROJECT_ROOT / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

from server import ai_generator
from server.content_library import ContentLibrary, LibraryEntry

# ---------------------------------------------------------------------------
# Server log capture — ring buffer that the frontend can poll
# ---------------------------------------------------------------------------

import builtins
import time as _time
import traceback as _traceback
from collections import deque

_log_buffer: deque[dict] = deque(maxlen=200)
_log_id = 0
_real_print = builtins.print


def _add_log(level: str, msg: str):
    global _log_id
    _log_id += 1
    _log_buffer.append({
        "id": _log_id,
        "ts": _time.time(),
        "level": level,
        "msg": msg.rstrip(),
    })


def server_log(msg: str, level: str = "info"):
    """Log a message to both console and the web log buffer."""
    _add_log(level, msg)
    _real_print(msg)  # bypasses _patched_print, no double-log


def _patched_print(*args, **kwargs):
    """Intercept all print() calls and tee them to the log buffer."""
    # Determine if this is going to stderr
    file = kwargs.get("file", None)
    level = "error" if file is sys.stderr or file is sys.__stderr__ else "info"
    # Build the message the same way print would
    sep = kwargs.get("sep", " ")
    msg = sep.join(str(a) for a in args)
    if msg.strip():
        _add_log(level, msg)
    # Call real print
    _real_print(*args, **kwargs)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = 8081
DATA_DIR = Path(__file__).parent.parent / "data"
PROJECT_ROOT = Path(__file__).parent.parent

from server.content_library import (
    MONSTER_LIBRARY_CAPACITY, TILE_LIBRARY_CAPACITY, ROOM_LIBRARY_CAPACITY,
)

MONSTER_CAPACITY = MONSTER_LIBRARY_CAPACITY
TILE_CAPACITY = TILE_LIBRARY_CAPACITY
ROOM_CAPACITY = ROOM_LIBRARY_CAPACITY

# ---------------------------------------------------------------------------
# Libraries — aliases to game.monster_library / tile_library / room_library
# ---------------------------------------------------------------------------

from server.state import game

generate_lock = asyncio.Lock()


def load_libraries():
    from server.dungeon_content import load_precreated_content
    from server.rooms import load_dungeon_templates

    # Initialize libraries on the shared GameState singleton
    game.monster_library = ContentLibrary("monster", MONSTER_CAPACITY)
    game.tile_library = ContentLibrary("tile", TILE_CAPACITY)
    game.room_library = ContentLibrary("room", ROOM_CAPACITY)

    # Load dungeon templates (needed for room library entries)
    load_dungeon_templates()

    # Add permanent precreated content first
    load_precreated_content(game.monster_library, game.tile_library, game.room_library, game.dungeon_templates)

    # Then load custom entries from JSON into remaining slots
    game.monster_library.load_custom(DATA_DIR / "monster_library.json")
    game.tile_library.load_custom(DATA_DIR / "tile_library.json")
    game.room_library.load_custom(DATA_DIR / "room_library.json")


def save_libraries():
    game.monster_library.save(DATA_DIR / "monster_library.json")
    game.tile_library.save(DATA_DIR / "tile_library.json")
    game.room_library.save(DATA_DIR / "room_library.json")


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def handle_libraries():
    """Return JSON with stats + all real entries per library."""
    def lib_json(lib):
        return {
            "capacity": lib.capacity,
            "real_count": lib.real_count,
            "permanent_count": lib.permanent_count,
            "placeholder_count": lib.placeholder_count,
            "entries": [
                {
                    "id": e.id,
                    "tags": e.tags,
                    "created_at": e.created_at,
                    "data": e.data,
                    "permanent": e.permanent,
                }
                for e in lib.real_entries
            ],
        }

    # Build deprecated entries with ref counts
    dep_monsters = []
    for mid in game.deprecated_monsters:
        dep_monsters.append({
            "id": mid,
            "deprecated": True,
            "ref_count": _count_room_references(mid, "monster"),
        })

    dep_tiles = []
    for tid in game.deprecated_tiles:
        dep_tiles.append({
            "id": tid,
            "deprecated": True,
            "ref_count": _count_room_references(tid, "tile"),
        })

    result = {
        "monsters": lib_json(game.monster_library),
        "tiles": lib_json(game.tile_library),
        "rooms": lib_json(game.room_library),
    }
    result["deprecated_monsters"] = dep_monsters
    result["deprecated_tiles"] = dep_tiles

    return json.dumps(result)


async def handle_generate(body: bytes) -> tuple[str, int]:
    """Generate a new room via AI and register results into libraries."""
    try:
        async with generate_lock:
            params = json.loads(body)
            theme = params.get("theme", "dungeon")
            difficulty = int(params.get("difficulty", 5))

            # Build existing content summaries (exclude deprecated)
            existing_monsters = [
                {"kind": e.id, "tags": e.tags}
                for e in game.monster_library.real_entries
                if e.id not in game.deprecated_monsters
            ]
            existing_tiles = [
                {"id": e.id, "walkable": e.data.get("walkable", False), "tags": e.tags}
                for e in game.tile_library.real_entries
                if e.id not in game.deprecated_tiles
            ]

            existing_room_names = [
                e.data.get("name", e.id) for e in game.room_library.real_entries
            ]

            try:
                result = await ai_generator.generate_room(
                    theme=theme,
                    difficulty=difficulty,
                    existing_monsters=existing_monsters,
                    existing_tiles=existing_tiles,
                    monster_library_full=game.monster_library.is_full,
                    tile_library_full=game.tile_library.is_full,
                    existing_room_names=existing_room_names,
                    monster_library_count=game.monster_library.real_count,
                    monster_library_capacity=game.monster_library.capacity,
                    tile_library_count=game.tile_library.real_count,
                    tile_library_capacity=game.tile_library.capacity,
                )
            except Exception as e:
                tb = _traceback.format_exc()
                server_log(f"[VIEWER] Generation exception: {e}\n{tb}", "error")
                return json.dumps({"error": f"Exception: {e}"}), 500

            if result is None:
                server_log("[VIEWER] Generation returned None", "error")
                return json.dumps({"error": "Generation failed. See server log for details."}), 500

            # Register new monsters
            import time
            for m in result.get("new_monsters", []):
                entry = LibraryEntry(
                    id=m["kind"],
                    content_type="monster",
                    tags=m.get("tags", []),
                    created_at=time.time(),
                    data=m,
                )
                game.monster_library.add(entry)

            # Register new tiles
            for t in result.get("new_tiles", []):
                entry = LibraryEntry(
                    id=t["id"],
                    content_type="tile",
                    tags=t.get("tags", []),
                    created_at=time.time(),
                    data=t,
                )
                game.tile_library.add(entry)

            # Register the room itself
            room_name = result.get("name", "Unknown Room")
            room_id = room_name.lower().replace(" ", "_")
            # Deduplicate room ID
            base_id = room_id
            counter = 1
            while game.room_library.get_by_id(room_id):
                counter += 1
                room_id = f"{base_id}_{counter}"

            room_entry = LibraryEntry(
                id=room_id,
                content_type="room",
                tags=[theme, f"difficulty_{difficulty}"],
                created_at=time.time(),
                data=result,
            )
            game.room_library.add(room_entry)

            save_libraries()
            return json.dumps(result), 200
    except Exception as e:
        tb = _traceback.format_exc()
        server_log(f"[VIEWER] Unexpected error in handle_generate: {e}\n{tb}", "error")
        return json.dumps({"error": f"Unexpected error: {e}"}), 500


async def handle_generate_monster(body: bytes) -> tuple[str, int]:
    """Generate a single monster (sprite + behavior) and register it."""
    try:
        async with generate_lock:
            params = json.loads(body)
            theme = params.get("theme", "dungeon")
            difficulty = int(params.get("difficulty", 5))

            existing_monsters = [
                {"kind": e.id, "tags": e.tags}
                for e in game.monster_library.real_entries
                if e.id not in game.deprecated_monsters
            ]

            # Step 1: Generate design (kind, tags, stats, behavior)
            design = await ai_generator.generate_monster_design(
                theme, difficulty, existing_monsters)
            if design is None:
                return json.dumps({"error": "Monster design generation failed"}), 500

            # Step 2: Generate sprite
            attack_types = [a.get("type", "") for a in design.get("behavior", {}).get("attacks", [])]
            sprite_data = await ai_generator.generate_monster_sprite(
                design["kind"],
                tags=design.get("tags"),
                attack_types=attack_types,
                theme=theme,
            )
            if sprite_data and isinstance(sprite_data.get("sprite"), dict):
                design["sprite"] = sprite_data["sprite"]
            else:
                return json.dumps({"error": f"Sprite generation failed for {design['kind']}"}), 500

            # Register
            import time
            entry = LibraryEntry(
                id=design["kind"],
                content_type="monster",
                tags=design.get("tags", []),
                created_at=time.time(),
                data=design,
            )
            game.monster_library.add(entry)
            save_libraries()
            return json.dumps(design), 200
    except Exception as e:
        tb = _traceback.format_exc()
        server_log(f"[VIEWER] Monster generation error: {e}\n{tb}", "error")
        return json.dumps({"error": f"Exception: {e}"}), 500


async def handle_generate_layout(body: bytes) -> tuple[str, int]:
    """Generate just a layout using existing library content."""
    try:
        async with generate_lock:
            params = json.loads(body)
            theme = params.get("theme", "dungeon")
            difficulty = int(params.get("difficulty", 5))

            available_monsters = [
                {"kind": e.id, "tags": e.tags}
                for e in game.monster_library.real_entries
                if e.id not in game.deprecated_monsters
            ]
            available_tiles = [
                {"id": e.id, "walkable": e.data.get("walkable", False), "tags": e.tags}
                for e in game.tile_library.real_entries
                if e.id not in game.deprecated_tiles
            ]
            existing_room_names = [
                e.data.get("name", e.id) for e in game.room_library.real_entries
            ]

            layout = await ai_generator.generate_layout(
                theme=theme,
                difficulty=difficulty,
                available_tiles=available_tiles,
                available_monsters=available_monsters,
                existing_room_names=existing_room_names,
            )
            if layout is None:
                return json.dumps({"error": "Layout generation failed"}), 500

            # Wrap as a room result for the preview to work
            result = {
                "name": layout["name"],
                "tilemap": layout["tilemap"],
                "new_tiles": [],
                "new_monsters": [],
                "monster_placements": layout["monster_placements"],
            }

            # Register as a room
            import time
            room_name = layout.get("name", "Unknown Room")
            room_id = room_name.lower().replace(" ", "_")
            base_id = room_id
            counter = 1
            while game.room_library.get_by_id(room_id):
                counter += 1
                room_id = f"{base_id}_{counter}"

            room_entry = LibraryEntry(
                id=room_id,
                content_type="room",
                tags=[theme, f"difficulty_{difficulty}"],
                created_at=time.time(),
                data=result,
            )
            game.room_library.add(room_entry)
            save_libraries()
            return json.dumps(result), 200
    except Exception as e:
        tb = _traceback.format_exc()
        server_log(f"[VIEWER] Layout generation error: {e}\n{tb}", "error")
        return json.dumps({"error": f"Exception: {e}"}), 500


async def handle_generate_tiles(body: bytes) -> tuple[str, int]:
    """Generate custom tiles and register them."""
    try:
        async with generate_lock:
            params = json.loads(body)
            theme = params.get("theme", "dungeon")
            difficulty = int(params.get("difficulty", 5))
            count = int(params.get("count", 2))

            existing_tiles = [
                {"id": e.id, "walkable": e.data.get("walkable", False), "tags": e.tags}
                for e in game.tile_library.real_entries
                if e.id not in game.deprecated_tiles
            ]

            tiles = await ai_generator.generate_tiles(
                theme, difficulty, existing_tiles, count=count)
            if tiles is None:
                return json.dumps({"error": "Tile generation failed"}), 500

            import time
            for t in tiles:
                entry = LibraryEntry(
                    id=t["id"],
                    content_type="tile",
                    tags=t.get("tags", []),
                    created_at=time.time(),
                    data=t,
                )
                game.tile_library.add(entry)
            save_libraries()
            return json.dumps({"tiles": tiles}), 200
    except Exception as e:
        tb = _traceback.format_exc()
        server_log(f"[VIEWER] Tile generation error: {e}\n{tb}", "error")
        return json.dumps({"error": f"Exception: {e}"}), 500


def _count_room_references(item_id: str, item_type: str) -> int:
    """Count how many rooms in the library reference a monster kind or tile ID."""
    count = 0
    for entry in game.room_library.real_entries:
        data = entry.data
        if item_type == "monster":
            for p in data.get("monster_placements", []):
                if p["kind"] == item_id:
                    count += 1
                    break
        elif item_type == "tile":
            for row in data.get("tilemap", []):
                if item_id in row:
                    count += 1
                    break
    return count


def _cleanup_deprecated():
    """Remove any deprecated monsters/tiles that are no longer referenced."""
    for mid in list(game.deprecated_monsters):
        if _count_room_references(mid, "monster") == 0:
            game.deprecated_monsters.discard(mid)
            server_log(f"[VIEWER] Cleaned up deprecated monster '{mid}'")
    for tid in list(game.deprecated_tiles):
        if _count_room_references(tid, "tile") == 0:
            game.deprecated_tiles.discard(tid)
            server_log(f"[VIEWER] Cleaned up deprecated tile '{tid}'")


def handle_delete(lib_type: str, item_id: str):
    """Delete an item from a library.

    Monsters/tiles: deprecated if still referenced by rooms, deleted if not.
    Rooms: deleted immediately, then deprecated monsters/tiles are cleaned up.
    Permanent items cannot be deleted.
    """
    lib_map = {"monster": game.monster_library, "tile": game.tile_library, "room": game.room_library}
    lib = lib_map.get(lib_type)
    if not lib:
        return json.dumps({"error": f"Unknown library type: {lib_type}"}), 404

    entry = lib.get_by_id(item_id)
    if not entry:
        return json.dumps({"error": f"Item not found: {item_id}"}), 404
    if entry.permanent:
        return json.dumps({"error": f"Cannot delete permanent item: {item_id}"}), 403

    if lib_type in ("monster", "tile"):
        ref_count = _count_room_references(item_id, lib_type)
        deprecated_set = game.deprecated_monsters if lib_type == "monster" else game.deprecated_tiles
        lib.remove(item_id)
        if ref_count > 0:
            deprecated_set.add(item_id)
            server_log(f"[VIEWER] Deprecated {lib_type} '{item_id}' ({ref_count} room refs)")
        else:
            server_log(f"[VIEWER] Deleted {lib_type} '{item_id}'")
        save_libraries()
        return json.dumps({"ok": True, "deprecated": ref_count > 0, "ref_count": ref_count}), 200

    else:  # room
        lib.remove(item_id)
        save_libraries()
        _cleanup_deprecated()
        server_log(f"[VIEWER] Deleted room '{item_id}'")
        return json.dumps({"ok": True}), 200


def handle_usage():
    """Return API usage stats."""
    tracker = ai_generator.usage_tracker
    return json.dumps({
        "total_calls": tracker.total_calls,
        "input_tokens": tracker.total_input_tokens,
        "output_tokens": tracker.total_output_tokens,
        "estimated_cost_usd": round(tracker.estimated_cost(), 4),
        "session_calls": tracker.session_calls,
        "session_cost_usd": round(tracker.session_cost(), 4),
        "daily_calls": ai_generator.rate_limiter.daily_calls,
    })


def handle_logs(since_id: int = 0):
    """Return log entries newer than since_id."""
    snapshot = list(_log_buffer)
    entries = [e for e in snapshot if e["id"] > since_id]
    return json.dumps({"logs": entries})


def handle_get_settings():
    """Return current AI backend and model settings."""
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return json.dumps({
        "backend": ai_generator.AI_BACKEND,
        "model": ai_generator.ANTHROPIC_MODEL,
        "has_api_key": has_key,
    })


def handle_set_settings(body: bytes) -> tuple[str, int]:
    """Update AI backend and/or model settings."""
    try:
        params = json.loads(body)
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON"}), 400

    VALID_MODELS = {
        "claude-haiku-4-5-20251001",
        "claude-sonnet-4-6",
        "claude-opus-4-6",
    }
    VALID_BACKENDS = {"cli", "api"}

    model = params.get("model")
    backend = params.get("backend")

    if model and model not in VALID_MODELS:
        return json.dumps({"error": f"Unknown model: {model}"}), 400
    if backend and backend not in VALID_BACKENDS:
        return json.dumps({"error": f"Unknown backend: {backend}"}), 400

    if backend == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
        return json.dumps({"error": "Cannot use API backend — no ANTHROPIC_API_KEY set"}), 400

    if model:
        ai_generator.ANTHROPIC_MODEL = model
        server_log(f"[VIEWER] Model changed to {model}")
    if backend:
        ai_generator.AI_BACKEND = backend
        label = "CLI (subscription)" if backend == "cli" else "API (paid)"
        server_log(f"[VIEWER] Backend changed to {label}")

    return json.dumps({"ok": True, "model": ai_generator.ANTHROPIC_MODEL, "backend": ai_generator.AI_BACKEND}), 200


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------

STATIC_FILES = {
    "/tiles.js": ("client/tiles.js", "application/javascript"),
    "/sprites.js": ("client/sprites.js", "application/javascript"),
    "/sprite_data.js": ("client/sprite_data.js", "application/javascript"),
}

CONTENT_TYPES = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
}


def serve_file(path: str):
    """Read and return a static file."""
    if path in STATIC_FILES:
        filename, ctype = STATIC_FILES[path]
        filepath = PROJECT_ROOT / filename
    elif path == "/" or path == "":
        filepath = Path(__file__).parent / "content_viewer.html"
        ctype = "text/html"
    else:
        return None, None

    if filepath.exists():
        return filepath.read_bytes(), ctype
    return None, None


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

async def handle_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    """Minimal HTTP/1.1 request handler."""
    try:
        # Read request line
        request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not request_line:
            writer.close()
            return

        request_line = request_line.decode("utf-8", errors="replace").strip()
        parts = request_line.split(" ")
        if len(parts) < 2:
            writer.close()
            return

        method = parts[0]
        path = parts[1]

        # Read headers
        content_length = 0
        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                break
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())

        # Read body if present
        body = b""
        if content_length > 0:
            body = await asyncio.wait_for(reader.readexactly(content_length), timeout=10.0)

        # Route dispatch
        status = 200
        content_type = "application/json"
        response_body = b""

        if method == "GET" and (path == "/" or path in STATIC_FILES):
            data, ctype = serve_file(path)
            if data:
                content_type = ctype
                response_body = data
            else:
                status = 404
                response_body = b"Not Found"
                content_type = "text/plain"

        elif method == "GET" and path == "/api/libraries":
            response_body = handle_libraries().encode("utf-8")

        elif method == "GET" and path == "/api/usage":
            response_body = handle_usage().encode("utf-8")

        elif method == "GET" and path == "/api/settings":
            response_body = handle_get_settings().encode("utf-8")

        elif method == "POST" and path == "/api/settings":
            result, status = handle_set_settings(body)
            response_body = result.encode("utf-8")

        elif method == "GET" and path.startswith("/api/logs"):
            # Parse ?since=N query param
            since_id = 0
            if "?" in path:
                from urllib.parse import parse_qs, urlparse
                qs = parse_qs(urlparse(path).query)
                since_id = int(qs.get("since", [0])[0])
            response_body = handle_logs(since_id).encode("utf-8")

        elif method == "POST" and path == "/api/generate":
            result, status = await handle_generate(body)
            response_body = result.encode("utf-8")

        elif method == "POST" and path == "/api/generate/layout":
            result, status = await handle_generate_layout(body)
            response_body = result.encode("utf-8")

        elif method == "POST" and path == "/api/generate/monster":
            result, status = await handle_generate_monster(body)
            response_body = result.encode("utf-8")

        elif method == "POST" and path == "/api/generate/tiles":
            result, status = await handle_generate_tiles(body)
            response_body = result.encode("utf-8")

        elif method == "DELETE" and path.startswith("/api/"):
            # Parse /api/{type}/{id}
            api_parts = path[5:].split("/", 1)
            if len(api_parts) == 2:
                lib_type, item_id = api_parts
                # URL-decode the item_id
                from urllib.parse import unquote
                item_id = unquote(item_id)
                result, status = handle_delete(lib_type, item_id)
                response_body = result.encode("utf-8")
            else:
                status = 400
                response_body = b'{"error": "Bad request"}'

        elif method == "OPTIONS":
            status = 204
            response_body = b""
            content_type = "text/plain"

        else:
            status = 404
            response_body = b'{"error": "Not found"}'

        # Build response
        status_text = {200: "OK", 204: "No Content", 400: "Bad Request", 404: "Not Found", 500: "Internal Server Error"}.get(status, "OK")
        header = (
            f"HTTP/1.1 {status} {status_text}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(response_body)}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"Access-Control-Allow-Methods: GET, POST, DELETE, OPTIONS\r\n"
            f"Access-Control-Allow-Headers: Content-Type\r\n"
            f"Connection: close\r\n"
            f"\r\n"
        )
        writer.write(header.encode("utf-8"))
        writer.write(response_body)
        await writer.drain()

    except Exception as e:
        print(f"[VIEWER] Request error: {e}")
    finally:
        writer.close()


async def main():
    builtins.print = _patched_print
    load_libraries()
    ai_generator.init()

    print(f"Content Viewer starting on http://localhost:{PORT}")
    print(f"  Monster library: {game.monster_library.real_count}/{game.monster_library.capacity}")
    print(f"  Tile library:    {game.tile_library.real_count}/{game.tile_library.capacity}")
    print(f"  Room library:    {game.room_library.real_count}/{game.room_library.capacity}")

    backend = ai_generator.AI_BACKEND
    if backend == "cli":
        print(f"  Backend: CLI (uses your Claude subscription)")
    else:
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        print(f"  Backend: API ({'key set' if has_key else 'NO KEY — generation disabled'})")
    print()

    server = await asyncio.start_server(handle_request, "127.0.0.1", PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
