"""Centralized mutable game state — single GameState instance shared by all modules."""

import json
from pathlib import Path


class GameState:
    def __init__(self):
        # World data (loaded from .room files)
        self.rooms = {}              # room_id -> room dict
        self.guards = {}             # room_id -> [guard dicts]
        self.monster_templates = {}  # room_id -> [template dicts]
        self.dungeon_templates = {}  # type_id -> {template_id: {name, tilemap, guards, monsters}}

        # Monster type registry (built-in + AI-generated)
        self.monster_stats = {}
        self.monster_behaviors = {}

        # Custom content registries (AI-generated, Stage 2+)
        self.custom_sprites = {}         # kind -> sprite data dict
        self.custom_death_sprites = {}   # kind -> death sprite data dict
        self.custom_tile_recipes = {}    # tile_id -> recipe dict {colors, layers, walkable}

        # Built-in IDs (loaded at startup, protected from registry sweeps)
        self.builtin_tile_ids = set()    # tile IDs from data/tiles.json
        self.builtin_monster_ids = set() # monster kinds from data/monsters.json + startup

        # NPC sprite data (loaded from data/npc_sprites.json)
        self.npc_sprites = {}

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
        self.locked_rooms = {}       # room_id -> {"original_tiles": {(row,col): tile_code}}
        self.room_pickup_freeze = {} # room_id -> {"start": monotonic, "end": monotonic}
        self.tombstones = {}         # player_name -> Tombstone

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
        """Check if a tile code (string) is walkable."""
        recipe = self.custom_tile_recipes.get(tile)
        return recipe is not None and recipe.get("walkable", False)

    def is_monster_walkable_tile(self, tile) -> bool:
        """Check if a tile code is walkable by monsters.

        Uses ``monster_walkable`` if present, otherwise falls back to ``walkable``.
        """
        recipe = self.custom_tile_recipes.get(tile)
        if recipe is None:
            return False
        if "monster_walkable" in recipe:
            return recipe["monster_walkable"]
        return recipe.get("walkable", False)

    def load_tiles(self):
        """Load all tile definitions from data/tiles.json."""
        path = Path(__file__).parent.parent / "data" / "tiles.json"
        if not path.exists():
            print("[STATE] WARNING: data/tiles.json not found")
            return
        tiles = json.loads(path.read_text(encoding="utf-8"))
        for tile_id, recipe in tiles.items():
            self.custom_tile_recipes[tile_id] = recipe
        self.builtin_tile_ids = set(tiles.keys())
        print(f"[STATE] Loaded {len(tiles)} tile recipes")

    def load_monsters(self):
        """Load all monster definitions from data/monsters.json."""
        from server.validation import register_monster_type
        path = Path(__file__).parent.parent / "data" / "monsters.json"
        if not path.exists():
            print("[STATE] WARNING: data/monsters.json not found")
            return
        monsters = json.loads(path.read_text(encoding="utf-8"))
        for kind, mdata in monsters.items():
            mdata.setdefault("kind", kind)
            ok, errors = register_monster_type(mdata)
            if ok:
                self.builtin_monster_ids.add(kind)
                print(f"[STATE] Registered monster: {kind}")
            else:
                print(f"[STATE] WARNING: Failed to register {kind}: {errors}")
        print(f"[STATE] Loaded {len(monsters)} monsters")

    def load_npc_sprites(self):
        """Load NPC sprite definitions from data/npc_sprites.json."""
        path = Path(__file__).parent.parent / "data" / "npc_sprites.json"
        if not path.exists():
            print("[STATE] WARNING: data/npc_sprites.json not found")
            return
        self.npc_sprites = json.loads(path.read_text(encoding="utf-8"))
        print(f"[STATE] Loaded {len(self.npc_sprites)} NPC sprites")


game = GameState()
