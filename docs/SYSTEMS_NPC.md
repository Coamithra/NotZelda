# NPC Systems

Detailed implementation notes for NPC chat, prompt tuning, gifts, guards, and quests.

## Chat & AI Backends

- **NPC chat backends**: `AI_BACKEND` supports `cli` (Claude CLI, default), `api` (Anthropic API), or `ollama` (local Ollama). Ollama uses native `/api/chat` endpoint (not `/v1`) with explicit `num_ctx` to avoid silent truncation. Default model: `gemma2:2b` (overridable via `OLLAMA_MODEL` env var). Hetzner production runs `gemma2:2b` on Ollama with `OLLAMA_NUM_PARALLEL=2` for multi-player cache slots.
- **NPC chat has a server-wide hourly budget** (`NPC_CHATS_PER_HOUR` in `npc_chat.py`, skipped for Ollama). When exhausted, NPCs fall back to static dialog. The system prompt is split into static (per-NPC, cached) and dynamic (per-player) parts for API prompt caching. Cooldown starts from NPC response time, not player message time.
- **NPC conversation seeding**: on the first LLM call for a player-NPC pair, `handle_npc_chat()` seeds the conversation with a synthetic `(approaches)` user message and the NPC's static `dialog` as an assistant message. This gives the AI context for what it already said via proximity greeting (e.g. "You look healthy!"). The synthetic pair follows `user → assistant` ordering so the Anthropic API accepts it.
- **NPC response cleanup**: server strips emojis, `*action*` text, and trailing incomplete sentences. Truncates at last sentence boundary within 200 chars. Raw model output logged to `event_log.txt` as `NPC_RAW` and printed to sidelog for debugging.

## Visual Feedback

- **NPC listening icon**: `renderNpcListening()` in `renderer.js` draws a small floating speech-bubble icon (three dots, bob + alpha pulse) above NPCs when the player is within Manhattan distance 2.25 (matching server's `find_adjacent_npc` range). Pure client-side — computed per frame from `G.player.displayX/Y` and `G.room.guards`. Hides when speech/thinking bubbles are active, or during death/item pickup.
- **NPC thinking bubble**: server sends `npc_thinking` message when LLM call starts. Client shows animated `...` bubble above the NPC, clears when the response arrives. One bubble per NPC max.

## Prompt Tuning

- **Forced-choice classification**: the system prompt requires Gemma to start every reply with a classification tag: `[FRIENDLY]`, `[NEUTRAL]`, `[ANGRY]`, or `[GIVE_ITEM]`. This "classify then respond" approach dramatically outperforms instruction-based approaches ("don't do X unless Y") for 2B models. See `docs/REPORT_NPC_PROMPT_TUNING.md` for the full iterative testing report.
- **Prompt tuning tips**: small models (gemma2:2b) are sensitive to prompt wording. Keep NPC personalities short. Avoid words like "gruff" or "stern" - the model reads them as hostile. Avoid negative framing ("do NOT do X") - it increases the unwanted behavior. Use positive framing and few-shot examples instead. Adding too many classification tiers (e.g. ANNOYED vs FURIOUS) confuses the model - keep choices to 3-4 with clear semantic gaps.
- **NPC situation context**: `_build_situation_context()` in `npc_chat.py` injects dynamic situational awareness into every NPC's AI prompt — equipment status (armed/unarmed), alive monsters in the room, and player kill history. Built per-call from `player.flags`, `player.quests`, and `game.room_monsters`. Uses `server/prompts/npc_situation_context.txt` template. Conditional details (e.g. "tell them about the Smith") go here, not in the personality, to avoid contradicting the situation context.
- **NPC debug chatlog**: in DEBUG_MODE, every NPC LLM call dumps the full system prompt + conversation history to `guard.txt` (appended). Useful for prompt tuning.

## Gifts & Guards

- **NPC gifts**: defined in `.room` files (`| Gift Name:condition`). Server-side effects keyed by display name in `GIFT_EFFECTS` dict in `npc_chat.py`. Tags like `[GIVE_ITEM]` and `[ANGRY]` are extracted from AI output *before* response cleanup (emoji/action stripping, truncation).
- **NPC guard summoning — consecutive-angry filter**: guards are only summoned after `ANGRY_STREAK_THRESHOLD` (default 2) consecutive `[ANGRY]` responses from the same NPC to the same player. This server-side filter reduces false positives without adding prompt tokens. Tracked per `(player, npc)` pair in `_angry_streak` dict, resets on any non-angry response. Gift giving (`[GIVE_ITEM]`) has no consecutive filter — occasional lucky gifts are fine.
- **NPC greeting overrides**: `set_npc_greeting(npc_name, room_id, fn)` in `npc_chat.py` registers a callable `fn(player, guard) -> str` that replaces the static room-file dialog. Evaluated fresh on each approach, so live game state (slime respawns, etc.) is always reflected. `handle_quest_npc` checks overrides before falling back to static dialog. The override dialog is also used to seed LLM conversation history.
- **NPC proximity dialog — once per visit**: NPCs speak their proximity dialog line once per player per room visit (tracked in `player.guard_greeted` set, cleared on room transition). `reset_npc_greeting_for_player(player, npc_name, room_id)` in `npc_chat.py` resets the tracker for a specific NPC when quest code changes the dialog text, so the new line triggers on next approach.

## Quest Events

- **Quest event system**: `quest_event(event_type, player, msgs, **kwargs)` in `quests.py` — synchronous event emitter called from tick code. Quest handlers register via `@on_event(event_type, quest_id, **filters)` decorator with kwarg matching. All one-off quest logic lives in `quests.py`; emitters in game code stay generic (one line each). Current events: `monster_killed` (from `commands.py`), `room_enter` (from `lifecycle.py`). NPC proximity handlers (`@npc_handler`) remain separate.
