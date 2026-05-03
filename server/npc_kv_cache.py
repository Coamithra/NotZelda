"""NPC KV-cache slot save/restore against llama-server.

For NPCs whose static system prompt is large (and identical across all players +
turns), we can persist the prefilled KV cache to disk via llama-server's
slot API and restore it before each chat. The dynamic part of the system
prompt + conversation history are processed normally on top of the cached
prefix — only the per-NPC static portion's prefill is skipped.

Workflow:
  1. First time we see (room_id, npc_name): send a one-token chat completion
     containing just the static prompt + a placeholder user turn. This causes
     llama-server to prefill the static system prompt into slot 0.
  2. POST /slots/0?action=save&filename=npc_<key>.bin to persist that KV state.
  3. On every subsequent chat for this NPC: POST /slots/0?action=restore&...
     before sending the chat completion. The completion's prompt prefix
     matches the restored KV, so prefill skips the static portion.

Server prerequisite: llama-server must be launched with `--slot-save-path
/var/lib/llama-cache` (set by the systemd unit shipped in deploy/).

This is wired only for the two NPCs in ENABLED_KEYS — keep the spike scope
narrow so we can measure cold-vs-warm latency without instrumenting everything.
"""

import asyncio
import os
import re

from server import log

LLAMACPP_BASE_URL = os.environ.get("LLAMACPP_BASE_URL", "http://localhost:8080/v1")
LLAMACPP_MODEL = os.environ.get("LLAMACPP_MODEL", "gemma-2-2b-it-Q4_K_M")

# (room_id, npc_name) pairs that should use disk-backed KV-cache slot saves.
# Spike scope: just the two NPCs we care about for the test.
ENABLED_KEYS: set[tuple[str, str]] = {
    ("town_square", "Guard"),
    ("blacksmith", "Smith"),
}

# Set on first warmup; survives until process restart. Membership = on-disk save exists.
_warmed: set[tuple[str, str]] = set()
# Tracks which key's KV is currently in slot 0, so we can skip redundant restores.
_active_slot: tuple[str, str] | None = None
# One global lock — slot 0 is shared across all chat requests under --parallel 1.
# Callers must hold this for both `prepare()` and the chat completion that
# follows, so a concurrent chat can't restore a different NPC's KV mid-flight.
slot_lock = asyncio.Lock()


def is_enabled(room_id: str, npc_name: str) -> bool:
    return (room_id, npc_name) in ENABLED_KEYS


def _slot_filename(room_id: str, npc_name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{room_id}_{npc_name}")
    return f"npc_{safe}.bin"


def _native_base() -> str:
    """Strip /v1 so we can reach native /slots and /completion endpoints."""
    base = LLAMACPP_BASE_URL.rstrip("/")
    return base[:-3] if base.endswith("/v1") else base


async def _post(url: str, *, params: dict | None = None, json: dict | None = None,
                timeout: float = 60.0):
    """Fire-and-await a POST to llama-server using httpx (transitively present via openai SDK)."""
    import httpx
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, params=params, json=json)
        r.raise_for_status()
        return r


async def warmup_and_save(static_prompt: str, room_id: str, npc_name: str) -> bool:
    """Prefill `static_prompt` into slot 0, then save the slot to disk.

    Returns True if the on-disk save now exists (whether we just made it or it
    was already there). Idempotent.
    """
    global _active_slot
    key = (room_id, npc_name)
    if not is_enabled(room_id, npc_name):
        return False
    if key in _warmed:
        return True

    base_v1 = LLAMACPP_BASE_URL.rstrip("/")
    base_native = _native_base()
    filename = _slot_filename(room_id, npc_name)

    body = {
        "model": LLAMACPP_MODEL,
        "messages": [
            {"role": "system", "content": static_prompt},
            {"role": "user", "content": "."},
        ],
        "max_tokens": 1,
        "cache_prompt": True,
    }
    try:
        await _post(f"{base_v1}/chat/completions", json=body, timeout=180.0)
        # llama-server's /slots/{id} endpoint splits the request: `action` is
        # read from query params (req.get_param), `filename` is read from the
        # JSON body. Either one missing returns 400/500.
        await _post(
            f"{base_native}/slots/0",
            params={"action": "save"},
            json={"filename": filename},
            timeout=30.0,
        )
        _warmed.add(key)
        _active_slot = key
        log.event("NPC_KV", f"warmup+save {npc_name}@{room_id} -> {filename}")
        return True
    except Exception as e:
        log.debug(f"[NPC_KV] warmup_and_save failed for {npc_name}@{room_id}: "
                  f"{type(e).__name__}: {e}")
        return False


async def restore(room_id: str, npc_name: str) -> str:
    """Restore this NPC's saved KV into slot 0. Returns one of:
       'warm'    — slot 0 already had this NPC's KV (no-op)
       'restore' — actually pulled the file from disk
       'miss'    — file isn't on disk yet (caller should warmup_and_save instead)
       'off'     — disabled for this NPC
       'fail'    — restore HTTP call errored
    """
    global _active_slot
    key = (room_id, npc_name)
    if not is_enabled(room_id, npc_name):
        return "off"
    if key not in _warmed:
        return "miss"
    if _active_slot == key:
        return "warm"

    base_native = _native_base()
    filename = _slot_filename(room_id, npc_name)
    try:
        await _post(
            f"{base_native}/slots/0",
            params={"action": "restore"},
            json={"filename": filename},
            timeout=10.0,
        )
        _active_slot = key
        return "restore"
    except Exception as e:
        log.debug(f"[NPC_KV] restore failed for {npc_name}@{room_id}: "
                  f"{type(e).__name__}: {e}")
        return "fail"


async def prepare(static_prompt: str, room_id: str, npc_name: str) -> str:
    """Make slot 0 ready for a chat completion targeting this NPC.

    Caller MUST already hold `slot_lock`. Returns one of:
       'off'     — disabled for this NPC
       'warm'    — slot 0 already had this NPC's KV (no-op)
       'restore' — pulled the saved file from disk
       'warmup'  — first time we've seen this NPC; did the prefill + save
       'fail'    — HTTP/restore error; chat will run cold
    """
    if not is_enabled(room_id, npc_name):
        return "off"
    status = await restore(room_id, npc_name)
    if status == "miss":
        ok = await warmup_and_save(static_prompt, room_id, npc_name)
        status = "warmup" if ok else "fail"
    return status
