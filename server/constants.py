"""Shared constants for the MUD server — tile IDs, directions, gameplay tuning."""

# ---------------------------------------------------------------------------
# Tile IDs
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
BRAZIER       = 36   # BZ - stone pedestal with fire (non-walkable)
MOSAIC_FLOOR  = 37   # MF - floor with decorative inlay (walkable)
CRACKED_FLOOR = 38   # CF - damaged floor with cracks (walkable)

WALKABLE_TILES = {GRASS, STONE, WOOD, FLOWERS, DIRT, STAIRS_UP, STAIRS_DOWN, DOOR,
                  SAND, CAVE_FLOOR, SWAMP, BRIDGE, RUINS_FLOOR, TALL_GRASS, ROAD,
                  SHALLOW_WATER, DUNGEON_FLOOR, MOSAIC_FLOOR, CRACKED_FLOOR}

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
    "BZ": BRAZIER, "MF": MOSAIC_FLOOR, "CF": CRACKED_FLOOR,
}

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
    "north": (7, 1), "south": (7, 9),
    "east": (13, 5), "west": (1, 5),
}
DEFAULT_SPAWN = (7, 5)

# ---------------------------------------------------------------------------
# Room dimensions
# ---------------------------------------------------------------------------

ROOM_COLS = 15
ROOM_ROWS = 11

# ---------------------------------------------------------------------------
# Gameplay
# ---------------------------------------------------------------------------

STARTING_ROOM = "town_square"
MOVE_COOLDOWN = 0.125
ATTACK_COOLDOWN = 0.4
HEART_RESTORE_HP = 2
PLAYER_MAX_HP = 6
PLAYER_RESPAWN_DELAY = 5.5
GUARD_COOLDOWN = 10
HEART_DROP_CHANCE = 0.1
INVINCIBILITY_DURATION = 1.5

# Monsters
MONSTER_TICK_RATE = 0.5  # ticks per second (default for unknown monsters)
ROOM_RESET_COOLDOWN = 10.0
PROJECTILE_TICK_RATE = 0.15

DUNGEON_MUSIC_TRACKS = [
    "dungeon1", "dungeon2", "dungeon3", "dungeon4",
    "dungeon5", "dungeon6", "dungeon7",
]
