"""NPC Chat — LLM-powered NPC conversations.

Players can talk to NPCs by sending chat messages while adjacent.
Each NPC has a personality defined in their .room file.
Conversation history is kept per (player, npc) pair in memory.
"""

import asyncio
import json
import os
import random
import re
import subprocess
import time
import urllib.request
import urllib.error
from collections import defaultdict

from pathlib import Path

from server.state import game
from server.constants import (
    DEBUG_MODE,
    NPC_RESPONSE_DELAY, NPC_MAX_RESPONSE_LENGTH, NPC_DETECTION_DISTANCE,
    GUARD_SPAWN_COUNT_MIN, GUARD_SPAWN_COUNT_MAX,
)
from server.net import broadcast_to_room, avatars_in_room, send_to
from server import log

# ---------------------------------------------------------------------------
# Prompt loading — templates live in server/prompts/*.txt
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(filename: str, **kwargs: str) -> str:
    """Load a prompt template, replacing {{key}} placeholders."""
    text = (_PROMPTS_DIR / filename).read_text(encoding="utf-8").strip()
    for key, value in kwargs.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Backend: "cli" (Claude CLI), "api" (Anthropic API), "ollama" (local Ollama)
AI_BACKEND = os.environ.get("AI_BACKEND", "cli").lower()
NPC_MODEL = "claude-haiku-4-5-20251001"
NPC_TIMEOUT = 30.0          # seconds — shorter than content gen
NPC_API_TIMEOUT = 10.0      # API is faster
MAX_HISTORY = 10            # conversation turns to remember per player-NPC pair
NPC_CHAT_COOLDOWN = 3.0     # seconds between NPC chat messages per player
GUARD_SUMMON_COOLDOWN = 60.0  # seconds between guard summons per room
NPC_CHATS_PER_HOUR = 150    # server-wide hourly LLM call budget (ignored for ollama)

# Ollama configuration — uses native /api/chat (NOT /v1) to support num_ctx.
# See learnings/ollama-considerations.md for why this matters.
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "gemma2:2b")
OLLAMA_TIMEOUT = 45.0       # seconds — CPU-only inference on CX22 is slow
OLLAMA_NUM_CTX = 1024       # smaller = faster prompt eval on CPU (CX22)
OLLAMA_NUM_PREDICT = 80     # ~200 chars max output; caps CPU inference time


def warmup_ollama():
    """Fire-and-forget request to preload the Ollama model into memory.

    Called on first player join so the model is warm when someone talks to an NPC.
    """
    if AI_BACKEND != "ollama":
        return
    def _ping():
        try:
            payload = json.dumps({
                "model": OLLAMA_MODEL,
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
                "keep_alive": -1,
                "options": {"num_predict": 1},
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
            log.debug("[NPC_CHAT] Ollama model warmed up")
        except Exception as e:
            log.debug(f"[NPC_CHAT] Ollama warmup failed: {e}")
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _ping)



# ---------------------------------------------------------------------------
# NPC gift item effects — server-side logic keyed by display name.
# Gift definitions (display_name, condition) are data-driven from .room files.
# The gift tracking flag is auto-generated as gift_{room}_{npc}_{item}.
# "flag" below is the *gameplay* flag (checked by combat, input, etc).
# ---------------------------------------------------------------------------

GIFT_EFFECTS = {
    "Sword": {"effect": "sword", "flag": "has_sword"},
    "Barmaid's Heart Container": {"effect": "heart"},
    "Ghost's Spirit Jar": {"effect": "spirit_jar", "flag": "has_spirit_jar"},
    "Hermit's Spirit Jar": {"effect": "spirit_jar", "flag": "has_spirit_jar"},
    # Items without an entry here get a generic "You obtained X!" message.
}

# ---------------------------------------------------------------------------
# Conversation history — maps (player_name, npc_name) -> list of messages
# ---------------------------------------------------------------------------

_conversations: dict[tuple[str, str], list[dict]] = defaultdict(list)
_last_chat_time: dict[str, float] = {}  # player_name -> last npc chat time
_last_guard_summon: dict[str, float] = {}  # room_id -> last summon time
_angry_streak: dict[tuple[str, str], int] = defaultdict(int)  # (player, npc) -> consecutive angry count
_active_npc_calls: set[tuple[str, str]] = set()  # (player, npc) — NPC is thinking for this player
_last_proximity_dialog: dict[tuple[str, str], str] = {}  # (player, npc) -> last proximity dialog text
_npc_greeting_overrides: dict[tuple[str, str], object] = {}  # (npc_name, room_id) -> callable(player, guard) -> str
ANGRY_STREAK_THRESHOLD = 2  # require N consecutive [ANGRY] before summoning guards


def set_npc_greeting(npc_name: str, room_id: str, fn):
    """Register a dynamic greeting function for an NPC.

    ``fn(player, guard) -> str`` is called each time the NPC is approached.
    This lets quest logic override the static room-file dialog based on
    current game state (e.g. slime alive/dead, player has sword).
    """
    _npc_greeting_overrides[(npc_name, room_id)] = fn


def reset_npc_greeting_for_player(player, npc_name: str, room_id: str):
    """Reset a player's greeting tracker for a specific NPC so the next
    proximity approach triggers dialog again.  Call this from quest code
    when an NPC's greeting text changes (e.g. after quest state advance).
    """
    guards = game.guards.get(room_id, [])
    for guard in guards:
        if guard["name"] == npc_name:
            key = f"{room_id}:{npc_name}:{guard['x']},{guard['y']}"
            player.guard_greeted.discard(key)


def get_npc_greeting(npc_name: str, room_id: str, player, guard) -> str | None:
    """Get the dynamic greeting for an NPC, or None to use the default."""
    fn = _npc_greeting_overrides.get((npc_name, room_id))
    if fn:
        return fn(player, guard)
    return None


def is_npc_thinking(player_name: str, npc_name: str) -> bool:
    """Check if an NPC is currently processing an LLM response for this player."""
    return (player_name, npc_name) in _active_npc_calls


# ---------------------------------------------------------------------------
# Server-wide hourly budget tracking
# ---------------------------------------------------------------------------

_hourly_chat_count = 0
_hourly_reset_time = 0.0  # monotonic — resets every hour

# ---------------------------------------------------------------------------
# Town guard monster — spawned when NPCs call for help
# ---------------------------------------------------------------------------

TOWN_GUARD_MONSTER = {
    "kind": "town_guard",
    "stats": {"hp": 3, "walk_time": 0.25, "decision_time": 1.67, "damage": 2},
    "behavior": {"rules": [
        {"if": "player_within", "range": 6, "do": "move", "direction": "player"},
        {"if": "always", "do": "move", "direction": "random"},
    ]},
    "sprite": {
        "colors": {
            "helmet": "#8090a0", "helmet_dark": "#606e7a", "armor": "#9aa8b8",
            "skin": "#e8c898", "eyes": "#222222", "pants": "#3a4a8a", "boots": "#3a2a1a",
        },
        "yOff": [0, -1],
        "frames": [
            [
                ["helmet",      4, 0, 8, 2],
                ["helmet_dark", 4, 2, 8, 1],
                ["skin",        5, 3, 6, 3],
                ["eyes",        6, 3, 1, 1],
                ["eyes",        9, 3, 1, 1],
                ["armor",       4, 6, 8, 5],
                ["armor",       3, 6, 1, 4],
                ["armor",      12, 6, 1, 4],
                ["skin",        3,10, 1, 1],
                ["skin",       12,10, 1, 1],
                ["pants",       5,11, 6, 2],
                ["boots",       5,13, 2, 2],
                ["boots",       9,13, 2, 2],
            ],
            [
                ["helmet",      4, 0, 8, 2],
                ["helmet_dark", 4, 2, 8, 1],
                ["skin",        5, 2, 6, 3],
                ["eyes",        6, 2, 1, 1],
                ["eyes",        9, 2, 1, 1],
                ["armor",       4, 5, 8, 5],
                ["armor",       3, 5, 1, 4],
                ["armor",      12, 5, 1, 4],
                ["skin",        3, 9, 1, 1],
                ["skin",       12, 9, 1, 1],
                ["pants",       5,10, 6, 2],
                ["boots",       5,12, 2, 2],
                ["boots",       9,12, 2, 2],
            ],
        ],
    },
    "death_sprite": {
        "colors": {"clr": "#9aa8b8"},
        "frames": [
            [["clr", 3, 11, 10, 3], ["clr", 5, 10, 6, 1]],
            [["clr", 1, 12, 3, 2], ["clr", 5, 13, 2, 1], ["clr", 8, 11, 3, 2], ["clr", 12, 13, 3, 1]],
            {"alpha": 0.4, "layers": [["clr", 0, 13, 2, 1], ["clr", 6, 14, 2, 1], ["clr", 13, 13, 2, 1]]},
        ],
    },
}


def register_town_guard():
    """Register the town_guard monster type at startup."""
    from server.validation import register_monster_type
    ok, errors = register_monster_type(TOWN_GUARD_MONSTER)
    if ok:
        game.builtin_monster_ids.add("town_guard")
        log.debug("[CONTENT] Registered monster type: town_guard")
    else:
        log.debug(f"[CONTENT] WARNING: Failed to register town_guard: {errors}")

# ---------------------------------------------------------------------------
# World context (shared across all NPCs)
# ---------------------------------------------------------------------------

def _build_situation_context(guard: dict, room_id: str, player) -> str:
    """Build situational context lines for an NPC's AI prompt.

    Checks room state (alive monsters) and player state (flags, quests) to give
    the NPC awareness of what's happening around them.
    """
    lines = []

    # Equipment awareness
    if player.has_flag("has_sword"):
        lines.append("The adventurer carries a sword.")
    else:
        lines.append("The adventurer is unarmed. You should tell them to visit the Smith in town for a weapon.")

    # Room monster awareness — build conditionally to avoid contradictions
    room_monsters = game.room_monsters.get(room_id, [])
    killed_clearing_slime = (player.has_flag("clearing_slime_killed")
                             and room_id == "clearing")
    for m in room_monsters:
        if m.alive:
            # Skip slime line if this player already killed it (it respawned)
            if killed_clearing_slime and m.kind == "slime":
                continue
            # Clarify monster type for small models
            lines.append(f"There is a monster (a {m.kind}) lurking nearby. You keep a nervous eye on it.")

    if killed_clearing_slime:
        lines.append("This adventurer slew the slime monster that once lurked here. You are grateful and impressed.")
    elif room_monsters and all(not m.alive for m in room_monsters):
        lines.append("The monsters that lurked here have been slain.")

    return "\n".join(lines)


def _build_system_prompt(guard: dict, room_id: str, player_name: str, player_desc: str,
                         player_flags: set | None = None,
                         situation_context: str = "") -> tuple[str, str]:
    """Build a system prompt for NPC conversation.

    Returns (static_prompt, dynamic_prompt) — split for prompt caching.
    The static part is per-NPC (cacheable across all players talking to this NPC).
    The dynamic part is per-player (small, changes per conversation).
    """
    room = game.rooms.get(room_id, {})
    room_name = room.get("name", room_id)
    biome = room.get("biome", "unknown")

    personality = guard.get("personality", "")
    if not personality:
        personality = f"A {guard['sprite']} who lives in this area."

    world_context = _load_prompt("npc_world_context.txt")
    static = _load_prompt("npc_system_static.txt",
                          npc_name=guard['name'],
                          room_name=room_name,
                          biome=biome,
                          personality=personality,
                          world_context=world_context)

    # Dynamic part — player-specific context (kept small to preserve cache hits)
    gift_section = ""
    gift = guard.get("gift")
    if gift:
        prompt_name = "a " + gift["display_name"].lower()
        # Check the gift tracking flag (and gameplay flag for non-stackable items)
        already_has = bool(player_flags and gift["flag"] in player_flags)
        if not already_has and player_flags:
            effect_info = GIFT_EFFECTS.get(gift["display_name"], {})
            gameplay_flag = effect_info.get("flag") if isinstance(effect_info, dict) else None
            # Spirit jars are stackable — don't block based on gameplay flag
            if gameplay_flag and gameplay_flag != "has_spirit_jar" and gameplay_flag in player_flags:
                already_has = True
        if already_has:
            gift_section = "\n\n" + _load_prompt("npc_gift_already_given.txt",
                                                  item_name=prompt_name)
        else:
            gift_section = "\n\n" + _load_prompt("npc_gift_available.txt",
                                                  item_name=prompt_name,
                                                  condition=gift["condition"])

    dynamic = _load_prompt("npc_system_dynamic.txt",
                           player_name=player_name,
                           player_desc=player_desc) + gift_section

    if situation_context:
        dynamic += "\n\n" + _load_prompt("npc_situation_context.txt",
                                          situation_lines=situation_context)

    return static, dynamic


# ---------------------------------------------------------------------------
# LLM call (simplified — no JSON parsing needed, just text)
# ---------------------------------------------------------------------------

async def _call_npc_llm(static_prompt: str, dynamic_prompt: str,
                        messages: list[dict]) -> str | None:
    """Call the LLM for NPC conversation. Returns plain text or None on failure."""
    backend = AI_BACKEND if AI_BACKEND in ("ollama", "api") else "cli"
    model = OLLAMA_MODEL if backend == "ollama" else NPC_MODEL
    try:
        if backend == "ollama":
            return await _call_ollama(static_prompt, dynamic_prompt, messages)
        elif backend == "api":
            return await _call_api(static_prompt, dynamic_prompt, messages)
        else:
            return await _call_cli(static_prompt, dynamic_prompt, messages)
    except asyncio.TimeoutError:
        log.debug("[NPC_CHAT] Timeout waiting for LLM response")
        return None
    except Exception as e:
        log.debug(f"[NPC_CHAT] LLM call failed: {type(e).__name__}: {e}")
        return None


async def _call_cli(static_prompt: str, dynamic_prompt: str,
                    messages: list[dict]) -> str:
    """Call the local Claude CLI for NPC chat."""
    # CLI doesn't support prompt caching — concatenate both parts
    system_prompt = static_prompt + "\n\n" + dynamic_prompt

    # Build a conversation prompt from history
    parts = [system_prompt, ""]
    for msg in messages:
        role = "Player" if msg["role"] == "user" else "You"
        parts.append(f"{role}: {msg['content']}")

    combined = "\n".join(parts)
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY")}

    proc = await asyncio.wait_for(
        asyncio.get_running_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                ["claude", "-p", combined, "--output-format", "json",
                 "--model", NPC_MODEL],
                capture_output=True, text=True, encoding="utf-8",
                timeout=int(NPC_TIMEOUT), env=env,
            )
        ),
        timeout=NPC_TIMEOUT + 5,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"Claude CLI exited {proc.returncode}: {proc.stderr[:300]}")

    # Parse CLI JSON output
    try:
        cli_output = json.loads(proc.stdout)
        text = cli_output.get("result", proc.stdout)
    except json.JSONDecodeError:
        text = proc.stdout

    return text.strip()


async def _call_api(static_prompt: str, dynamic_prompt: str,
                    messages: list[dict]) -> str:
    """Call the Anthropic API for NPC chat with prompt caching.

    The system prompt is split into two blocks:
    - Static (NPC identity, personality, world, rules) — marked for caching
      so it's reused across all players talking to the same NPC.
    - Dynamic (player name, description, gift status) — small, uncached,
      changes per player without invalidating the cached prefix.

    Note: Haiku requires ~2048 tokens in the cached prefix for caching to
    activate. Shorter prompts are sent correctly but may not get cache hits.
    """
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    client = anthropic.Anthropic(api_key=api_key)
    response = await asyncio.wait_for(
        asyncio.get_running_loop().run_in_executor(
            None,
            lambda: client.messages.create(
                model=NPC_MODEL,
                max_tokens=100,
                system=[
                    {
                        "type": "text",
                        "text": static_prompt,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": dynamic_prompt,
                    },
                ],
                messages=messages,
                metadata={"user_id": "notzelda-npc-chat"},
            )
        ),
        timeout=NPC_API_TIMEOUT,
    )
    return response.content[0].text.strip()


async def _call_ollama(static_prompt: str, dynamic_prompt: str,
                       messages: list[dict]) -> str:
    """Call a local Ollama instance for NPC chat.

    Uses the native /api/chat endpoint (NOT /v1/chat/completions) because
    the OpenAI-compatible endpoint silently ignores num_ctx, which causes
    Ollama to fall back to a VRAM-based default (often 4k or less).
    """
    system_prompt = static_prompt + "\n\n" + dynamic_prompt

    # Build messages list with system prompt first
    ollama_messages = [{"role": "system", "content": system_prompt}]
    ollama_messages.extend(messages)

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": ollama_messages,
        "stream": False,
        "keep_alive": -1,
        "options": {
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": OLLAMA_NUM_PREDICT,
        },
    }).encode("utf-8")

    def _do_request():
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))

    result = await asyncio.wait_for(
        asyncio.get_running_loop().run_in_executor(None, _do_request),
        timeout=OLLAMA_TIMEOUT + 5,
    )

    text = result.get("message", {}).get("content", "")
    return text.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_adjacent_npc(room_id, avatar) -> dict | None:
    """Find an NPC adjacent to the avatar (Manhattan distance, float-aware)."""
    if avatar is None:
        return None
    for guard in game.guards.get(room_id, []):
        dx = abs(avatar.x - guard["x"])
        dy = abs(avatar.y - guard["y"])
        if dx + dy <= NPC_DETECTION_DISTANCE:
            return guard
    return None


async def handle_npc_chat(player, guard: dict, text: str):
    """Handle a player chatting with an NPC via LLM.

    1. Broadcast the player's message so everyone sees it
    2. Send a 'thinking' indicator
    3. Call LLM with conversation history
    4. Broadcast the NPC's response
    """
    global _hourly_chat_count, _hourly_reset_time

    # Rate limit — cooldown starts from when NPC last responded
    now = time.monotonic()
    last = _last_chat_time.get(player.name, 0)
    if now - last < NPC_CHAT_COOLDOWN:
        return
    _last_chat_time[player.name] = now  # prevent dupes during LLM call

    npc_name = guard["name"]
    conv_key = (player.name, npc_name)

    # Don't start a new LLM call if this NPC is already thinking for this player
    if conv_key in _active_npc_calls:
        return

    # --- Server-wide hourly budget (skipped for ollama — it's free) ---
    if AI_BACKEND != "ollama":
        if now - _hourly_reset_time >= 3600:
            _hourly_chat_count = 0
            _hourly_reset_time = now

        if _hourly_chat_count >= NPC_CHATS_PER_HOUR:
            # Budget exhausted — fall back to static dialog
            response = guard.get("dialog") or "..."
            log.event("NPC_CHAT", f"BUDGET — {npc_name} used static dialog for {player.name}")
            await asyncio.sleep(1.0)
            _last_chat_time[player.name] = time.monotonic()
            await broadcast_to_room(player.room, {
                "type": "chat",
                "from": npc_name,
                "text": response,
            })
            return

        _hourly_chat_count += 1

    # Seed conversation with NPC's proximity greeting so the AI knows what it said.
    # Use the stored dynamic dialog if available (from quest handlers), fall back to static.
    if not _conversations[conv_key]:
        greeting = _last_proximity_dialog.pop(conv_key, "") or guard.get("dialog", "")
        if greeting:
            _conversations[conv_key].append({"role": "user", "content": "(approaches)"})
            _conversations[conv_key].append({"role": "assistant", "content": greeting})

    # Add player message to history
    _conversations[conv_key].append({"role": "user", "content": text})

    # Trim history
    if len(_conversations[conv_key]) > MAX_HISTORY * 2:
        _conversations[conv_key] = _conversations[conv_key][-MAX_HISTORY * 2:]

    # Build system prompt (split for caching — static is per-NPC, dynamic is per-player)
    situation = _build_situation_context(guard, player.room, player)
    static_prompt, dynamic_prompt = _build_system_prompt(
        guard, player.room, player.name,
        player.description or "a wandering adventurer",
        player.flags,
        situation_context=situation)

    # Dump full chatlog to guard.txt for debugging (debug mode only)
    if DEBUG_MODE:
        try:
            system_prompt = static_prompt + "\n\n" + dynamic_prompt
            with open("guard.txt", "a", encoding="utf-8") as gf:
                gf.write(f"\n{'='*60}\n")
                gf.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {npc_name} -> {player.name}\n")
                gf.write(f"{'='*60}\n\n")
                gf.write(f"--- SYSTEM ---\n{system_prompt}\n\n")
                for msg in _conversations[conv_key]:
                    role = "USER" if msg["role"] == "user" else "ASSISTANT"
                    gf.write(f"--- {role} ---\n{msg['content']}\n\n")
        except Exception:
            pass

    # Show thinking indicator to all players in the room
    _active_npc_calls.add(conv_key)
    await broadcast_to_room(player.room, {
        "type": "npc_thinking", "name": npc_name,
    })

    # Call LLM — wrapped in try/finally to guarantee thinking bubble cleanup.
    # handle_npc_chat runs via ensure_future, so uncaught exceptions are silent.
    response = None
    try:
        t0 = time.monotonic()
        response = await _call_npc_llm(static_prompt, dynamic_prompt,
                                       _conversations[conv_key])

        # NPCs should pause before responding (feels more natural)
        elapsed = time.monotonic() - t0
        if elapsed < NPC_RESPONSE_DELAY:
            await asyncio.sleep(NPC_RESPONSE_DELAY - elapsed)
    except Exception as e:
        log.debug(f"[NPC_CHAT] LLM call failed for {npc_name}: {type(e).__name__}: {e}")

    try:
        if not response:
            # Fallback to static dialog
            response = guard.get("dialog", "...")
            if not response:
                response = "..."

        # Clean up response — remove quotes, truncate
        raw_response = response  # keep original for debug log
        response = response.strip('"\'')

        # Check for special tags before cleanup — forced-choice classification tags
        is_angry = "[ANGRY]" in response
        give_item = "[GIVE_ITEM]" in response

        # Consecutive-angry filter: only summon guards after N angry responses in a row
        if is_angry:
            _angry_streak[conv_key] += 1
            summon_guards = _angry_streak[conv_key] >= ANGRY_STREAK_THRESHOLD
        else:
            _angry_streak[conv_key] = 0
            summon_guards = False

        # Also support legacy [CALL_GUARDS] tag (e.g. from CLI/API backends)
        if "[CALL_GUARDS]" in response:
            summon_guards = True

        # Strip all classification tags from the response
        response = re.sub(r'\[(FRIENDLY|NEUTRAL|ANGRY|CALL_GUARDS|GIVE_ITEM)\]', '', response).strip()

        # Strip emojis and *actions* — small models love these
        response = re.sub(r'\*[^*]+\*', '', response)  # *winks*, *laughs*, etc.
        response = re.sub(
            r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF'
            r'\U0001F900-\U0001F9FF\U00002702-\U000027B0\U0000FE00-\U0000FE0F'
            r'\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF'
            r'\U0000200D\U00002B50]+', '', response)
        response = re.sub(r'\s{2,}', ' ', response).strip()

        # Trim trailing incomplete sentence (small models hard-stop at token limit)
        if response and response[-1] not in '.!?':
            last_sentence = max(response.rfind('.'), response.rfind('!'), response.rfind('?'))
            if last_sentence > 20:  # only if we keep a reasonable chunk
                response = response[:last_sentence + 1]

        if len(response) > NPC_MAX_RESPONSE_LENGTH:
            # Truncate at last sentence boundary, fall back to hard cut
            truncated = response[:NPC_MAX_RESPONSE_LENGTH]
            last_sentence = max(truncated.rfind('.'), truncated.rfind('!'), truncated.rfind('?'))
            if last_sentence > 40:
                response = truncated[:last_sentence + 1]
            else:
                response = response[:NPC_MAX_RESPONSE_LENGTH - 3] + "..."

        # Add NPC response to history (without tags)
        _conversations[conv_key].append({"role": "assistant", "content": response})

        # Cooldown starts from when the NPC finishes responding
        _last_chat_time[player.name] = time.monotonic()

        # Log and broadcast NPC response
        room_name = game.rooms.get(player.room, {}).get("name", player.room)
        _backend = AI_BACKEND if AI_BACKEND in ("ollama", "api") else "cli"
        _model = OLLAMA_MODEL if _backend == "ollama" else NPC_MODEL
        log.event("NPC_CHAT", f"[{_backend}:{_model}] {npc_name} -> {player.name} ({room_name}): {response}")
        if raw_response != response:
            log.event("NPC_RAW", f"{npc_name}: {raw_response}")
        # Print raw response to sidelog (encode-safe for Windows cp1252 console)
        safe_raw = raw_response.encode("ascii", errors="replace").decode("ascii")
        log.server(f"[NPC_RAW] [{_backend}:{_model}] {npc_name}: {safe_raw}")
        await broadcast_to_room(player.room, {
            "type": "chat",
            "from": npc_name,
            "text": response,
        })

        # Spawn guards if the NPC called for them
        if summon_guards:
            await _spawn_summoned_guards(player.room, guard["x"], guard["y"], npc_name, player.name)

        # Grant item if the NPC decided to give one
        if give_item:
            await _grant_npc_gift(player, guard)
    except Exception as e:
        log.debug(f"[NPC_CHAT] Response processing failed for {npc_name}: {type(e).__name__}: {e}")
    finally:
        _active_npc_calls.discard(conv_key)


async def _grant_npc_gift(player, guard: dict):
    """Grant an NPC's special item to the player (gift defined in .room file)."""
    gift = guard.get("gift")
    if not gift:
        return
    flag = gift["flag"]  # auto-generated gift tracking flag
    if player.has_flag(flag):
        return  # Already received this NPC's gift

    display_name = gift["display_name"]
    effect_info = GIFT_EFFECTS.get(display_name, {})
    effect = effect_info.get("effect") if isinstance(effect_info, dict) else None
    gameplay_flag = effect_info.get("flag") if isinstance(effect_info, dict) else None

    # Check gameplay flag too (player may have gotten the item another way)
    # Spirit jars are stackable — skip this block for them
    if gameplay_flag and gameplay_flag != "has_spirit_jar" and player.has_flag(gameplay_flag):
        player.grant_flag(flag)  # Mark gift as given so NPC won't try again
        return

    player.grant_flag(flag)
    if gameplay_flag == "has_spirit_jar":
        player.spirit_jar_count += 1
    elif gameplay_flag:
        player.grant_flag(gameplay_flag)
    log.event("NPC_GIFT", f"{guard['name']} gave {display_name} to {player.name}")

    if effect in ("sword", "heart", "spirit_jar"):
        # Use item pickup animation (golden glow + sparkles + hold pose)
        await send_to(player, {"type": "item_obtained", "item_type": effect, "item_name": display_name})
        await broadcast_to_room(player.room, {
            "type": "item_effect", "item_type": effect, "name": player.name,
        }, exclude=player.ws)
    else:
        # Generic item obtained message
        item_key = display_name.lower().replace(" ", "_")
        await send_to(player, {
            "type": "item_obtained",
            "item": item_key,
            "name": display_name,
        })

    if effect == "heart":
        # +1 heart (2 HP), heal to new max
        player.max_hp += 2
        player.hp = player.max_hp
        await send_to(player, {
            "type": "hp_update",
            "hp": player.hp,
            "max_hp": player.max_hp,
        })


async def _spawn_summoned_guards(room_id: str, npc_x: int, npc_y: int, npc_name: str, target_player: str):
    """Spawn 3-5 town guard monsters near an NPC who called for help."""
    from server.constants import ROOM_COLS, ROOM_ROWS
    from server.models import Monster

    # Cooldown — don't spam guards
    now = time.monotonic()
    last = _last_guard_summon.get(room_id, 0)
    if now - last < GUARD_SUMMON_COOLDOWN:
        return
    _last_guard_summon[room_id] = now

    # Don't spawn if there are already summoned guards in this room
    existing = game.room_monsters.get(room_id, [])
    if any(m.kind == "town_guard" and m.alive for m in existing):
        return

    room = game.rooms.get(room_id)
    if not room:
        return
    tilemap = room["tilemap"]
    guards = game.guards.get(room_id, [])
    player_positions = {(a.x, a.y) for _p, a in avatars_in_room(room_id)}

    # Find walkable tiles near the NPC (expanding Manhattan distance rings)
    candidates = []
    for dist in range(1, 6):
        for dx in range(-dist, dist + 1):
            for dy in range(-dist, dist + 1):
                if abs(dx) + abs(dy) != dist:
                    continue
                nx, ny = npc_x + dx, npc_y + dy
                if 0 <= nx < ROOM_COLS and 0 <= ny < ROOM_ROWS:
                    if game.is_walkable_tile(tilemap[ny][nx]):
                        if not any(g["x"] == nx and g["y"] == ny for g in guards):
                            if (nx, ny) not in player_positions:
                                candidates.append((nx, ny))

    if not candidates:
        return

    count = random.randint(GUARD_SPAWN_COUNT_MIN, GUARD_SPAWN_COUNT_MAX)
    random.shuffle(candidates)
    spawn_points = candidates[:count]

    if room_id not in game.room_monsters:
        game.room_monsters[room_id] = []
    monster_list = game.room_monsters[room_id]

    log.event("GUARD_SUMMON", f"{npc_name} called {len(spawn_points)} guards in {room_id}")
    log.debug(f"[GUARDS] {npc_name} summoned {len(spawn_points)} town guards in {room_id}")

    for sx, sy in spawn_points:
        monster = Monster(sx, sy, "town_guard")
        monster.last_action_time = time.monotonic()
        monster._guard_spawn_time = time.monotonic()
        monster._guard_target = target_player
        monster_id = len(monster_list)
        monster_list.append(monster)

        spawn_msg = {
            "type": "monster_spawned",
            "id": monster_id,
            "kind": "town_guard",
            "x": sx,
            "y": sy,
        }
        if "town_guard" in game.custom_sprites:
            spawn_msg["custom_sprites"] = {"town_guard": game.custom_sprites["town_guard"]}
        if "town_guard" in game.custom_death_sprites:
            spawn_msg["custom_death_sprites"] = {"town_guard": game.custom_death_sprites["town_guard"]}

        await broadcast_to_room(room_id, spawn_msg)


def clear_player_history(player_name: str):
    """Clear conversation history for a player (call on disconnect)."""
    keys_to_remove = [k for k in _conversations if k[0] == player_name]
    for k in keys_to_remove:
        del _conversations[k]
    streak_keys = [k for k in _angry_streak if k[0] == player_name]
    for k in streak_keys:
        del _angry_streak[k]
    _active_npc_calls.difference_update(
        {k for k in _active_npc_calls if k[0] == player_name})
    _last_chat_time.pop(player_name, None)
