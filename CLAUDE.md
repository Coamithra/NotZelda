# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Legends of Amara** — a browser-based multiplayer Zelda-style top-down visual game. Players connect via browser, log in with a name/description, walk around tile-based rooms with arrow keys/WASD, chat via speech bubbles, fight monsters and gain treasures.

For detailed module descriptions and game system documentation, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

**Project tracking:** [Trello — Legends of Amara](https://trello.com/b/FEqdR6QL/legends-of-amara). Bugs, features, and refactoring are tracked there. Use the `trello` CLI (installed from `C:\Programming\TrelloCLI`) with subcommand groups — `trello card ls <list>`, `trello card show <id>`, `trello card move <id> <list>`, `trello comment add <id> <text>`, etc. Config in `~/.trello-cli.json`. **Use real newlines in card descriptions, not `\n` escape sequences** — the CLI passes strings literally.

**Contributing workflow:** See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for the step-by-step runbook for tackling any Trello card (pick up → worktree → research → design → implement → verify → review & ship). All feature work happens in git worktrees under `.trees/` — the root checkout stays on `master`.

## General Rules

When pushing to git make sure to update CLAUDE.md first!

**NEVER run `python worldgen.py` without explicit user permission.** The overworld `.room` files in `rooms/` contain hand-edited changes that worldgen will overwrite. Running it will destroy manual edits. Always warn the user that data will be lost before re-running.

**After any changes to `server/ai_generator.py`, `tools/content_viewer.py`, or `.env`, run `python tools/test_api_leak.py` to verify the Anthropic API key cannot leak into CLI subprocess calls.** The game uses the Claude CLI (subscription-based) for AI generation — the API must never be called directly. All 4 tests must pass.

**Test suites** in `tools/`: `test_api_leak.py` (4 tests — API key safety), `test_content_library.py` (23 tests — library CRUD/persistence), `test_npc_prompts.py` (NPC prompt generation), `test_treasure_trap.py` (10 tests — trap room lock/unlock, item hiding during lockdown, treasure cell eligibility, challenging tier randomness). Run all with `python tools/test_<name>.py`.

**Integration tests** in `tools/`: `test_movement.py` (7 tests — spawn, walk, wall collision, room exit), `test_combat.py` (7 tests — sword hit, cooldown, kill, contact damage, knockback, projectile), `test_monster_scripts.py` (7 tests — wander, timing, projectile, charge, patrol, all-behaviors sweep), `test_multiplayer.py` (7 tests — presence, enter/leave, chat, combat visibility, revival), `test_reachability.py` (7 tests — BFS, dungeon generation across all types, boss/item reachability, key solvability with exploration simulation, disconnected room detection). Run all with `python tools/run_integration_tests.py` or individually. Uses `test_harness.py` (MockWebSocket, GameClock, headless tick simulation). Dungeon tests iterate all `DUNGEON_TYPES` automatically.

**Avoid calling the Anthropic API directly unless expressly permitted by the user.** If you must call it (e.g. for testing), always set `metadata={"user_id": "claude-code"}` so the call is identifiable in the Console. Claude API docs: https://platform.claude.com/docs/en/api/overview

**All AI prompt text must live in `server/prompts/*.txt` files**, loaded at runtime via `_load_prompt()`. Never inline prompt strings in Python code. Use `{{placeholder}}` syntax for template variables.

## Directory Structure

```
├── mud_server.py          # Main entry point
├── worldgen.py            # Offline world generator (DO NOT run without permission)
├── client/                # Browser-served HTML + JS
├── server/                # Python modules imported by mud_server
│   └── prompts/           # AI prompt templates ({{placeholder}} syntax)
├── audio/                 # All game audio
│   ├── music/             # MP3 tracks by area (overworld, dungeon1-3, other)
│   └── sfx/               # AI-generated WAV sound effects by category
├── rooms/                 # .room data files + dungeon template subdirs
├── data/                  # tiles.json, monsters.json, npc_sprites.json
├── tools/                 # Dev utilities (renderers, content viewer, tests)
├── docs/                  # Architecture docs, system references, planning docs
├── deploy/                # Nginx config, redirect page
└── local_ignore/          # Local-only files (SSH keys, archives) — gitignored
```

## Key Conventions

- **Client state**: all mutable state on shared `G` namespace (`game_state.js`) — sub-objects: `G.conn`, `G.player`, `G.room`, `G.ui`, `G.fx`, `G.debug`.
- **Server state**: all mutable state on `GameState` singleton (`from server.state import game`).
- **Player vs Avatar**: `Player` = session/identity (name, hp, room). `Avatar` = physical presence (x, y, direction). `player.avatar` is `None` during room transitions. Use `avatars_in_room()` for combat/targeting, `players_in_room()` for broadcasting.
- **Data-driven**: tiles, monsters, NPC sprites loaded from JSON in `data/`. Tilemaps use 2-char codes (`"GR"`, `"DW"`). Sprites/tiles use `[colorKey, x, y, w, h]` rect layers. All rooms from `.room` files.
- **AI backend**: Claude CLI by default (`AI_BACKEND=cli`). `.env` must NOT set `AI_BACKEND=api`. Supports `cli`, `api`, `ollama`.
- **Logging** via `server/log.py` — never use bare `print()`:
  - `log.debug(msg)` → sidebar + file + stdout
  - `log.server(msg)` → file + stdout only
  - `log.event(kind, text)` → sidebar + file + stdout (structured)
- **DEBUG_MODE**: `from server.constants import DEBUG_MODE` — evaluated at import from env.
- **Boss monsters**: use `monster.is_boss` — never hardcode boss checks to a kind.

### System References

Detailed implementation notes for each game system:

- [Combat & Netcode](docs/SYSTEMS_COMBAT.md) — sword hitbox, knockback, collision, server-auth movement, entity interpolation, lag compensation, dead reckoning, monster movement, debug tools
- [Dungeons](docs/SYSTEMS_DUNGEONS.md) — topology, item/key placement, difficulty tiers, trap rooms, locked doors, dark rooms, dungeon map/compass
- [NPCs](docs/SYSTEMS_NPC.md) — chat backends, prompt tuning, gifts, guards, conversation seeding, quest events
- [Items & Player](docs/SYSTEMS_ITEMS.md) — lantern, tide medallion, spirit jar, treasure chest, seal fragment, revival, item pickup, reveal tilemap, portal tiles
- [Audio & SFX](docs/SYSTEMS_AUDIO.md) — AudioGen SFX pipeline, manifest format, generation tool, prompt tips

## Key Gotchas

- **Client script load order**: `game_state.js` → `tweak.js` → `title.js` → `tiles.js` → `sprite_data.js` → `sprites.js` → `music.js` → `renderer.js` → `fx.js` → `net.js` → inline init/gameLoop → `input.js`
- **Import order** avoids circular deps: `constants` → `state` → `log` → `models` → `net` → `rooms` → `validation` → `dungeon_types` → `dungeon_topology` → `dungeons` → `quests` → `lifecycle` → `behavior_engine` → `commands` → `combat` → `debug_monsters` → `mud_server`.
- **Command queue**: websocket messages append to `player.command_queue`, drained by `game_tick()`. Only `ping` handled directly.
- **game_tick() is synchronous** — no `await` mid-tick. Messages batched as tuples, flushed after tick.
- **Room transitions**: avatar set to `None` during `do_room_transition()`. `avatars_in_room()` excludes avatar-less players.
- **Dungeon room resolution is synchronous** — no JIT AI generation. Custom rooms from library pool or precreated fallback.
- **Tile properties** in `custom_tile_recipes[tile_id]` — no separate walkability sets.
- **`websockets` must stay at 12.0** — v16+ breaks `process_request` API. HTTP routing lives in `_GameServerProtocol.process_request()` (a subclass of `WebSocketServerProtocol`), not a standalone function, because websockets 12.0 only accepts GET — the subclass overrides `read_http_request()` to also accept POST for `/clear-log`.
- **WebSocket bypasses nginx** — client connects `wss://` directly to Python on port 8443 (TLS via Python `ssl`). nginx only serves static files.

### Debug Draw Mode

`/draw` (debug only) enables in-game tile editing:

- **Tile palette** appears below chat bar: room tiles + expandable "All Tiles" (56 built-in)
- **LMB/RMB** click palette tiles to bind, then click canvas to place
- **Smart undo**: placing same tile twice restores the original; placing on an identical tile is a no-op
- **Edge sync**: placing on room border auto-updates neighbor room's corresponding tile (walkable→predominant walkable, wall→predominant wall)
- **Instant persistence**: `.room` files saved to disk on every edit
- **Server state**: `game.draw_overrides` tracks originals + linked neighbor overrides for undo
- **Key files**: `server/commands.py` (`_cmd_draw`, `_process_draw_tile`), `server/rooms.py` (`save_room_tilemap`), `client/client.html` (palette HTML/CSS/JS), `client/input.js` (canvas click/contextmenu), `client/renderer.js` (`renderDrawMode`)

### Debug Tweak Console

`/tweak` (debug only) opens a runtime parameter tweaking panel to the right of the game canvas:

- **Panel layout**: right sidebar (380px), coexists with `/draw` palette, collapsible groups with filter bar
- **Client constants**: `const` changed to `let` in game_state.js, fx.js, renderer.js, music.js; registered via `registerTweak()` getter/setter pattern in `client/tweak.js`
- **Server constants**: whitelist in `TWEAKABLE_SERVER_CONSTANTS` dict in `server/commands.py`; updates via `setattr()` on constants module; sent to client on `/tweak` toggle
- **Monster scripts**: per-kind stats + behavior rule params; server sends built-in monster registry (excludes AI-generated); patches existing instances on change
- **Controls**: direct input field + slider (when min/max defined) + -/+ buttons + reset per param
- **Export**: copies all non-default values to clipboard as readable text
- **Key files**: `client/tweak.js` (registry + UI), `client/client.html` (panel HTML/CSS), `server/commands.py` (`_cmd_tweak`, `_process_tweak`, `_process_tweak_monster`)
- **Script load order**: `game_state.js` -> `tweak.js` -> `title.js` -> ... (tweak.js must load after game_state.js but before other scripts that call `registerTweak()`)

## Workflow Preferences

- **Prefer self-hosted/local tools** over cloud APIs when quality is comparable. The user has an RTX 4070 Ti (12GB) and prefers owning the toolchain. Lead with open-source options first; suggest cloud APIs only as fallback.
- **Preserve client-side feel.** When there's a client/server mismatch, adjust the server to match what feels good on the client — not the other way around. Only change client feel if the user explicitly asks.
- **Don't time client UI on server messages.** Client should hold its current visual state (overlays, death screens, transitions) until the actual WebSocket message arrives. Never use `setTimeout` to anticipate server responses.

## Running

```
python mud_server.py
```

Opens on http://localhost:8080.

## Hosting (Hetzner Cloud VPS)

- **Server:** Hetzner CX22, Ubuntu 24.04 — IP `46.225.218.207`
- **SSH:** `ssh root@46.225.218.207` — Code at `/opt/NotZelda/`
- **Service:** `notzelda` systemd service — `systemctl restart notzelda`, `journalctl -u notzelda -f`
- **Ollama:** `gemma2:2b` for NPC chat, `OLLAMA_NUM_PARALLEL=2`, `.env` sets `AI_BACKEND=ollama`
- **Deploy:** `cd /opt/NotZelda && git pull && systemctl restart notzelda`

## Dependencies

- Python 3.12+
- `websockets` (12.0 — pinned, v16+ breaks the `process_request` API)
- `pyngrok` (optional, for local dev tunneling)
