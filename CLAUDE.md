# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A browser-based multiplayer MUD (Multi-User Dungeon) rendered as a Zelda-style top-down visual game. Players connect via browser, log in with a name/description, walk around tile-based rooms with arrow keys/WASD, and chat via speech bubbles.

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
│   ├── dungeon1/          # Dungeon ambient (a-f), boss1/2/3 + choir variants
│   └── dungeon2/          # Water temple ambient + boss tracks
├── rooms/                 # .room data files + dungeon template subdirs
│   ├── dungeon1/          # d1 (Dark Dungeon) room templates (64 + boss + treasure)
│   └── dungeon2/          # d2 (Water Temple) room templates (7 + boss + treasure)
├── data/                  # Game data files + runtime libraries
│   ├── builtin_tiles.json     # All 42 tile definitions (loaded at startup)
│   ├── builtin_monsters.json  # 5 overworld monster definitions (loaded at startup)
│   └── npc_sprites.json       # 14 NPC sprite definitions (loaded at startup)
├── tools/                 # Dev utilities (renderers, content viewer, tests)
├── docs/                  # Architecture docs, generated images, planning docs
├── deploy/                # Nginx config, redirect page
└── local_ignore/          # Local-only files (SSH keys, archives) — gitignored
```

## Key Gotchas & Non-Obvious Conventions

- **Client script load order matters**: `game_state.js` → `tiles.js` → `sprite_data.js` → `sprites.js` → `music.js` → `renderer.js` → `net.js` → inline init/gameLoop → `input.js`
- **Client state**: all mutable state lives on the shared `G` namespace object (`game_state.js`)
- **Server state**: all mutable state lives on the `GameState` singleton (`from server.state import game`)
- **Import order** avoids circular deps: `constants` → `state` → `models` → `net` → `rooms` → `validation` → `dungeon_types` → `dungeons` → `quests` → `lifecycle` → `combat` → `debug_monsters` → `mud_server`. Combat uses lazy imports for lifecycle.
- **Single unified `game_tick()` loop** at ~30Hz (`TICK_INTERVAL = 1/30` in `constants.py`). Ticks players, monsters, and projectiles (projectiles use a time accumulator to keep their ~150ms effective rate). All synchronous with message batching — no `await` mid-tick. Messages collected as tuples, flushed after the full tick. This prevents dungeon teardown crashes.
- **Room transitions**: player is temporarily removed from `game.players` during `do_room_transition()` so tick loops can't target them mid-swap. Re-added in `finally` block.
- **Dungeon room resolution is synchronous** — no JIT AI generation. Custom rooms resolve from the library pool or fall back to precreated.
- **All content is data-driven**: Tiles, monsters, and NPC sprites are loaded from JSON files in `data/` at startup (`builtin_tiles.json`, `builtin_monsters.json`, `npc_sprites.json`). No hardcoded tile IDs, sprite data, or monster stats in code. All tilemaps use 2-char string codes (`"GR"`, `"DW"`, etc.). Server sends tile recipes, monster sprites, and NPC sprites to client via `room_enter` messages. Client registries: `customTiles`, `customMonsterSprites`, `customDeathSprites`, `customNPCSprites`. The `WALKABLE` set on the client starts empty and is populated from server data on each room enter.
- **Tile system**: `server/constants.py` has no tile constants — all tile definitions live in `data/builtin_tiles.json`. `game.custom_tile_recipes` holds ALL tile recipes (built-in + AI-generated). `is_walkable_tile()` checks only `custom_tile_recipes`. Room files store 2-char string codes directly.
- **All rooms loaded from `.room` files** — no hardcoded room definitions in Python.
- **AI generation uses Claude CLI by default** (`AI_BACKEND=cli`), not the API. The `.env` must NOT set `AI_BACKEND=api`.
- **API path uses prompt caching** — system prompts are marked with `cache_control: {"type": "ephemeral"}` for 5-minute caching. `UsageTracker` tracks cache write/read tokens separately with accurate cost multipliers (1.25x write, 0.10x read).
- **AI prompt templates** are in `server/prompts/*.txt` — edit the text files directly, no Python changes needed.
- **Sprites/tiles use `[colorKey, x, y, w, h]` rect layer format** everywhere (client + server validation + AI prompts).
- **Tile properties** (walkable, etc.) live in `custom_tile_recipes[tile_id]` — no separate sets. `is_walkable_tile()` reads from the recipe dict. Client receives walkable flag via `custom_tiles` in `room_enter` and adds to its `WALKABLE` set. NPC sprites are sent via `npc_sprites` field in `room_enter`.
- **Boss choir overlay**: when a player hits any boss monster (`is_boss` flag in stats), an ethereal choir track plays for all other dungeon players, volume scaled by BFS distance from boss room. Managed via `boss_engaged` on `DungeonInstance` (reset to `False` on boss death), choir updates sent automatically by `send_room_enter()`. Choir track is dynamic — matched to the randomized boss music track (e.g. boss2 → music_boss2_choir.mp3), sent via `choir_track` field in `boss_choir_start` messages.
- **Multi-dungeon architecture**: Multiple dungeon types supported via `server/dungeon_types.py` `DUNGEON_TYPES` dict. Each type config has: layouts, music/boss tracks, biome, theme (for AI generation), exit room, wall tile, entrance exit, boss/treasure template IDs, and optional per-type library capacities (`room_capacity`, `monster_capacity`, `tile_capacity`). State: `game.active_dungeons` (type_id → DungeonInstance), `game.room_to_dungeon` (room_id → type_id for O(1) lookup), `game.content_libraries` (type_id → {rooms, monsters, tiles}), `game.deprecated_content` (type_id → {monsters, tiles}). Use `get_dungeon_for_room(room_id)` to find the instance for any room. Room IDs are `{type_id}_{col}_{row}` (e.g. `d1_3_3`, `d2_0_1`). Dungeon entrance exits in `.room` files map to types via `ENTRANCE_TO_TYPE`. Content libraries are per-type with files at `data/{type_id}_*_library.json`. Precreated content is per-type via `PRECREATED_CONTENT` dict in `dungeon_content.py`.
- **Dungeon types**: d1 = Dark Dungeon (8x8 layouts, 64 rooms, DW/DF tiles, entrance in `clearing`), d2 = Water Temple (3x3 layouts, 7 rooms, TW/TF/CR tiles, entrance in `forest_path`). Wall tile for unused exits is configurable per type (`wall_tile` in config).
- **Boss monsters** have `"boss": True` in their stats dict. `Monster.is_boss` reads this flag. Boss detection in combat (choir engagement, music silencing, room clearing) uses `monster.is_boss` — not hardcoded to a specific kind.
- **Boss music is randomized**: Boss tracks come from `DUNGEON_TYPES[type_id]["boss_tracks"]`. A random boss track is picked at dungeon creation and stored as `DungeonInstance.boss_track`, same pattern as ambient `music_track`.
- **Movement uses server-side walk state**: walks are continuous (250ms per tile for players), not instant teleports. Server tracks `Player.walk` dict with origin, target, start_time, committed flag. The unified `game_tick()` loop handles midway commit (position + collision) and walk completion for both players and monsters via `_tick_players()` and `_tick_all_monsters()`. Client sends `walk` (with origin), `cancel_walk`, and `face` messages. Server responds with `reconcile` (full state snapshot) on any disagreement. Cancel window is 90ms; `LATENCY_COMP=66ms` is the leeway constant. See `docs/PLAN_WALK_SYSTEM.md` for the full design.
- **Monster state machine**: mirrors the player pattern. `monster.state` (`"idle"`, `"walking"`, `"charging"`, `"teleporting"`, `"area"`) + `monster.state_data`. Two timing knobs: `walk_time` (seconds per tile animation, default 0.25) and `decision_time` (seconds between behavior evaluations, default 2.0). Decision timer runs continuously — if `decision_time <= walk_time`, monsters move continuously with no pause. Multi-tile walks via `distance` param on move actions. Everything runs in the unified `game_tick()` loop — walk progression, behavior evaluation, warmup countdowns. Wire protocol: `monster_walk_started`/`monster_walk_complete` for smooth walks; existing `monster_moved` for instant position changes (charges/teleports).
- **Client input events are buffered**: direction key presses/releases are pushed to `G.inputEvents` with real timestamps and drained at the start of each game tick. This ensures inter-frame key releases (e.g., rapid tapping) are detected even if the frame arrives after the cancel window.
- **Client player state machine**: `G.state` is an enum (`"idle"`, `"walking"`, `"attacking"`, `"dying"`) with `G.stateData` holding state-scoped variables (replaced on every `setState()` call). Each state handles its own input and tick logic in `playerTick()`. Attacks are optimistic (animation starts immediately, server handles hit detection). Holding space chains attacks; holding space while walking attacks on landing; space during cancel window cancels walk and attacks. Reconcile messages hard-reset to idle and clear all animations.
- **NPC gifts are data-driven from `.room` files**: NPCs can give items to players through AI dialog. Room file format: `npc Name X Y sprite Dialog | Personality | Item Name:condition text`. The third `|` section is optional. Gift tracking flags are auto-generated as `gift_{room}_{npc}_{item}` for uniqueness. Special item effects (sword animation, heart container HP boost) are mapped in `GIFT_EFFECTS` in `npc_chat.py` by display name. The AI includes `[GIVE_ITEM]` in its response when it judges the condition is met (same pattern as `[CALL_GUARDS]`).
- **Heart HUD is dynamic**: `renderHeartsHUD()` derives heart count from `G.myMaxHp / 2`, not hardcoded. Heart containers add +2 max HP (1 heart).
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
