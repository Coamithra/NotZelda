"""Shared constants and room geometry utilities for the MUD server."""

import os
from collections import deque

# ---------------------------------------------------------------------------
# Debug
# ---------------------------------------------------------------------------

DEBUG_MODE = os.environ.get("DEBUG_MODE", "").lower() in ("1", "true")

# ---------------------------------------------------------------------------
# Directions
# ---------------------------------------------------------------------------

DIRECTIONS = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": (1,  0),
}

DIRECTION_OPPOSITES = {"up": "down", "down": "up", "left": "right", "right": "left"}

# Maps exit direction to entry side of the destination room
ENTRY_DIR = {
    "north": "south", "south": "north",
    "east": "west", "west": "east",
    "up": "up", "down": "down",
}

EDGE_SPAWN_POINTS = {
    "north": (7, 0), "south": (7, 10),
    "east": (14, 5), "west": (0, 5),
}
DEFAULT_SPAWN = (8, 5)

# ---------------------------------------------------------------------------
# Room dimensions
# ---------------------------------------------------------------------------

ROOM_COLS = 15
ROOM_ROWS = 11

# ---------------------------------------------------------------------------
# Gameplay
# ---------------------------------------------------------------------------

STARTING_ROOM = "town_square"
WALK_TIME = 0.250          # seconds — monster tile-to-tile walk duration (kept for monster walks)
CANCEL_TIME = 0.090        # seconds — legacy (kept for backward compat)
LATENCY_COMP = 0.066       # seconds — legacy (kept for backward compat)
ATTACK_COOLDOWN = 0.27  # 1.5 * SWORD_ACTIVE_DURATION (0.18) — gap = 0.5 * active
SWORD_ACTIVE_DURATION = 0.18
SWORD_PERP_WIDTH = 0.6  # perpendicular hitbox width (was implicit 1.0 with tile-based collision)
MOVE_STEP = 0.5         # monster movement step size in tiles (was implicit 1.0)

# Half-tile free movement (NES Zelda-style)
HALF_TILE = 0.5
HALF_WALK_TIME = 0.125          # 125ms — other-player half-tile animation
POSITION_UPDATE_RATE = 0.04     # min seconds between updates (25/sec max)
MAX_MOVE_PER_UPDATE = 1.25      # max distance per position_update (0.5 on each axis + margin)
PLAYER_SPEED = 4.0              # tiles/sec (for anti-cheat speed check)
HEART_RESTORE_HP = 2
PLAYER_MAX_HP = 6
PLAYER_RESPAWN_DELAY = 5.5
GUARD_COOLDOWN = 10
GUARD_DESPAWN_TIMEOUT = 30.0   # seconds before summoned guards vanish
GUARD_DESPAWN_DISTANCE = 4     # Manhattan tiles — target escapes if beyond this
GUARD_DESPAWN_GRACE = 3.0      # seconds before distance check kicks in
HEART_DROP_CHANCE = 0.1
INVINCIBILITY_DURATION = 1.5
COLLISION_GRACE_PERIOD = 0.04  # seconds (~1 tick) before contact damage triggers (corner-scrape forgiveness)
ITEM_PICKUP_FREEZE_DURATION = 2.5  # seconds — monsters pause during item pickup animation
REVIVAL_DURATION = 6.5              # seconds — channel time to revive a tombstone
REVIVAL_PROXIMITY = 1.0             # tile distance — how close reviver must be to tombstone
REVIVAL_HP = 6                      # HP on revive (3 hearts) — caps both spirit jar and player revival

# Darkness & Lantern
DARK_ROOM_FRACTION = 0.25           # ~25% of eligible rooms flagged dark (d1)
DEFAULT_DARK_FRACTION = 0.10        # 10% of eligible rooms flagged dark (other dungeons)
LANTERN_RADIUS = 3.5                # tile visibility radius with lantern
NO_LANTERN_RADIUS = 0.75            # tile visibility radius without lantern (practically blind)
BRIGHT_TILE_RADIUS = 3.0            # static light radius for sconces, braziers, fireplaces
SEAL_FRAGMENT_HP_BONUS = 2          # +1 heart container = +2 HP

# Tick loop
TICK_INTERVAL = 1.0 / 30     # ~33ms — unified game tick rate

# Monsters
ROOM_RESET_COOLDOWN = 10.0
PROJECTILE_TICK_RATE = 0.15

DUNGEON_MUSIC_TRACKS = [
    "dungeon1", "dungeon2", "dungeon3", "dungeon4",
    "dungeon5", "dungeon6",
]

DUNGEON_BOSS_TRACKS = ["boss1", "boss2", "boss3"]

# ---------------------------------------------------------------------------
# Room geometry — doorway positions
# ---------------------------------------------------------------------------

# Standard doorway tile positions (row, col) per direction
DOORWAY_TILES = {
    "north": [(0, 6), (0, 7), (0, 8)],
    "south": [(10, 6), (10, 7), (10, 8)],
    "west":  [(4, 0), (5, 0), (6, 0)],
    "east":  [(4, 14), (5, 14), (6, 14)],
}

ALL_DOORWAY_TILES = [(r, c) for tiles in DOORWAY_TILES.values() for r, c in tiles]


def bfs_reachable(tilemap, is_walkable, seeds=None):
    """BFS from seed tiles to find all reachable walkable tiles.

    Args:
        tilemap: 11x15 grid of tile codes
        is_walkable: callable(tile_code) -> bool
        seeds: list of (row, col) start positions.
               Defaults to all 12 standard doorway tiles.
    Returns:
        set of (row, col) reachable walkable tiles.
    """
    if seeds is None:
        seeds = ALL_DOORWAY_TILES
    reachable = set()
    queue = deque()
    for r, c in seeds:
        if 0 <= r < ROOM_ROWS and 0 <= c < ROOM_COLS and is_walkable(tilemap[r][c]):
            if (r, c) not in reachable:
                reachable.add((r, c))
                queue.append((r, c))
    while queue:
        r, c = queue.popleft()
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if (0 <= nr < ROOM_ROWS and 0 <= nc < ROOM_COLS
                    and (nr, nc) not in reachable
                    and is_walkable(tilemap[nr][nc])):
                reachable.add((nr, nc))
                queue.append((nr, nc))
    return reachable
