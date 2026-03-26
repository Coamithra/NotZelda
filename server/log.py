"""Unified logging — three destinations, one API.

Destinations:
    log.debug(msg)        → debug sidebar + server log file + stdout
    log.server(msg)       → server log file + stdout only (verbose)
    log.event(kind, text) → server log file + stdout (structured)

The debug sidebar is the #server-log panel shown to the right of the
playing field in debug mode.  Messages arrive as ``server_log`` WebSocket
frames — the same type the client already colour-codes by keyword.

The server log file (event_log.txt) is the persistent, verbose record.
It contains everything that appears in the debug sidebar, plus extra
verbose output that would flood the panel.

stdout goes through sys.__stdout__ (the real file descriptor) so that
_LogBroadcaster in mud_server.py never double-broadcasts lines that
this module already sent to the sidebar.
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from server.constants import DEBUG_MODE

# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

_LOG_FILE = Path(__file__).parent.parent / "event_log.txt"
_sidebar_tasks: set = set()  # prevent GC of fire-and-forget sends


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_file(line: str) -> None:
    """Append a timestamped line to the server log file."""
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _to_stdout(text: str) -> None:
    """Write to the real stdout, bypassing any wrapper."""
    out = sys.__stdout__ or sys.stdout
    out.write(text + "\n")
    out.flush()


async def _safe_send(ws, msg: str) -> None:
    try:
        await ws.send(msg)
    except Exception:
        pass


def _broadcast_sidebar(text: str) -> None:
    """Send a server_log WebSocket message to all connected players."""
    try:
        import server.state as _state
        players = _state.game.players
    except (ImportError, AttributeError):
        return
    if not players:
        return
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            return
    except RuntimeError:
        return
    msg = json.dumps({"type": "server_log", "text": text})
    for p in list(players.values()):
        try:
            task = asyncio.ensure_future(_safe_send(p.ws, msg))
            _sidebar_tasks.add(task)
            task.add_done_callback(_sidebar_tasks.discard)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def debug(msg: str) -> None:
    """Log to: debug sidebar + server log file + stdout.

    Use for operational events you want visible in the debug panel:
    connections, dungeon events, errors, warnings, milestones.
    """
    _write_file(f"[{_timestamp()}] {msg}")
    if DEBUG_MODE:
        _broadcast_sidebar(msg)
    _to_stdout(msg)


def server(msg: str) -> None:
    """Log to: server log file + stdout only.

    Use for verbose output that would flood the debug panel:
    raw LLM responses, AI generation progress, registration details.
    """
    _write_file(f"[{_timestamp()}] {msg}")
    _to_stdout(msg)


def event(kind: str, text: str) -> None:
    """Structured event → server log file + stdout.

    Written as ``[timestamp] KIND: text``.  Use for discrete lifecycle
    events: JOIN, DISCONNECT, NPC_CHAT, etc.
    """
    ts = _timestamp()
    _write_file(f"[{ts}] {kind}: {text}")
    _to_stdout(f"[{kind}] {text}")
