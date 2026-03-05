"""
MUD Server — Zelda-style multiplayer online dungeon.

Run with: python mud_server.py
Then open http://localhost:8080 in your browser.
"""

import asyncio
import json
import html
import time
from datetime import datetime
from http import HTTPStatus
from pathlib import Path

import websockets
from websockets.http import Headers

# ---------------------------------------------------------------------------
# Tile constants
# ---------------------------------------------------------------------------

GRASS       = 0
STONE       = 1
WOOD        = 2
WALL_STONE  = 3
WALL_WOOD   = 4
WATER       = 5
TREE        = 6
FLOWERS     = 7
DIRT        = 8
STAIRS_UP   = 9
STAIRS_DOWN = 10
ANVIL       = 11
FIREPLACE   = 12
TABLE       = 13
PEW         = 14
DOOR        = 15
SAND        = 16
CACTUS      = 17
MOUNTAIN    = 18
CAVE_FLOOR  = 19
SWAMP       = 20
DEAD_TREE   = 21
BRIDGE      = 22
GRAVESTONE  = 23
IRON_FENCE  = 24
RUINS_WALL  = 25
RUINS_FLOOR = 26
TALL_GRASS  = 27
ROAD        = 28
CLIFF       = 29
SHALLOW_WATER = 30
BOULDER     = 31

WALKABLE_TILES = {GRASS, STONE, WOOD, FLOWERS, DIRT, STAIRS_UP, STAIRS_DOWN, DOOR,
                  SAND, CAVE_FLOOR, SWAMP, BRIDGE, RUINS_FLOOR, TALL_GRASS, ROAD,
                  SHALLOW_WATER}

# Tile code string -> numeric ID (for .room file parsing)
TILE_CODES = {
    "GR": GRASS, "ST": STONE, "WD": WOOD, "WS": WALL_STONE, "WW": WALL_WOOD,
    "WA": WATER, "TR": TREE, "FL": FLOWERS, "DT": DIRT, "SU": STAIRS_UP,
    "SD": STAIRS_DOWN, "AN": ANVIL, "FP": FIREPLACE, "TB": TABLE, "PW": PEW,
    "DR": DOOR, "SA": SAND, "CC": CACTUS, "MT": MOUNTAIN, "CV": CAVE_FLOOR,
    "SM": SWAMP, "DK": DEAD_TREE, "BR": BRIDGE, "GS": GRAVESTONE, "IF": IRON_FENCE,
    "RW": RUINS_WALL, "RF": RUINS_FLOOR, "TG": TALL_GRASS, "RD": ROAD, "CL": CLIFF,
    "SH": SHALLOW_WATER, "BO": BOULDER,
}

# Shorthand aliases for tilemap readability
G  = GRASS
S  = STONE
W  = WOOD
WS = WALL_STONE
WW = WALL_WOOD
WA = WATER
T  = TREE
FL = FLOWERS
DI = DIRT
SU = STAIRS_UP
SD = STAIRS_DOWN
AN = ANVIL
FP = FIREPLACE
TB = TABLE
PW = PEW
DR = DOOR

# ---------------------------------------------------------------------------
# World data — 15 columns x 11 rows per room
# ---------------------------------------------------------------------------

ROOMS = {
    "town_square": {
        "name": "Town Square",
        "exits": {"north": "blacksmith", "south": "forest_path", "east": "tavern", "west": "old_chapel"},
        "tilemap": [
            [WS,WS,WS,WS,WS,WS,DR,DR,DR,WS,WS,WS,WS,WS,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [DR, S, S, S, S,WA,WA,WA, S, S, S, S, S, S,DR],
            [DR, S, S, S, S,WA,WA,WA, S, S, S, S, S, S,DR],
            [DR, S, S, S, S,WA,WA,WA, S, S, S, S, S, S,DR],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS,WS,WS,WS,WS,WS,DR,DR,DR,WS,WS,WS,WS,WS,WS],
        ],
        "spawn_points": {
            "north": (7, 1), "south": (7, 9), "east": (13, 5), "west": (1, 5), "default": (7, 5),
        },
    },
    "tavern": {
        "name": "The Rusty Flagon",
        "exits": {"west": "town_square", "up": "tavern_upstairs"},
        "tilemap": [
            [WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W,SU,WW],
            [WW, W,TB, W, W, W, W, W, W, W,TB, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [DR, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [DR, W, W, W,TB, W, W, W, W,TB, W, W, W, W,WW],
            [DR, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW, W, W, W,FP,FP,FP,FP,FP, W, W, W, W, W,WW],
            [WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW],
        ],
        "spawn_points": {
            "west": (1, 5), "down": (13, 1), "default": (7, 5),
        },
    },
    "tavern_upstairs": {
        "name": "Tavern Upper Floor",
        "exits": {"down": "tavern"},
        "tilemap": [
            [WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W,SD,WW],
            [WW, W, W,WW, W, W,WW, W, W,WW, W, W, W, W,WW],
            [WW, W, W,WW, W, W,WW, W, W,WW, W, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW, W, W,WW, W, W,WW, W, W,WW, W, W, W, W,WW],
            [WW, W, W,WW, W, W,WW, W, W,WW, W, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW, W, W, W, W, W, W, W, W, W, W, W, W, W,WW],
            [WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW,WW],
        ],
        "spawn_points": {
            "up": (13, 1), "default": (7, 5),
        },
    },
    "blacksmith": {
        "name": "The Blacksmith's Forge",
        "exits": {"south": "town_square"},
        "tilemap": [
            [WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S,FP,FP, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S,AN,AN, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S,AN,AN, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS,WS,WS,WS,WS,WS,DR,DR,DR,WS,WS,WS,WS,WS,WS],
        ],
        "spawn_points": {
            "south": (7, 9), "default": (7, 5),
        },
    },
    "forest_path": {
        "name": "Forest Path",
        "exits": {"north": "town_square", "south": "clearing"},
        "tilemap": [
            [ T, T, T, T, T, T,DR,DR,DR, T, T, T, T, T, T],
            [ T, T, G, G, G,DI,DI,DI, G, G, G, G, T, T, T],
            [ T, G, G, G,DI,DI,DI,DI,DI, G, G, G, G, T, T],
            [ T, G, G,DI,DI,DI, G,DI,DI,DI, G, G, G, G, T],
            [ T, G, G,DI,DI, G, G, G,DI,DI, G, G, G, T, T],
            [ T, G,DI,DI, G, G, G, G, G,DI,DI, G, G, G, T],
            [ T, G,DI,DI, G, G, G, G, G, G,DI, G, G, T, T],
            [ T, G, G,DI,DI, G, G, G, G,DI,DI, G, G, G, T],
            [ T, T, G, G,DI,DI,DI,DI,DI,DI, G, G, G, T, T],
            [ T, G, G, G, G,DI,DI,DI, G, G, G, G, T, T, T],
            [ T, T, T, T, T, T, G, G, G, T, T, T, T, T, T],
        ],
        "spawn_points": {
            "north": (7, 1), "south": (7, 9), "default": (7, 5),
        },
    },
    "clearing": {
        "name": "Sunlit Clearing",
        "exits": {"north": "forest_path"},
        "tilemap": [
            [ T, T, T, T, T, T, G, G, G, T, T, T, T, T, T],
            [ T, T, G, G, G, G, G, G, G, G, G, G, G, T, T],
            [ T, G, G,FL, G, G, G, G, G, G,FL, G, G, G, T],
            [ T, G, G, G, G,FL, G, G, G, G, G, G, G, T, T],
            [ T, G,FL, G, G, G, G, G, G,FL, G, G, G, G, T],
            [ T, G, G, G, G, G, G, G, G, G, G,FL, G, T, T],
            [ T, G, G, G,FL, G, G, G,FL, G, G, G, G, G, T],
            [ T, G,FL, G, G, G, G, G, G, G, G, G,FL, T, T],
            [ T, T, G, G, G, G,FL, G, G, G, G, G, G, T, T],
            [ T, T, T, G, G, G, G, G, G, G, G, T, T, T, T],
            [ T, T, T, T, T, T, G, G, G, T, T, T, T, T, T],
        ],
        "spawn_points": {
            "north": (7, 1), "default": (7, 5),
        },
    },
    "old_chapel": {
        "name": "Old Chapel",
        "exits": {"east": "town_square"},
        "tilemap": [
            [WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S,PW,PW, S,PW,PW, S,PW,PW, S,PW,PW, S,WS],
            [WS, S,PW,PW, S,PW,PW, S,PW,PW, S,PW,PW, S,DR],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,DR],
            [WS, S,PW,PW, S,PW,PW, S,PW,PW, S,PW,PW, S,DR],
            [WS, S,PW,PW, S,PW,PW, S,PW,PW, S,PW,PW, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS, S, S, S, S, S, S, S, S, S, S, S, S, S,WS],
            [WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS,WS],
        ],
        "spawn_points": {
            "east": (13, 5), "default": (7, 5),
        },
    },
}

# ---------------------------------------------------------------------------
# Room file loader — reads .room files from rooms/ directory
# ---------------------------------------------------------------------------

def load_room_files(directory: str = "rooms"):
    """Load all .room files and merge into ROOMS, GUARDS, MONSTER_TEMPLATES."""
    rooms_dir = Path(__file__).parent / directory
    if not rooms_dir.exists():
        print(f"[ROOMS] No '{directory}/' directory found, skipping room file loading")
        return

    count = 0
    for room_file in sorted(rooms_dir.glob("*.room")):
        room_id = room_file.stem  # e.g. "ow_0_7" from "ow_0_7.room"
        try:
            text = room_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[ROOMS] Error reading {room_file.name}: {e}")
            continue

        parts = text.split("---")
        if len(parts) < 2:
            print(f"[ROOMS] Skipping {room_file.name}: missing --- separator")
            continue

        # Parse header
        header = {}
        for line in parts[0].strip().splitlines():
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                header[key.strip()] = val.strip()

        # Parse exits
        exits = {}
        if "exits" in header:
            for pair in header["exits"].split():
                if "=" in pair:
                    direction, target = pair.split("=", 1)
                    exits[direction] = target

        # Parse tilemap
        tilemap_text = parts[1].strip()
        tilemap = []
        for row_line in tilemap_text.splitlines():
            row_line = row_line.strip()
            if not row_line:
                continue
            codes = row_line.split()
            row = [TILE_CODES.get(code, GRASS) for code in codes]
            # Pad or trim to 15 columns
            while len(row) < 15:
                row.append(GRASS)
            row = row[:15]
            tilemap.append(row)
        # Pad or trim to 11 rows
        while len(tilemap) < 11:
            tilemap.append([GRASS] * 15)
        tilemap = tilemap[:11]

        # Build spawn points from exits
        # Key = entry direction (the side of the room you enter from)
        # Value = position near that side
        spawn_points = {"default": (7, 5)}
        if "north" in exits:
            spawn_points["north"] = (7, 1)   # enter from north edge = near top
        if "south" in exits:
            spawn_points["south"] = (7, 9)   # enter from south edge = near bottom
        if "east" in exits:
            spawn_points["east"] = (13, 5)   # enter from east edge = near right
        if "west" in exits:
            spawn_points["west"] = (1, 5)    # enter from west edge = near left
        if "up" in exits:
            spawn_points["up"] = (7, 5)
        if "down" in exits:
            spawn_points["down"] = (7, 5)

        room = {
            "name": header.get("name", room_id),
            "exits": exits,
            "tilemap": tilemap,
            "spawn_points": spawn_points,
            "biome": header.get("biome", "plains"),
            "music": header.get("music", "overworld"),
        }
        ROOMS[room_id] = room

        # Parse entity section (after second ---)
        if len(parts) >= 3:
            entity_text = parts[2].strip()
            for line in entity_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                tokens = line.split()
                if tokens[0] == "npc" and len(tokens) >= 5:
                    npc_name = tokens[1].replace("_", " ")
                    npc_x = int(tokens[2])
                    npc_y = int(tokens[3])
                    npc_dialog = " ".join(tokens[4:])
                    if room_id not in GUARDS:
                        GUARDS[room_id] = []
                    GUARDS[room_id].append({
                        "name": npc_name, "x": npc_x, "y": npc_y, "dialog": npc_dialog,
                    })
                elif tokens[0] == "monster" and len(tokens) >= 4:
                    kind = tokens[1]
                    mx = int(tokens[2])
                    my = int(tokens[3])
                    if room_id not in MONSTER_TEMPLATES:
                        MONSTER_TEMPLATES[room_id] = []
                    MONSTER_TEMPLATES[room_id].append({"kind": kind, "x": mx, "y": my})

        count += 1

    # Wire clearing's south exit to ow_0_7 if that room was loaded
    if "ow_0_7" in ROOMS and "south" not in ROOMS["clearing"]["exits"]:
        ROOMS["clearing"]["exits"]["south"] = "ow_0_7"
        ROOMS["clearing"]["spawn_points"]["south"] = (7, 9)
        # Update clearing tilemap: open south edge (cols 6-8, row 10)
        for c in range(6, 9):
            ROOMS["clearing"]["tilemap"][10][c] = GRASS

    print(f"[ROOMS] Loaded {count} room files from {directory}/")
    print(f"[ROOMS] Total rooms: {len(ROOMS)}")


STARTING_ROOM = "town_square"

# ---------------------------------------------------------------------------
# NPC Guards
# ---------------------------------------------------------------------------

GUARDS = {
    "town_square": [
        {"name": "Guard", "x": 7, "y": 8, "dialog": "Welcome to Corneria!"},
    ],
    "clearing": [
        {"name": "Guard", "x": 7, "y": 9, "dialog": "Careful, it's dangerous to go alone!"},
    ],
}

GUARD_COOLDOWN = 10  # seconds between repeated guard messages per player

# Maps direction player walked to the direction they should enter from
ENTRY_DIR = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "up": "up",
    "down": "down",
}

MOVE_COOLDOWN = 0.125  # seconds between moves
ATTACK_COOLDOWN = 0.4  # seconds between attacks

# ---------------------------------------------------------------------------
# Monsters
# ---------------------------------------------------------------------------

MONSTER_HOP_INTERVAL = 2.0    # seconds between random hops (default)
ROOM_RESET_COOLDOWN = 10.0   # seconds after all-killed + empty before respawn

# Per-kind monster stats
MONSTER_STATS = {
    "slime":      {"hp": 1, "hop_interval": 2.0},
    "bat":        {"hp": 1, "hop_interval": 1.0},
    "scorpion":   {"hp": 2, "hop_interval": 2.0},
    "skeleton":   {"hp": 2, "hop_interval": 2.0},
    "swamp_blob": {"hp": 1, "hop_interval": 2.0},
}

import random

class Monster:
    def __init__(self, x, y, kind="slime"):
        self.x = x
        self.y = y
        self.kind = kind
        self.alive = True
        self.last_hop_time = time.monotonic()
        stats = MONSTER_STATS.get(kind, {"hp": 1, "hop_interval": 2.0})
        self.hp = stats["hp"]
        self.hop_interval = stats["hop_interval"]

# Templates — define what monsters belong in each room (never mutated)
MONSTER_TEMPLATES = {
    "clearing": [
        {"kind": "slime", "x": 7, "y": 5},
    ],
}

# Live monster instances per room — only populated while players are present
# room_id -> [Monster, ...]
room_monsters: dict[str, list[Monster]] = {}

# Room cooldown — when all monsters were killed and all players left
# room_id -> timestamp when cooldown started
room_cooldowns: dict[str, float] = {}


def spawn_monsters(room_id: str) -> list[Monster]:
    """Create fresh Monster instances from templates for a room."""
    templates = MONSTER_TEMPLATES.get(room_id, [])
    now = time.monotonic()
    monsters = []
    for t in templates:
        m = Monster(t["x"], t["y"], t["kind"])
        m.last_hop_time = now
        monsters.append(m)
    return monsters


def get_room_monsters(room_id: str) -> list[Monster]:
    """Get the live monster list for a room (may be empty list)."""
    return room_monsters.get(room_id, [])


async def on_player_enter_room(room_id: str):
    """Called when a player enters a room. Spawns monsters if needed."""
    if room_id not in MONSTER_TEMPLATES:
        return
    if room_id in room_monsters:
        return  # already active (other players present)

    # Check cooldown
    if room_id in room_cooldowns:
        elapsed = time.monotonic() - room_cooldowns[room_id]
        if elapsed < ROOM_RESET_COOLDOWN:
            # Still on cooldown — room stays empty, reset timer
            room_cooldowns[room_id] = time.monotonic()
            room_monsters[room_id] = []
            return
        else:
            del room_cooldowns[room_id]

    # Spawn fresh monsters
    monsters = spawn_monsters(room_id)
    room_monsters[room_id] = monsters
    # No need to broadcast monster_spawned here — room_enter message includes them


async def on_player_leave_room(room_id: str):
    """Called after a player leaves a room. Cleans up if room is now empty."""
    if players_in_room(room_id):
        return  # still has players

    if room_id in room_monsters:
        monster_list = room_monsters[room_id]
        all_killed = len(monster_list) > 0 and all(not m.alive for m in monster_list)
        empty_list = len(monster_list) == 0
        del room_monsters[room_id]

        if all_killed:
            # First time all killed — start cooldown
            room_cooldowns[room_id] = time.monotonic()
        elif empty_list and room_id in room_cooldowns:
            # Was on cooldown, player visited empty room and left — reset timer
            room_cooldowns[room_id] = time.monotonic()

# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

next_color_index = 0

class Player:
    def __init__(self, ws, name: str, description: str, color_index: int):
        self.ws = ws
        self.name = name
        self.description = description
        self.room = STARTING_ROOM
        self.x = 7
        self.y = 5
        self.direction = "down"
        self.color_index = color_index
        self.last_move_time = 0.0
        self.last_attack_time = 0.0
        self.dancing = False
        self.guard_cooldowns = {}  # guard_key -> last_trigger_time


# websocket -> Player
players: dict = {}

# Activity log — appended on join/leave/chat, persisted to disk
LOG_FILE = Path(__file__).parent / "event_log.txt"


def log_event(kind: str, text: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {kind}: {text}"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def send_to(player: Player, msg: dict):
    try:
        await player.ws.send(json.dumps(msg))
    except websockets.ConnectionClosed:
        pass


async def broadcast_to_room(room_id: str, msg: dict, exclude=None):
    targets = [p for p in players.values() if p.room == room_id and p.ws != exclude]
    await asyncio.gather(*(send_to(t, msg) for t in targets))


def players_in_room(room_id: str, exclude=None):
    return [p for p in players.values() if p.room == room_id and p.ws != exclude]


def player_info(p: Player) -> dict:
    info = {
        "name": p.name,
        "x": p.x,
        "y": p.y,
        "direction": p.direction,
        "color_index": p.color_index,
    }
    if p.dancing:
        info["dancing"] = True
    return info


async def send_room_enter(player: Player, exit_direction: str = None):
    room = ROOMS[player.room]
    others = [player_info(p) for p in players_in_room(player.room, exclude=player.ws)]
    guards = GUARDS.get(player.room, [])
    monsters = [
        {"id": i, "kind": m.kind, "x": m.x, "y": m.y}
        for i, m in enumerate(get_room_monsters(player.room))
        if m.alive
    ]
    exits = room["exits"]
    await send_to(player, {
        "type": "room_enter",
        "room_id": player.room,
        "name": room["name"],
        "tilemap": room["tilemap"],
        "your_pos": {"x": player.x, "y": player.y},
        "players": others,
        "guards": [{"name": g["name"], "x": g["x"], "y": g["y"]} for g in guards],
        "monsters": monsters,
        "exits": {d: exits[d] for d in exits},
        "biome": room.get("biome", "town"),
        "exit_direction": exit_direction,
    })

# ---------------------------------------------------------------------------
# Movement & room transitions
# ---------------------------------------------------------------------------

async def do_room_transition(player: Player, exit_direction: str):
    old_room = player.room
    new_room_id = ROOMS[old_room]["exits"][exit_direction]
    new_room = ROOMS[new_room_id]

    # Broadcast departure
    await broadcast_to_room(old_room, {"type": "player_left", "name": player.name}, exclude=player.ws)

    # Move player — preserve column/row through the doorway
    old_x, old_y = player.x, player.y
    player.room = new_room_id
    entry = ENTRY_DIR.get(exit_direction, "default")
    spawn = new_room["spawn_points"].get(entry, new_room["spawn_points"]["default"])
    player.x, player.y = spawn
    if exit_direction in ("north", "south"):
        player.x = old_x  # keep column
    elif exit_direction in ("east", "west"):
        player.y = old_y  # keep row

    # Monster lifecycle — leave old room, enter new room
    await on_player_leave_room(old_room)
    await on_player_enter_room(new_room_id)

    # Send new room to player
    await send_room_enter(player, exit_direction=exit_direction)

    # Broadcast arrival
    await broadcast_to_room(
        new_room_id,
        {"type": "player_entered", **player_info(player)},
        exclude=player.ws,
    )


def check_edge_exit(player, new_x, new_y, room):
    """Check if walking off-edge corresponds to a room exit."""
    exits = room["exits"]
    if new_y < 0 and "north" in exits and 6 <= player.x <= 8:
        return "north"
    if new_y > 10 and "south" in exits and 6 <= player.x <= 8:
        return "south"
    if new_x < 0 and "west" in exits and 4 <= player.y <= 6:
        return "west"
    if new_x > 14 and "east" in exits and 4 <= player.y <= 6:
        return "east"
    return None


async def check_guard_proximity(player: Player):
    """If adjacent to a guard and cooldown has passed, send guard dialog."""
    now = time.monotonic()
    for guard in GUARDS.get(player.room, []):
        dx = abs(player.x - guard["x"])
        dy = abs(player.y - guard["y"])
        if dx + dy == 1:  # adjacent (not diagonal)
            key = f"{player.room}:{guard['name']}:{guard['x']},{guard['y']}"
            last = player.guard_cooldowns.get(key, 0)
            if now - last >= GUARD_COOLDOWN:
                player.guard_cooldowns[key] = now
                await broadcast_to_room(player.room, {
                    "type": "chat",
                    "from": guard["name"],
                    "text": guard["dialog"],
                })


async def handle_move(player: Player, direction: str):
    now = time.monotonic()
    if now - player.last_move_time < MOVE_COOLDOWN:
        return
    player.last_move_time = now

    dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}.get(direction, (0, 0))
    if dx == 0 and dy == 0:
        return

    player.direction = direction
    player.dancing = False
    new_x = player.x + dx
    new_y = player.y + dy

    room = ROOMS[player.room]
    tilemap = room["tilemap"]

    # Off edge — check for room exit
    if new_x < 0 or new_x >= 15 or new_y < 0 or new_y >= 11:
        exit_dir = check_edge_exit(player, new_x, new_y, room)
        if exit_dir:
            await do_room_transition(player, exit_dir)
        else:
            # Broadcast facing change only
            await broadcast_to_room(player.room, {
                "type": "player_moved",
                "name": player.name,
                "x": player.x,
                "y": player.y,
                "direction": player.direction,
            })
        return

    tile = tilemap[new_y][new_x]

    # Stairs trigger
    if tile == STAIRS_UP and "up" in room["exits"]:
        await do_room_transition(player, "up")
        return
    if tile == STAIRS_DOWN and "down" in room["exits"]:
        await do_room_transition(player, "down")
        return

    # Walkability check
    if tile not in WALKABLE_TILES:
        # Still update facing direction
        await broadcast_to_room(player.room, {
            "type": "player_moved",
            "name": player.name,
            "x": player.x,
            "y": player.y,
            "direction": player.direction,
        })
        return

    # Guard collision — can't walk onto a guard's tile
    for guard in GUARDS.get(player.room, []):
        if new_x == guard["x"] and new_y == guard["y"]:
            await broadcast_to_room(player.room, {
                "type": "player_moved",
                "name": player.name,
                "x": player.x,
                "y": player.y,
                "direction": player.direction,
            })
            return

    player.x = new_x
    player.y = new_y

    await broadcast_to_room(player.room, {
        "type": "player_moved",
        "name": player.name,
        "x": player.x,
        "y": player.y,
        "direction": player.direction,
    })

    # Guard proximity chat
    await check_guard_proximity(player)

# ---------------------------------------------------------------------------
# Attack
# ---------------------------------------------------------------------------

async def handle_attack(player: Player):
    now = time.monotonic()
    if now - player.last_attack_time < ATTACK_COOLDOWN:
        return
    player.last_attack_time = now
    player.dancing = False

    await broadcast_to_room(player.room, {
        "type": "attack",
        "name": player.name,
        "direction": player.direction,
    })

    # Hit detection — check if sword hits a monster
    dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}.get(player.direction, (0, 0))
    hit_x = player.x + dx
    hit_y = player.y + dy
    for i, monster in enumerate(get_room_monsters(player.room)):
        if monster.alive and monster.x == hit_x and monster.y == hit_y:
            monster.hp -= 1
            if monster.hp <= 0:
                monster.alive = False
                await broadcast_to_room(player.room, {
                    "type": "monster_killed",
                    "id": i,
                    "x": monster.x,
                    "y": monster.y,
                })
            else:
                await broadcast_to_room(player.room, {
                    "type": "monster_hit",
                    "id": i,
                    "x": monster.x,
                    "y": monster.y,
                    "hp": monster.hp,
                })

# ---------------------------------------------------------------------------
# Monster AI tick
# ---------------------------------------------------------------------------

async def monster_tick():
    """Background loop — hops alive monsters in rooms that have players."""
    while True:
        await asyncio.sleep(1.0)
        now = time.monotonic()
        for room_id, monster_list in list(room_monsters.items()):
            # Only simulate rooms with players
            if not players_in_room(room_id):
                continue
            tilemap = ROOMS[room_id]["tilemap"]
            guards = GUARDS.get(room_id, [])
            for i, monster in enumerate(monster_list):
                if not monster.alive:
                    continue
                if now - monster.last_hop_time < monster.hop_interval:
                    continue
                monster.last_hop_time = now

                # Pick a random walkable adjacent tile
                directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
                random.shuffle(directions)
                for ddx, ddy in directions:
                    nx, ny = monster.x + ddx, monster.y + ddy
                    if nx < 0 or nx >= 15 or ny < 0 or ny >= 11:
                        continue
                    if tilemap[ny][nx] not in WALKABLE_TILES:
                        continue
                    if any(g["x"] == nx and g["y"] == ny for g in guards):
                        continue
                    monster.x = nx
                    monster.y = ny
                    await broadcast_to_room(room_id, {
                        "type": "monster_moved",
                        "id": i,
                        "x": nx,
                        "y": ny,
                    })
                    break

# ---------------------------------------------------------------------------
# Chat commands (typed in chat bar)
# ---------------------------------------------------------------------------

async def handle_chat(player: Player, text: str):
    text = text.strip()
    if not text:
        return

    # Slash commands
    if text.startswith("/"):
        parts = text[1:].split(None, 1)
        cmd = parts[0].lower() if parts else ""
        if cmd == "who":
            lines = ["Players online:"]
            for p in players.values():
                room_name = ROOMS[p.room]["name"]
                lines.append(f"  {p.name} — {p.description} (in {room_name})")
            await send_to(player, {"type": "info", "text": "\n".join(lines)})
        elif cmd == "help":
            await send_to(player, {"type": "info", "text": (
                "Arrow keys / WASD — Move\n"
                "Space — Attack\n"
                "Enter — Open chat\n"
                "Escape — Close chat\n"
                "M — Toggle music\n"
                "/who — List online players\n"
                "/dance — Bust a move\n"
                "/help — Show this message"
            )})
        elif cmd == "dance":
            player.dancing = True
            await broadcast_to_room(player.room, {
                "type": "dance", "name": player.name,
            })
        elif cmd == "me":
            action = parts[1] if len(parts) > 1 else ""
            if action:
                await broadcast_to_room(player.room, {
                    "type": "chat", "from": player.name, "text": f"*{action}*",
                })
        else:
            await send_to(player, {"type": "info", "text": "Unknown command. Try /help"})
        return

    # Normal chat — broadcast to room
    room_name = ROOMS[player.room]["name"]
    log_event("CHAT", f"{player.name} ({room_name}): {text}")
    await broadcast_to_room(player.room, {
        "type": "chat",
        "from": player.name,
        "text": text,
    })

# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------

async def handle_connection(websocket):
    global next_color_index
    player = None
    remote = websocket.remote_address
    addr = f"{remote[0]}:{remote[1]}" if remote else "unknown"
    print(f"[CONN] New connection from {addr}")
    try:
        raw = await websocket.recv()
        data = json.loads(raw)
        if data.get("type") != "login":
            print(f"[CONN] {addr} sent non-login first message, dropping")
            return

        name = html.escape(data.get("name", "").strip()[:20])
        desc = html.escape(data.get("description", "").strip()[:80])

        if not name:
            await websocket.send(json.dumps({"type": "error", "text": "Name cannot be empty."}))
            return

        if any(p.name.lower() == name.lower() for p in players.values()):
            await websocket.send(json.dumps({"type": "error", "text": "That name is already taken."}))
            return

        color_index = next_color_index
        next_color_index = (next_color_index + 1) % 6

        player = Player(websocket, name, desc or "A mysterious stranger.", color_index)
        spawn = ROOMS[STARTING_ROOM]["spawn_points"]["default"]
        player.x, player.y = spawn
        players[websocket] = player
        log_event("JOIN", f"{name} ({player.description})")
        print(f"[JOIN] {name} from {addr}")

        await send_to(player, {"type": "login_ok", "color_index": color_index})
        await on_player_enter_room(player.room)
        await send_room_enter(player)
        await broadcast_to_room(
            player.room,
            {"type": "player_entered", **player_info(player)},
            exclude=websocket,
        )

        async for raw in websocket:
            try:
                data = json.loads(raw)
                msg_type = data.get("type")
                if msg_type == "move":
                    await handle_move(player, data.get("direction", ""))
                elif msg_type == "attack":
                    await handle_attack(player)
                elif msg_type == "chat":
                    await handle_chat(player, data.get("text", ""))
                elif msg_type == "ping":
                    await player.ws.send(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                print(f"[WARN] {name}: bad JSON: {raw[:200]}")
            except websockets.ConnectionClosed:
                raise  # re-raise so the outer handler logs it
            except Exception as e:
                print(f"[ERROR] {name}: message handler error: {type(e).__name__}: {e}")
                # Don't break the loop — keep the connection alive

    except websockets.ConnectionClosed as e:
        reason = f"code={e.code} reason='{e.reason}'" if e.code else "no close frame"
        who = player.name if player else addr
        print(f"[DISC] {who} disconnected: {reason}")
        log_event("DISCONNECT", f"{who} — {reason}")
    except Exception as e:
        who = player.name if player else addr
        print(f"[ERROR] {who} error: {type(e).__name__}: {e}")
        log_event("ERROR", f"{who} — {type(e).__name__}: {e}")
    finally:
        if player and websocket in players:
            leaving_room = player.room
            del players[websocket]
            log_event("LEAVE", player.name)
            print(f"[LEAVE] {player.name}")
            await broadcast_to_room(
                leaving_room,
                {"type": "player_left", "name": player.name},
            )
            await on_player_leave_room(leaving_room)

# ---------------------------------------------------------------------------
# HTTP server for client.html
# ---------------------------------------------------------------------------

CLIENT_DIR = Path(__file__).parent

# Static files that the client can request
STATIC_FILES = {
    "/":            ("client.html", "text/html; charset=utf-8"),
    "/index.html":  ("client.html", "text/html; charset=utf-8"),
    "/sprites.js":  ("sprites.js",  "application/javascript; charset=utf-8"),
    "/tiles.js":    ("tiles.js",    "application/javascript; charset=utf-8"),
    "/music.js":    ("music.js",    "application/javascript; charset=utf-8"),
    "/music.mp3":         ("not zelda.mp3",          "audio/mpeg"),
    "/music_forest.mp3":  ("not zelda (forest).mp3", "audio/mpeg"),
    "/music_tavern.mp3":  ("not zelda (tavern).mp3", "audio/mpeg"),
    "/music_chapel.mp3":  ("not zelda (chapel).mp3", "audio/mpeg"),
    "/music_overworld.mp3": ("not zelda (overworld).mp3", "audio/mpeg"),
}


async def process_request(path, request_headers):
    path = path.split("?")[0]  # strip query string for cache-busting support
    if path == "/ws":
        return None
    if path == "/get-log":
        body = LOG_FILE.read_bytes() if LOG_FILE.exists() else b""
        return HTTPStatus.OK, [("Content-Type", "text/plain; charset=utf-8")], body
    if path == "/clear-log":
        LOG_FILE.write_text("", encoding="utf-8")
        return HTTPStatus.OK, [("Content-Type", "text/plain; charset=utf-8")], b"Log cleared."
    if path in STATIC_FILES:
        filename, content_type = STATIC_FILES[path]
        body = (CLIENT_DIR / filename).read_bytes()
        return HTTPStatus.OK, [("Content-Type", content_type)], body
    return HTTPStatus.NOT_FOUND, [], b"Not Found"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    load_room_files()
    port = 8080
    server = await websockets.serve(
        handle_connection, "0.0.0.0", port,
        process_request=process_request,
        ping_interval=30,    # send WebSocket ping every 30s
        ping_timeout=60,     # close if no pong within 60s (lenient for mobile)
    )
    asyncio.create_task(monster_tick())
    print("MUD server running!")
    print(f"Local:  http://localhost:{port}")

    try:
        from pyngrok import ngrok
        tunnel = ngrok.connect(port, "http")
        print(f"Public: {tunnel.public_url}")
        print("\nShare the public URL with your friends!")
    except Exception as e:
        print(f"\nngrok not available ({e})")
        print("Friends can still join on your local network.")

    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
