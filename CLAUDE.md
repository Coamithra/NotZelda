# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Legends of Amara** — a browser-based multiplayer MUD rendered as a Zelda-style top-down visual game. Players connect via browser, log in with a name/description, walk around tile-based rooms with arrow keys/WASD, and chat via speech bubbles.

For detailed module descriptions and game system documentation, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Project tracking:** [Trello — Legends of Amara](https://trello.com/b/FEqdR6QL/legends-of-amara). Bugs, features, and refactoring are tracked there.

**Contributing workflow:** See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for the step-by-step runbook for tackling any Trello card (pick up → worktree → research → design → implement → verify → review & ship). All feature work happens in git worktrees under `.trees/` — the root checkout stays on `master`.

## General Rules

When pushing to git make sure to update CLAUDE.md first!

**NEVER run `python worldgen.py` without explicit user permission.** The overworld `.room` files in `rooms/` contain hand-edited changes that worldgen will overwrite. Running it will destroy manual edits. Always warn the user that data will be lost before re-running.

**After any changes to `server/ai_generator.py`, `tools/content_viewer.py`, or `.env`, run `python tools/test_api_leak.py` to verify the Anthropic API key cannot leak into CLI subprocess calls.** The game uses the Claude CLI (subscription-based) for AI generation — the API must never be called directly. All 4 tests must pass.

**Avoid calling the Anthropic API directly unless expressly permitted by the user.** If you must call it (e.g. for testing), always set `metadata={"user_id": "claude-code"}` so the call is identifiable in the Console. Claude API docs: https://platform.claude.com/docs/en/api/overview

**All AI prompt text must live in `server/prompts/*.txt` files**, loaded at runtime via `_load_prompt()`. Never inline prompt strings in Python code. Use `{{placeholder}}` syntax for template variables.

## Directory Structure

```
├── mud_server.py          # Main entry point
├── worldgen.py            # Offline world generator (DO NOT run without permission)
├── client/                # Browser-served HTML + JS
├── server/                # Python modules imported by mud_server
│   └── prompts/           # AI prompt templates ({{placeholder}} syntax)
├── music/                 # MP3 tracks, organized by area
│   ├── overworld/         # Village, tavern, chapel, overworld tracks
│   ├── dungeon1/          # Dungeon ambient (b,d-f), boss1/2/3 + choir variants
│   └── dungeon2/          # Water temple ambient + boss tracks
├── rooms/                 # .room data files + dungeon template subdirs
│   ├── dungeon1/          # d1 (Dark Dungeon) room templates (64 + boss + treasure)
│   └── dungeon2/          # d2 (Water Temple) room templates (7 + boss + treasure)
├── data/                  # Game data files + runtime libraries
│   ├── tiles.json             # All tile definitions (loaded at startup)
│   ├── monsters.json          # All monster definitions (loaded at startup)
│   └── npc_sprites.json       # 14 NPC sprite definitions (loaded at startup)
├── tools/                 # Dev utilities (renderers, content viewer, tests)
├── docs/                  # Architecture docs, generated images, planning docs
├── deploy/                # Nginx config, redirect page
└── local_ignore/          # Local-only files (SSH keys, archives) — gitignored
```

## Key Conventions

- **Client state**: all mutable state lives on the shared `G` namespace object (`game_state.js`), organized into sub-objects: `G.conn` (connection/session), `G.player` (local player state), `G.room` (current room & entities), `G.ui` (DOM refs & screens), `G.fx` (visual effects), `G.debug` (dev tools).
- **Server state**: all mutable state lives on the `GameState` singleton (`from server.state import game`).
- **Player vs Avatar**: `Player` holds session/identity state (name, hp, quests, flags, room, color_index). `Avatar` holds physical-world state (x, y, direction, dancing, pending_collisions). Access position via `player.avatar.x` or use `avatars_in_room()` which returns `(player, avatar)` tuples. `player.avatar` is `None` during room transitions — monsters can't target avatar-less players. `player.room` stays on Player so dungeon tracking works even without an avatar.
- **Room queries**: `players_in_room(room_id)` returns all players in a room (for broadcasting, player lookup). `avatars_in_room(room_id)` returns `(player, avatar)` tuples for players with physical presence (for combat, collision, targeting).
- **All content is data-driven**: tiles, monsters, NPC sprites loaded from JSON in `data/`. No hardcoded tile IDs, sprite data, or monster stats in code. Tilemaps use 2-char string codes (`"GR"`, `"DW"`). Sprites/tiles use `[colorKey, x, y, w, h]` rect layer format everywhere.
- **All rooms loaded from `.room` files** — no hardcoded room definitions in Python.
- **AI prompt templates** are in `server/prompts/*.txt` — edit the text files directly, no Python changes needed.
- **AI generation uses Claude CLI by default** (`AI_BACKEND=cli`), not the API. The `.env` must NOT set `AI_BACKEND=api`.
- **NPC chat backends**: `AI_BACKEND` supports `cli` (Claude CLI, default), `api` (Anthropic API), or `ollama` (local Ollama). Ollama uses native `/api/chat` endpoint (not `/v1`) with explicit `num_ctx` to avoid silent truncation. Default model: `gemma2:2b` (overridable via `OLLAMA_MODEL` env var). Hetzner production runs `gemma2:2b` on Ollama with `OLLAMA_NUM_PARALLEL=2` for multi-player cache slots.
- **NPC thinking bubble**: server sends `npc_thinking` message when LLM call starts. Client shows animated `...` bubble above the NPC, clears when the response arrives. One bubble per NPC max.
- **NPC chat has a server-wide hourly budget** (`NPC_CHATS_PER_HOUR` in `npc_chat.py`, skipped for Ollama). When exhausted, NPCs fall back to static dialog. The system prompt is split into static (per-NPC, cached) and dynamic (per-player) parts for API prompt caching. Cooldown starts from NPC response time, not player message time.
- **NPC response cleanup**: server strips emojis, `*action*` text, and trailing incomplete sentences. Truncates at last sentence boundary within 200 chars. Raw model output logged to `event_log.txt` as `NPC_RAW` and printed to sidelog for debugging.
- **Boss monsters** have `"boss": True` in their stats dict. Use `monster.is_boss` — never hardcode boss checks to a specific kind. Boss sprites use `"resolution": 2` in their sprite data for higher detail density — coordinates are in a 32x32 grid instead of 16x16, and `drawMonsterSprite`/`drawMonsterDeath`/`renderCorpses` divide scale by resolution so each unit maps to the same pixel size as normal sprites.
- **Trap rooms** (lock-in): dungeon rooms with 3+ monsters have a 1/3 chance of locking doors until all monsters are defeated. Boss rooms always lock. Decided at dungeon creation time (stored in `instance.trap_cells`), applied during room resolution. Runtime lock state tracked in `game.locked_rooms`. `CD` tile = closed door. Dungeon items are hidden and non-pickable during trap lockdown.
- **Locked doors & keys**: dungeons have 0-N locked doorways (configurable via `min_locks`/`max_locks` in `DUNGEON_TYPES`). `LD` tile = locked door side, `KD` tile = keyhole door center. Key distribution uses `KeyMath/key_solver.py` constraint solver to guarantee no deadlocks regardless of player door-opening order. Keys are per-player (`player.keys`), persist across dungeon exits. Client sends `unlock_door` command when walking into LD/KD tiles. Custom room slots are assigned at dungeon creation time (not lazily) so trap room detection and key placement have full room data.
- **Monster walk state**: `WalkState` dataclass in `models.py` holds walk data (from/to positions, timing, direction). Assigned to `monster.state_data` when `state == "walking"` — access via `sd.from_x`, not `sd["from_x"]`. Other states (charging, teleporting, area) still use plain dicts.
- **DEBUG_MODE constant**: `DEBUG_MODE` in `constants.py` is evaluated at import time from `os.environ`. Use `from server.constants import DEBUG_MODE` instead of inline `os.environ.get("DEBUG_MODE", ...)` checks.
- **Guard despawn constants**: `GUARD_DESPAWN_TIMEOUT`, `GUARD_DESPAWN_DISTANCE`, `GUARD_DESPAWN_GRACE` live in `constants.py`. Use `_despawn_guards(guards, room_id, msgs)` helper in `combat.py` to kill all guards in a list.
- **Monster walk collision**: server checks collision at two points during a walk — at 50% (hitbox at the midpoint between origin and destination) and at 100% (hitbox at destination). This gives players a dodge window since the monster doesn't reach the target tile until the walk completes.
- **Monster knockback**: controlled by `monster.knockbackable` (from `"knockback"` in monster stats, defaults to `true` for non-bosses, `false` for bosses). Knockbackable monsters get pushed 1 tile in the attack direction when hit (if they survive). Every hit resets the decision timer and interrupts the current action (walk/charge/etc.), even if the monster can't be knocked back due to a wall. Client uses a separate `knockbackSlide` state (not `walkState`) for a 200ms easeOutQuad slide animation. Non-knockbackable monsters (bosses, heavy monsters) take damage but continue their behavior script uninterrupted.
- **Sword hitbox**: 1.5 tiles in the attack direction (extends 0.5 tiles back into the player's own tile), 1 tile perpendicular. This lets players hit monsters overlapping their position.
- **Player knockback slide**: `G.player.knockbackSlide` in `client.html` game loop — 200ms easeOutQuad, separate from walk interpolation. Other players and monsters each use their own `knockbackSlide` object.
- **Water mist** (d2 only): `renderWaterMist()` in `renderer.js` scales wisp count by water tile coverage (WA=1pt, SH=0.5pt, max 40). Opacity stays constant; density increases with more water.
- **Dungeon map vs compass**: map reveals room layout but does NOT show current position. Compass adds blinking yellow dot for current room.
- **Item pickup animation**: all item grants (sword, map, compass, heart) use the same `item_obtained`/`item_effect` message flow with `drawItemPickupOverlay` (golden glow + sparkles). Player is frozen during the 2.5s animation. `ITEM_DRAW_FNS` in `sprites.js` maps item_type to draw functions. Heart container uses a larger hand-crafted 18x13 sprite (`drawBigHeartSolid`) with gold container border.
- **NPC gifts**: defined in `.room` files (`| Gift Name:condition`). Server-side effects keyed by display name in `GIFT_EFFECTS` dict in `npc_chat.py`. Tags like `[GIVE_ITEM]` and `[ANGRY]` are extracted from AI output *before* response cleanup (emoji/action stripping, truncation).
- **NPC prompt tuning — forced-choice classification**: the system prompt requires Gemma to start every reply with a classification tag: `[FRIENDLY]`, `[NEUTRAL]`, `[ANGRY]`, or `[GIVE_ITEM]`. This "classify then respond" approach dramatically outperforms instruction-based approaches ("don't do X unless Y") for 2B models. See `docs/REPORT_NPC_PROMPT_TUNING.md` for the full iterative testing report.
- **NPC guard summoning — consecutive-angry filter**: guards are only summoned after `ANGRY_STREAK_THRESHOLD` (default 2) consecutive `[ANGRY]` responses from the same NPC to the same player. This server-side filter reduces false positives without adding prompt tokens. Tracked per `(player, npc)` pair in `_angry_streak` dict, resets on any non-angry response. Gift giving (`[GIVE_ITEM]`) has no consecutive filter — occasional lucky gifts are fine.
- **NPC prompt tuning tips**: small models (gemma2:2b) are very sensitive to prompt wording. Keep NPC personalities short. Avoid words like "gruff" or "stern" — the model reads them as hostile. Avoid negative framing ("do NOT do X") — it increases the unwanted behavior. Use positive framing and few-shot examples instead. Adding too many classification tiers (e.g. ANNOYED vs FURIOUS) confuses the model — keep choices to 3-4 with clear semantic gaps.
- **Logging — 3 destinations** via `server/log.py` (`from server import log`). Never use bare `print()` in server code — use the log module:
  - `log.debug(msg)` → debug sidebar + `event_log.txt` + stdout. For operational events visible in the debug panel.
  - `log.server(msg)` → `event_log.txt` + stdout only. For verbose output that would flood the sidebar (AI generation, registration details).
  - `log.event(kind, text)` → debug sidebar + `event_log.txt` + stdout. For structured lifecycle events (JOIN, DISCONNECT, NPC_CHAT, etc.). Written as `[timestamp] KIND: text`.
  - Chat window messages are a separate system (WebSocket game messages, not logging).
  - `broadcast_debug()` in `net.py` is for the canvas overlay HUD (12-line `G.debug.debugLog` buffer), not the sidebar — keep using it where needed.
  - `_LogBroadcaster` in `mud_server.py` is a safety net that catches stray `print()` from libraries/tracebacks → sidebar + file.
  - Exception: `state.py` startup prints stay as `print()` (runs before game exists). `ai_generator.py` `__main__` block stays as `print()` (standalone test).
- **Debug /viewserver**: sends full `debug_state` snapshot every tick to subscribed players (toggled via `/viewserver` chat command, debug-only). Renders semi-transparent red shapes for server-side entity positions.
- **Room geometry constants** live in `server/constants.py`: `DOORWAY_TILES`, `ALL_DOORWAY_TILES`, `bfs_reachable()`. Use `bfs_reachable()` instead of inline BFS for tile reachability checks.

## Key Gotchas

- **Client script load order matters**: `game_state.js` → `title.js` → `tiles.js` → `sprite_data.js` → `sprites.js` → `music.js` → `renderer.js` → `fx.js` → `net.js` → inline init/gameLoop → `input.js`
- **Import order** avoids circular deps: `constants` → `state` → `log` → `models` → `net` → `rooms` → `validation` → `dungeon_types` → `dungeons` → `quests` → `lifecycle` → `behavior_engine` → `commands` → `combat` → `debug_monsters` → `mud_server`. `behavior_engine` imports from `lifecycle` (for `set_monster_idle`); `combat` imports `behavior_engine`; `_apply_damage` is injected into the engine via `init()` to avoid a circular dep. Combat uses lazy imports for commands; commands imports from lifecycle.
- **Command queue**: websocket messages are never processed inline — handler appends to `player.command_queue`, drained by `game_tick()`. Only `ping` is handled directly.
- **game_tick() is synchronous** with message batching — no `await` mid-tick. Messages collected as tuples, flushed after the full tick. This prevents dungeon teardown crashes.
- **Room transitions**: player's avatar is set to `None` during `do_room_transition()`, then a new avatar is created at the spawn point. `avatars_in_room()` naturally excludes avatar-less players so monsters can't target them mid-transition. Player stays in `game.players` throughout.
- **Dungeon room resolution is synchronous** — no JIT AI generation. Custom rooms resolve from the library pool or fall back to precreated.
- **Tile properties** live in `custom_tile_recipes[tile_id]` — no separate walkability sets. `is_walkable_tile()` reads from the recipe dict.
- **`websockets` must stay at 12.0** — v16+ breaks the `process_request` API.
- **WebSocket bypasses nginx** — nginx 1.24.0 kills proxied WebSocket connections over TLS after exactly 30 seconds (affects all mobile browsers, not configurable via standard timeout directives). The client connects `wss://` directly to Python on port 8443 (TLS handled by Python's `ssl` module using the Let's Encrypt cert). nginx only serves static files on port 443.

## Running

```
python mud_server.py
```

Opens on http://localhost:8080.

## Hosting (Hetzner Cloud VPS)

- **Server:** Hetzner CX22, Ubuntu 24.04
- **IP:** `46.225.218.207`
- **Live URL:** http://46.225.218.207:8080
- **SSH:** `ssh root@46.225.218.207`
- **Code on server:** `/opt/NotZelda/` (cloned from GitHub)
- **Python venv:** `/opt/NotZelda/venv/` (websockets 12.0 pinned)
- **Systemd service:** `notzelda` — auto-starts on boot, restarts on crash
  - `systemctl status notzelda` — check status
  - `systemctl restart notzelda` — restart after changes
  - `journalctl -u notzelda -f` — tail logs
- **Ollama:** installed as systemd service (`ollama`), runs `gemma2:2b` for NPC chat (CPU-only)
  - `OLLAMA_NUM_PARALLEL=2` configured via `/etc/systemd/system/ollama.service.d/parallel.conf`
  - Model warmup fires on first player join (`warmup_ollama()`)
  - `.env` on server sets `AI_BACKEND=ollama` and `OLLAMA_MODEL=gemma2:2b`
- **Deploying updates:** `cd /opt/NotZelda && git pull && systemctl restart notzelda`

## Dependencies

- Python 3.12+
- `websockets` (12.0 — pinned, v16+ breaks the `process_request` API)
- `pyngrok` (optional, for local dev tunneling)
