"""Shared constants for the MUD server — directions, gameplay tuning."""

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
WALK_TIME = 0.250          # seconds — full tile-to-tile walk duration
CANCEL_TIME = 0.090        # seconds — window to cancel a walk by releasing the key
LATENCY_COMP = 0.066       # seconds — dead reckoning offset; also used as leeway for all timing checks
ATTACK_COOLDOWN = 0.4
HEART_RESTORE_HP = 2
PLAYER_MAX_HP = 6
PLAYER_RESPAWN_DELAY = 5.5
GUARD_COOLDOWN = 10
HEART_DROP_CHANCE = 0.1
INVINCIBILITY_DURATION = 1.5

# Monsters
ROOM_RESET_COOLDOWN = 10.0
PROJECTILE_TICK_RATE = 0.15

DUNGEON_MUSIC_TRACKS = [
    "dungeon1", "dungeon2", "dungeon3", "dungeon4",
    "dungeon5", "dungeon6",
]

DUNGEON_BOSS_TRACKS = ["boss1", "boss2", "boss3"]
