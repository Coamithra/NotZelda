# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Legends of Amara** — a browser-based multiplayer MUD rendered as a Zelda-style top-down visual game. Players connect via browser, log in with a name/description, walk around tile-based rooms with arrow keys/WASD, and chat via speech bubbles.

For detailed module-by-module descriptions, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## General Rules

When pushing to git make sure to update CLAUDE.md first!

**NEVER run `python worldgen.py` without explicit user permission.** The overworld `.room` files in `rooms/` contain hand-edited changes that worldgen will overwrite. Running it will destroy manual edits. Always warn the user that data will be lost before re-running.

**After any changes to `server/ai_generator.py`, `tools/content_viewer.py`, or `.env`, run `python tools/test_api_leak.py` to verify the Anthropic API key cannot leak into CLI subprocess calls.** The game uses the Claude CLI (subscription-based) for AI generation — the API must never be called directly. All 4 tests must pass.

**Avoid calling the Anthropic API directly unless expressly permitted by the user.** If you must call it (e.g. for testing), always set `metadata={"user_id": "claude-code"}` so the call is identifiable in the Console. Claude API docs: https://platform.claude.com/docs/en/api/overview

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

## Key Gotchas & Non-Obvious Conventions

- **Client script load order matters**: `game_state.js` → `title.js` → `tiles.js` → `sprite_data.js` → `sprites.js` → `music.js` → `renderer.js` → `fx.js` → `net.js` → inline init/gameLoop → `input.js`
- **Client state**: all mutable state lives on the shared `G` namespace object (`game_state.js`)
- **Server state**: all mutable state lives on the `GameState` singleton (`from server.state import game`)
- **Import order** avoids circular deps: `constants` → `state` → `models` → `net` → `rooms` → `validation` → `dungeon_types` → `dungeons` → `quests` → `lifecycle` → `commands` → `combat` → `debug_monsters` → `mud_server`. Combat uses lazy imports for commands; commands imports from lifecycle.
- **Command queue architecture**: Websocket messages are never processed inline. The handler just appends `(msg_type, data)` to `player.command_queue` (a deque). The unified `game_tick()` loop drains all queues via `process_player_commands()` before ticking monsters/projectiles. All command processors are sync and append to the `msgs` batch. `ping` is the only message handled directly (latency measurement). Command processors live in `server/commands.py`. Player position updates (`position_update`), `face`, `attack`, and `chat` are the queued message types.
- **Single unified `game_tick()` loop** at ~30Hz (`TICK_INTERVAL = 1/30` in `constants.py`). Processes commands, then ticks players, monsters, and projectiles (projectiles use a time accumulator to keep their ~150ms effective rate). All synchronous with message batching — no `await` mid-tick. Messages collected as tuples, flushed after the full tick. This prevents dungeon teardown crashes.
- **Room transitions**: player is temporarily removed from `game.players` during `do_room_transition()` so tick loops can't target them mid-swap. Re-added in `finally` block.
- **Dungeon room resolution is synchronous** — no JIT AI generation. Custom rooms resolve from the library pool or fall back to precreated.
- **All content is data-driven**: Tiles, monsters, and NPC sprites are loaded from JSON files in `data/` at startup (`tiles.json`, `monsters.json`, `npc_sprites.json`). No hardcoded tile IDs, sprite data, or monster stats in code. All tilemaps use 2-char string codes (`"GR"`, `"DW"`, etc.). Server sends tile recipes, monster sprites, and NPC sprites to client via `room_enter` messages. Client registries: `customTiles`, `customMonsterSprites`, `customDeathSprites`, `customNPCSprites`. The `WALKABLE` set on the client starts empty and is populated from server data on each room enter.
- **Tile system**: `server/constants.py` has no tile constants — all tile definitions live in `data/tiles.json`. `game.custom_tile_recipes` holds ALL tile recipes (permanent + AI-generated). `is_walkable_tile()` checks only `custom_tile_recipes`. Room files store 2-char string codes directly. Tiles can have an optional `"bright": true` flag that adds a flickering radial glow effect on the client (used for torches, braziers, fireplaces).
- **Dungeon content config**: `server/dungeon_content.py` declares which monster/tile IDs are permanent members of each dungeon's content library (ID lists only — all recipes live in `data/monsters.json` and `data/tiles.json`). The library system tracks permanent vs AI-generated entries for capacity counting and deprecation.
- **All rooms loaded from `.room` files** — no hardcoded room definitions in Python.
- **AI generation uses Claude CLI by default** (`AI_BACKEND=cli`), not the API. The `.env` must NOT set `AI_BACKEND=api`.
- **API path uses prompt caching** — system prompts are marked with `cache_control: {"type": "ephemeral"}` for 5-minute caching. `UsageTracker` tracks cache write/read tokens separately with accurate cost multipliers (1.25x write, 0.10x read).
- **AI prompt templates** are in `server/prompts/*.txt` — edit the text files directly, no Python changes needed.
- **Sprites/tiles use `[colorKey, x, y, w, h]` rect layer format** everywhere (client + server validation + AI prompts).
- **Tile properties** (walkable, etc.) live in `custom_tile_recipes[tile_id]` — no separate sets. `is_walkable_tile()` reads from the recipe dict. Client receives walkable flag via `custom_tiles` in `room_enter` and adds to its `WALKABLE` set. NPC sprites are sent via `npc_sprites` field in `room_enter`.
- **Boss choir overlay**: when a player hits any boss monster (`is_boss` flag in stats), an ethereal choir track plays for all other dungeon players, volume scaled by BFS distance from boss room. Managed via `boss_engaged` on `DungeonInstance` (reset to `False` on boss death), choir updates sent automatically by `send_room_enter()`. Choir track is dynamic — matched to the randomized boss music track (e.g. boss2 → music_boss2_choir.mp3), sent via `choir_track` field in `boss_choir_start` messages.
- **Multi-dungeon architecture**: Multiple dungeon types supported via `server/dungeon_types.py` `DUNGEON_TYPES` dict. Each type config has: layouts, music/boss tracks, biome, theme (for AI generation), exit room, wall tile, entrance exit, boss/treasure template IDs, and optional per-type library capacities (`room_capacity`, `monster_capacity`, `tile_capacity`). State: `game.active_dungeons` (type_id → DungeonInstance), `game.room_to_dungeon` (room_id → type_id for O(1) lookup), `game.content_libraries` (type_id → {rooms, monsters, tiles}), `game.deprecated_content` (type_id → {monsters, tiles}). Use `get_dungeon_for_room(room_id)` to find the instance for any room. Room IDs are `{type_id}_{col}_{row}` (e.g. `d1_3_3`, `d2_0_1`). Dungeon entrance exits in `.room` files map to types via `ENTRANCE_TO_TYPE`. Content libraries are per-type with files at `data/{type_id}_*_library.json`. Precreated content is per-type via `PRECREATED_CONTENT` dict in `dungeon_content.py`.
- **Dungeon types**: d1 = Dark Dungeon (8x8 layouts, 64 rooms, DW/DF tiles, entrance in `clearing`), d2 = Water Temple (3x3 layouts, 7 rooms, TW/TF/CR/WA/SH tiles, entrance in `forest_path`). Wall tile for unused exits is configurable per type (`wall_tile` in config). Water temple rooms have ambient mist FX (client-side, triggered by `dungeon_type` field in `room_enter`).
- **Boss monsters** have `"boss": True` in their stats dict. `Monster.is_boss` reads this flag. Boss detection in combat (choir engagement, music silencing, room clearing) uses `monster.is_boss` — not hardcoded to a specific kind.
- **Boss music is randomized**: Boss tracks come from `DUNGEON_TYPES[type_id]["boss_tracks"]`. A random boss track is picked at dungeon creation and stored as `DungeonInstance.boss_track`, same pattern as ambient `music_track`.
- **Dungeon items (Map & Compass)**: Each dungeon instance places a Map and Compass in two random non-special cells. Items are placed on reachable walkable interior tiles at room resolution time. Per-dungeon-instance state: `instance.item_cells` (cell assignments), `instance.dungeon_items` (room→item list), `instance.collected_items` (set of collected types). Once ANY player picks up an item, ALL dungeon players benefit. Map reveals minimap (uniform layout); Compass adds boss room marker and blinking player dot. Items reset when dungeon is destroyed. Server sends `dungeon_collected`, `dungeon_items`, `dungeon_boss_cell` in `room_enter`. Pickup triggers `item_obtained` (collector), `item_effect` (room), `dungeon_item_collected` (all dungeon players). Client state: `G.dungeonState` (collected set, cells, boss cell), `G.dungeonGroundItems`, `G.itemPickupActive`, `G.itemPickupEffects`.
- **Item pickup animation**: Player enters hold-item pose (`ITEM_HOLD_FRAME` in `sprite_data.js`, `drawPlayerHoldItem` in `sprites.js`). Movement frozen for 2.5s (`ITEM_PICKUP_DURATION`). Item floats above head with golden glow and sparkles (`drawItemPickupOverlay`). Used for dungeon map/compass pickups. Sword pickup keeps its existing separate animation.
- **NES Zelda-style half-tile free movement**: players move continuously while keys are held, at `PLAYER_SPEED=4.0` tiles/sec. Positions are sub-tile floats. Axis alignment: switching direction smoothly snaps the perpendicular coordinate to the nearest half-tile. Wall overlap: collision only checks the bottom half of the 1×1 hitbox (`y+0.5` to `y+1`), so sprite heads can overlap walls regardless of direction (NES Zelda style). `_is_position_walkable()` checks all tiles overlapping the bottom-half hitbox. All entity collisions (monsters, hearts, items, guards, projectiles) use float AABB overlap. Monsters still use the old tile-to-tile walk system (`WALK_TIME`). Client collision uses the aligned (snap-target) half-tile for the perpendicular axis, so players can slip through 1-tile gaps even when slightly misaligned (NES Zelda corner-nudge). Movement is blocked during dungeon conjuring animation (`G.conjuring`).
- **Movement networking model**: Client moves locally at 60fps and reports to server when `Math.round(precisePos * 2) / 2` changes (i.e. the nearest half-tile snaps to a new value — triggers at 0.25 past each half-tile boundary). Client sends `position_update` with snapped `{x, y, direction}`. Server validates: half-tile snapped, rate limit (`POSITION_UPDATE_RATE`), distance (`MAX_MOVE_PER_UPDATE`), walkability, guard collision. On accept: updates `player.x/y`, relays `player_walk_half` to other clients (excluding sender). On reject: sends `reconcile` with server position. Other clients receive `player_walk_half` and animate a smooth interpolation over `HALF_WALK_TIME_MS` (125ms). Player state: `self.x/y` (floats), `self.last_pos_update_time`, `self.last_reported_x/y`. Client state: `G.preciseX/Y` (local float), `G.lastReportedX/Y` (last sent to server).
- **Knockback system**: On damage, player is knocked back 1 tile (snapped to half-tile) away from damage source. Direction uses **previous positions** (before overlap) for contact damage, current positions for projectile/area/charge damage. Fallback: push away from facing direction if delta is zero. 200ms client-side hitstun (`G.stunUntil`) freezes controls. Monster contact collision uses interpolated walk position (`_get_monster_visual_pos`) not just committed tile. `_apply_damage()` accepts `prev_player_x/y`, `prev_source_x/y`, `source_w/h` for accurate knockback.
- **Collision grace period**: Contact damage uses a 100ms buffer (`COLLISION_GRACE_PERIOD`) for corner-scrape forgiveness. First AABB overlap records a pending collision on `player.pending_collisions` (keyed by `id(monster)`). `_resolve_pending_collisions()` in `game_tick()` re-validates (player alive, same room, monster alive, still overlapping) before applying damage. Pending collisions cleared on room change. Prevents false hits when player and monster slide past each other perpendicular.
- **Collision debug overlay** (debug mode, backtick toggle): `G.debugCollision` shows player AABB (green, bottom-half bright), monster AABBs (red), and 5-second hit ghosts with cyan (pre-knockback player), red (source AABB + previous dashed), yellow dashed (knockback destination), orange arrow (prev_source→prev_player delta). `renderCollisionDebug()` in `renderer.js`. Server sends `debug_*` fields in `player_hurt` messages.
- **Heart HUD wraps**: `renderHeartsHUD()` wraps at 10 hearts per row, right-aligned, stacking downward.
- **Monster state machine**: mirrors the player pattern. `monster.state` (`"idle"`, `"walking"`, `"charging"`, `"teleporting"`, `"area"`) + `monster.state_data`. Two timing knobs: `walk_time` (seconds per tile animation, default 0.25) and `decision_time` (seconds between behavior evaluations, default 2.0). Decision timer runs continuously — if `decision_time <= walk_time`, monsters move continuously with no pause. Multi-tile walks via `distance` param on move actions. Everything runs in the unified `game_tick()` loop — walk progression, behavior evaluation, warmup countdowns. Wire protocol: `monster_walk_started`/`monster_walk_complete` for smooth walks; existing `monster_moved` for instant position changes (charges/teleports).
- **Client player state machine**: `G.state` is an enum (`"idle"`, `"attacking"`, `"dying"`) with `G.stateData` holding state-scoped variables (replaced on every `setState()` call). Movement happens continuously in the `"idle"` state while direction keys are held — `playerTick()` computes local movement, collision, and position reporting each frame. Attacks are optimistic (animation starts immediately, server handles hit detection via float AABB overlap — sword is a 1×1 hitbox at `player.x+dx, player.y+dy` vs monster footprint). Holding space chains attacks. Reconcile messages hard-reset to idle and snap `preciseX/Y`.
- **NPC gifts are data-driven from `.room` files**: NPCs can give items to players through AI dialog. Room file format: `npc Name X Y sprite Dialog | Personality | Item Name:condition text`. The third `|` section is optional. Gift tracking flags are auto-generated as `gift_{room}_{npc}_{item}` for uniqueness. Special item effects (sword animation, heart container HP boost) are mapped in `GIFT_EFFECTS` in `npc_chat.py` by display name. The AI includes `[GIVE_ITEM]` in its response when it judges the condition is met (same pattern as `[CALL_GUARDS]`).
- **Title screen** (`client/title.js`): NES Zelda-style canvas-rendered title screen. Renders at 240×176 virtual pixels, scaled 3× to 720×528. Scene: rocky cliff walls (brick pattern), twinkling stars, mountains, pine trees, waterfall (left), flickering torch (right), pixel-art sword with gleam, golden title frame. Text rendered at full resolution for crispness. Chapel music attempts autoplay on load, falls back to first user interaction. `TITLE.phase`: `"title"` → `"login"` (Enter/click reveals login card) → `"done"` (on `login_ok`). `TITLE.hide()` called from `net.js` on successful login.
- **Heart HUD is dynamic**: `renderHeartsHUD()` derives heart count from `G.myMaxHp / 2`, not hardcoded. Heart containers add +2 max HP (1 heart).
- **Juice/FX system** (`client/fx.js`): Client-side visual effects — particle system (capped at 100), screen shake (CSS transform), hit pause (freezes game loop updates for ~40-60ms on impact), sword slash arcs, floating damage numbers, damage vignette (red edge flash on hurt), monster death corpses (last death frame lingers on ground until room exit), dust puffs on movement start, monster spawn pop (scale 0→1.15→1.0 with stagger), knockback dust trail. All FX state lives on `G` namespace. Particle system: `spawnBurst()` for radial bursts, `spawnParticle()` for individual. Screen shake: `triggerShake(intensity, durationMs)` — stronger shakes override weaker ones. Effects are triggered from `net.js` message handlers (`monster_hit`, `monster_killed`, `player_hurt`, etc.).
- **Monster death sprites**: 4-frame death animations in `data/monsters.json` under `death_sprite`. Frame 4 is a visible corpse/remains (not a vanishing fade). AI prompt (`monster_sprite_system.txt`) requests `death_sprite` alongside `sprite`. Fallback: generic splat if AI omits it or for monsters without custom death sprites. Corpses rendered by `renderCorpses()` in `fx.js`, cleared on room enter.
- **`websockets` must stay at 12.0** — v16+ breaks the `process_request` API.

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
- **Deploying updates:** `cd /opt/NotZelda && git pull && systemctl restart notzelda`

## Dependencies

- Python 3.12+
- `websockets` (12.0 — pinned, v16+ breaks the `process_request` API)
- `pyngrok` (optional, for local dev tunneling)
