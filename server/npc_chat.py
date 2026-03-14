"""NPC Chat — LLM-powered NPC conversations.

Players can talk to NPCs by sending chat messages while adjacent.
Each NPC has a personality defined in their .room file.
Conversation history is kept per (player, npc) pair in memory.
"""

import asyncio
import json
import os
import subprocess
import time
from collections import defaultdict

from server.state import game
from server.net import broadcast_to_room, log_event

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Use same backend as ai_generator
AI_BACKEND = os.environ.get("AI_BACKEND", "cli").lower()
NPC_MODEL = "claude-haiku-4-5-20251001"
NPC_TIMEOUT = 30.0          # seconds — shorter than content gen
NPC_API_TIMEOUT = 10.0      # API is faster
MAX_HISTORY = 10            # conversation turns to remember per player-NPC pair
NPC_CHAT_COOLDOWN = 3.0     # seconds between NPC chat messages per player

# ---------------------------------------------------------------------------
# Conversation history — maps (player_name, npc_name) -> list of messages
# ---------------------------------------------------------------------------

_conversations: dict[tuple[str, str], list[dict]] = defaultdict(list)
_last_chat_time: dict[str, float] = {}  # player_name -> last npc chat time

# ---------------------------------------------------------------------------
# World context (shared across all NPCs)
# ---------------------------------------------------------------------------

WORLD_CONTEXT = """\
This is a medieval fantasy world. The main settlement is a small village with a \
Town Square, Blacksmith, Tavern, Old Chapel, and Chapel Sanctum. Beyond the village \
lies a vast wilderness with forests, mountains, deserts, swamps, a lake, rivers, \
graveyards, and a ruined castle. Underneath the village clearing is a dungeon \
filled with monsters.

Princess Amara lies cursed in the Chapel Sanctum — no one knows who cursed her. \
The Priest watches over the chapel. The Smith forges weapons. The Barmaid runs the \
tavern and can heal wounds. Monsters roam the wilderness — slimes in the forests, \
scorpions in the desert, skeletons in the graveyard, and bats in the caves.

Players are adventurers who explore this world, fight monsters with swords, and \
seek to lift the curse on Princess Amara."""


def _build_system_prompt(guard: dict, room_id: str) -> str:
    """Build a system prompt for an NPC conversation."""
    room = game.rooms.get(room_id, {})
    room_name = room.get("name", room_id)
    biome = room.get("biome", "unknown")

    personality = guard.get("personality", "")
    if not personality:
        # Generic fallback based on sprite type
        personality = f"A {guard['sprite']} who lives in this area."

    return f"""\
You are {guard['name']}, an NPC in a fantasy adventure game.
You are in {room_name} ({biome} area).

Your personality: {personality}

World context:
{WORLD_CONTEXT}

Rules:
- Stay in character at ALL times. You ARE this character.
- KEEP IT VERY SHORT. One sentence, 10-15 words max. This is a tiny speech bubble in a game.
- Be colorful and interesting — give the player a reason to talk to you.
- You can hint at lore, give directions, share rumors, or be funny.
- Never break the fourth wall or mention being an AI.
- Never use quotation marks around your response.
- Never use em dashes. Use commas or periods instead.
- If asked about game mechanics, answer in-character (e.g. "swing your sword" not "press space").
- Match your speech style to your character (a farmer talks differently than a ghost)."""


# ---------------------------------------------------------------------------
# LLM call (simplified — no JSON parsing needed, just text)
# ---------------------------------------------------------------------------

async def _call_npc_llm(system_prompt: str, messages: list[dict]) -> str | None:
    """Call the LLM for NPC conversation. Returns plain text or None on failure."""
    try:
        if AI_BACKEND == "api":
            return await _call_api(system_prompt, messages)
        else:
            return await _call_cli(system_prompt, messages)
    except asyncio.TimeoutError:
        print("[NPC_CHAT] Timeout waiting for LLM response")
        return None
    except Exception as e:
        print(f"[NPC_CHAT] LLM call failed: {type(e).__name__}: {e}")
        return None


async def _call_cli(system_prompt: str, messages: list[dict]) -> str:
    """Call the local Claude CLI for NPC chat."""
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


async def _call_api(system_prompt: str, messages: list[dict]) -> str:
    """Call the Anthropic API for NPC chat."""
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
                system=system_prompt,
                messages=messages,
                metadata={"user_id": "notzelda-npc-chat"},
            )
        ),
        timeout=NPC_API_TIMEOUT,
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def find_adjacent_npc(player) -> dict | None:
    """Find an NPC adjacent to the player (Manhattan distance 1)."""
    for guard in game.guards.get(player.room, []):
        dx = abs(player.x - guard["x"])
        dy = abs(player.y - guard["y"])
        if dx + dy <= 2:  # within 1 tile gap
            return guard
    return None


async def handle_npc_chat(player, guard: dict, text: str):
    """Handle a player chatting with an NPC via LLM.

    1. Broadcast the player's message so everyone sees it
    2. Send a 'thinking' indicator
    3. Call LLM with conversation history
    4. Broadcast the NPC's response
    """
    # Rate limit
    now = time.monotonic()
    last = _last_chat_time.get(player.name, 0)
    if now - last < NPC_CHAT_COOLDOWN:
        return
    _last_chat_time[player.name] = now

    npc_name = guard["name"]
    conv_key = (player.name, npc_name)

    # Add player message to history
    _conversations[conv_key].append({"role": "user", "content": text})

    # Trim history
    if len(_conversations[conv_key]) > MAX_HISTORY * 2:
        _conversations[conv_key] = _conversations[conv_key][-MAX_HISTORY * 2:]

    # Build system prompt
    system = _build_system_prompt(guard, player.room)

    # Call LLM
    t0 = time.monotonic()
    response = await _call_npc_llm(system, _conversations[conv_key])

    # NPCs should pause before responding (feels more natural)
    elapsed = time.monotonic() - t0
    if elapsed < 1.5:
        await asyncio.sleep(1.5 - elapsed)

    if not response:
        # Fallback to static dialog
        response = guard.get("dialog", "...")
        if not response:
            response = "..."

    # Clean up response — remove quotes, truncate
    response = response.strip('"\'')
    if len(response) > 200:
        response = response[:197] + "..."

    # Add NPC response to history
    _conversations[conv_key].append({"role": "assistant", "content": response})

    # Log and broadcast NPC response
    room_name = game.rooms.get(player.room, {}).get("name", player.room)
    log_event("NPC_CHAT", f"{npc_name} -> {player.name} ({room_name}): {response}")
    await broadcast_to_room(player.room, {
        "type": "chat",
        "from": npc_name,
        "text": response,
    })


def clear_player_history(player_name: str):
    """Clear conversation history for a player (call on disconnect)."""
    keys_to_remove = [k for k in _conversations if k[0] == player_name]
    for k in keys_to_remove:
        del _conversations[k]
    _last_chat_time.pop(player_name, None)
