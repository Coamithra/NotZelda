"""Centralized mutable game state — single GameState instance shared by all modules."""

from pathlib import Path

from server.constants import WALKABLE_TILES


class GameState:
    def __init__(self):
        # World data (loaded from .room files)
        self.rooms = {}              # room_id -> room dict
        self.guards = {}             # room_id -> [guard dicts]
        self.monster_templates = {}  # room_id -> [template dicts]
        self.dungeon_templates = {}  # type_id -> {template_id: {name, tilemap, guards, monsters}}

        # Monster type registry (built-in + AI-generated)
        self.monster_stats = {
            "slime":      {"hp": 1, "walk_time": 0.25, "decision_time": 2.0, "damage": 1},
            "bat":        {"hp": 1, "walk_time": 0.2,  "decision_time": 1.0, "damage": 1},
            "scorpion":   {"hp": 2, "walk_time": 0.25, "decision_time": 2.0, "damage": 2},
            "skeleton":   {"hp": 2, "walk_time": 0.25, "decision_time": 2.0, "damage": 3},
            "swamp_blob": {"hp": 1, "walk_time": 0.35, "decision_time": 2.0, "damage": 1},
        }

        # Custom content registries (AI-generated, Stage 2+)
        self.custom_sprites = {}         # kind -> sprite data dict
        self.custom_death_sprites = {}   # kind -> death sprite data dict
        self.custom_tile_recipes = {}    # tile_id -> recipe dict {colors, layers, walkable}
        self.monster_behaviors = {       # kind -> behavior dict
            "slime": {"rules": [
                {"if": "always", "do": "move", "direction": "random", "distance": 2},
            ]},
        }

        # Content libraries (per dungeon type)
        # type_id -> {"rooms": ContentLibrary, "monsters": ContentLibrary, "tiles": ContentLibrary}
        self.content_libraries = {}

        # Deprecated content (per dungeon type)
        # type_id -> {"monsters": set(), "tiles": set()}
        self.deprecated_content = {}

        # Live game state
        self.players = {}            # websocket -> Player
        self.room_monsters = {}      # room_id -> [Monster]
        self.room_cooldowns = {}     # room_id -> timestamp
        self.room_hearts = {}        # room_id -> [heart dicts]
        self.room_projectiles = {}   # room_id -> {proj_id: Projectile}

        # Dungeons
        self.active_dungeons = {}    # type_id -> DungeonInstance
        self.room_to_dungeon = {}    # room_id -> type_id (reverse lookup)

        # Counters
        self.next_heart_id = 0
        self.next_color_index = 0
        self.next_projectile_id = 0

        # Content deprecation & background regen
        self.last_deprecation_time = 0.0  # timestamp of last deprecation pass
        self.regen_tasks = {}              # type_id -> asyncio.Task

        # Activity log path
        self.log_file = Path(__file__).parent.parent / "event_log.txt"

    def is_walkable_tile(self, tile) -> bool:
        """Check if a tile ID (numeric or string) is walkable."""
        if tile in WALKABLE_TILES:
            return True
        recipe = self.custom_tile_recipes.get(tile)
        return recipe is not None and recipe.get("walkable", False)


game = GameState()
