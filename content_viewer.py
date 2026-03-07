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
import shutil
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load .env file if present
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

import ai_generator
from content_library import ContentLibrary, LibraryEntry

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


builtins.print = _patched_print

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = 8081
DATA_DIR = Path(__file__).parent / "data"
PROJECT_ROOT = Path(__file__).parent

MONSTER_CAPACITY = 7
TILE_CAPACITY = 12
ROOM_CAPACITY = 50

# ---------------------------------------------------------------------------
# Libraries (loaded at startup)
# ---------------------------------------------------------------------------

monster_lib: ContentLibrary | None = None
tile_lib: ContentLibrary | None = None
room_lib: ContentLibrary | None = None
generate_lock = asyncio.Lock()


def load_libraries():
    global monster_lib, tile_lib, room_lib
    monster_lib = ContentLibrary.load("monster", MONSTER_CAPACITY, DATA_DIR / "monster_library.json")
    tile_lib = ContentLibrary.load("tile", TILE_CAPACITY, DATA_DIR / "tile_library.json")
    room_lib = ContentLibrary.load("room", ROOM_CAPACITY, DATA_DIR / "room_library.json")


def save_libraries():
    monster_lib.save(DATA_DIR / "monster_library.json")
    tile_lib.save(DATA_DIR / "tile_library.json")
    room_lib.save(DATA_DIR / "room_library.json")


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def handle_libraries():
    """Return JSON with stats + all real entries per library."""
    def lib_json(lib):
        return {
            "capacity": lib.capacity,
            "real_count": lib.real_count,
            "placeholder_count": lib.placeholder_count,
            "entries": [
                {
                    "id": e.id,
                    "tags": e.tags,
                    "created_at": e.created_at,
                    "data": e.data,
                }
                for e in lib.real_entries
            ],
        }

    return json.dumps({
        "monsters": lib_json(monster_lib),
        "tiles": lib_json(tile_lib),
        "rooms": lib_json(room_lib),
    })


async def handle_generate(body: bytes):
    """Generate a new room via AI and register results into libraries."""
    async with generate_lock:
        params = json.loads(body)
        theme = params.get("theme", "dungeon")
        difficulty = int(params.get("difficulty", 5))

        # Build existing content summaries
        existing_monsters = [
            {"kind": e.id, "tags": e.tags}
            for e in monster_lib.real_entries
        ]
        existing_tiles = [
            {"id": e.id, "walkable": e.data.get("walkable", False), "tags": e.tags}
            for e in tile_lib.real_entries
        ]

        existing_room_names = [
            e.data.get("name", e.id) for e in room_lib.real_entries
        ]

        try:
            result = await ai_generator.generate_room(
                theme=theme,
                difficulty=difficulty,
                existing_monsters=existing_monsters,
                existing_tiles=existing_tiles,
                monster_library_full=monster_lib.is_full,
                tile_library_full=tile_lib.is_full,
                existing_room_names=existing_room_names,
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
            monster_lib.add(entry)

        # Register new tiles
        for t in result.get("new_tiles", []):
            entry = LibraryEntry(
                id=t["id"],
                content_type="tile",
                tags=t.get("tags", []),
                created_at=time.time(),
                data=t,
            )
            tile_lib.add(entry)

        # Register the room itself
        room_name = result.get("name", "Unknown Room")
        room_id = room_name.lower().replace(" ", "_")
        # Deduplicate room ID
        base_id = room_id
        counter = 1
        while room_lib.get_by_id(room_id):
            counter += 1
            room_id = f"{base_id}_{counter}"

        room_entry = LibraryEntry(
            id=room_id,
            content_type="room",
            tags=[theme, f"difficulty_{difficulty}"],
            created_at=time.time(),
            data=result,
        )
        room_lib.add(room_entry)

        save_libraries()
        return json.dumps(result), 200


def handle_delete(lib_type: str, item_id: str):
    """Delete an item from a library."""
    lib_map = {"monster": monster_lib, "tile": tile_lib, "room": room_lib}
    lib = lib_map.get(lib_type)
    if not lib:
        return json.dumps({"error": f"Unknown library type: {lib_type}"}), 404

    if lib.remove(item_id):
        save_libraries()
        return json.dumps({"ok": True}), 200
    else:
        return json.dumps({"error": f"Item not found: {item_id}"}), 404


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


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------

STATIC_FILES = {
    "/tiles.js": ("tiles.js", "application/javascript"),
    "/sprites.js": ("sprites.js", "application/javascript"),
    "/sprite_data.js": ("sprite_data.js", "application/javascript"),
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
        filepath = PROJECT_ROOT / "content_viewer.html"
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

        elif method == "GET" and path.startswith("/api/logs"):
            # Parse ?since=N query param
            since_id = 0
            if "?" in path:
                from urllib.parse import parse_qs, urlparse
                qs = parse_qs(urlparse(path).query)
                since_id = int(qs.get("since", [0])[0])
            response_body = handle_logs(since_id).encode("utf-8")

        elif method == "POST" and path == "/api/test-cli":
            # Quick CLI smoke test — send a trivial prompt
            import subprocess
            env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            server_log("[TEST-CLI] Starting claude CLI test...", "info")
            claude_path = shutil.which("claude")
            server_log(f"[TEST-CLI] claude location: {claude_path or 'NOT FOUND'}", "info")

            model = ai_generator.ANTHROPIC_MODEL
            server_log(f"[TEST-CLI] Running: claude -p '...' --output-format json --model {model}", "info")
            try:
                import time as _t
                t0 = _t.time()
                result = subprocess.run(
                    ["claude", "-p", "Reply with exactly one word: HELLO", "--output-format", "json", "--model", model],
                    capture_output=True, text=True, timeout=60, env=env,
                )
                elapsed = _t.time() - t0
                server_log(f"[TEST-CLI] Finished in {elapsed:.1f}s, exit code: {result.returncode}", "info")
                server_log(f"[TEST-CLI] stdout ({len(result.stdout)} chars):", "info")
                # Log in chunks so nothing gets cut off
                for i in range(0, len(result.stdout), 300):
                    server_log(f"  {result.stdout[i:i+300]}", "info")
                if result.stderr:
                    server_log(f"[TEST-CLI] stderr ({len(result.stderr)} chars):", "error")
                    for i in range(0, len(result.stderr), 300):
                        server_log(f"  {result.stderr[i:i+300]}", "error")
                response_body = json.dumps({"ok": True, "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "elapsed": round(elapsed, 1)}).encode("utf-8")
            except subprocess.TimeoutExpired:
                server_log("[TEST-CLI] TIMED OUT after 60s", "error")
                response_body = json.dumps({"ok": False, "error": "timeout after 60s"}).encode("utf-8")
                status = 500
            except Exception as e:
                server_log(f"[TEST-CLI] Exception: {e}", "error")
                response_body = json.dumps({"ok": False, "error": str(e)}).encode("utf-8")
                status = 500

        elif method == "POST" and path == "/api/generate":
            result, status = await handle_generate(body)
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
    load_libraries()
    ai_generator.init()

    print(f"Content Viewer starting on http://localhost:{PORT}")
    print(f"  Monster library: {monster_lib.real_count}/{monster_lib.capacity}")
    print(f"  Tile library:    {tile_lib.real_count}/{tile_lib.capacity}")
    print(f"  Room library:    {room_lib.real_count}/{room_lib.capacity}")

    backend = ai_generator.AI_BACKEND
    if backend == "cli":
        print(f"  Backend: CLI (uses your Claude subscription)")
    else:
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        print(f"  Backend: API ({'key set' if has_key else 'NO KEY — generation disabled'})")
    print()

    server = await asyncio.start_server(handle_request, "0.0.0.0", PORT)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
