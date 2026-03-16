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
├── music/                 # MP3 tracks (village.mp3, dungeon_a.mp3, etc.)
├── rooms/                 # .room data files + dungeon1/ templates
├── data/                  # Runtime data (libraries, API usage) — gitignored
├── tools/                 # Dev utilities (renderers, content viewer, tests)
├── docs/                  # Architecture docs, generated images, planning docs
├── deploy/                # Nginx config, redirect page
└── local_ignore/          # Local-only files (SSH keys, archives) — gitignored
```

## Key Gotchas & Non-Obvious Conventions

- **Client script load order matters**: `game_state.js` → `tiles.js` → `sprite_data.js` → `sprites.js` → `music.js` → `renderer.js` → `net.js` → inline init/gameLoop → `input.js`
- **Client state**: all mutable state lives on the shared `G` namespace object (`game_state.js`)
- **Server state**: all mutable state lives on the `GameState` singleton (`from server.state import game`)
- **Import order** avoids circular deps: `constants` → `state` → `models` → `net` → `rooms` → `validation` → `dungeons` → `quests` → `lifecycle` → `combat` → `debug_monsters` → `mud_server`. Combat uses lazy imports for lifecycle.
- **Tick loops are synchronous** with message batching — no `await` mid-tick. Messages collected as tuples, flushed after the full tick. This prevents dungeon teardown crashes.
- **Room transitions**: player is temporarily removed from `game.players` during `do_room_transition()` so tick loops can't target them mid-swap. Re-added in `finally` block.
- **Dungeon room resolution is synchronous** — no JIT AI generation. Custom rooms resolve from the library pool or fall back to precreated.
- **Dungeon tilemaps use string tile codes** (`"DW"`, `"DF"`, etc.) not numeric IDs.
- **All rooms loaded from `.room` files** — no hardcoded room definitions in Python.
- **AI generation uses Claude CLI by default** (`AI_BACKEND=cli`), not the API. The `.env` must NOT set `AI_BACKEND=api`.
- **AI prompt templates** are in `server/prompts/*.txt` — edit the text files directly, no Python changes needed.
- **Sprites/tiles use `[colorKey, x, y, w, h]` rect layer format** everywhere (client + server validation + AI prompts).
- **Custom tile properties** (walkable, etc.) live in `custom_tile_recipes[tile_id]` — no separate sets. `is_walkable_tile()` reads from the recipe dict. Client receives walkable flag via `custom_tiles` in `room_enter` and adds to its `WALKABLE` set.
- **Boss choir overlay**: when a player hits the dungeon warden, an ethereal choir track plays for all other dungeon players, volume scaled by BFS distance from boss room. Managed via `boss_engaged` on `DungeonInstance`, choir updates sent automatically by `send_room_enter()`.
- **Movement uses server-side walk state**: walks are continuous (250ms per tile for players), not instant teleports. Server tracks `Player.walk` dict with origin, target, start_time, committed flag. A 33ms tick loop (`player_walk_tick`) handles midway commit (position + collision) and walk completion for both players and monsters. Client sends `walk` (with origin), `cancel_walk`, and `face` messages. Server responds with `reconcile` (full state snapshot) on any disagreement. Cancel window is 90ms; `LATENCY_COMP=66ms` is the leeway constant. See `docs/PLAN_WALK_SYSTEM.md` for the full design.
- **Monster state machine**: mirrors the player pattern. `monster.state` (`"idle"`, `"walking"`, `"charging"`, `"teleporting"`, `"area"`) + `monster.state_data`. Behavior engine evaluates only when `state == "idle"` and `walk_time` has elapsed. `walk_time` (seconds per tile) replaces old `tick_rate` — it controls both walk duration AND behavior tick interval. Lower = faster. The 33ms loop handles monster walk progression; the 250ms loop handles behavior evaluation and warmup countdowns. Wire protocol: `monster_walk_started`/`monster_walk_complete` for smooth walks; existing `monster_moved` for instant position changes (charges/teleports).
- **Client input events are buffered**: direction key presses/releases are pushed to `G.inputEvents` with real timestamps and drained at the start of each game tick. This ensures inter-frame key releases (e.g., rapid tapping) are detected even if the frame arrives after the cancel window.
- **Client player state machine**: `G.state` is an enum (`"idle"`, `"walking"`, `"attacking"`, `"dying"`) with `G.stateData` holding state-scoped variables (replaced on every `setState()` call). Each state handles its own input and tick logic in `playerTick()`. Attacks are optimistic (animation starts immediately, server handles hit detection). Holding space chains attacks; holding space while walking attacks on landing; space during cancel window cancels walk and attacks. Reconcile messages hard-reset to idle and clear all animations.
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
