"""
MUD Server — Zelda-style multiplayer online dungeon.

Run with: python mud_server.py
Then open http://localhost:8080 in your browser.
"""

import asyncio
import copy
import json
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
DUNGEON_WALL  = 32   # DW - smooth dark stone wall (non-walkable)
DUNGEON_FLOOR = 33   # DF - worn stone floor (walkable)
PILLAR        = 34   # PL - stone pillar (non-walkable)
SCONCE_WALL   = 35   # SC - wall with torch sconce (non-walkable)

WALKABLE_TILES = {GRASS, STONE, WOOD, FLOWERS, DIRT, STAIRS_UP, STAIRS_DOWN, DOOR,
                  SAND, CAVE_FLOOR, SWAMP, BRIDGE, RUINS_FLOOR, TALL_GRASS, ROAD,
                  SHALLOW_WATER, DUNGEON_FLOOR}

# Tile code string -> numeric ID (for .room file parsing)
TILE_CODES = {
    "GR": GRASS, "ST": STONE, "WD": WOOD, "WS": WALL_STONE, "WW": WALL_WOOD,
    "WA": WATER, "TR": TREE, "FL": FLOWERS, "DT": DIRT, "SU": STAIRS_UP,
    "SD": STAIRS_DOWN, "AN": ANVIL, "FP": FIREPLACE, "TB": TABLE, "PW": PEW,
    "DR": DOOR, "SA": SAND, "CC": CACTUS, "MT": MOUNTAIN, "CV": CAVE_FLOOR,
    "SM": SWAMP, "DK": DEAD_TREE, "BR": BRIDGE, "GS": GRAVESTONE, "IF": IRON_FENCE,
    "RW": RUINS_WALL, "RF": RUINS_FLOOR, "TG": TALL_GRASS, "RD": ROAD, "CL": CLIFF,
    "SH": SHALLOW_WATER, "BO": BOULDER,
    "DW": DUNGEON_WALL, "DF": DUNGEON_FLOOR, "PL": PILLAR, "SC": SCONCE_WALL,
}

# ---------------------------------------------------------------------------
# World data — 15 columns x 11 rows per room
# All rooms loaded from .room files in rooms/ directory
# ---------------------------------------------------------------------------

ROOMS = {}

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
        spawn_points = {"default": DEFAULT_SPAWN}
        for direction, pos in EDGE_SPAWN_POINTS.items():
            if direction in exits:
                spawn_points[direction] = pos
        # Scan for stairs tiles — use them for up/down spawn points
        su_pos = None
        sd_pos = None
        for ry, row in enumerate(tilemap):
            for rx, tile in enumerate(row):
                if tile == STAIRS_UP and su_pos is None:
                    su_pos = (rx, ry)
                elif tile == STAIRS_DOWN and sd_pos is None:
                    sd_pos = (rx, ry)
        if su_pos:
            spawn_points["down"] = su_pos   # entering from above → land at stairs up
        if sd_pos:
            spawn_points["up"] = sd_pos     # entering from below → land at stairs down

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
                    npc_sprite = tokens[4]
                    npc_dialog = " ".join(tokens[5:]) if len(tokens) > 5 else ""
                    if room_id not in GUARDS:
                        GUARDS[room_id] = []
                    GUARDS[room_id].append({
                        "name": npc_name, "x": npc_x, "y": npc_y,
                        "sprite": npc_sprite, "dialog": npc_dialog,
                    })
                elif tokens[0] == "monster" and len(tokens) >= 4:
                    kind = tokens[1]
                    mx = int(tokens[2])
                    my = int(tokens[3])
                    if room_id not in MONSTER_TEMPLATES:
                        MONSTER_TEMPLATES[room_id] = []
                    MONSTER_TEMPLATES[room_id].append({"kind": kind, "x": mx, "y": my})

        count += 1

    print(f"[ROOMS] Loaded {count} room files from {directory}/")
    print(f"[ROOMS] Total rooms: {len(ROOMS)}")


# ---------------------------------------------------------------------------
# Dungeon template loader
# ---------------------------------------------------------------------------

DUNGEON_TEMPLATES = {}  # template_id -> {name, tilemap, guards, monsters}

def load_dungeon_templates(directory: str = "rooms/dungeon1"):
    """Load dungeon room templates from .room files (no exits parsed)."""
    rooms_dir = Path(__file__).parent / directory
    if not rooms_dir.exists():
        print(f"[DUNGEON] No '{directory}/' directory found, skipping")
        return

    count = 0
    for room_file in sorted(rooms_dir.glob("*.room")):
        template_id = room_file.stem
        try:
            text = room_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[DUNGEON] Error reading {room_file.name}: {e}")
            continue

        parts = text.split("---")
        if len(parts) < 2:
            continue

        header = {}
        for line in parts[0].strip().splitlines():
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                header[key.strip()] = val.strip()

        tilemap_text = parts[1].strip()
        tilemap = []
        for row_line in tilemap_text.splitlines():
            row_line = row_line.strip()
            if not row_line:
                continue
            codes = row_line.split()
            row = [TILE_CODES.get(code, DUNGEON_FLOOR) for code in codes]
            while len(row) < 15:
                row.append(DUNGEON_FLOOR)
            row = row[:15]
            tilemap.append(row)
        while len(tilemap) < 11:
            tilemap.append([DUNGEON_FLOOR] * 15)
        tilemap = tilemap[:11]

        guards = []
        monsters = []
        if len(parts) >= 3:
            for line in parts[2].strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                tokens = line.split()
                if tokens[0] == "npc" and len(tokens) >= 5:
                    guards.append({
                        "name": tokens[1].replace("_", " "),
                        "x": int(tokens[2]), "y": int(tokens[3]),
                        "sprite": tokens[4],
                        "dialog": " ".join(tokens[5:]) if len(tokens) > 5 else "",
                    })
                elif tokens[0] == "monster" and len(tokens) >= 4:
                    monsters.append({"kind": tokens[1], "x": int(tokens[2]), "y": int(tokens[3])})

        DUNGEON_TEMPLATES[template_id] = {
            "name": header.get("name", template_id),
            "tilemap": tilemap,
            "guards": guards,
            "monsters": monsters,
        }
        count += 1

    print(f"[DUNGEON] Loaded {count} dungeon templates from {directory}/")


STARTING_ROOM = "town_square"

# ---------------------------------------------------------------------------
# NPC Guards
# ---------------------------------------------------------------------------

GUARDS = {}  # Populated from .room files by load_room_files()

GUARD_COOLDOWN = 10  # seconds between repeated guard messages per player

# Unified direction data
DIRECTIONS = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": (1,  0),
}

DIRECTION_OPPOSITES = {"up": "down", "down": "up", "left": "right", "right": "left"}

# Maps direction player walked to the direction they should enter from
ENTRY_DIR = {
    "north": "south", "south": "north",
    "east": "west", "west": "east",
    "up": "up", "down": "down",
}

# Spawn points relative to room edges
EDGE_SPAWN_POINTS = {
    "north": (7, 1), "south": (7, 9),
    "east": (13, 5), "west": (1, 5),
}
DEFAULT_SPAWN = (7, 5)

# Room dimensions
ROOM_COLS = 15
ROOM_ROWS = 11

# Gameplay constants
MOVE_COOLDOWN = 0.125
ATTACK_COOLDOWN = 0.4
HEART_RESTORE_HP = 2
PLAYER_MAX_HP = 6
PLAYER_RESPAWN_DELAY = 5.5

# ---------------------------------------------------------------------------
# Monsters
# ---------------------------------------------------------------------------

MONSTER_HOP_INTERVAL = 2.0    # seconds between random hops (default)
ROOM_RESET_COOLDOWN = 10.0   # seconds after all-killed + empty before respawn

# Per-kind monster stats
MONSTER_STATS = {
    "slime":      {"hp": 1, "hop_interval": 2.0, "damage": 1},
    "bat":        {"hp": 1, "hop_interval": 1.0, "damage": 1},
    "scorpion":   {"hp": 2, "hop_interval": 2.0, "damage": 2},
    "skeleton":   {"hp": 2, "hop_interval": 2.0, "damage": 3},
    "swamp_blob": {"hp": 1, "hop_interval": 2.0, "damage": 1},
}

HEART_DROP_CHANCE = 0.1
INVINCIBILITY_DURATION = 1.5

import random

class Monster:
    def __init__(self, x, y, kind="slime"):
        self.x = x
        self.y = y
        self.kind = kind
        self.alive = True
        self.last_hop_time = time.monotonic()
        stats = MONSTER_STATS.get(kind, {"hp": 1, "hop_interval": 2.0, "damage": 1})
        self.hp = stats["hp"]
        self.hop_interval = stats["hop_interval"]
        self.damage = stats.get("damage", 1)

# Templates — define what monsters belong in each room (never mutated)
MONSTER_TEMPLATES = {}  # Populated from .room files by load_room_files()

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
    # Dungeon cleared rooms stay empty (no respawn)
    if active_dungeon and room_id in active_dungeon.cleared_rooms:
        room_monsters[room_id] = []
        return
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

    room_hearts.pop(room_id, None)

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

    # Dungeon cleanup — destroy instance when all players have left
    if active_dungeon and room_id in active_dungeon.active_rooms:
        if dungeon_player_count() == 0:
            destroy_dungeon()

# ---------------------------------------------------------------------------
# Heart pickups
# ---------------------------------------------------------------------------

room_hearts: dict[str, list[dict]] = {}
next_heart_id = 0

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
        self.hp = PLAYER_MAX_HP
        self.max_hp = PLAYER_MAX_HP
        self.last_damage_time = 0.0
        self.last_move_time = 0.0
        self.last_attack_time = 0.0
        self.dancing = False
        self.guard_cooldowns = {}  # guard_key -> last_trigger_time
        self.quests = {}   # quest_id (str) -> stage (int)
        self.flags = set() # string flags, e.g. {"has_sword"}

    def quest(self, qid: str) -> int:
        return self.quests.get(qid, 0)

    def set_quest(self, qid: str, stage: int):
        self.quests[qid] = stage

    def has_flag(self, flag: str) -> bool:
        return flag in self.flags

    def grant_flag(self, flag: str):
        self.flags.add(flag)


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


# ---------------------------------------------------------------------------
# Dungeon Instance System
# ---------------------------------------------------------------------------

from dungeon_layouts import DUNGEON_LAYOUTS

DUNGEON_MUSIC_TRACKS = ["dungeon1", "dungeon2", "dungeon3", "dungeon4"]

class DungeonInstance:
    def __init__(self, dungeon_id, layout, room_map, active_rooms, entrance_room_id, music_track):
        self.dungeon_id = dungeon_id
        self.layout = layout
        self.room_map = room_map           # (col, row) -> template_id
        self.active_rooms = active_rooms   # set of room_id strings
        self.cleared_rooms = set()         # room_ids where all monsters killed
        self.entrance_room_id = entrance_room_id
        self.music_track = music_track

active_dungeon: DungeonInstance | None = None


def create_dungeon() -> DungeonInstance:
    """Create a new dungeon instance from random layout + templates."""
    global active_dungeon

    layout = random.choice(DUNGEON_LAYOUTS)
    music_track = random.choice(DUNGEON_MUSIC_TRACKS)

    # Find all active cells in layout
    active_cells = []
    for row_idx, row_str in enumerate(layout["grid"]):
        for col_idx, ch in enumerate(row_str):
            if ch == "X":
                active_cells.append((col_idx, row_idx))

    # Assign templates to cells
    template_keys = list(DUNGEON_TEMPLATES.keys())
    if not template_keys:
        print("[DUNGEON] No dungeon templates loaded, cannot create dungeon")
        return None
    random.shuffle(template_keys)
    # Cycle through templates if we have more cells than templates
    room_map = {}
    for i, cell in enumerate(active_cells):
        room_map[cell] = template_keys[i % len(template_keys)]

    entrance_col, entrance_row = layout["entrance"]
    entrance_room_id = f"d1_{entrance_col}_{entrance_row}"
    active_rooms = set()

    for (col, row), template_id in room_map.items():
        room_id = f"d1_{col}_{row}"
        active_rooms.add(room_id)
        tmpl = DUNGEON_TEMPLATES[template_id]

        # Deep-copy tilemap
        tilemap = [list(r) for r in tmpl["tilemap"]]

        # Auto-generate exits from layout adjacency
        exits = {}
        if (col, row - 1) in room_map:
            exits["north"] = f"d1_{col}_{row - 1}"
        if (col, row + 1) in room_map:
            exits["south"] = f"d1_{col}_{row + 1}"
        if (col - 1, row) in room_map:
            exits["west"] = f"d1_{col - 1}_{row}"
        if (col + 1, row) in room_map:
            exits["east"] = f"d1_{col + 1}_{row}"

        # Wall off unused exits
        if "north" not in exits:
            for c in (6, 7, 8):
                tilemap[0][c] = DUNGEON_WALL
        if "south" not in exits:
            for c in (6, 7, 8):
                tilemap[10][c] = DUNGEON_WALL
        if "west" not in exits:
            for r in (4, 5, 6):
                tilemap[r][0] = DUNGEON_WALL
        if "east" not in exits:
            for r in (4, 5, 6):
                tilemap[r][14] = DUNGEON_WALL

        # Entrance cell gets stairs up to clearing
        if col == entrance_col and row == entrance_row:
            exits["up"] = "clearing"
            tilemap[9][7] = STAIRS_UP

        # Build spawn points
        spawn_points = {"default": DEFAULT_SPAWN}
        for direction, pos in EDGE_SPAWN_POINTS.items():
            if direction in exits:
                spawn_points[direction] = pos
        # Scan for stairs
        for ry, trow in enumerate(tilemap):
            for rx, tile in enumerate(trow):
                if tile == STAIRS_UP:
                    spawn_points["down"] = (rx, ry)
                elif tile == STAIRS_DOWN:
                    spawn_points["up"] = (rx, ry)

        ROOMS[room_id] = {
            "name": tmpl["name"],
            "exits": exits,
            "tilemap": tilemap,
            "spawn_points": spawn_points,
            "biome": "dungeon",
            "music": music_track,
        }
        if tmpl["guards"]:
            GUARDS[room_id] = copy.deepcopy(tmpl["guards"])
        if tmpl["monsters"]:
            MONSTER_TEMPLATES[room_id] = copy.deepcopy(tmpl["monsters"])

    instance = DungeonInstance(
        dungeon_id="d1",
        layout=layout,
        room_map=room_map,
        active_rooms=active_rooms,
        entrance_room_id=entrance_room_id,
        music_track=music_track,
    )
    active_dungeon = instance
    print(f"[DUNGEON] Created instance: layout={layout['name']}, rooms={len(active_rooms)}, entrance={entrance_room_id}, music={music_track}")
    return instance


def destroy_dungeon():
    """Tear down the active dungeon instance."""
    global active_dungeon
    if active_dungeon is None:
        return

    for room_id in active_dungeon.active_rooms:
        ROOMS.pop(room_id, None)
        GUARDS.pop(room_id, None)
        MONSTER_TEMPLATES.pop(room_id, None)
        room_monsters.pop(room_id, None)
        room_cooldowns.pop(room_id, None)
        room_hearts.pop(room_id, None)

    print(f"[DUNGEON] Destroyed instance: layout={active_dungeon.layout['name']}")
    active_dungeon = None


def is_dungeon_room(room_id: str) -> bool:
    return active_dungeon is not None and room_id in active_dungeon.active_rooms


def dungeon_player_count() -> int:
    if active_dungeon is None:
        return 0
    return sum(1 for p in players.values() if p.room in active_dungeon.active_rooms)


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
        "guards": [{"name": g["name"], "x": g["x"], "y": g["y"], "sprite": g.get("sprite", "guard")} for g in guards],
        "monsters": monsters,
        "exits": {d: exits[d] for d in exits},
        "biome": room.get("biome", "town"),
        "music": room.get("music", "overworld"),
        "exit_direction": exit_direction,
        "hp": player.hp,
        "max_hp": player.max_hp,
    })

# ---------------------------------------------------------------------------
# Movement & room transitions
# ---------------------------------------------------------------------------

async def do_room_transition(player: Player, exit_direction: str):
    old_room = player.room
    new_room_id = ROOMS[old_room]["exits"][exit_direction]

    # Dungeon entrance — create instance on demand
    if new_room_id == "d1_entrance":
        if active_dungeon is None:
            if create_dungeon() is None:
                await send_to(player, {"type": "info", "text": "The dungeon entrance is sealed."})
                return
        new_room_id = active_dungeon.entrance_room_id

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
                await handle_quest_npc(player, guard)


# ---------------------------------------------------------------------------
# Contact damage
# ---------------------------------------------------------------------------

async def damage_player(player: Player, damage: int, room_id: str):
    """Apply contact damage to a player from a monster."""
    now = time.monotonic()
    if now - player.last_damage_time < INVINCIBILITY_DURATION:
        return
    player.hp = max(0, player.hp - damage)
    player.last_damage_time = now

    if player.hp > 0:
        # Calculate knockback — push player away from facing direction
        opp = DIRECTION_OPPOSITES.get(player.direction, "down")
        kdx, kdy = DIRECTIONS[opp]
        kx, ky = player.x + kdx, player.y + kdy
        knocked = False
        room = ROOMS[room_id]
        tilemap = room["tilemap"]
        guards = GUARDS.get(room_id, [])
        if 0 <= kx < ROOM_COLS and 0 <= ky < ROOM_ROWS and tilemap[ky][kx] in WALKABLE_TILES:
            if not any(g["x"] == kx and g["y"] == ky for g in guards):
                player.x, player.y = kx, ky
                knocked = True

        await broadcast_to_room(room_id, {
            "type": "player_hurt",
            "name": player.name,
            "hp": player.hp,
            "max_hp": player.max_hp,
            "x": player.x,
            "y": player.y,
            "knockback": knocked,
        })
    else:
        # Player died
        await broadcast_to_room(room_id, {
            "type": "player_died",
            "name": player.name,
            "x": player.x,
            "y": player.y,
            "color_index": player.color_index,
        }, exclude=player.ws)
        await send_to(player, {
            "type": "you_died",
            "x": player.x,
            "y": player.y,
        })

        # Respawn after delay (match client death animation duration)
        await asyncio.sleep(PLAYER_RESPAWN_DELAY)
        old_room = player.room
        player.hp = player.max_hp
        player.room = STARTING_ROOM
        spawn = ROOMS[STARTING_ROOM]["spawn_points"]["default"]
        player.x, player.y = spawn
        player.direction = "down"
        player.dancing = False

        await broadcast_to_room(old_room, {
            "type": "player_left", "name": player.name,
        })
        await on_player_leave_room(old_room)
        await on_player_enter_room(STARTING_ROOM)
        await send_room_enter(player)
        await broadcast_to_room(
            STARTING_ROOM,
            {"type": "player_entered", **player_info(player)},
            exclude=player.ws,
        )


# ---------------------------------------------------------------------------
# Quest NPC handler registry
# ---------------------------------------------------------------------------

NPC_HANDLERS = {}  # (npc_name, room_id) -> async handler(player, guard)

def npc_handler(name: str, room: str):
    """Decorator to register a quest-aware NPC handler."""
    def decorator(fn):
        NPC_HANDLERS[(name, room)] = fn
        return fn
    return decorator


@npc_handler("Amara", "chapel_sanctum")
async def amara_interact(player: Player, guard: dict):
    if player.quest("amara") == 0:
        player.set_quest("amara", 1)
        await broadcast_to_room(player.room, {
            "type": "chat",
            "from": player.name,
            "text": "Who could have done this to her?",
        })
        await send_to(player, {"type": "quest_update", "quest": "amara", "stage": 1})
    # Amara never speaks


@npc_handler("Priest", "old_chapel")
async def priest_interact(player: Player, guard: dict):
    stage = player.quest("amara")
    if stage == 0:
        dialog = "Peace be with you, traveler."
    elif stage == 1:
        dialog = "The princess has been cursed. Please, speak to the smith before you go."
    else:
        dialog = "May the light guide you. Save Princess Amara!"
    await broadcast_to_room(player.room, {
        "type": "chat", "from": guard["name"], "text": dialog,
    })


@npc_handler("Smith", "blacksmith")
async def smith_interact(player: Player, guard: dict):
    stage = player.quest("amara")
    if stage == 0:
        dialog = "Well met!"
    elif stage == 1:
        dialog = "It's dangerous to go alone \u2014 take this!"
        player.grant_flag("has_sword")
        player.set_quest("amara", 2)
        await broadcast_to_room(player.room, {
            "type": "chat", "from": guard["name"], "text": dialog,
        })
        await send_to(player, {"type": "sword_obtained"})
        await broadcast_to_room(player.room, {
            "type": "sword_effect", "name": player.name,
        }, exclude=player.ws)
        return
    else:
        dialog = "Give those monsters what they deserve!"
    await broadcast_to_room(player.room, {
        "type": "chat", "from": guard["name"], "text": dialog,
    })


@npc_handler("Barmaid", "tavern")
async def barmaid_interact(player: Player, guard: dict):
    if player.hp < player.max_hp:
        player.hp = player.max_hp
        await send_to(player, {"type": "hp_update", "hp": player.hp, "max_hp": player.max_hp})
        dialog = "Here, let me patch you up!"
    else:
        dialog = "You look healthy to me!"
    await broadcast_to_room(player.room, {
        "type": "chat", "from": guard["name"], "text": dialog,
    })


async def handle_quest_npc(player: Player, guard: dict):
    """Dispatch to registered NPC handler, or fall back to static dialog."""
    handler = NPC_HANDLERS.get((guard["name"], player.room))
    if handler:
        await handler(player, guard)
    elif guard["dialog"]:
        await broadcast_to_room(player.room, {
            "type": "chat", "from": guard["name"], "text": guard["dialog"],
        })


async def handle_move(player: Player, direction: str):
    if player.hp <= 0:
        return
    now = time.monotonic()
    if now - player.last_move_time < MOVE_COOLDOWN:
        return
    player.last_move_time = now

    delta = DIRECTIONS.get(direction)
    if not delta:
        return
    dx, dy = delta

    player.direction = direction
    player.dancing = False
    new_x = player.x + dx
    new_y = player.y + dy

    room = ROOMS[player.room]
    tilemap = room["tilemap"]

    # Off edge — check for room exit
    if new_x < 0 or new_x >= ROOM_COLS or new_y < 0 or new_y >= ROOM_ROWS:
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

    # Monster contact damage — check if player walked onto a monster
    if player.hp > 0:
        for monster in get_room_monsters(player.room):
            if monster.alive and monster.x == new_x and monster.y == new_y:
                await damage_player(player, monster.damage, player.room)
                break

    # Heart pickup
    hearts = room_hearts.get(player.room, [])
    for heart in hearts:
        if heart["x"] == player.x and heart["y"] == player.y and player.hp < player.max_hp:
            player.hp = min(player.max_hp, player.hp + HEART_RESTORE_HP)
            hearts.remove(heart)
            await send_to(player, {"type": "hp_update", "hp": player.hp, "max_hp": player.max_hp})
            await broadcast_to_room(player.room, {"type": "heart_collected", "id": heart["id"]})
            break

    # Guard proximity chat
    await check_guard_proximity(player)

# ---------------------------------------------------------------------------
# Attack
# ---------------------------------------------------------------------------

async def handle_attack(player: Player):
    if player.hp <= 0:
        return
    if not player.has_flag("has_sword"):
        await send_to(player, {"type": "info", "text": "You don't have a weapon."})
        return
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
    dx, dy = DIRECTIONS.get(player.direction, (0, 0))
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
                # Heart drop
                global next_heart_id
                if random.random() < HEART_DROP_CHANCE:
                    hid = next_heart_id
                    next_heart_id += 1
                    heart = {"x": monster.x, "y": monster.y, "id": hid}
                    room_hearts.setdefault(player.room, []).append(heart)
                    await broadcast_to_room(player.room, {
                        "type": "heart_spawned",
                        "id": hid,
                        "x": monster.x,
                        "y": monster.y,
                    })
                # Mark dungeon room as cleared if all monsters dead
                if is_dungeon_room(player.room):
                    alive = [m for m in room_monsters[player.room] if m.alive]
                    if not alive:
                        active_dungeon.cleared_rooms.add(player.room)
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
                    if nx < 0 or nx >= ROOM_COLS or ny < 0 or ny >= ROOM_ROWS:
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
                    # Check if monster landed on a player
                    for p in players_in_room(room_id):
                        if p.x == nx and p.y == ny and p.hp > 0:
                            await damage_player(p, monster.damage, room_id)
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

        name = data.get("name", "").strip()[:20]
        desc = data.get("description", "").strip()[:80]

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

        await send_to(player, {"type": "login_ok", "color_index": color_index, "hp": PLAYER_MAX_HP, "max_hp": PLAYER_MAX_HP})
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
    "/sprite_data.js": ("sprite_data.js", "application/javascript; charset=utf-8"),
    "/sprites.js":  ("sprites.js",  "application/javascript; charset=utf-8"),
    "/tiles.js":    ("tiles.js",    "application/javascript; charset=utf-8"),
    "/music.js":    ("music.js",    "application/javascript; charset=utf-8"),
    "/music.mp3":         ("not zelda (village).mp3", "audio/mpeg"),
    "/music_tavern.mp3":  ("not zelda (tavern).mp3", "audio/mpeg"),
    "/music_chapel.mp3":  ("not zelda (chapel).mp3", "audio/mpeg"),
    "/music_overworld.mp3": ("not zelda (overworld).mp3", "audio/mpeg"),
    "/music_dungeon1.mp3": ("not zelda (dungeon theme a).mp3", "audio/mpeg"),
    "/music_dungeon2.mp3": ("not zelda (dungeon theme b).mp3", "audio/mpeg"),
    "/music_dungeon3.mp3": ("not zelda (dungeon theme c).mp3", "audio/mpeg"),
    "/music_dungeon4.mp3": ("not zelda (dungeon theme d).mp3", "audio/mpeg"),
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
    load_dungeon_templates()
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
