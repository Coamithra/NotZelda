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
ATTACK_COOLDOWN = 0.4

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
HEART_DROP_CHANCE = 0.1
INVINCIBILITY_DURATION = 1.5
COLLISION_GRACE_PERIOD = 0.1  # seconds before contact damage triggers (corner-scrape forgiveness)

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
