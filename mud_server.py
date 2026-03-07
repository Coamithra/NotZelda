"""
MUD Server — Zelda-style multiplayer online dungeon.

Run with: python mud_server.py
Then open http://localhost:8080 in your browser.
"""

import asyncio
import json
import time
from http import HTTPStatus
from pathlib import Path

import websockets

from server import behavior_engine
from server.state import game
from server.constants import (
    STAIRS_UP, STAIRS_DOWN,
    DIRECTIONS, ROOM_COLS, ROOM_ROWS,
    MOVE_COOLDOWN, HEART_RESTORE_HP, GUARD_COOLDOWN,
    STARTING_ROOM, PLAYER_MAX_HP,
)
from server.models import Player
from server.net import send_to, broadcast_to_room, players_in_room, player_info, log_event
from server.rooms import load_room_files, load_dungeon_templates
from server.lifecycle import (
    get_room_monsters, on_player_enter_room, on_player_leave_room,
    send_room_enter, do_room_transition,
)
from server.combat import damage_player, handle_attack, monster_tick, projectile_tick
from server.quests import handle_quest_npc
from server.debug_monsters import handle_debug_spawn, auto_register_debug_monsters


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


async def check_guard_proximity(player):
    """If adjacent to a guard and cooldown has passed, send guard dialog."""
    now = time.monotonic()
    for guard in game.guards.get(player.room, []):
        dx = abs(player.x - guard["x"])
        dy = abs(player.y - guard["y"])
        if dx + dy == 1:  # adjacent (not diagonal)
            key = f"{player.room}:{guard['name']}:{guard['x']},{guard['y']}"
            last = player.guard_cooldowns.get(key, 0)
            if now - last >= GUARD_COOLDOWN:
                player.guard_cooldowns[key] = now
                await handle_quest_npc(player, guard)


async def handle_move(player, direction: str):
    if player.hp <= 0:
        return
    now = time.monotonic()
    if now - player.last_move_time < MOVE_COOLDOWN:
        return
    player.last_move_time = now

    delta = DIRECTIONS.get(direction)
    if not delta:
        return
    dx, dy = delta

    player.direction = direction
    player.dancing = False
    new_x = player.x + dx
    new_y = player.y + dy

    room = game.rooms[player.room]
    tilemap = room["tilemap"]

    # Off edge — check for room exit
    if new_x < 0 or new_x >= ROOM_COLS or new_y < 0 or new_y >= ROOM_ROWS:
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
    if not game.is_walkable_tile(tile):
        # Still update facing direction
        await broadcast_to_room(player.room, {
            "type": "player_moved",
            "name": player.name,
            "x": player.x,
            "y": player.y,
            "direction": player.direction,
        })
        return

    # Guard collision — can't walk onto a guard's tile
    for guard in game.guards.get(player.room, []):
        if new_x == guard["x"] and new_y == guard["y"]:
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

    # Monster contact damage — check if player walked onto a monster
    if player.hp > 0:
        for monster in get_room_monsters(player.room):
            if monster.alive and monster.x == new_x and monster.y == new_y:
                await damage_player(player, monster.damage, player.room)
                break

    # Heart pickup
    hearts = game.room_hearts.get(player.room, [])
    for heart in hearts:
        if heart["x"] == player.x and heart["y"] == player.y and player.hp < player.max_hp:
            player.hp = min(player.max_hp, player.hp + HEART_RESTORE_HP)
            hearts.remove(heart)
            await send_to(player, {"type": "hp_update", "hp": player.hp, "max_hp": player.max_hp})
            await broadcast_to_room(player.room, {"type": "heart_collected", "id": heart["id"]})
            break

    # Guard proximity chat
    await check_guard_proximity(player)


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
        elif cmd == "debug_spawn":
            await handle_debug_spawn(player, parts[1] if len(parts) > 1 else "")
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

        await send_to(player, {"type": "login_ok", "color_index": color_index, "hp": PLAYER_MAX_HP, "max_hp": PLAYER_MAX_HP})
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
                if msg_type == "move":
                    await handle_move(player, data.get("direction", ""))
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
    "/music.mp3":         ("music/village.mp3", "audio/mpeg"),
    "/music_tavern.mp3":  ("music/tavern.mp3", "audio/mpeg"),
    "/music_chapel.mp3":  ("music/chapel.mp3", "audio/mpeg"),
    "/music_overworld.mp3": ("music/overworld.mp3", "audio/mpeg"),
    "/music_dungeon1.mp3": ("music/dungeon_a.mp3", "audio/mpeg"),
    "/music_dungeon2.mp3": ("music/dungeon_b.mp3", "audio/mpeg"),
    "/music_dungeon3.mp3": ("music/dungeon_c.mp3", "audio/mpeg"),
    "/music_dungeon4.mp3": ("music/dungeon_d.mp3", "audio/mpeg"),
    "/music_dungeon5.mp3": ("music/dungeon_e.mp3", "audio/mpeg"),
    "/music_dungeon6.mp3": ("music/dungeon_f.mp3", "audio/mpeg"),
    "/music_dungeon7.mp3": ("music/dungeon_g.mp3", "audio/mpeg"),
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
    load_room_files()
    load_dungeon_templates()
    auto_register_debug_monsters()
    behavior_engine.init(players_in_room, ROOM_COLS, ROOM_ROWS, game.is_walkable_tile, game.guards, game.rooms)
    port = 8080
    server = await websockets.serve(
        handle_connection, "0.0.0.0", port,
        process_request=process_request,
        ping_interval=30,
        ping_timeout=60,
    )
    asyncio.create_task(monster_tick())
    asyncio.create_task(projectile_tick())
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
