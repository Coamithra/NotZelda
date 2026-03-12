"""Centralized mutable game state — single GameState instance shared by all modules."""

from pathlib import Path

from server.constants import WALKABLE_TILES


class GameState:
    def __init__(self):
        # World data (loaded from .room files)
        self.rooms = {}              # room_id -> room dict
        self.guards = {}             # room_id -> [guard dicts]
        self.monster_templates = {}  # room_id -> [template dicts]
        self.dungeon_templates = {}  # template_id -> {name, tilemap, guards, monsters}

        # Monster type registry (built-in + AI-generated)
        self.monster_stats = {
            "slime":      {"hp": 1, "tick_rate": 0.5, "damage": 1},
            "bat":        {"hp": 1, "tick_rate": 1.0, "damage": 1},
            "scorpion":   {"hp": 2, "tick_rate": 0.5, "damage": 2},
            "skeleton":   {"hp": 2, "tick_rate": 0.5, "damage": 3},
            "swamp_blob": {"hp": 1, "tick_rate": 0.5, "damage": 1},
        }

        # Custom content registries (AI-generated, Stage 2+)
        self.custom_sprites = {}         # kind -> sprite data dict
        self.custom_death_sprites = {}   # kind -> death sprite data dict
        self.custom_tile_recipes = {}    # tile_id -> recipe dict
        self.custom_walkable_tiles = set()
        self.monster_behaviors = {}      # kind -> behavior dict

        # Content libraries (Stage 7 — tag-based content management)
        self.monster_library = None  # ContentLibrary | None
        self.tile_library = None     # ContentLibrary | None
        self.room_library = None     # ContentLibrary | None

        # Deprecated content — removed from libraries but kept in game
        # registries because existing rooms still reference them.
        # Cleaned up when no room references them anymore.
        self.deprecated_monsters = set()  # kind IDs
        self.deprecated_tiles = set()     # tile IDs

        # Live game state
        self.players = {}            # websocket -> Player
        self.room_monsters = {}      # room_id -> [Monster]
        self.room_cooldowns = {}     # room_id -> timestamp
        self.room_hearts = {}        # room_id -> [heart dicts]
        self.room_projectiles = {}   # room_id -> {proj_id: Projectile}

        # Dungeon
        self.active_dungeon = None   # DungeonInstance | None

        # Counters
        self.next_heart_id = 0
        self.next_color_index = 0
        self.next_projectile_id = 0

        # Content deprecation & background regen
        self.last_deprecation_time = 0.0  # timestamp of last deprecation pass
        self.regen_task = None             # asyncio.Task for background content generation

        # Activity log path
        self.log_file = Path(__file__).parent.parent / "event_log.txt"

    def is_walkable_tile(self, tile) -> bool:
        """Check if a tile ID (numeric or string) is walkable."""
        return tile in WALKABLE_TILES or tile in self.custom_walkable_tiles


game = GameState()
