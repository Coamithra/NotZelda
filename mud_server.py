"""
MUD Server — Zelda-style multiplayer online dungeon.

Run with: python mud_server.py
Then open http://localhost:8080 in your browser.
"""

import asyncio
import json
import html
import time
from datetime import datetime
from http import HTTPStatus
from pathlib import Path

import websockets
from websockets.http import Headers

# ---------------------------------------------------------------------------
# Tile constants
# ---------------------------------------------------------------------------

GRASS       = 0
STONE       = 1
WOOD        = 2
WALL_STONE  = 3
WALL_WOOD   = 4
WATER       = 5
TREE        = 6
FLOWERS     = 7
DIRT        = 8
STAIRS_UP   = 9
STAIRS_DOWN = 10
ANVIL       = 11
FIREPLACE   = 12
TABLE       = 13
PEW         = 14
DOOR        = 15

WALKABLE_TILES = {GRASS, STONE, WOOD, FLOWERS, DIRT, STAIRS_UP, STAIRS_DOWN, DOOR}

# Shorthand aliases for tilemap readability
G  = GRASS
S  = STONE
W  = WOOD
WS = WALL_STONE
WW = WALL_WOOD
WA = WATER
T  = TREE
FL = FLOWERS
DI = DIRT
SU = STAIRS_UP
SD = STAIRS_DOWN
AN = ANVIL
FP = FIREPLACE
TB = TABLE
PW = PEW
DR = DOOR

# ---------------------------------------------------------------------------
# World data — 15 columns x 11 rows per room
# ---------------------------------------------------------------------------

ROOMS = {
    "town_square": {
        "name": "Town Square",
        "exits": {"north": "blacksmith", "south": "forest_path", "east": "tavern", "west": "old_chapel"},
        "tilemap": [
            [WS,WS,WS,WS,WS,WS,DR,DR,DR,WS,WS,WS,WS,WS,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [DR, S, S, S, S,WA,WA,WA, S, S, S, S, S, S,DR],
            [DR, S, S, S, S,WA,WA,WA, S, S, S, S, S, S,DR],
            [DR, S, S, S, S,WA,WA,WA, S, S, S, S, S, S,DR],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS,WS,WS,WS,WS,WS,DR,DR,DR,WS,WS,WS,WS,WS,WS],
        ],
        "spawn_points": {
            "north": (7, 1), "south": (7, 9), "east": (13, 5), "west": (1, 5), "default": (7, 5),
        },
    },
    "tavern": {
        "name": "The Rusty Flagon",
        "exits": {"west": "town_square", "up": "tavern_upstairs"},
        "tilemap": [
            [WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W,SU,WW],
            [WW, W,TB, W, W, W, W, W, W, W,TB, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [DR, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [DR, W, W, W,TB, W, W, W, W,TB, W, W, W, W,WW],
            [DR, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW, W, W, W,FP,FP,FP,FP,FP, W, W, W, W, W,WW],
            [WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW],
        ],
        "spawn_points": {
            "west": (1, 5), "down": (13, 1), "default": (7, 5),
        },
    },
    "tavern_upstairs": {
        "name": "Tavern Upper Floor",
        "exits": {"down": "tavern"},
        "tilemap": [
            [WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W,SD,WW],
            [WW, W, W,WW, W, W,WW, W, W,WW, W, W, W, W,WW],
            [WW, W, W,WW, W, W,WW, W, W,WW, W, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW, W, W,WW, W, W,WW, W, W,WW, W, W, W, W,WW],
            [WW, W, W,WW, W, W,WW, W, W,WW, W, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW],
        ],
        "spawn_points": {
            "up": (13, 1), "default": (7, 5),
        },
    },
    "blacksmith": {
        "name": "The Blacksmith's Forge",
        "exits": {"south": "town_square"},
        "tilemap": [
            [WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S,FP,FP, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S,AN,AN, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S,AN,AN, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS,WS,WS,WS,WS,WS,DR,DR,DR,WS,WS,WS,WS,WS,WS],
        ],
        "spawn_points": {
            "south": (7, 9), "default": (7, 5),
        },
    },
    "forest_path": {
        "name": "Forest Path",
        "exits": {"north": "town_square", "south": "clearing"},
        "tilemap": [
            [ T, T, T, T, T, T,DR,DR,DR, T, T, T, T, T, T],
            [ T, T, G, G, G,DI,DI,DI, G, G, G, G, T, T, T],
            [ T, G, G, G,DI,DI,DI,DI,DI, G, G, G, G, T, T],
            [ T, G, G,DI,DI,DI, G,DI,DI,DI, G, G, G, G, T],
            [ T, G, G,DI,DI, G, G, G,DI,DI, G, G, G, T, T],
            [ T, G,DI,DI, G, G, G, G, G,DI,DI, G, G, G, T],
            [ T, G,DI,DI, G, G, G, G, G, G,DI, G, G, T, T],
            [ T, G, G,DI,DI, G, G, G, G,DI,DI, G, G, G, T],
            [ T, T, G, G,DI,DI,DI,DI,DI,DI, G, G, G, T, T],
            [ T, G, G, G, G,DI,DI,DI, G, G, G, G, T, T, T],
            [ T, T, T, T, T, T,DR,DR,DR, T, T, T, T, T, T],
        ],
        "spawn_points": {
            "north": (7, 1), "south": (7, 9), "default": (7, 5),
        },
    },
    "clearing": {
        "name": "Sunlit Clearing",
        "exits": {"north": "forest_path"},
        "tilemap": [
            [ T, T, T, T, T, T,DR,DR,DR, T, T, T, T, T, T],
            [ T, T, G, G, G, G, G, G, G, G, G, G, G, T, T],
            [ T, G, G,FL, G, G, G, G, G, G,FL, G, G, G, T],
            [ T, G, G, G, G,FL, G, G, G, G, G, G, G, T, T],
            [ T, G,FL, G, G, G, G, G, G,FL, G, G, G, G, T],
            [ T, G, G, G, G, G, G, G, G, G, G,FL, G, T, T],
            [ T, G, G, G,FL, G, G, G,FL, G, G, G, G, G, T],
            [ T, G,FL, G, G, G, G, G, G, G, G, G,FL, T, T],
            [ T, T, G, G, G, G,FL, G, G, G, G, G, G, T, T],
            [ T, T, T, G, G, G, G, G, G, G, G, T, T, T, T],
            [ T, T, T, T, T, T, T, T, T, T, T, T, T, T, T],
        ],
        "spawn_points": {
            "north": (7, 1), "default": (7, 5),
        },
    },
    "old_chapel": {
        "name": "Old Chapel",
        "exits": {"east": "town_square"},
        "tilemap": [
            [WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S,PW,PW, S,PW,PW, S,PW,PW, S,PW,PW, S,WS],
            [WS, S,PW,PW, S,PW,PW, S,PW,PW, S,PW,PW, S,DR],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,DR],
            [WS, S,PW,PW, S,PW,PW, S,PW,PW, S,PW,PW, S,DR],
            [WS, S,PW,PW, S,PW,PW, S,PW,PW, S,PW,PW, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS],
        ],
        "spawn_points": {
            "east": (13, 5), "default": (7, 5),
        },
    },
}

STARTING_ROOM = "town_square"

# Maps direction player walked to the direction they should enter from
ENTRY_DIR = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "up": "up",
    "down": "down",
}

MOVE_COOLDOWN = 0.125  # seconds between moves

# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

next_color_index = 0

class Player:
    def __init__(self, ws, name: str, description: str, color_index: int):
        self.ws = ws
        self.name = name
        self.description = description
        self.room = STARTING_ROOM
        self.x = 7
        self.y = 5
        self.direction = "down"
        self.color_index = color_index
        self.last_move_time = 0.0


# websocket -> Player
players: dict = {}

# Activity log — entries appended on join/leave/chat, cleared on download
event_log: list[str] = []


def log_event(kind: str, text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    event_log.append(f"[{ts}] {kind}: {text}")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def send_to(player: Player, msg: dict):
    try:
        await player.ws.send(json.dumps(msg))
    except websockets.ConnectionClosed:
        pass


async def broadcast_to_room(room_id: str, msg: dict, exclude=None):
    targets = [p for p in players.values() if p.room == room_id and p.ws != exclude]
    await asyncio.gather(*(send_to(t, msg) for t in targets))


def players_in_room(room_id: str, exclude=None):
    return [p for p in players.values() if p.room == room_id and p.ws != exclude]


def player_info(p: Player) -> dict:
    return {
        "name": p.name,
        "x": p.x,
        "y": p.y,
        "direction": p.direction,
        "color_index": p.color_index,
    }


async def send_room_enter(player: Player):
    room = ROOMS[player.room]
    others = [player_info(p) for p in players_in_room(player.room, exclude=player.ws)]
    await send_to(player, {
        "type": "room_enter",
        "room_id": player.room,
        "name": room["name"],
        "tilemap": room["tilemap"],
        "your_pos": {"x": player.x, "y": player.y},
        "players": others,
    })

# ---------------------------------------------------------------------------
# Movement & room transitions
# ---------------------------------------------------------------------------

async def do_room_transition(player: Player, exit_direction: str):
    old_room = player.room
    new_room_id = ROOMS[old_room]["exits"][exit_direction]
    new_room = ROOMS[new_room_id]

    # Broadcast departure
    await broadcast_to_room(old_room, {"type": "player_left", "name": player.name}, exclude=player.ws)

    # Move player
    player.room = new_room_id
    entry = ENTRY_DIR.get(exit_direction, "default")
    spawn = new_room["spawn_points"].get(entry, new_room["spawn_points"]["default"])
    player.x, player.y = spawn

    # Send new room to player
    await send_room_enter(player)

    # Broadcast arrival
    await broadcast_to_room(
        new_room_id,
        {"type": "player_entered", **player_info(player)},
        exclude=player.ws,
    )


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


async def handle_move(player: Player, direction: str):
    now = time.monotonic()
    if now - player.last_move_time < MOVE_COOLDOWN:
        return
    player.last_move_time = now

    dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}.get(direction, (0, 0))
    if dx == 0 and dy == 0:
        return

    player.direction = direction
    new_x = player.x + dx
    new_y = player.y + dy

    room = ROOMS[player.room]
    tilemap = room["tilemap"]

    # Off edge — check for room exit
    if new_x < 0 or new_x >= 15 or new_y < 0 or new_y >= 11:
        exit_dir = check_edge_exit(player, new_x, new_y, room)
        if exit_dir:
            await do_room_transition(player, exit_dir)
        else:
            # Broadcast facing change only
            await broadcast_to_room(player.room, {
                "type": "player_moved",
                "name": player.name,
                "x": player.x,
                "y": player.y,
                "direction": player.direction,
            })
        return

    tile = tilemap[new_y][new_x]

    # Stairs trigger
    if tile == STAIRS_UP and "up" in room["exits"]:
        await do_room_transition(player, "up")
        return
    if tile == STAIRS_DOWN and "down" in room["exits"]:
        await do_room_transition(player, "down")
        return

    # Walkability check
    if tile not in WALKABLE_TILES:
        # Still update facing direction
        await broadcast_to_room(player.room, {
            "type": "player_moved",
            "name": player.name,
            "x": player.x,
            "y": player.y,
            "direction": player.direction,
        })
        return

    player.x = new_x
    player.y = new_y

    await broadcast_to_room(player.room, {
        "type": "player_moved",
        "name": player.name,
        "x": player.x,
        "y": player.y,
        "direction": player.direction,
    })

# ---------------------------------------------------------------------------
# Chat commands (typed in chat bar)
# ---------------------------------------------------------------------------

async def handle_chat(player: Player, text: str):
    text = text.strip()
    if not text:
        return

    # Slash commands
    if text.startswith("/"):
        parts = text[1:].split(None, 1)
        cmd = parts[0].lower() if parts else ""
        if cmd == "who":
            lines = ["Players online:"]
            for p in players.values():
                room_name = ROOMS[p.room]["name"]
                lines.append(f"  {p.name} — {p.description} (in {room_name})")
            await send_to(player, {"type": "info", "text": "\n".join(lines)})
        elif cmd == "help":
            await send_to(player, {"type": "info", "text": (
                "Arrow keys / WASD — Move\n"
                "Enter — Open chat\n"
                "Escape — Close chat\n"
                "M — Toggle music\n"
                "/who — List online players\n"
                "/help — Show this message"
            )})
        elif cmd == "me":
            action = parts[1] if len(parts) > 1 else ""
            if action:
                await broadcast_to_room(player.room, {
                    "type": "chat", "from": player.name, "text": f"*{action}*",
                })
        else:
            await send_to(player, {"type": "info", "text": "Unknown command. Try /help"})
        return

    # Normal chat — broadcast to room
    room_name = ROOMS[player.room]["name"]
    log_event("CHAT", f"{player.name} ({room_name}): {text}")
    await broadcast_to_room(player.room, {
        "type": "chat",
        "from": player.name,
        "text": text,
    })

# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------

async def handle_connection(websocket):
    global next_color_index
    player = None
    try:
        raw = await websocket.recv()
        data = json.loads(raw)
        if data.get("type") != "login":
            return

        name = html.escape(data.get("name", "").strip()[:20])
        desc = html.escape(data.get("description", "").strip()[:80])

        if not name:
            await websocket.send(json.dumps({"type": "error", "text": "Name cannot be empty."}))
            return

        if any(p.name.lower() == name.lower() for p in players.values()):
            await websocket.send(json.dumps({"type": "error", "text": "That name is already taken."}))
            return

        color_index = next_color_index
        next_color_index = (next_color_index + 1) % 6

        player = Player(websocket, name, desc or "A mysterious stranger.", color_index)
        spawn = ROOMS[STARTING_ROOM]["spawn_points"]["default"]
        player.x, player.y = spawn
        players[websocket] = player
        log_event("JOIN", f"{name} ({player.description})")

        await send_to(player, {"type": "login_ok", "color_index": color_index})
        await send_room_enter(player)
        await broadcast_to_room(
            player.room,
            {"type": "player_entered", **player_info(player)},
            exclude=websocket,
        )

        async for raw in websocket:
            data = json.loads(raw)
            msg_type = data.get("type")
            if msg_type == "move":
                await handle_move(player, data.get("direction", ""))
            elif msg_type == "chat":
                await handle_chat(player, data.get("text", ""))

    except websockets.ConnectionClosed:
        pass
    finally:
        if player and websocket in players:
            del players[websocket]
            log_event("LEAVE", player.name)
            await broadcast_to_room(
                player.room,
                {"type": "player_left", "name": player.name},
            )

# ---------------------------------------------------------------------------
# HTTP server for client.html
# ---------------------------------------------------------------------------

CLIENT_DIR = Path(__file__).parent

# Static files that the client can request
STATIC_FILES = {
    "/":            ("client.html", "text/html; charset=utf-8"),
    "/index.html":  ("client.html", "text/html; charset=utf-8"),
    "/sprites.js":  ("sprites.js",  "application/javascript; charset=utf-8"),
    "/tiles.js":    ("tiles.js",    "application/javascript; charset=utf-8"),
    "/music.js":    ("music.js",    "application/javascript; charset=utf-8"),
    "/music.mp3":         ("not zelda.mp3",          "audio/mpeg"),
    "/music_forest.mp3":  ("not zelda (forest).mp3", "audio/mpeg"),
}


async def process_request(path, request_headers):
    if path == "/ws":
        return None
    if path == "/get-log":
        lines = event_log.copy()
        event_log.clear()
        body = "\n".join(lines).encode()
        return HTTPStatus.OK, [("Content-Type", "text/plain; charset=utf-8")], body
    if path in STATIC_FILES:
        filename, content_type = STATIC_FILES[path]
        body = (CLIENT_DIR / filename).read_bytes()
        return HTTPStatus.OK, [("Content-Type", content_type)], body
    return HTTPStatus.NOT_FOUND, [], b"Not Found"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    port = 8080
    server = await websockets.serve(
        handle_connection, "0.0.0.0", port,
        process_request=process_request,
    )
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
