# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Legends of Amara** — a browser-based multiplayer MUD rendered as a Zelda-style top-down visual game. Players connect via browser, log in with a name/description, walk around tile-based rooms with arrow keys/WASD, and chat via speech bubbles.

For detailed module descriptions and game system documentation, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Project tracking:** [Trello — Legends of Amara](https://trello.com/b/FEqdR6QL/legends-of-amara). Bugs, features, and refactoring are tracked there. Use the `trello` CLI (installed from `C:\Programming\TrelloCLI`) for card operations — `trello cards <list>`, `trello card <id>`, `trello move <id> <list>`, `trello comment <id> <text>`, etc. Config in `~/.trello-cli.json`.

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
- **Debug-only exits**: room file exits support a `:debug[:replacement_tile]` suffix (e.g. `down=d1_entrance:debug:GR`). In release mode the exit is skipped and associated stair tiles (SD/SU) are replaced with the specified tile (default GR). Used to keep shortcut dungeon entrances in the starting area during development.
- **Dungeon entrance locations**: d1 (Dark Dungeon) entrance is in the Shattered Armory (`ow_7_9.room`, castle area). d2 (Water Temple) entrance is in the Sinking Marsh (`ow_5_12.room`, swamp area). Debug-only shortcuts exist in the Sunlit Clearing (d1) and Forest Path (d2).
- **Castle area**: 4x4 grid of overworld rooms (rows 7-10, cols 6-9). Maze-like connectivity — the west and east halves connect only through ow_8_7↔ow_8_8 (row 8) and ow_9_7↔ow_9_8 (row 9). The Shattered Armory (dungeon entrance) has no direct horizontal connection to other row-7 rooms; players must navigate through the lower castle to reach it. All castle rooms use `castle_ruins` music.
- **AI prompt templates** are in `server/prompts/*.txt` — edit the text files directly, no Python changes needed.
- **AI generation uses Claude CLI by default** (`AI_BACKEND=cli`), not the API. The `.env` must NOT set `AI_BACKEND=api`.
- **NPC chat backends**: `AI_BACKEND` supports `cli` (Claude CLI, default), `api` (Anthropic API), or `ollama` (local Ollama). Ollama uses native `/api/chat` endpoint (not `/v1`) with explicit `num_ctx` to avoid silent truncation. Default model: `gemma2:2b` (overridable via `OLLAMA_MODEL` env var). Hetzner production runs `gemma2:2b` on Ollama with `OLLAMA_NUM_PARALLEL=2` for multi-player cache slots.
- **NPC listening icon**: `renderNpcListening()` in `renderer.js` draws a small floating speech-bubble icon (three dots, bob + alpha pulse) above NPCs when the player is within Manhattan distance 2.25 (matching server's `find_adjacent_npc` range). Pure client-side — computed per frame from `G.player.displayX/Y` and `G.room.guards`. Hides when speech/thinking bubbles are active, or during death/item pickup.
- **NPC thinking bubble**: server sends `npc_thinking` message when LLM call starts. Client shows animated `...` bubble above the NPC, clears when the response arrives. One bubble per NPC max.
- **NPC chat has a server-wide hourly budget** (`NPC_CHATS_PER_HOUR` in `npc_chat.py`, skipped for Ollama). When exhausted, NPCs fall back to static dialog. The system prompt is split into static (per-NPC, cached) and dynamic (per-player) parts for API prompt caching. Cooldown starts from NPC response time, not player message time.
- **NPC conversation seeding**: on the first LLM call for a player-NPC pair, `handle_npc_chat()` seeds the conversation with a synthetic `(approaches)` user message and the NPC's static `dialog` as an assistant message. This gives the AI context for what it already said via proximity greeting (e.g. "You look healthy!"). The synthetic pair follows `user → assistant` ordering so the Anthropic API accepts it.
- **NPC response cleanup**: server strips emojis, `*action*` text, and trailing incomplete sentences. Truncates at last sentence boundary within 200 chars. Raw model output logged to `event_log.txt` as `NPC_RAW` and printed to sidelog for debugging.
- **Boss monsters** have `"boss": True` in their stats dict. Use `monster.is_boss` — never hardcode boss checks to a specific kind. Boss sprites use `"resolution": 2` in their sprite data for higher detail density — coordinates are in a 32x32 grid instead of 16x16, and `drawMonsterSprite`/`drawMonsterDeath`/`renderCorpses` divide scale by resolution so each unit maps to the same pixel size as normal sprites.
- **Trap rooms** (lock-in): dungeon rooms with 3+ monsters have a 1/3 chance of locking doors until all monsters are defeated. Boss rooms always lock. Decided at dungeon creation time (stored in `instance.trap_cells`), applied during room resolution. Overworld rooms can also be trap rooms via `locked: true` in the `.room` file header (e.g. Forsaken Bailey `ow_8_9.room`). Runtime lock state tracked in `game.locked_rooms`. `CD` tile = closed door. Dungeon items are hidden and non-pickable during trap lockdown.
- **Locked doors & keys**: dungeons have 0-N locked doorways (configurable via `min_locks`/`max_locks` in `DUNGEON_TYPES`). `LD` tile = locked door side, `KD` tile = keyhole door center. Key distribution uses `KeyMath/key_solver.py` constraint solver to guarantee no deadlocks regardless of player door-opening order. Keys are per-player (`player.keys`), persist across dungeon exits. Client sends `unlock_door` command when walking into LD/KD tiles. Custom room slots are assigned at dungeon creation time (not lazily) so trap room detection and key placement have full room data.
- **DungeonTopology**: lazy spatial oracle in `server/dungeon_topology.py`. Constructed with `(active_cells, connections, entrance)`, answers distance/path/zone queries on demand with caching. Uses a **mark system**: `topo.mark(cell, "boss")` increments a counter, `topo.marks(cell, "boss")` returns count, `topo.has_mark()`/`topo.lacks_mark()` for booleans. Distance queries like `topo.dist(cell, "boss")` lazily BFS from the marked cell and cache. `topo.path_between("entrance", "treasure")` traces shortest paths. Zones set via `topo.set_zones()` after lock placement. `topo.add_connections()` accepts new edges and clears caches.
- **Dungeon naming**: "sanctum" = the seal-shard room at the dungeon's deepest point (past the boss). "treasure" = the chest room (contains lantern in d1, TBD for d2). These were previously both called "treasure."
- **Item & key placement pipeline**: all placement flows through `DungeonTopology` in `create_dungeon()`. Order: sanctum (furthest leaf) → boss (parent of sanctum) → traps → treasure chest (far from boss+entrance) → darkness → locked doors → keys → map → compass. All scoring uses **higher = better** with `max()` and commented tuple keys using `topo.lacks_mark()` for readable constraints. Graph generation is separated: `_build_spanning_tree()` and `_pick_extra_edges()` in `dungeons.py`. Lock placement (`_place_locked_doors()`) returns doors + zones only; key placement is in the main pipeline. `_solve_key_distribution()` wraps the constraint solver.
- **Monster walk state**: `WalkState` dataclass in `models.py` holds walk data (from/to positions, walk_time, timing, direction). Assigned to `monster.state_data` when `state == "walking"` — access via `sd.from_x`, not `sd["from_x"]`. `sd.walk_time` is the actual step duration (base `monster.walk_time` scaled by step distance). Other states (charging, teleporting, area) still use plain dicts.
- **Continuous monster movement**: monsters move in full-tile steps (`MOVE_STEP = 1.0`). `_is_walkable_at()` in `behavior_engine.py` checks all tiles covered by a float-position footprint. Monster positions are interpolated every tick during walks. Knockback and error recovery snap to nearest integer tile (`round(x)`).
- **DEBUG_MODE constant**: `DEBUG_MODE` in `constants.py` is evaluated at import time from `os.environ`. Use `from server.constants import DEBUG_MODE` instead of inline `os.environ.get("DEBUG_MODE", ...)` checks.
- **Guard despawn constants**: `GUARD_DESPAWN_TIMEOUT`, `GUARD_DESPAWN_DISTANCE`, `GUARD_DESPAWN_GRACE` live in `constants.py`. Use `_despawn_guards(guards, room_id, msgs)` helper in `combat.py` to kill all guards in a list.
- **Monster walk collision**: server updates `monster.x/y` to the interpolated position **every tick** during a walk and checks contact collision continuously. Dodge window is natural (move out of the monster's path) rather than artificial checkpoints. `WalkState.walk_time` stores the actual duration for the step (scaled by distance).
- **Monster knockback**: controlled by `monster.knockbackable` (from `"knockback"` in monster stats, defaults to `true` for non-bosses, `false` for bosses). Knockbackable monsters get pushed 1 tile in the attack direction when hit (if they survive). Every hit resets the decision timer and interrupts the current action (walk/charge/etc.), even if the monster can't be knocked back due to a wall. Client uses a separate `knockbackSlide` state (not `walkState`) for a 200ms easeOutQuad slide animation. Non-knockbackable monsters (bosses, heavy monsters) take damage but continue their behavior script uninterrupted.
- **Sword hitbox**: 1.0 tile in the attack direction (0.25 back into player + 0.75 forward), `SWORD_PERP_WIDTH` (0.6) tiles perpendicular (centered on player body). Computed by `sword_hitbox()` in `commands.py` (single source of truth — also used by `/viewserver` debug overlay). Narrowed from 1.0 to prevent corner-camping exploits now that monster positions are continuous. The hitbox stays active for `SWORD_ACTIVE_DURATION` (180ms, ~5 ticks) after the swing — `sword_hit_scan()` runs each tick, tracking already-hit monsters by `id(monster)` so each is only damaged once per swing. `player.active_attack` holds the swing state (direction, start_time, room, anchor position, hit set); `_tick_active_attacks()` in `combat.py` drives the per-tick scans. Client sends precise `x`/`y` with the attack message so the hitbox anchors to the client's exact position rather than the server's potentially-stale half-tile grid position. `ATTACK_COOLDOWN` (300ms) matches client animation (150ms × 2 frames) — cooldown check has one `TICK_INTERVAL` of tolerance to absorb tick alignment jitter.
- **Player position model**: single canonical position on `G.player.myPlayer.x/y`. `G.player.displayX/Y` is computed each frame as `myPlayer.x/y + knockbackOffsetX/Y`. No separate `preciseX/Y`. Knockback sets `knockbackOffsetX/Y` (visual offset from old position, decays to 0 over 200ms via easeOutQuad). Player input is blocked during knockback (`knockbackSlide` guard in `playerTick()`). Other players and monsters still use `from/to` knockbackSlide interpolation.
- **Water mist** (d2 only): `renderWaterMist()` in `renderer.js` scales wisp count by water tile coverage (WA=1pt, SH=0.5pt, max 40). Opacity stays constant; density increases with more water.
- **Dungeon map vs compass**: map reveals room layout but does NOT show current position or locked doors. Compass adds blinking yellow dot for current room, pulsing amber marker for treasure chest (if uncollected), and red square for boss room.
- **Item pickup animation**: all item grants (sword, map, compass, heart, spirit_jar) use the same `item_obtained`/`item_effect` message flow with `drawItemPickupOverlay` (golden glow + sparkles). Player is frozen during the 2.5s animation. `ITEM_DRAW_FNS` in `sprites.js` maps item_type to draw functions. Heart container uses a larger hand-crafted 18x13 sprite (`drawBigHeartSolid`) with gold container border.
- **Item pickup monster freeze**: when a dungeon item is picked up, all monsters in the room freeze for `ITEM_PICKUP_FREEZE_DURATION` (2.5s, matching the client animation). Server skips monster ticks, contact damage, and projectile movement for the room. On thaw, all monster timers (walk `start_time`, warmup `end_time`, `last_action_time`) are shifted forward by the freeze duration so walks resume mid-stride and warmups continue from where they paused. Client receives `room_freeze` message and clamps `performance.now()` to the freeze start for walk interpolation, then shifts walk `startTime`s on thaw. State tracked in `game.room_pickup_freeze` (room_id → {start, end}). Other players can still attack frozen monsters.
- **Player revival**: when a player dies with allies in the same area (dungeon instance or overworld), a `Tombstone` game object spawns at the death position instead of auto-respawning. The `Tombstone` class in `models.py` is a standalone entity (like `Monster` or `Projectile`) — all revival state (reviver, timer) lives on it, not on `Player`. Dead player's avatar is destroyed as normal (`player.avatar = None`). Other players walk onto the tombstone to channel a `REVIVAL_DURATION` (6.5s) revive — if the reviver takes damage, the channel resets. Dead player sees a "Waiting for revival" overlay with a Respawn button (sends `respawn_request`). Tombstones tracked in `game.tombstones` (player_name → Tombstone). Revival proximity checked by `_tick_revivals()` in `combat.py`. On revival, player is resurrected in-place with `REVIVAL_HP` (3 hearts) and brief invincibility. If no allies remain in the area, dead players auto-respawn normally. Client renders tombstone sprite via `drawTombstone()` in `sprites.js`, revival progress ring in `renderTombstones()`, and waiting screen in `renderRevivalWaiting()` (smoothstep fade from black to 20% overlay over 5s).
- **Dark rooms & Magic Lantern**: dungeon rooms can be flagged `dark` (room-level, not per-tile). Without lantern: 0.75-tile visibility radius. With lantern (`has_lantern` flag): 3.5-tile radius. Sconce/brazier/fireplace tiles (`"bright": true` in `tiles.json`) provide 3-tile static light in dark rooms — rooms with bright tiles are auto-flagged dark for atmosphere. Darkness rendered client-side via `renderDarkness()` in `renderer.js` using offscreen canvas + `destination-out` radial gradient punching. Multiplayer: each lantern-holder creates their own light circle; `player_info()` in `net.py` includes `has_lantern` flag; `lanternHolders` tracked in `G.room` via `room_enter`, `player_entered`, `player_left`, and `item_effect` messages. BFS helpers (`_bfs_distances`, `_trace_path`, `_connection_adj`) live in `server/dungeon_topology.py`. Darkness assignment is inlined in `create_dungeon()`: d1 uses `DARK_ROOM_FRACTION` (25%) with entrance→treasure path immune and boss-adjacent rooms always dark; other dungeons use `DEFAULT_DARK_FRACTION` (10%) excluding boss/sanctum. Rooms with bright tiles are auto-flagged dark at room resolution time. Lantern is per-player pickup (stays on ground for others via `per_player_items` dict).
- **Treasure chest**: placed via topology scoring in the room furthest from both boss and entrance. In d1, contains the Magic Lantern. Rendered with `drawChestClosed`/`drawChestOpened` in `sprites.js`. Two states: closed (with subtle shimmer) and opened (lid up, golden glow). State is per-client — each player sees their own chest state. On pickup, chest transitions to opened and the item rises with the standard pickup animation. Opened chests persist when leaving/returning to the room (server sends `opened_chests` in `room_enter`). `G.room.openedChests` tracks positions client-side. Compass shows a pulsing amber marker at the chest cell (sent as `lantern_cell` in minimap data, hidden once collected). Debug minimap shows item cell labels.
- **Seal Fragment**: dungeon completion reward in the sanctum (room past boss). Spawns at center (7,5) when boss is killed. Per-player pickup: grants +1 heart container (`SEAL_FRAGMENT_HP_BONUS` = 2 HP), spawns exit stairwell at (2,2) via `_spawn_treasure_exit()` and `tile_change` broadcast. Sanctum template (`d1_treasure.room`) has braziers around center and sconces at corners for atmospheric dark-room lighting.
- **Boss hit behavior**: non-knockbackable monsters (bosses) take damage but do NOT have their current action interrupted — charge/aoe windups continue through hits. Controlled by `monster.knockbackable` check in `commands.py` hit handling.
- **Spirit Jar**: consumable item (`has_spirit_jar` flag) that auto-revives the player on death. Checked in `_tick_players()` Phase 1 before tombstone/respawn logic — `_spirit_jar_revive()` in `combat.py`. Revives at death position with `REVIVAL_HP` (3 hearts). On consumption, clears both `has_spirit_jar` and the NPC gift tracking flag (any `gift_*_spirit_jar`) so the Ghost NPC can re-gift. Client receives `spirit_jar_revive` message → `renderSpiritJarRevive()` overlay (2.5s, ghostly green glow) → `room_enter` restores gameplay. Item type `spirit_jar` is registered in `ITEM_DRAW_FNS` for ground items and pickup animation. Ghost Knight NPC in Shattered Armory (`ow_7_9.room`, dungeon 1 entrance) gives "Ghost's Spirit Jar" to players who lament the dungeon.
- **NPC gifts**: defined in `.room` files (`| Gift Name:condition`). Server-side effects keyed by display name in `GIFT_EFFECTS` dict in `npc_chat.py`. Tags like `[GIVE_ITEM]` and `[ANGRY]` are extracted from AI output *before* response cleanup (emoji/action stripping, truncation).
- **NPC prompt tuning — forced-choice classification**: the system prompt requires Gemma to start every reply with a classification tag: `[FRIENDLY]`, `[NEUTRAL]`, `[ANGRY]`, or `[GIVE_ITEM]`. This "classify then respond" approach dramatically outperforms instruction-based approaches ("don't do X unless Y") for 2B models. See `docs/REPORT_NPC_PROMPT_TUNING.md` for the full iterative testing report.
- **NPC guard summoning — consecutive-angry filter**: guards are only summoned after `ANGRY_STREAK_THRESHOLD` (default 2) consecutive `[ANGRY]` responses from the same NPC to the same player. This server-side filter reduces false positives without adding prompt tokens. Tracked per `(player, npc)` pair in `_angry_streak` dict, resets on any non-angry response. Gift giving (`[GIVE_ITEM]`) has no consecutive filter — occasional lucky gifts are fine.
- **NPC prompt tuning tips**: small models (gemma2:2b) are very sensitive to prompt wording. Keep NPC personalities short. Avoid words like "gruff" or "stern" — the model reads them as hostile. Avoid negative framing ("do NOT do X") — it increases the unwanted behavior. Use positive framing and few-shot examples instead. Adding too many classification tiers (e.g. ANNOYED vs FURIOUS) confuses the model — keep choices to 3-4 with clear semantic gaps.
- **NPC situation context**: `_build_situation_context()` in `npc_chat.py` injects dynamic situational awareness into every NPC's AI prompt — equipment status (armed/unarmed), alive monsters in the room, and player kill history. Built per-call from `player.flags`, `player.quests`, and `game.room_monsters`. Uses `server/prompts/npc_situation_context.txt` template. Conditional details (e.g. "tell them about the Smith") go here, not in the personality, to avoid contradicting the situation context.
- **NPC greeting overrides**: `set_npc_greeting(npc_name, room_id, fn)` in `npc_chat.py` registers a callable `fn(player, guard) -> str` that replaces the static room-file dialog. Evaluated fresh on each approach, so live game state (slime respawns, etc.) is always reflected. `handle_quest_npc` checks overrides before falling back to static dialog. The override dialog is also used to seed LLM conversation history.
- **NPC proximity dialog — once per visit**: NPCs speak their proximity dialog line once per player per room visit (tracked in `player.guard_greeted` set, cleared on room transition). `reset_npc_greeting_for_player(player, npc_name, room_id)` in `npc_chat.py` resets the tracker for a specific NPC when quest code changes the dialog text, so the new line triggers on next approach.
- **NPC debug chatlog**: in DEBUG_MODE, every NPC LLM call dumps the full system prompt + conversation history to `guard.txt` (appended). Useful for prompt tuning.
- **Quest event system**: `quest_event(event_type, player, msgs, **kwargs)` in `quests.py` — synchronous event emitter called from tick code. Quest handlers register via `@on_event(event_type, quest_id, **filters)` decorator with kwarg matching. All one-off quest logic lives in `quests.py`; emitters in game code stay generic (one line each). Current events: `monster_killed` (from `commands.py`), `room_enter` (from `lifecycle.py`). NPC proximity handlers (`@npc_handler`) remain separate.
- **Monster barrier tiles**: `MB` tile in `tiles.json` — visually identical to grass, `walkable: true` (players pass through), `monster_walkable: false` (monsters blocked). `game.is_monster_walkable_tile()` in `state.py` checks `monster_walkable` property, falls back to `walkable`. Behavior engine's `_is_walkable()` uses the monster-specific check. Used in `clearing.room` to fence the slime to the bottom half.
- **Logging — 3 destinations** via `server/log.py` (`from server import log`). Never use bare `print()` in server code — use the log module:
  - `log.debug(msg)` → debug sidebar + `event_log.txt` + stdout. For operational events visible in the debug panel.
  - `log.server(msg)` → `event_log.txt` + stdout only. For verbose output that would flood the sidebar (AI generation, registration details).
  - `log.event(kind, text)` → debug sidebar + `event_log.txt` + stdout. For structured lifecycle events (JOIN, DISCONNECT, NPC_CHAT, etc.). Written as `[timestamp] KIND: text`.
  - Chat window messages are a separate system (WebSocket game messages, not logging).
  - `broadcast_debug()` in `net.py` is for the canvas overlay HUD (12-line `G.debug.debugLog` buffer), not the sidebar — keep using it where needed.
  - `_LogBroadcaster` in `mud_server.py` is a safety net that catches stray `print()` from libraries/tracebacks → sidebar + file.
  - Exception: `state.py` startup prints stay as `print()` (runs before game exists). `ai_generator.py` `__main__` block stays as `print()` (standalone test).
- **Debug /viewserver**: sends full `debug_state` snapshot every tick to subscribed players (toggled via `/viewserver` chat command, debug-only). Renders semi-transparent red shapes for server-side entity positions.
- **Admin `/admin/library-stats`**: password-protected HTTP endpoint returning JSON snapshot of content library composition (per-dungeon real/permanent/custom/placeholder counts), deprecated content, and API usage (tokens, cost, rate limits). Gated behind `ADMIN_PASSWORD` env var — returns 404 if unset, requires HTTP Basic Auth (`admin:<password>`) if set. Works in both debug and production. Built by `_build_library_stats()` in `mud_server.py`.
- **Room geometry constants** live in `server/constants.py`: `DOORWAY_TILES`, `ALL_DOORWAY_TILES`, `bfs_reachable()`. Use `bfs_reachable()` instead of inline BFS for tile reachability checks.
- **The Gauntlet** (debug-only): monster difficulty tuning arena in `server/gauntlet.py`. `/gauntlet [kind] [count]` creates a linear dungeon of trap rooms with the specified monster type. `/gt <param> <value>` tunes stats (walk_time, decision_time, damage, hp, count, plus rule-level params like warmup, cooldown, range, drift, damage_radius). `/gt hard` resets to max difficulty; `/gt halve` bisects toward defaults. Auto binary-search adjusts one random param per wave based on outcome (EASY/GOOD/HARD/TOO HARD). Death = wave over (advances to next room). Results logged to `gauntlet_results.txt` (append-only). Heart drops disabled in gauntlet for clean damage tracking. Session state in `_sessions` dict, cleaned up on `/gauntlet stop`, room exit, or disconnect.
- **`log` message type**: client-side chat-log-only message (no popup overlay). Used for monster kill messages to reduce visual clutter. Handler in `net.js`.
- **Attack cooldown gap**: 90ms `attack_cooldown` client state between sword swings (`ATTACK_GAP_MS` in `renderer.js`). Player can't move or attack during the gap. Creates a vulnerability window between swings. Under review (Trello #88).
- **Player-vs-monster collision**: player hitbox is inset by `PLAYER_COLLISION_MARGIN` (0.2) per side, making a 0.6×0.6 AABB for contact damage. Smaller box replaces the old grace period for corner-scrape forgiveness. Shown in `/viewserver` overlay as bright red inset within faint red full tile.
- **Player position sync**: `syncPosition()` in the game loop sends `position_update` to the server at ~30fps (`SYNC_INTERVAL = 33ms`) with a dirty check (only when position or direction changes). No server-side rate limit — anti-cheat uses distance check only (`MAX_MOVE_PER_UPDATE`). Client-side axis-alignment still snaps toward half-tiles for NES Zelda feel.
- **Stair re-trigger guard**: `Avatar.spawn_stair` tracks the stair tile a player spawned on after a room transition. Stair detection is skipped until the player moves off that tile, preventing infinite transition loops with continuous position updates.
- **Combat constants tuned**: `ATTACK_COOLDOWN` = 0.27s (was 0.3), `COLLISION_GRACE_PERIOD` = 0.0s (removed — smaller hitbox handles it). `SWORD_PERP_WIDTH` = 0.6 (was implicit 1.0). `PLAYER_COLLISION_MARGIN` = 0.2. `MOVE_STEP` = 1.0 (full-tile monster movement).

## Key Gotchas

- **Client script load order matters**: `game_state.js` → `title.js` → `tiles.js` → `sprite_data.js` → `sprites.js` → `music.js` → `renderer.js` → `fx.js` → `net.js` → inline init/gameLoop → `input.js`
- **Import order** avoids circular deps: `constants` → `state` → `log` → `models` → `net` → `rooms` → `validation` → `dungeon_types` → `dungeon_topology` → `dungeons` → `quests` → `lifecycle` → `behavior_engine` → `commands` → `combat` → `debug_monsters` → `mud_server`. `dungeon_topology` has no game dependencies (only stdlib). `behavior_engine` imports from `lifecycle` (for `set_monster_idle`); `combat` imports `behavior_engine`; `_apply_damage` is injected into the engine via `init()` to avoid a circular dep. Combat uses lazy imports for commands; commands imports from lifecycle.
- **Command queue**: websocket messages are never processed inline — handler appends to `player.command_queue`, drained by `game_tick()`. Only `ping` is handled directly.
- **game_tick() is synchronous** with message batching — no `await` mid-tick. Messages collected as tuples, flushed after the full tick. This prevents dungeon teardown crashes.
- **Room transitions**: player's avatar is set to `None` during `do_room_transition()`, then a new avatar is created at the spawn point. `avatars_in_room()` naturally excludes avatar-less players so monsters can't target them mid-transition. Player stays in `game.players` throughout.
- **Dungeon room resolution is synchronous** — no JIT AI generation. Custom rooms resolve from the library pool or fall back to precreated.
- **Tile properties** live in `custom_tile_recipes[tile_id]` — no separate walkability sets. `is_walkable_tile()` reads from the recipe dict. `is_monster_walkable_tile()` checks `monster_walkable` first, falls back to `walkable`.
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
