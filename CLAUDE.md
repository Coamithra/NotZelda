# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Legends of Amara** — a browser-based multiplayer MUD rendered as a Zelda-style top-down visual game. Players connect via browser, log in with a name/description, walk around tile-based rooms with arrow keys/WASD, and chat via speech bubbles.

For detailed module descriptions and game system documentation, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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

## Key Conventions

- **Client state**: all mutable state lives on the shared `G` namespace object (`game_state.js`).
- **Server state**: all mutable state lives on the `GameState` singleton (`from server.state import game`).
- **All content is data-driven**: tiles, monsters, NPC sprites loaded from JSON in `data/`. No hardcoded tile IDs, sprite data, or monster stats in code. Tilemaps use 2-char string codes (`"GR"`, `"DW"`). Sprites/tiles use `[colorKey, x, y, w, h]` rect layer format everywhere.
- **All rooms loaded from `.room` files** — no hardcoded room definitions in Python.
- **AI prompt templates** are in `server/prompts/*.txt` — edit the text files directly, no Python changes needed.
- **AI generation uses Claude CLI by default** (`AI_BACKEND=cli`), not the API. The `.env` must NOT set `AI_BACKEND=api`.
- **Boss monsters** have `"boss": True` in their stats dict. Use `monster.is_boss` — never hardcode boss checks to a specific kind.
- **Trap rooms** (lock-in): dungeon rooms with 3+ monsters have a 1/3 chance of locking doors until all monsters are defeated. Boss rooms always lock. Decided at resolution time in `_resolve_room_from_entry()`. Runtime lock state tracked in `game.locked_rooms`. `CD` tile = closed door. Dungeon items are hidden and non-pickable during trap lockdown.
- **Monster knockback**: non-boss monsters get knocked back 1 tile in the attack direction when hit (if they survive). Server cancels any in-progress walk state. Client uses a separate `knockbackSlide` state (not `walkState`) for a 200ms easeOutQuad slide animation.
- **Sword hitbox**: 1.5 tiles in the attack direction (extends 0.5 tiles back into the player's own tile), 1 tile perpendicular. This lets players hit monsters overlapping their position.
- **Player knockback slide**: `G.knockbackSlide` in `client.html` game loop — 200ms easeOutQuad, separate from walk interpolation. Other players and monsters each use their own `knockbackSlide` object.
- **Water mist** (d2 only): `renderWaterMist()` in `renderer.js` scales wisp count by water tile coverage (WA=1pt, SH=0.5pt, max 40). Opacity stays constant; density increases with more water.
- **Dungeon map vs compass**: map reveals room layout but does NOT show current position. Compass adds blinking yellow dot for current room.
- **Room geometry constants** live in `server/constants.py`: `DOORWAY_TILES`, `ALL_DOORWAY_TILES`, `bfs_reachable()`. Use `bfs_reachable()` instead of inline BFS for tile reachability checks.

## Key Gotchas

- **Client script load order matters**: `game_state.js` → `title.js` → `tiles.js` → `sprite_data.js` → `sprites.js` → `music.js` → `renderer.js` → `fx.js` → `net.js` → inline init/gameLoop → `input.js`
- **Import order** avoids circular deps: `constants` → `state` → `models` → `net` → `rooms` → `validation` → `dungeon_types` → `dungeons` → `quests` → `lifecycle` → `commands` → `combat` → `debug_monsters` → `mud_server`. Combat uses lazy imports for commands; commands imports from lifecycle.
- **Command queue**: websocket messages are never processed inline — handler appends to `player.command_queue`, drained by `game_tick()`. Only `ping` is handled directly.
- **game_tick() is synchronous** with message batching — no `await` mid-tick. Messages collected as tuples, flushed after the full tick. This prevents dungeon teardown crashes.
- **Room transitions**: player is temporarily removed from `game.players` during `do_room_transition()` so tick loops can't target them mid-swap.
- **Dungeon room resolution is synchronous** — no JIT AI generation. Custom rooms resolve from the library pool or fall back to precreated.
- **Tile properties** live in `custom_tile_recipes[tile_id]` — no separate walkability sets. `is_walkable_tile()` reads from the recipe dict.
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
