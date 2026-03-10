# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A browser-based multiplayer MUD (Multi-User Dungeon) rendered as a Zelda-style top-down visual game. Players connect via browser, log in with a name/description, walk around tile-based rooms with arrow keys/WASD, and chat via speech bubbles.

## General Rules

When pushing to git make sure to update CLAUDE.md first!

**NEVER run `python worldgen.py` without explicit user permission.** The overworld `.room` files in `rooms/` contain hand-edited changes that worldgen will overwrite. Running it will destroy manual edits. Always warn the user that data will be lost before re-running.

**After any changes to `server/ai_generator.py`, `tools/content_viewer.py`, or `.env`, run `python tools/test_api_leak.py` to verify the Anthropic API key cannot leak into CLI subprocess calls.** The game uses the Claude CLI (subscription-based) for AI generation — the API must never be called directly. All 4 tests must pass.

**Avoid calling the Anthropic API directly unless expressly permitted by the user.** If you must call it (e.g. for testing), always set `metadata={"user_id": "claude-code"}` so the call is identifiable in the Console. Claude API docs: https://platform.claude.com/docs/en/api/overview

## Directory Structure

```
├── mud_server.py          # Main entry point
├── worldgen.py            # Offline world generator (stays at root)
├── client/                # Browser-served HTML + JS
├── server/                # Python modules imported by mud_server
│   └── prompts/           # AI prompt templates ({{placeholder}} syntax)
├── music/                 # MP3 tracks (village.mp3, dungeon_a.mp3, etc.)
├── rooms/                 # .room data files + dungeon1/ templates
├── data/                  # Runtime data (libraries, API usage) — gitignored
├── tools/                 # Dev utilities (renderers, content viewer, tests)
├── docs/                  # Generated images, planning docs
├── deploy/                # Nginx config, redirect page
└── local_ignore/          # Local-only files (SSH keys, archives) — gitignored
```

## Architecture

Multi-file architecture, no build tools or external assets:

### Client (`client/`)

All client-side state lives on a shared `G` namespace object (defined in `game_state.js`, loaded first). Constants (`TILE`, `SCALE`, `TS`, `COLS`, `ROWS`, `CW`, `CH`, `MOVE_LERP`) are plain globals. Script load order in `client.html` matters: `game_state.js` → `tiles.js` → `sprite_data.js` → `sprites.js` → `music.js` → `renderer.js` → `net.js` → inline init/gameLoop → `input.js`.

- **`client/client.html`** — HTML + CSS + inline init script. Login overlay, mobile detection, DOM ref binding to `G`, `processMovement()`, `gameLoop()`. Loads all other JS files via `<script>` tags.
- **`client/game_state.js`** — Constants and the `G` namespace object holding all mutable state (ws, myName, myPlayer, otherPlayers, currentRoom, monsters, projectiles, keysDown, animation timers, etc.).
- **`client/renderer.js`** — All `render*()` functions (room, players, speech bubbles, UI, HUD, transitions, projectiles, area warnings, charge effects, death animations, sword/heart pickups). All `update*()` functions (dances, attacks, dying monsters/players, projectiles, attack effects). Helper functions (`startDance`, `stopDance`, `startAttack`, `getExitDirs`, `roundRect`).
- **`client/net.js`** — WebSocket connection (`connect()`, `scheduleReconnect()`), `handleMessage()` switch for all server message types, `dbg()` debug logger.
- **`client/input.js`** — Keyboard handlers (keydown/keyup), chat input focus/blur/submit, login button, visibility change reconnect, mobile d-pad touch handlers, mobile chat/sword buttons, debug toggle. Must load last (after DOM refs are bound and all functions defined).
- **`client/sprite_data.js`** — Declarative sprite definitions. All NPC, monster, death animation, player dance/walk/fall sprites defined as data arrays of `[colorKey, x, y, w, h]` layers. Color keys resolve via sprite-local colors > `PALETTE` globals > literal hex. Monster data includes per-frame hop offsets. Special effects (bob, alpha, pulse glow) declared as `effects` on the sprite entry. Also defines `customMonsterSprites` and `customDeathSprites` runtime registries for AI-generated monster sprites (populated from server data at room entry).
- **`client/sprites.js`** — Sprite renderer + remaining procedural sprites. Core `drawLayers()` function renders data from `sprite_data.js`. `drawNPCSprite()` handles effects (bob, alpha, pulse). `drawMonsterSprite()`/`drawMonsterDeath()` handle frame selection and yOff, checking both static `MONSTER_SPRITE_DATA`/`DEATH_SPRITE_DATA` and the custom runtime registries. `drawMonsterDeath()` auto-generates a generic splat from the monster's primary color if no death sprite exists. Player sprites use `SHIRT` color placeholder resolved at draw time via `makePlayerColorMap()`. Attack/sword/heart sprites remain procedural (dynamic offsets). All original function names preserved as backward-compatible wrappers.
- **`client/tiles.js`** — Data-driven tile rendering using rect layers (same `[colorKey, x, y, w, h]` format as sprites). `TILE_COLORS` defines per-tile color palettes. `TILE_SPRITE_DATA` defines each built-in tile as an array of rect layers drawn on top of the base color fill. `drawTileLayers()` renders the layers. `createTileCanvas()` fills base color then draws layers. Cached to offscreen canvases. Exposes `getTileCanvas(tileId, TS, TILE, SCALE)` and `TILE_COLORS`. Also defines `customTiles` runtime registry and `runTileRecipe()` interpreter for AI-generated tiles — recipes are JSON objects with named colors and a `layers` array of `[colorKey, x, y, w, h]` rects. `getTileCanvas()` checks `customTiles` for string tile IDs before falling back to static data.
- **`client/music.js`** — Background music. MP3 playback with crossfade. Server sends a `music` field per room (e.g. `village`, `tavern`, `chapel`, `overworld`, `dungeon1`–`dungeon7`); client maps it to a track URL via `MUSIC_TRACKS`. Falls back to `BIOME_MUSIC[biome]` if no music field. Exposes `MusicPlayer.start()`, `.stop()`, `.toggle()`, `.isPlaying()`, `.setRoom(roomId, biome, music)`. Auto-starts on login, toggled with M key.

### Server (`server/`)

All server-side shared state lives on a `GameState` singleton (`game = GameState()` in `server/state.py`). Modules import `from server.state import game` to access rooms, players, monsters, etc. Import order avoids circular deps: `constants` → `state` → `models` → `net` → `rooms` → `validation` → `dungeons` → `quests` → `lifecycle` → `combat` → `debug_monsters` → `mud_server`. Combat uses lazy imports for lifecycle to break one remaining cycle.

- **`mud_server.py`** — Main entry point. `handle_move()`, `check_edge_exit()`, `check_guard_proximity()`, `handle_chat()`, `handle_connection()`, `process_request()`, `STATIC_FILES` dict, `main()`. Imports and orchestrates all `server/` modules.
- **`server/constants.py`** — All tile ID constants, `WALKABLE_TILES` set, `TILE_CODES` dict, direction constants (`DX`, `DY`, `OPPOSITE_DIR`), room dimensions, gameplay tuning constants.
- **`server/state.py`** — `GameState` class holding all mutable state as singleton `game`. Contains: rooms, guards, monster_templates, dungeon_templates, monster_stats, custom sprite/tile registries, players dict, room_monsters, room_cooldowns, room_hearts, room_projectiles, active_dungeon, counters, event_log, log_file. `is_walkable_tile()` method checks both static `WALKABLE_TILES` and `custom_walkable_tiles`.
- **`server/models.py`** — `Player`, `Monster`, `Projectile` data classes. `Monster.__init__` reads stats from `game.monster_stats` and behaviors from `game.monster_behaviors`.
- **`server/net.py`** — `send_to()`, `broadcast_to_room()`, `players_in_room()`, `player_info()`, `log_event()`. Core networking helpers used by all other modules.
- **`server/rooms.py`** — `load_room_files()` and `load_dungeon_templates()`. Reads `.room` files, populates `game.rooms`, `game.guards`, `game.monster_templates`, `game.dungeon_templates`.
- **`server/validation.py`** — `validate_monster()`, `validate_tile()`, `register_monster_type()`, `register_tile_type()`. Validation constants for behavior conditions/actions, attack types. Tile validation checks `layers` array of `[colorKey, x, y, w, h]` rects.
- **`server/dungeons.py`** — `DungeonInstance` class, `create_dungeon()`, `destroy_dungeon()`, `is_dungeon_room()`, `dungeon_player_count()`.
- **`server/lifecycle.py`** — `spawn_monsters()`, `get_room_monsters()`, `on_player_enter_room()`, `on_player_leave_room()`, `send_room_enter()`, `do_room_transition()`. Room lifecycle management.
- **`server/combat.py`** — `damage_player()`, `handle_attack()`, `execute_monster_attack()`, all `attack_*()` functions (melee, projectile, charge, teleport, area), `monster_tick()`, `projectile_tick()` background loops.
- **`server/quests.py`** — `NPC_HANDLERS` dict, `npc_handler` decorator, quest NPC interaction handlers (Amara, Priest, Smith, Barmaid).
- **`server/debug_monsters.py`** — `DEBUG_MONSTERS` dict (7 test monsters with full sprite data), `handle_debug_spawn()`, `auto_register_debug_monsters()`.
- **`server/behavior_engine.py`** — Data-driven monster AI with tick-based warmup/cooldown. `monster_tick()` evaluates rules top-to-bottom; first match wins. Returns `{"phase": "execute"|"warmup", "action": ..., ...params}` or None. Conditions: `player_within`, `player_beyond`, ``player_in_range_line` (with `los`), `hp_below`, `hp_above`, `random_chance`, `always`. Actions: `move` (direction: random/player/away/patrol/cardinal), `hold`, `projectile`, `charge`, `teleport`, `area` — all with params inline in the rule. Warmup (ticks) delays execution while locking params; cooldown (ticks) prevents re-evaluation of a specific rule. Initialized by `mud_server.main()` via `init()`. Monsters without behavior data default to `[{"if": "always", "do": "move", "direction": "random"}]`. Behavior data stored in `game.monster_behaviors` dict.
- **`server/dungeon_layouts.py`** — Dungeon layout templates. Defines 11 Zelda-inspired 8x8 grid layouts (eagle, fortress, shield, hammer, lizard, dragon, demon, lion, death_mountain, skull, axe, crown). Each layout has a name, grid (X=room, .=empty), and entrance cell.
- **`server/content_library.py`** — Library system for AI-generated content. `LibraryEntry` dataclass with id/tags/data/permanent (permanent entries never expire or get deleted). `ContentLibrary` class with fixed capacity, placeholder slots, tag-based queries (`query_by_tags` for exact match, `query_by_tag_overlap` for Jaccard-scored ranking), expiry of oldest entries (skips permanent), and late-binding resolution (preferred → best tag overlap → any → generate). Tile resolution supports a `walkable` hard constraint — walkable tiles can only substitute for walkable, and vice versa. Persists custom entries to JSON (permanent entries loaded from source at startup). Free-form tags normalized on ingestion. Library capacities: rooms 96 (64p+32c), monsters 8 (4p+4c), tiles 14 (7p+7c).
- **`server/dungeon_content.py`** — Precreated dungeon content definitions. 4 permanent monsters (skeleton, bat, dungeon_slime, phantom) and 7 permanent tiles (DW, DF, PL, SC, BZ, MF, CF) defined as data dicts with full stats, sprites, behaviors, and tags. `register_precreated_types()` registers new monster types (dungeon_slime, phantom) at startup. `load_precreated_content()` populates monster/tile/room libraries with permanent entries. Room conversion: `_convert_room_template()` converts parsed .room templates (numeric tilemaps) to library-compatible data (string tile codes).
- **`server/ai_generator.py`** — Claude integration for procedural dungeon content. **Multi-step generation** using focused AI calls, each with its own system prompt and validation: `generate_monster_design()` (kind/tags/stats/behavior), `generate_monster_sprite()` (sprite art given the design), `generate_tiles()` (custom tile definitions), `generate_layout()` (room name/tilemap/monster placements). The orchestrator `generate_room()` rolls for 0-2 new monsters and 0-2 new tiles (based on library fullness + random chance), generates them first, then calls `generate_layout()` with the full inventory — flagging newly created content as preferred. Uses Claude Haiku (`claude-haiku-4-5-20251001`). **Two backends** controlled by `AI_BACKEND` env var: `"api"` (Anthropic SDK, needs `ANTHROPIC_API_KEY`, 15s timeout) or `"cli"` (shells out to local `claude` CLI, uses subscription, 10min timeout, unsets `CLAUDECODE` env var to avoid nested-session detection). Default is `"cli"`. Generic `_call_ai()` helper handles rate limiting, JSON parsing, markdown fence stripping, validation callbacks, auto-patching callbacks, and retry logic for all steps. **Auto-patching** fixes common AI mistakes: moves monsters to reachable walkable tiles, carves paths to disconnected doorways, deduplicates room names, clamps attack stats. **Focused validators**: `validate_tile_definition()`, `validate_monster_sprite()`, `validate_monster_behavior()`, `validate_layout()`. Backward-compat `validate_room_response()` wraps all four. Rate limiting (15/min, 600/day — higher limits since one room = multiple calls), token usage tracking persisted to `data/api_usage.json`. `generate_room()` returns same format as before: `{name, tilemap, new_tiles, new_monsters, monster_placements}`. Standalone test via `python server/ai_generator.py`.
- **`server/prompts/`** — AI prompt templates stored as plain text files, loaded by `ai_generator.py` via `_load_prompt()`. Placeholders use `{{name}}` double-curly-brace syntax to avoid collisions with JSON in the prompt text. **System prompts** (4 files): `monster_design_system.txt`, `monster_sprite_system.txt`, `tiles_system.txt`, `layout_system.txt`. **User prompt templates** (4 files): `monster_design_user.txt`, `monster_sprite_user.txt`, `tiles_user.txt`, `layout_user.txt`. Edit the `.txt` files directly to tweak prompts — no Python changes needed.

### World data
- **`worldgen.py`** — Offline world generator. Creates ~104 `.room` files in `rooms/` directory. Defines 16x8 biome grid, builds MST connectivity graph, generates tilemaps with biome-specific features, places NPCs and monsters. Biome config consolidated in `BIOME_CONFIG` dict (base tile, border, decor, walkable tiles, music, monsters per biome). Run once with `python worldgen.py`.
- **`rooms/*.room`** — Room data files. Village rooms are hand-authored; overworld rooms are generated by `worldgen.py`. Plain text format with header (name, biome, music, exits), tilemap (2-char tile codes), and entity sections (NPCs, monsters). All rooms (village + overworld) are loaded from `.room` files at startup — there are no hardcoded room definitions in `mud_server.py`.
- **`rooms/dungeon1/*.room`** — Dungeon room templates (64 files). Same `.room` format but without exits (exits are auto-generated from layout adjacency at runtime). Used as a template pool — the dungeon instance system picks a random layout and assigns templates to cells.
- **`music/*.mp3`** — Eleven mp3 tracks: `village.mp3`, `tavern.mp3`, `chapel.mp3`, `overworld.mp3`, `dungeon_a.mp3`–`dungeon_g.mp3`. Served via URL routes `/music.mp3`, `/music_tavern.mp3`, etc. (mapped in `STATIC_FILES`).

### Tools (`tools/`)
- **`tools/render_map.py`** — Standalone map renderer. Reads all `.room` files and renders `docs/world_map.png` overview image. Requires Pillow. Run with `python tools/render_map.py`.
- **`tools/render_dungeon_rooms.py`** — Dungeon room template renderer. Renders all 64 dungeon room templates from `rooms/dungeon1/` as `docs/dungeon_rooms.png` in an 8x8 grid. Requires Pillow.
- **`tools/render_dungeons.py`** — Dungeon layout renderer. Reads `server/dungeon_layouts.py` and renders all layout shapes as `docs/dungeon_layouts.png`. Requires Pillow.
- **`tools/download_log.py`** — Local utility script. Fetches the server's event log via `/get-log`, saves it to `log_YYYYMMDD_HHMMSS.txt`, and clears the log on the server. Defaults to the Hetzner server; pass `http://localhost:8080` as arg for local dev.
- **`tools/content_viewer.py`** + **`tools/content_viewer.html`** — Standalone dev tool for browsing and generating AI dungeon content. Async HTTP server on port 8081. Single-page app that can browse monster/tile/room libraries as rendered thumbnails, inspect items (tags, stats, behavior, sprite data), generate new rooms on demand with theme/difficulty controls, delete library items, and view API usage stats. Intercepts all `print()` calls into a ring buffer exposed via `/api/logs` for real-time server log streaming. Serves `client/tiles.js`, `client/sprites.js`, `client/sprite_data.js` for client-side rendering. Routes: `GET /api/libraries`, `POST /api/generate` (full room), `POST /api/generate/monster` (single monster design+sprite), `POST /api/generate/tiles` (custom tiles), `DELETE /api/{type}/{id}`, `GET /api/usage`, `GET /api/logs?since=N`. Run with `python tools/content_viewer.py`.
- **`tools/test_content_library.py`** — Unit tests for content_library.
- **`tools/test_api_leak.py`** — Mandatory tests verifying the Anthropic API key never leaks into CLI subprocess calls. Tests: `_call_cli` strips `ANTHROPIC_API_KEY` from env, `AI_BACKEND` defaults to `"cli"`, `.env` doesn't set `AI_BACKEND=api`, `content_viewer.py` doesn't force API backend. Run with `python tools/test_api_leak.py`.

### Docs (`docs/`)
- **`docs/PLAN_AI_GENERATION.md`** — Staged plan for AI-powered procedural content generation. Stages 1–6 complete. Stage 6.5 (Unified Content Refactor) adds `permanent` flag to library entries so precreated dungeon content (4 monsters, 7 tiles, 64 rooms) uses the same data-driven system as AI-generated content. Stage 7 (Library-Managed Dungeons) builds ~50% precreated / ~50% custom rooms with lazy generation. All dungeon sprites/tiles sent via custom registries (Option B). AI prompt sees a flat list of all content — no built-in vs custom distinction. See file for full details.
- **`docs/world_map.png`**, **`docs/dungeon_layouts.png`**, **`docs/dungeon_rooms.png`** — Generated reference images.

### Deploy (`deploy/`)
- **`deploy/notzelda.nginx.conf`** — Nginx configuration for the Hetzner VPS.
- **`deploy/notzelda_redirect/`** — Static redirect page for `haraldmaassen.com/notzelda`.

**Protocol:** JSON over WebSocket.
- Client → Server: `login` (name, description), `move` (direction), `attack`, `chat` (text), `ping`
- Server → Client: `login_ok` (color_index, hp, max_hp), `room_enter` (tilemap + players + guards + monsters + exits + biome + music + exit_direction + hp + max_hp + optional custom_sprites + custom_death_sprites + custom_tiles), `player_moved`, `player_entered`, `player_left`, `attack` (name, direction), `chat`, `dance`, `info`, `error`, `pong`, `monster_moved`, `monster_killed`, `monster_hit`, `monster_spawned`, `player_hurt` (name, hp, max_hp, x, y, knockback), `you_died` (x, y), `player_died` (name, x, y, color_index), `hp_update` (hp, max_hp), `heart_spawned` (id, x, y), `heart_collected` (id)

**State:** All in-memory on the `game` singleton (`server/state.py`). Players tracked in `game.players` dict (websocket → Player). Rooms loaded from `.room` files into `game.rooms` at startup (15x11 tilemaps). NPCs and monsters parsed into `game.guards` and `game.monster_templates`. State resets on server restart. An `game.event_log` list records joins, leaves, and chat messages (with timestamps); exposed via `GET /get-log` which returns the log as plain text and clears it.

**World map:** 112+ rooms total. Village (8 rooms): Town Square (center) connects to Blacksmith (north), Forest Path (south), Tavern (east), Old Chapel (west). Old Chapel → Chapel Sanctum (west). Forest Path → Clearing → overworld gate (ow_0_7). The overworld is a 16x8 grid of ~100 rooms across 9 biomes (forest, mountain, desert, swamp, graveyard, castle, plains, lake, river) plus 4 interior rooms (2 caves, oasis, witch hut). Tavern has stairs up to Tavern Upper Floor. The Clearing also has stairs down to the dungeon entrance.

**NPCs:** NPCs defined in `.room` files via `npc Name X Y sprite dialog` lines (sprite is the sprite type key, e.g. `guard`, `smith`, `priest`, `barmaid`, `amara`, `witch`, `ghost`, `ghost_knight`, `ranger`, `farmer`, `nomad`, `merchant`, `elder`, `fisher`). Loaded into `game.guards` at startup. Each NPC has a name, position, sprite type, and dialog line. NPCs are rendered client-side via `drawNPC(ctx, px, py, sprite, S)` which dispatches to the appropriate sprite function from `NPC_SPRITES` map. Players can't walk on NPC tiles. Walking adjacent triggers the NPC's dialog as a chat bubble (broadcast to room), with a 10-second per-player cooldown to prevent spam. Quest-aware NPCs (Amara, Priest, Smith, Barmaid) have registered handlers in `NPC_HANDLERS` (`server/quests.py`) that override static dialog.

**Monsters:** Monster templates defined in `.room` files via `monster kind X Y` lines, loaded into `game.monster_templates` at startup. Five built-in types: slime (forest/plains, 1HP, 1dmg), bat (cave/graveyard, 1HP, 1dmg, fast), scorpion (desert, 2HP, 2dmg), skeleton (graveyard/castle/dungeon, 2HP, 3dmg), swamp_blob (swamp, 1HP, 1dmg). Lifecycle: spawn when first player enters, despawn when all leave. Monsters move via `monster_tick()` (`server/combat.py`) with per-kind `tick_rate` intervals, using the data-driven behavior engine (`server/behavior_engine.py`). Built-in monsters default to random wander; custom monsters can have behavior rules with conditions, actions, warmup, and cooldown. Multi-HP monsters take multiple hits — server sends `monster_hit` on damage and `monster_killed` on death. Protocol messages: `monster_moved`, `monster_killed`, `monster_hit`, `monster_spawned` (optionally carries `custom_sprites`/`custom_death_sprites`). Killed monsters have a 10% chance to drop a heart pickup. **Dynamic monster types** can be registered at runtime via `register_monster_type(data)` (`server/validation.py`) which validates and adds to `game.monster_stats`, `game.custom_sprites`, optionally `game.custom_death_sprites`, and optionally `game.monster_behaviors`. **Dynamic tiles** via `register_tile_type(data)` which validates and adds to `game.custom_tile_recipes` and tracks walkability in `game.custom_walkable_tiles`. Both have validation functions (`validate_monster()`, `validate_tile()`) that check stat ranges, sprite bounds, color formats, behavior rules, tile layer bounds, and grid coordinates. All walkability checks use `game.is_walkable_tile(tile)` which checks both the static `WALKABLE_TILES` set and `game.custom_walkable_tiles`. The `room_enter` message carries custom sprite/tile data to the client, which merges it into `customMonsterSprites`/`customDeathSprites`/`customTiles` registries. Client rendering uses generic `drawMonsterSprite()`/`drawMonsterDeath()` for all monster kinds (no hardcoded if/else chains). Custom tiles use `runTileRecipe()` interpreter. Chat command `/debug_spawn <kind>` spawns test monsters (7 built-in: fire_slime, ice_bat, shadow_skull, skeleton_archer, ghost_teleporter, war_boar, flame_mage; also works with any registered or built-in kind).

**Monster Behavior Engine:** Tick-based rule evaluation with warmup/cooldown. Each monster has a `tick_rate` (ticks per second — higher = faster; internally converted to `tick_interval` = 1/tick_rate for timing). Each tick, rules evaluate top-to-bottom; first match wins. **Conditions**: `player_within` (Manhattan range), `player_beyond`, `player_in_range_line` (same row/column, optional `los` for line-of-sight), `hp_below`, `hp_above`, `random_chance`, `always`. **Actions**: `move` (with `direction`: `random`/`player`/`away`/`patrol`/cardinal), `hold`, `projectile` (direction + damage + sprite_color), `charge` (direction + range + damage), `teleport` (target: player/random/away + drift + range + damage), `area` (range + damage). **Warmup** (ticks): delays execution after condition matches; monster does nothing during warmup; parameters locked at warmup start. Used for telegraphed attacks — charge gets `charge_prep` message, area gets `area_warning`, teleport gets `teleport_start` (monster becomes intangible). **Cooldown** (ticks): after execution, this rule is skipped for N ticks. Attacks are inline in rules (no separate `attacks` array). `stats.damage` is contact-only; each attack rule carries its own `damage`. Example: `{"if": "player_in_range_line", "range": 6, "los": true, "do": "projectile", "direction": "player", "damage": 1, "sprite_color": "#ff0000", "warmup": 1, "cooldown": 5}`. Projectiles tracked per-room in `game.room_projectiles` dict and moved by `projectile_tick()` async loop. Protocol messages: `projectile_spawned`, `projectile_moved`, `projectile_hit`, `projectile_gone`, `charge_prep`, `monster_charged`, `teleport_start`, `teleport_end`, `area_warning`, `area_attack`.

**Player Health:** Players have 6 HP (displayed as 3 hearts in HUD). Contact damage occurs when a player walks onto a monster or a monster hops onto a player — damage amount varies by monster kind. On damage: 1.5s invincibility frames (client flickers sprite), knockback away from facing direction, red flash overlay. At 0 HP: death animation (spin + fade to black + "You died!"), then respawn at Town Square after 5.5s delay with full HP. The Barmaid NPC in the tavern heals players to full HP.

**Heart pickups:** When a monster is killed, there's a 10% chance it drops a heart on its tile. Hearts bounce on the ground and restore 2 HP when walked over. Hearts are tracked per-room in `game.room_hearts` and cleaned up when all players leave.

**Dungeons:** Procedurally generated dungeon instances, entered via stairs down in the Clearing room. Each instance uses a random layout from `dungeon_layouts.py` (11 Zelda-inspired 8x8 grid shapes) and assigns random room templates from `rooms/dungeon1/` (64 templates) to each cell. Exits between dungeon rooms are auto-generated from grid adjacency; unused exits are walled off. The entrance room gets stairs up back to the Clearing. Each instance gets a random dungeon music track (1 of 7). Dungeon rooms use the `dungeon` biome with 7 tile types: dungeon_wall (DW), dungeon_floor (DF), pillar (PL), sconce_wall (SC), brazier (BZ), mosaic_floor (MF), cracked_floor (CF). Cleared rooms (all monsters killed) don't respawn. The entire dungeon instance is destroyed when all players leave. A new instance is created on demand when anyone enters.

**Music:** Eleven mp3 tracks in `music/` dir (`village.mp3`, `tavern.mp3`, `chapel.mp3`, `overworld.mp3`, `dungeon_a.mp3`–`dungeon_g.mp3`), served via URL routes `/music.mp3`, `/music_tavern.mp3`, `/music_chapel.mp3`, `/music_overworld.mp3`, `/music_dungeon1.mp3`–`/music_dungeon7.mp3`. Each `.room` file specifies a `music` field (`village`, `tavern`, `chapel`, `overworld`, or `dungeon1`–`dungeon7`). The server sends this field in `room_enter`; the client maps it to a track URL via `MUSIC_TRACKS`. Fallback: `BIOME_MUSIC[biome]` → overworld default (dungeon biome falls back to dungeon1). `music.js` switches tracks per room via `MusicPlayer.setRoom(roomId, biome, music)`. Toggled with M key.

**Emotes:** `/dance` makes the player do a looping boogie animation (4 frames). Dance stops when the player moves. Dancing state is synced — new players entering a room see ongoing dances.

**Combat:** Space bar triggers a sword stab attack (NES Zelda-style). The attack is a 2-frame animation (~300ms) that draws a thrust pose on the player and a sword on the adjacent tile in the facing direction. Player movement is frozen during the attack. Server enforces a 0.4s cooldown. Hits monsters on adjacent tile — damage reduces HP, kills at 0.

**Networking model:** Server-authoritative. The client sends action requests (`move`, `attack`, `chat`) and the server validates, updates state, and broadcasts results to all players in the same room. The client does not predict — it interpolates display positions toward server-confirmed coordinates using linear interpolation (lerp). All sync is scoped per room; players only receive messages about their current room.

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
- **Python venv:** `/opt/NotZelda/venv/` (websockets 12.0 pinned — v16 breaks the `process_request` API)
- **Systemd service:** `notzelda` — auto-starts on boot, restarts on crash
  - `systemctl status notzelda` — check status
  - `systemctl restart notzelda` — restart after changes
  - `journalctl -u notzelda -f` — tail logs
- **Deploying updates:** `cd /opt/NotZelda && git pull && systemctl restart notzelda`
- **Web redirect:** `haraldmaassen.com/notzelda` redirects to the game (static HTML hosted on separate Hetzner shared hosting, uploaded via WebFTP)

## Dependencies

- Python 3.12+
- `websockets` (12.0 — pinned, v16+ breaks the `process_request` API)
- `pyngrok` (optional, for local dev tunneling)
