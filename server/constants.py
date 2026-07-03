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
ATTACK_COOLDOWN = 0.27  # 1.5 * SWORD_ACTIVE_DURATION (0.18) — gap = 0.5 * active
SWORD_ACTIVE_DURATION = 0.18
SWORD_DAMAGE = 1        # HP per sword hit on monsters
SWORD_PERP_WIDTH = 0.6  # perpendicular hitbox width (was implicit 1.0 with tile-based collision)
PLAYER_COLLISION_MARGIN = 0.275  # inset per side for player-vs-monster AABB (0.45 tile box)
MOVE_STEP = 1.0         # monster movement step size in tiles
KNOCKBACK_TILES = 1     # tiles a monster is pushed back on hit
KNOCKBACK_DURATION = 0.2  # seconds — server-side knockback slide duration

# Half-tile free movement (NES Zelda-style)
HALF_TILE = 0.5
WALK_ANIM_TIME = 0.250          # 250ms — other-player walk animation
MAX_MOVE_PER_UPDATE = 1.25      # max distance per player_state frame (tiles, Manhattan)
PLAYER_SPEED = 4.0              # tiles/sec (server-authoritative movement simulation)
DT_CLAMP = 0.05                 # max dt per input frame (50ms — matches client clamp)
MAX_INPUTS_PER_TICK = 5          # anti-spam: max inputs processed per player per tick
# anti-spam: cap queued commands drained per player per tick so a flooding client
# can't get N× the per-frame movement/attack budget in one tick. Generous enough
# for a legit input burst + a couple of state frames + chat/backlog.
MAX_COMMANDS_PER_TICK = 10
# hard bound on the per-player command backlog; excess (oldest) is dropped so the
# queue can't grow unboundedly between ticks under a flood.
MAX_COMMAND_QUEUE = 100
HEART_RESTORE_HP = 2
PLAYER_MAX_HP = 6
PLAYER_RESPAWN_DELAY = 5.5
GUARD_COOLDOWN = 10
GUARD_DESPAWN_TIMEOUT = 30.0   # seconds before summoned guards vanish
GUARD_DESPAWN_DISTANCE = 4     # Manhattan tiles — target escapes if beyond this
GUARD_DESPAWN_GRACE = 3.0      # seconds before distance check kicks in
HEART_DROP_CHANCE = 0.1
INVINCIBILITY_DURATION = 1.5
COLLISION_GRACE_PERIOD = 0.0   # seconds before contact damage triggers (no grace — smaller hitbox handles it)
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

# Ghost items — rendered as translucent ghosts after this player picks them up,
# while other players in the dungeon/world still need them.
GHOST_ELIGIBLE = {"seal_fragment", "heart_container", "spirit_jar"}

# Tick loop
TICK_INTERVAL = 1.0 / 30     # ~33ms — unified game tick rate

# Monsters
MONSTER_SPAWN_DELAY = 1.0      # seconds - base delay before monsters act when player enters room
MONSTER_SPAWN_STAGGER = 1.0    # seconds - random per-monster stagger added on top of spawn delay
ROOM_RESET_COOLDOWN = 300.0
PROJECTILE_TICK_RATE = 0.15
SWIM_WATER_PREFERENCE = 0.7    # probability aquatic monsters prefer water tiles when moving

# Gauntlet
GAUNTLET_STARTING_HP = 6       # HP reset on gauntlet entry and between waves
GAUNTLET_SPIRIT_JARS = 1       # spirit jars granted per wave
GAUNTLET_HARD_HP_THRESHOLD = 4 # HP lost >= this = "HARD" outcome
GAUNTLET_GOOD_HP_THRESHOLD = 1 # HP lost >= this (but < HARD) = "GOOD" outcome
GAUNTLET_GOOD_STREAK_RESET = 2 # consecutive "GOOD" results before resetting to max-hard

# NPC & Guards
NPC_RESPONSE_DELAY = 1.5       # seconds - minimum pause before NPC responds (feels natural)
NPC_MAX_RESPONSE_LENGTH = 200  # characters - hard cap on NPC response length
NPC_DETECTION_DISTANCE = 2.25  # Manhattan tiles - distance for detecting adjacent NPCs
NPC_PROXIMITY_DISTANCE = 1.5   # Manhattan tiles - distance for proximity dialog trigger
GUARD_SPAWN_COUNT_MIN = 3      # minimum guards spawned when NPC calls for help
GUARD_SPAWN_COUNT_MAX = 5      # maximum guards spawned when NPC calls for help

# Variant monsters
VARIANT_MIN_WALK_TIME = 0.1    # seconds - speed floor for variant monsters
VARIANT_MIN_DECISION_TIME = 0.2  # seconds - decision time floor for variant monsters

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
