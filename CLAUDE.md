# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A browser-based multiplayer MUD (Multi-User Dungeon) rendered as a Zelda-style top-down visual game. Players connect via browser, log in with a name/description, walk around tile-based rooms with arrow keys/WASD, and chat via speech bubbles. See `ZeldaPlan.md` for the full design spec.

## Architecture

Multi-file architecture, no build tools or external assets:

- **`mud_server.py`** — Python server handling everything: WebSocket game logic (asyncio + websockets), room/player state, command dispatch, and HTTP static file serving. Binds to port 8080 with auto-ngrok tunneling for internet access. Static file routes are defined in `STATIC_FILES` dict.
- **`client.html`** — Browser client (HTML + CSS + core game JS). Login overlay, game loop, rendering, input handling, WebSocket connection to `/ws` endpoint.
- **`sprites.js`** — Player sprite drawing. Procedural 16x16 character rendering with directional poses and walk animation. Exposes `drawPlayer(ctx, px, py, direction, colorIndex, animFrame, SCALE)`.
- **`tiles.js`** — Tile rendering. Procedural tile textures (grass, stone, wood, water, etc.) cached to offscreen canvases. Exposes `getTileCanvas(tileId, TS, TILE, SCALE)` and `TILE_COLORS`.
- **`music.js`** — Background music. Procedural chiptune loop using Web Audio API (square + triangle wave oscillators). Exposes `MusicPlayer.start()`, `.stop()`, `.toggle()`, `.isPlaying()`. Auto-starts on login, toggled with M key.

**Protocol:** JSON over WebSocket.
- Client → Server: `login` (name, description), `move` (direction), `chat` (text)
- Server → Client: `login_ok`, `room_enter` (tilemap + players), `player_moved`, `player_entered`, `player_left`, `chat`, `info`, `error`

**State:** All in-memory. Players tracked in `dict[websocket, Player]`. Rooms defined in the `ROOMS` dict with 15x11 tilemaps. State resets on server restart.

**World map:** Town Square (center) connects to Blacksmith (north), Forest Path (south), Tavern (east), Old Chapel (west). Forest Path leads to Clearing (south). Tavern has stairs up to Tavern Upper Floor.

**Music:** Two mp3 tracks served as `/music.mp3` and `/music_forest.mp3` (mapped from `not zelda.mp3` and `not zelda (forest).mp3` in `STATIC_FILES`). Toggled with M key.

## Running

```
python mud_server.py
```

Opens on http://localhost:8080. Automatically creates an ngrok tunnel for public access (requires `pyngrok` + auth token configured).
Always print the ngrok server URL to the command line when running so that I can invite my good friend.

## Dependencies

- Python 3.12+
- `websockets` (12.0)
- `pyngrok` (optional, for public internet access)
