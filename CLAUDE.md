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

## Key Gotchas

- **Client script load order**: `game_state.js` → `title.js` → `tiles.js` → `sprite_data.js` → `sprites.js` → `music.js` → `renderer.js` → `fx.js` → `net.js` → inline init/gameLoop → `input.js`
- **Import order** avoids circular deps: `constants` → `state` → `log` → `models` → `net` → `rooms` → `validation` → `dungeon_types` → `dungeon_topology` → `dungeons` → `quests` → `lifecycle` → `behavior_engine` → `commands` → `combat` → `debug_monsters` → `mud_server`.
- **Command queue**: websocket messages append to `player.command_queue`, drained by `game_tick()`. Only `ping` handled directly.
- **game_tick() is synchronous** — no `await` mid-tick. Messages batched as tuples, flushed after tick.
- **Room transitions**: avatar set to `None` during `do_room_transition()`. `avatars_in_room()` excludes avatar-less players.
- **Dungeon room resolution is synchronous** — no JIT AI generation. Custom rooms from library pool or precreated fallback.
- **Tile properties** in `custom_tile_recipes[tile_id]` — no separate walkability sets.
- **`websockets` must stay at 12.0** — v16+ breaks `process_request` API.
- **WebSocket bypasses nginx** — client connects `wss://` directly to Python on port 8443 (TLS via Python `ssl`). nginx only serves static files.

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
