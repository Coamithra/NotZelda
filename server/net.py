"""Network helpers — send/broadcast messages, player queries."""

import asyncio
import json

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
    """Return all players whose current room matches — regardless of avatar state."""
    return [p for p in game.players.values() if p.room == room_id and p.ws != exclude]


def avatars_in_room(room_id: str, exclude=None):
    """Return (player, avatar) tuples for players physically present in a room.

    Use this for combat targeting, collision checks, and anything that requires
    the character to be physically in the world.  Avatar is guaranteed non-None.
    """
    return [(p, p.avatar) for p in game.players.values()
            if p.avatar is not None and p.room == room_id and p.ws != exclude]


def player_info(p) -> dict:
    """Build the wire-format dict for a player (requires avatar)."""
    a = p.avatar
    info = {
        "name": p.name,
        "x": a.x,
        "y": a.y,
        "direction": a.direction,
        "color_index": p.color_index,
    }
    if a.dancing:
        info["dancing"] = True
    return info


_debug_tasks = set()  # prevent GC of fire-and-forget debug sends


async def _safe_debug_send(player, msg):
    """send_to wrapper that swallows all exceptions for fire-and-forget use."""
    try:
        await send_to(player, msg)
    except Exception:
        pass


def broadcast_debug(text: str):
    """Send a debug_log message to all connected players (fire-and-forget).

    Safe to call from synchronous code — schedules sends on the event loop.
    """
    msg = {"type": "debug_log", "text": text}
    for p in list(game.players.values()):
        task = asyncio.ensure_future(_safe_debug_send(p, msg))
        _debug_tasks.add(task)
        task.add_done_callback(_debug_tasks.discard)


