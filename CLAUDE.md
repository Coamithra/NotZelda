# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A browser-based multiplayer MUD (Multi-User Dungeon) rendered as a Zelda-style top-down visual game. Players connect via browser, log in with a name/description, walk around tile-based rooms with arrow keys/WASD, and chat via speech bubbles.

## General Rules

When pushing to git make sure to update CLAUDE.md first!

**NEVER run `python worldgen.py` without explicit user permission.** The overworld `.room` files in `rooms/` contain hand-edited changes that worldgen will overwrite. Running it will destroy manual edits. Always warn the user that data will be lost before re-running.

## Architecture

Multi-file architecture, no build tools or external assets:

- **`mud_server.py`** — Python server handling everything: WebSocket game logic (asyncio + websockets), room/player state, command dispatch, and HTTP static file serving. Binds to port 8080. Static file routes are defined in `STATIC_FILES` dict.
- **`client.html`** — Browser client (HTML + CSS + core game JS). Login overlay, game loop, rendering, input handling, WebSocket connection to `/ws` endpoint.
- **`sprite_data.js`** — Declarative sprite definitions. All NPC, monster, death animation, player dance/walk/fall sprites defined as data arrays of `[colorKey, x, y, w, h]` layers. Color keys resolve via sprite-local colors > `PALETTE` globals > literal hex. Monster data includes per-frame hop offsets. Special effects (bob, alpha, pulse glow) declared as `effects` on the sprite entry. Also defines `customMonsterSprites` and `customDeathSprites` runtime registries for AI-generated monster sprites (populated from server data at room entry).
- **`sprites.js`** — Sprite renderer + remaining procedural sprites. Core `drawLayers()` function renders data from `sprite_data.js`. `drawNPCSprite()` handles effects (bob, alpha, pulse). `drawMonsterSprite()`/`drawMonsterDeath()` handle frame selection and yOff, checking both static `MONSTER_SPRITE_DATA`/`DEATH_SPRITE_DATA` and the custom runtime registries. `drawMonsterDeath()` auto-generates a generic splat from the monster's primary color if no death sprite exists. Player sprites use `SHIRT` color placeholder resolved at draw time via `makePlayerColorMap()`. Attack/sword/heart sprites remain procedural (dynamic offsets). All original function names preserved as backward-compatible wrappers.
- **`tiles.js`** — Data-driven tile rendering. Shared drawing operations (`drawNoise`, `drawBricks`, `drawGridLines`, `drawHStripes`, `drawRects`, etc.) composed via `TILE_GENERATORS` dispatch table (one function per tile type). `createTileCanvas()` fills base color then delegates to the generator. Cached to offscreen canvases. Exposes `getTileCanvas(tileId, TS, TILE, SCALE)` and `TILE_COLORS`. Also defines `customTiles` runtime registry and `runTileRecipe()` interpreter for AI-generated tiles — recipes are JSON objects with named colors and an operations array (fill, noise, bricks, grid_lines, hstripes, vstripes, wave, ripple, rects, pixels). `getTileCanvas()` checks `customTiles` for string tile IDs before falling back to static generators.
- **`music.js`** — Background music. MP3 playback with crossfade. Server sends a `music` field per room (e.g. `village`, `tavern`, `chapel`, `overworld`, `dungeon1`–`dungeon4`); client maps it to a track URL via `MUSIC_TRACKS`. Falls back to `BIOME_MUSIC[biome]` if no music field. Exposes `MusicPlayer.start()`, `.stop()`, `.toggle()`, `.isPlaying()`, `.setRoom(roomId, biome, music)`. Auto-starts on login, toggled with M key.
- **`dungeon_layouts.py`** — Dungeon layout templates. Defines 11 Zelda-inspired 8x8 grid layouts (eagle, fortress, shield, hammer, lizard, dragon, demon, lion, death_mountain, skull, axe, crown). Each layout has a name, grid (X=room, .=empty), and entrance cell. Imported by `mud_server.py`.
- **`worldgen.py`** — Offline world generator. Creates ~104 `.room` files in `rooms/` directory. Defines 16x8 biome grid, builds MST connectivity graph, generates tilemaps with biome-specific features, places NPCs and monsters. Biome config consolidated in `BIOME_CONFIG` dict (base tile, border, decor, walkable tiles, music, monsters per biome). Run once with `python worldgen.py`.
- **`render_map.py`** — Standalone map renderer. Reads all `.room` files and renders `world_map.png` overview image. Requires Pillow. Run with `python render_map.py`.
- **`render_dungeon_rooms.py`** — Dungeon room template renderer. Renders all 64 dungeon room templates from `rooms/dungeon1/` as `dungeon_rooms.png` in an 8x8 grid. Requires Pillow.
- **`render_dungeons.py`** — Dungeon layout renderer. Reads `dungeon_layouts.py` and renders all layout shapes as `dungeon_layouts.png`. Requires Pillow.
- **`download_log.py`** — Local utility script. Fetches the server's event log via `/get-log`, saves it to `log_YYYYMMDD_HHMMSS.txt`, and clears the log on the server. Defaults to the Hetzner server; pass `http://localhost:8080` as arg for local dev.
- **`rooms/*.room`** — Room data files. Village rooms are hand-authored; overworld rooms are generated by `worldgen.py`. Plain text format with header (name, biome, music, exits), tilemap (2-char tile codes), and entity sections (NPCs, monsters). All rooms (village + overworld) are loaded from `.room` files at startup — there are no hardcoded room definitions in `mud_server.py`.
- **`rooms/dungeon1/*.room`** — Dungeon room templates (64 files). Same `.room` format but without exits (exits are auto-generated from layout adjacency at runtime). Used as a template pool — the dungeon instance system picks a random layout and assigns templates to cells.
- **`content_library.py`** — Library system for AI-generated content. `LibraryEntry` dataclass with id/role/tags/data. `ContentLibrary` class with fixed capacity, placeholder slots, tag-based queries (exact + fuzzy matching), expiry of oldest entries, and late-binding resolution (preferred → role+tags → role → generate). Persists to JSON. Free-form tags normalized on ingestion.
- **`behavior_engine.py`** — Data-driven monster AI. Rule evaluator (`evaluate_rules`) checks conditions top-to-bottom, first match wins. Conditions: `player_within`, `player_beyond`, `hp_below_pct`, `hp_above_pct`, `random_chance`, `always`/`default`, `can_attack`, `player_in_attack_range`. Movement actions: `wander` (random adjacent), `chase` (greedy toward nearest player), `flee` (away from nearest player), `patrol` (cycle waypoints relative to spawn), `hold` (stay still), `attack` (signal attack intent — actual execution in mud_server.py). Initialized by `mud_server.main()` via `init()` to receive shared state references. Monsters without behavior data default to `[{"default": "wander"}]`. Behavior data stored in `MONSTER_BEHAVIORS` dict, assigned to Monster instances at creation.
- **`ai_generator.py`** — Claude API integration for procedural dungeon content. Generates complete rooms (tilemap + monsters + tiles) in a single API call. System prompt specifies full sprite/tile/behavior format. Adapts prompts to library fullness: sparse → creative freedom, full → "use only these". Includes response validation (tilemap dimensions, doorway constraints, tile/monster formats, placement bounds), single retry on failure, rate limiting (5/min, 200/day), token usage tracking (persisted to `data/api_usage.json`). Few-shot examples included. Async `generate_room()` is the main entry point. Standalone test via `python ai_generator.py`. Uses `ANTHROPIC_API_KEY` env var and Claude Haiku model.
- **`PLAN_AI_GENERATION.md`** — Staged plan for AI-powered procedural content generation using Claude Haiku. Nine stages from tag system through library-managed dungeons. See file for full details.

**Protocol:** JSON over WebSocket.
- Client → Server: `login` (name, description), `move` (direction), `attack`, `chat` (text), `ping`
- Server → Client: `login_ok` (color_index, hp, max_hp), `room_enter` (tilemap + players + guards + monsters + exits + biome + music + exit_direction + hp + max_hp + optional custom_sprites + custom_death_sprites + custom_tiles), `player_moved`, `player_entered`, `player_left`, `attack` (name, direction), `chat`, `dance`, `info`, `error`, `pong`, `monster_moved`, `monster_killed`, `monster_hit`, `monster_spawned`, `player_hurt` (name, hp, max_hp, x, y, knockback), `you_died` (x, y), `player_died` (name, x, y, color_index), `hp_update` (hp, max_hp), `heart_spawned` (id, x, y), `heart_collected` (id)

**State:** All in-memory. Players tracked in `dict[websocket, Player]`. Rooms loaded from `.room` files into the `ROOMS` dict at startup (15x11 tilemaps). NPCs and monsters are also parsed from `.room` files into `GUARDS` and `MONSTER_TEMPLATES` dicts. State resets on server restart. An `event_log` list records joins, leaves, and chat messages (with timestamps); exposed via `GET /get-log` which returns the log as plain text and clears it.

**World map:** 112+ rooms total. Village (8 rooms): Town Square (center) connects to Blacksmith (north), Forest Path (south), Tavern (east), Old Chapel (west). Old Chapel → Chapel Sanctum (west). Forest Path → Clearing → overworld gate (ow_0_7). The overworld is a 16x8 grid of ~100 rooms across 9 biomes (forest, mountain, desert, swamp, graveyard, castle, plains, lake, river) plus 4 interior rooms (2 caves, oasis, witch hut). Tavern has stairs up to Tavern Upper Floor. The Clearing also has stairs down to the dungeon entrance.

**NPCs:** NPCs defined in `.room` files via `npc Name X Y sprite dialog` lines (sprite is the sprite type key, e.g. `guard`, `smith`, `priest`, `barmaid`, `amara`, `witch`, `ghost`, `ghost_knight`, `ranger`, `farmer`, `nomad`, `merchant`, `elder`, `fisher`). Loaded into the `GUARDS` dict at startup. Each NPC has a name, position, sprite type, and dialog line. NPCs are rendered client-side via `drawNPC(ctx, px, py, sprite, S)` which dispatches to the appropriate sprite function from `NPC_SPRITES` map. Players can't walk on NPC tiles. Walking adjacent triggers the NPC's dialog as a chat bubble (broadcast to room), with a 10-second per-player cooldown to prevent spam. Quest-aware NPCs (Amara, Priest, Smith, Barmaid) have registered handlers in `NPC_HANDLERS` that override static dialog.

**Monsters:** Monster templates defined in `.room` files via `monster kind X Y` lines, loaded into the `MONSTER_TEMPLATES` dict at startup. Five built-in types: slime (forest/plains, 1HP, 1dmg), bat (cave/graveyard, 1HP, 1dmg, fast), scorpion (desert, 2HP, 2dmg), skeleton (graveyard/castle/dungeon, 2HP, 3dmg), swamp_blob (swamp, 1HP, 1dmg). Lifecycle: spawn when first player enters, despawn when all leave. Monsters move via `monster_tick()` with per-kind intervals, using the data-driven behavior engine (`behavior_engine.py`). Built-in monsters default to random wander; custom monsters can have behavior rules (chase, flee, patrol, hold, attack, etc.). Multi-HP monsters take multiple hits — server sends `monster_hit` on damage and `monster_killed` on death. Protocol messages: `monster_moved`, `monster_killed`, `monster_hit`, `monster_spawned` (optionally carries `custom_sprites`/`custom_death_sprites`). Killed monsters have a 10% chance to drop a heart pickup. **Dynamic monster types** can be registered at runtime via `register_monster_type(data)` which validates and adds to `MONSTER_STATS`, `CUSTOM_SPRITES`, optionally `CUSTOM_DEATH_SPRITES`, and optionally `MONSTER_BEHAVIORS`. **Dynamic tiles** via `register_tile_type(data)` which validates and adds to `CUSTOM_TILE_RECIPES`. Both have validation functions (`validate_monster()`, `validate_tile()`) that check stat ranges, sprite bounds, color formats, behavior rule/action names, attack types, tile op names, and grid coordinates. The `room_enter` message carries custom sprite/tile data to the client, which merges it into `customMonsterSprites`/`customDeathSprites`/`customTiles` registries. Client rendering uses generic `drawMonsterSprite()`/`drawMonsterDeath()` for all monster kinds (no hardcoded if/else chains). Custom tiles use `runTileRecipe()` interpreter. Chat command `/debug_spawn <kind>` spawns test monsters (7 built-in: fire_slime, ice_bat, shadow_skull, skeleton_archer, ghost_teleporter, war_boar, flame_mage; also works with any registered or built-in kind).

**Monster Attacks (Stage 5):** Monsters can have data-driven attacks defined in `behavior.attacks` array. Five attack types: `melee` (strike adjacent player without moving), `projectile` (fire colored projectile in cardinal direction toward player, moves 1 tile per 0.15s tick), `charge` (requires player on same row/column; 2-tick sequence: prep tick locks direction + shows pulsing red lane warning + monster shakes, next tick dashes in locked direction — player can dodge between ticks), `teleport` (fade out, 0.5s delay, reappear adjacent to player, damage on landing), `area` (warning indicator on tiles within range, 0.75s delay, then damage all players in area). Each attack has `type`, `range`, `damage`, `cooldown` (per-attack cooldown in seconds), and optionally `sprite_color` (for projectiles). Behavior conditions `can_attack` (cooldown ready + player in range) and `player_in_attack_range` control when monsters use attacks. The `attack` action in behavior rules triggers `execute_monster_attack()` which selects the first usable attack. Projectiles are tracked per-room in `room_projectiles` dict and moved by `projectile_tick()` async loop. Teleport/area attacks use `asyncio.create_task()` for delayed effects. Client renders: projectile glow dots, pulsing area warnings on ground tiles, charge trail flashes, teleport fade in/out on monster alpha, melee/projectile hit white flashes. Protocol messages: `projectile_spawned`, `projectile_moved`, `projectile_hit`, `projectile_gone`, `monster_attack`, `charge_prep`, `monster_charged`, `teleport_start`, `teleport_end`, `area_warning`, `area_attack`.

**Player Health:** Players have 6 HP (displayed as 3 hearts in HUD). Contact damage occurs when a player walks onto a monster or a monster hops onto a player — damage amount varies by monster kind. On damage: 1.5s invincibility frames (client flickers sprite), knockback away from facing direction, red flash overlay. At 0 HP: death animation (spin + fade to black + "You died!"), then respawn at Town Square after 5.5s delay with full HP. The Barmaid NPC in the tavern heals players to full HP.

**Heart pickups:** When a monster is killed, there's a 10% chance it drops a heart on its tile. Hearts bounce on the ground and restore 2 HP when walked over. Hearts are tracked per-room in `room_hearts` and cleaned up when all players leave.

**Dungeons:** Procedurally generated dungeon instances, entered via stairs down in the Clearing room. Each instance uses a random layout from `dungeon_layouts.py` (11 Zelda-inspired 8x8 grid shapes) and assigns random room templates from `rooms/dungeon1/` (64 templates) to each cell. Exits between dungeon rooms are auto-generated from grid adjacency; unused exits are walled off. The entrance room gets stairs up back to the Clearing. Each instance gets a random dungeon music track (1 of 4). Dungeon rooms use the `dungeon` biome with 4 tile types: dungeon_wall (DW), dungeon_floor (DF), pillar (PL), sconce_wall (SC). Cleared rooms (all monsters killed) don't respawn. The entire dungeon instance is destroyed when all players leave. A new instance is created on demand when anyone enters.

**Music:** Ten mp3 tracks served as `/music.mp3` (village), `/music_tavern.mp3`, `/music_chapel.mp3`, `/music_overworld.mp3`, and `/music_dungeon1.mp3` through `/music_dungeon6.mp3`. Each `.room` file specifies a `music` field (`village`, `tavern`, `chapel`, `overworld`, or `dungeon1`–`dungeon6`). The server sends this field in `room_enter`; the client maps it to a track URL via `MUSIC_TRACKS`. Fallback: `BIOME_MUSIC[biome]` → overworld default (dungeon biome falls back to dungeon1). `music.js` switches tracks per room via `MusicPlayer.setRoom(roomId, biome, music)`. Toggled with M key.

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
