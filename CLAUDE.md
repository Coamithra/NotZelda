# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A browser-based multiplayer MUD (Multi-User Dungeon) rendered as a Zelda-style top-down visual game. Players connect via browser, log in with a name/description, walk around tile-based rooms with arrow keys/WASD, and chat via speech bubbles. See `ZeldaPlan.md` for the full design spec.

## Architecture

Multi-file architecture, no build tools or external assets:

- **`mud_server.py`** — Python server handling everything: WebSocket game logic (asyncio + websockets), room/player state, command dispatch, and HTTP static file serving. Binds to port 8080. Static file routes are defined in `STATIC_FILES` dict.
- **`client.html`** — Browser client (HTML + CSS + core game JS). Login overlay, game loop, rendering, input handling, WebSocket connection to `/ws` endpoint.
- **`sprites.js`** — Player & NPC sprite drawing. Procedural 16x16 character rendering with directional poses and walk animation. Exposes `drawPlayer(ctx, px, py, direction, colorIndex, animFrame, SCALE)`, `drawPlayerDance(ctx, px, py, colorIndex, danceFrame, SCALE)`, `drawPlayerAttack(ctx, px, py, direction, colorIndex, attackFrame, SCALE)`, `drawSwordAttack(ctx, px, py, direction, attackFrame, SCALE)`, `drawGuard(ctx, px, py, SCALE)`, `drawSlime(ctx, px, py, hopFrame, SCALE)`, and `drawSlimeDeath(ctx, px, py, deathFrame, SCALE)`.
- **`tiles.js`** — Tile rendering. Procedural tile textures (grass, stone, wood, water, etc.) cached to offscreen canvases. Exposes `getTileCanvas(tileId, TS, TILE, SCALE)` and `TILE_COLORS`.
- **`music.js`** — Background music. Procedural chiptune loop using Web Audio API (square + triangle wave oscillators). Exposes `MusicPlayer.start()`, `.stop()`, `.toggle()`, `.isPlaying()`. Auto-starts on login, toggled with M key.
- **`download_log.py`** — Local utility script. Fetches the server's event log via `/get-log`, saves it to `log_YYYYMMDD_HHMMSS.txt`, and clears the log on the server. Defaults to the Hetzner server; pass `http://localhost:8080` as arg for local dev.

**Protocol:** JSON over WebSocket.
- Client → Server: `login` (name, description), `move` (direction), `attack`, `chat` (text), `ping`
- Server → Client: `login_ok`, `room_enter` (tilemap + players + guards), `player_moved`, `player_entered`, `player_left`, `attack` (name, direction), `chat`, `dance`, `info`, `error`, `pong`

**State:** All in-memory. Players tracked in `dict[websocket, Player]`. Rooms defined in the `ROOMS` dict with 15x11 tilemaps. State resets on server restart. An `event_log` list records joins, leaves, and chat messages (with timestamps); exposed via `GET /get-log` which returns the log as plain text and clears it.

**World map:** Town Square (center) connects to Blacksmith (north), Forest Path (south), Tavern (east), Old Chapel (west). Forest Path leads to Clearing (south). Tavern has stairs up to Tavern Upper Floor.

**NPCs:** Guard NPCs defined in `GUARDS` dict in `mud_server.py`. Each guard has a name, position, and dialog line. Guards are rendered client-side with `drawGuard()` (helmet + armor sprite). Players can't walk on guard tiles. Walking adjacent triggers the guard's dialog as a chat bubble (broadcast to room), with a 10-second per-player cooldown to prevent spam.

**Monsters:** Monster templates defined in `MONSTER_TEMPLATES` dict in `mud_server.py` (keyed by room ID). Currently one green slime in the Clearing. Lifecycle: monsters spawn when the first player enters a room and despawn when all players leave. Only rooms with players are simulated. Monsters hop randomly to adjacent walkable tiles every 2 seconds via `monster_tick()` coroutine. Players kill monsters by attacking (Space) on an adjacent tile — slimes have 1 HP. On death, the server broadcasts `monster_killed` and the client plays a 3-frame splat animation. Individual monsters do NOT respawn. If all monsters in a room are killed, they stay dead. When all players then leave the room, a 10-second cooldown starts (`ROOM_RESET_COOLDOWN`). During cooldown the room stays empty even if re-entered. After cooldown expires, the next player entering spawns fresh monsters. The `room_enter` message includes a `monsters` array for alive monsters. Players can walk through monsters (they're squishy). Protocol messages: `monster_moved {id, x, y}`, `monster_killed {id, x, y}`, `monster_spawned {id, kind, x, y}`.

**Music:** Four mp3 tracks served as `/music.mp3`, `/music_forest.mp3`, `/music_tavern.mp3`, and `/music_chapel.mp3` (mapped from `not zelda*.mp3` files in `STATIC_FILES`). `music.js` switches tracks per room via `MusicPlayer.setRoom()`. Toggled with M key.

**Emotes:** `/dance` makes the player do a looping boogie animation (4 frames). Dance stops when the player moves. Dancing state is synced — new players entering a room see ongoing dances.

**Combat:** Space bar triggers a sword stab attack (NES Zelda-style). The attack is a 2-frame animation (~300ms) that draws a thrust pose on the player and a sword on the adjacent tile in the facing direction. Player movement is frozen during the attack. Server enforces a 0.4s cooldown. Visual-only for now — no damage/hit system.

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
