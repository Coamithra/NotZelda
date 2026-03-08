"""Network helpers — send/broadcast messages, player queries, event logging."""

import asyncio
import json
from datetime import datetime

import websockets

from server.state import game


async def send_to(player, msg: dict):
    try:
        await player.ws.send(json.dumps(msg))
    except websockets.ConnectionClosed:
        pass


async def broadcast_to_room(room_id: str, msg: dict, exclude=None):
    targets = [p for p in game.players.values() if p.room == room_id and p.ws != exclude]
    await asyncio.gather(*(send_to(t, msg) for t in targets))


def players_in_room(room_id: str, exclude=None):
    return [p for p in game.players.values() if p.room == room_id and p.ws != exclude]


def player_info(p) -> dict:
    info = {
        "name": p.name,
        "x": p.x,
        "y": p.y,
        "direction": p.direction,
        "color_index": p.color_index,
    }
    if p.dancing:
        info["dancing"] = True
    return info


def log_event(kind: str, text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {kind}: {text}"
    with open(game.log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")
