# MUD — Zelda-Style Visual Multiplayer Game

## Context
Transform the existing text-based MUD into a Zelda-style top-down visual game. Players walk around with arrow keys/WASD, see pixel-art rooms on an HTML5 Canvas, and chat via speech bubbles. The text commands are replaced by real-time tile-based movement with classic screen transitions between rooms.

## Files (unchanged — still just 2)
- `mud_server.py` — Server: movement validation, tile maps, room transitions, chat
- `client.html` — Canvas renderer, sprites, tile art, game loop, speech bubbles

## Visual Design
- **16x16 pixel tiles**, rendered at 3x scale on canvas (48x48 screen pixels)
- **Room grid:** 15 columns x 11 rows = 720x528 canvas
- **Pixel art sprites** for players (4 directions, 2 walk frames each)
- **Speech bubbles** float above players when chatting
- **Screen transitions** slide old/new room like classic Zelda

## Tile Types
| ID | Name | Walkable | Used in |
|----|------|----------|---------|
| 0 | Grass | Yes | Outdoor rooms |
| 1 | Stone floor | Yes | Town square, chapel, blacksmith |
| 2 | Wood floor | Yes | Tavern interiors |
| 3 | Stone wall | No | Building edges |
| 4 | Wood wall | No | Tavern walls |
| 5 | Water | No | Fountain in town square |
| 6 | Tree | No | Forest rooms |
| 7 | Flowers | Yes | Clearing |
| 8 | Dirt path | Yes | Forest path |
| 9 | Stairs up | Yes (trigger) | Tavern → upstairs |
| 10 | Stairs down | Yes (trigger) | Upstairs → tavern |
| 11 | Anvil | No | Blacksmith |
| 12 | Fireplace | No | Tavern |
| 13 | Table | No | Tavern |
| 14 | Pew | No | Chapel |
| 15 | Door/exit | Yes | Room edges at exits |

## Room Layout Rules
- Each room is a 15x11 tile grid
- North/south exits: 3-tile gap (cols 6-8) in top/bottom row
- East/west exits: 3-tile gap (rows 4-6) in left/right column
- Up/down exits: stairs tiles placed inside the room

## New Protocol
**Client → Server:**
- `{type: "login", name, description}` — unchanged
- `{type: "move", direction: "up|down|left|right"}` — tile movement
- `{type: "chat", text: "..."}` — chat message

**Server → Client:**
- `{type: "login_ok", color_index: N}` — with sprite color variant
- `{type: "room_enter", name, tilemap, your_pos, players}` — full room data on entry
- `{type: "player_moved", name, x, y, direction}` — another player moved
- `{type: "player_entered", name, x, y, direction, color_index}` — player joined room
- `{type: "player_left", name}` — player left room
- `{type: "chat", from, text}` — speech bubble
- `{type: "info", text}` — system messages

## Server Changes (`mud_server.py`)

### Step 1: Tile constants and walkability
Add tile ID constants (GRASS=0, STONE=1, etc.) and a `WALKABLE_TILES` set.

### Step 2: Room tilemaps
Add a `tilemap` (15x11 grid of tile IDs) and `spawn_points` dict to each room in `ROOMS`. Design 7 unique room layouts:
- **Town Square:** Stone floor, water fountain center, 4 exits
- **Tavern:** Wood floor, fireplace, tables, stairs-up tile, exits west
- **Tavern Upstairs:** Wood floor, stairs-down tile, exit down only
- **Blacksmith:** Stone floor, anvil center, forge, exit south
- **Forest Path:** Dirt path between trees, exits north+south
- **Clearing:** Grass + flowers, trees around edge, exit north
- **Old Chapel:** Stone floor, pew rows, exit east

### Step 3: Player position tracking
Add `x`, `y`, `direction`, `color_index` to `Player` class. Add color index counter.

### Step 4: Movement handler
New `handle_move(player, direction)`:
- Compute new tile position
- Check bounds → if off-edge and exit exists, trigger room transition
- Check walkability of target tile
- Check for stairs tiles → trigger up/down transition
- Broadcast `player_moved` to room
- Rate limit: 125ms between moves (8 tiles/sec)

### Step 5: Room transition refactor
Refactor `cmd_go` into `do_room_transition(player, exit_direction)`:
- Broadcast `player_left` to old room
- Set new room + spawn position from `spawn_points`
- Broadcast `player_entered` to new room
- Send `room_enter` with tilemap to transitioning player

### Step 6: Update message routing
Accept `{type: "move"}` and `{type: "chat"}` in the websocket loop alongside existing `{type: "command"}`.

## Client Changes (`client.html`)

### Step 7: Canvas + game loop setup
Replace `#output` div with `<canvas>`. Set up `requestAnimationFrame` game loop. Keep login overlay and chat input bar.

### Step 8: Tile rendering
Define tile pixel data as compact palette-indexed strings. Implement `drawTile()` that draws 16x16 pixels at 3x scale using `fillRect`.

### Step 9: Sprite rendering
Define 8 player sprite frames (4 directions x 2 walk frames) as inline pixel data. Implement `drawSprite()` with color swapping per `color_index` for distinct player appearances.

### Step 10: Input handling
- Arrow keys / WASD → send `{type: "move"}` at 125ms throttle
- Enter or `/` → focus chat input
- Escape → blur chat input
- Arrow keys ignored for movement when chat input is focused

### Step 11: Room rendering + player drawing
`renderRoom()`: draw all tiles from tilemap. `renderPlayers()`: draw all sprites sorted by Y for depth, with name labels above.

### Step 12: Screen transitions
On `room_enter`: capture old canvas, slide old room out + new room in over 300ms. Stairs use fade-to-black instead of slide. Lock input during transition.

### Step 13: Speech bubbles
On `chat` message: create bubble with 4s lifetime. Render as white rounded rect + text above player sprite. Fade out in last 500ms.

### Step 14: UI polish
- Room name in top-left corner
- Exit indicators (arrows) on room edges
- Player name labels above sprites
- Chat commands: `/who`, `/help` still work via server

## Controls
| Input | Action |
|-------|--------|
| Arrow keys / WASD | Walk around |
| Enter | Focus chat input |
| Escape | Unfocus chat input |
| Type + Enter | Send chat message (appears as speech bubble) |

## Verification
1. Run `python mud_server.py`
2. Open `http://localhost:8080` in two browser tabs
3. Log in → see pixel-art Town Square with your character sprite
4. Walk around with arrow keys, bump into walls
5. Walk to the east edge → screen slides, you're in the Tavern
6. In tab 2, walk to the Tavern too → see both players
7. Type a message → speech bubble appears above your character in both tabs
8. Walk onto stairs in the Tavern → fade transition to upstairs
9. Close one tab → other tab sees the player sprite disappear
