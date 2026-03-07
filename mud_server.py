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

from server import behavior_engine

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

def is_walkable_tile(tile) -> bool:
    """Check if a tile ID (numeric or string) is walkable."""
    return tile in WALKABLE_TILES or tile in CUSTOM_WALKABLE_TILES

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

# Custom sprite/tile data for AI-generated content (Stage 2: dynamic registries)
# Populated by register_monster_type() / register_tile_type()
CUSTOM_SPRITES = {}       # kind -> sprite data dict (same shape as MONSTER_SPRITE_DATA entries)
CUSTOM_DEATH_SPRITES = {} # kind -> death sprite data dict
CUSTOM_TILE_RECIPES = {}  # tile_id -> recipe dict (colors + operations)
CUSTOM_WALKABLE_TILES = set()  # set of custom tile IDs that are walkable
MONSTER_BEHAVIORS = {}    # kind -> behavior dict {rules: [...], patrol_waypoints: [...]}

# ---------------------------------------------------------------------------
# Validation & registration for dynamic content (Stage 3)
# ---------------------------------------------------------------------------

import re as _re

_HEX_COLOR_RE = _re.compile(r'^#[0-9a-fA-F]{6}$')

VALID_TILE_OPS = frozenset({
    "fill", "noise", "bricks", "grid_lines", "hstripes", "vstripes",
    "wave", "ripple", "rects", "pixels",
})

VALID_BEHAVIOR_CONDITIONS = frozenset({
    "player_within", "player_beyond", "hp_below_pct", "hp_above_pct",
    "random_chance", "always", "default", "can_attack", "player_in_attack_range",
})

VALID_BEHAVIOR_ACTIONS = frozenset({
    "wander", "chase", "flee", "patrol", "hold", "attack",
})

VALID_ATTACK_TYPES = frozenset({
    "melee", "projectile", "charge", "teleport", "area",
})


def _is_hex_color(s) -> bool:
    """Check if a string is a valid #RRGGBB hex color."""
    return isinstance(s, str) and bool(_HEX_COLOR_RE.match(s))


def validate_monster(data: dict) -> list[str]:
    """Validate a monster definition. Returns a list of error strings (empty = valid).

    Expected shape:
      kind: str
      stats: {hp: int, hop_interval: float, damage: int}
      sprite: {colors: {key: "#hex"}, frames: [[[colorKey, x, y, w, h], ...], ...]}
      behavior: {rules: [...], attacks: [...]}  (optional)
      death_sprite: {colors: {...}, frames: [...]}  (optional)
    """
    errors = []

    # -- kind --
    kind = data.get("kind")
    if not isinstance(kind, str) or not kind:
        errors.append("kind must be a non-empty string")
    elif not _re.match(r'^[a-z][a-z0-9_]*$', kind):
        errors.append("kind must be lowercase alphanumeric with underscores")

    # -- stats --
    stats = data.get("stats")
    if not isinstance(stats, dict):
        errors.append("stats must be a dict")
    else:
        hp = stats.get("hp")
        if not isinstance(hp, (int, float)) or hp < 1 or hp > 100:
            errors.append("stats.hp must be 1-100")
        hop = stats.get("hop_interval")
        if not isinstance(hop, (int, float)) or hop < 0.2 or hop > 10.0:
            errors.append("stats.hop_interval must be 0.2-10.0")
        dmg = stats.get("damage")
        if not isinstance(dmg, (int, float)) or dmg < 1 or dmg > 20:
            errors.append("stats.damage must be 1-20")

    # -- sprite --
    sprite = data.get("sprite")
    if not isinstance(sprite, dict):
        errors.append("sprite must be a dict")
    else:
        colors = sprite.get("colors")
        if not isinstance(colors, dict):
            errors.append("sprite.colors must be a dict")
        else:
            for k, v in colors.items():
                if not _is_hex_color(v):
                    errors.append(f"sprite.colors.{k} must be #RRGGBB, got {v!r}")
        frames = sprite.get("frames")
        if not isinstance(frames, list) or len(frames) < 1:
            errors.append("sprite.frames must be a non-empty list")
        else:
            for fi, frame in enumerate(frames):
                if not isinstance(frame, list):
                    errors.append(f"sprite.frames[{fi}] must be a list of layers")
                    continue
                for li, layer in enumerate(frame):
                    if not isinstance(layer, list) or len(layer) != 5:
                        errors.append(f"sprite.frames[{fi}][{li}] must be [colorKey, x, y, w, h]")
                        continue
                    _, x, y, w, h = layer
                    if not all(isinstance(v, (int, float)) for v in (x, y, w, h)):
                        errors.append(f"sprite.frames[{fi}][{li}] x/y/w/h must be numbers")
                    elif x < 0 or y < 0 or x + w > 16 or y + h > 16:
                        errors.append(f"sprite.frames[{fi}][{li}] out of 16x16 bounds")

    # -- behavior (optional) --
    behavior = data.get("behavior")
    if behavior is not None:
        if not isinstance(behavior, dict):
            errors.append("behavior must be a dict")
        else:
            rules = behavior.get("rules", [])
            if not isinstance(rules, list):
                errors.append("behavior.rules must be a list")
            else:
                for ri, rule in enumerate(rules):
                    if not isinstance(rule, dict):
                        errors.append(f"behavior.rules[{ri}] must be a dict")
                        continue
                    # Check condition
                    cond = rule.get("if") or rule.get("default") and "default"
                    if cond and cond not in VALID_BEHAVIOR_CONDITIONS:
                        errors.append(f"behavior.rules[{ri}] unknown condition: {cond}")
                    # Check action
                    action = rule.get("do") or (rule.get("default") if "default" in rule else None)
                    if isinstance(action, str) and action not in VALID_BEHAVIOR_ACTIONS:
                        errors.append(f"behavior.rules[{ri}] unknown action: {action}")

            attacks = behavior.get("attacks", [])
            if not isinstance(attacks, list):
                errors.append("behavior.attacks must be a list")
            else:
                for ai, atk in enumerate(attacks):
                    if not isinstance(atk, dict):
                        errors.append(f"behavior.attacks[{ai}] must be a dict")
                        continue
                    atype = atk.get("type")
                    if atype not in VALID_ATTACK_TYPES:
                        errors.append(f"behavior.attacks[{ai}] unknown type: {atype}")
                    rng = atk.get("range")
                    if not isinstance(rng, (int, float)) or rng < 1 or rng > 15:
                        errors.append(f"behavior.attacks[{ai}] range must be 1-15")
                    cd = atk.get("cooldown")
                    if cd is not None and (not isinstance(cd, (int, float)) or cd < 0.5 or cd > 30.0):
                        errors.append(f"behavior.attacks[{ai}] cooldown must be 0.5-30.0")
                    dmg = atk.get("damage")
                    if dmg is not None and (not isinstance(dmg, (int, float)) or dmg < 1 or dmg > 20):
                        errors.append(f"behavior.attacks[{ai}] damage must be 1-20")
                    if atype == "projectile":
                        sc = atk.get("sprite_color")
                        if sc is not None and not _is_hex_color(sc):
                            errors.append(f"behavior.attacks[{ai}] sprite_color must be #RRGGBB")
                        spd = atk.get("speed")
                        if spd is not None and (not isinstance(spd, (int, float)) or spd < 1 or spd > 5):
                            errors.append(f"behavior.attacks[{ai}] speed must be 1-5")
                        prc = atk.get("piercing")
                        if prc is not None and not isinstance(prc, bool):
                            errors.append(f"behavior.attacks[{ai}] piercing must be boolean")
                    if atype == "teleport":
                        dly = atk.get("delay")
                        if dly is not None and (not isinstance(dly, (int, float)) or dly < 0.2 or dly > 3.0):
                            errors.append(f"behavior.attacks[{ai}] delay must be 0.2-3.0")
                    if atype == "area":
                        wd = atk.get("warning_duration")
                        if wd is not None and (not isinstance(wd, (int, float)) or wd < 0.3 or wd > 3.0):
                            errors.append(f"behavior.attacks[{ai}] warning_duration must be 0.3-3.0")

    # -- death_sprite (optional) --
    death_sprite = data.get("death_sprite")
    if death_sprite is not None:
        if not isinstance(death_sprite, dict):
            errors.append("death_sprite must be a dict")
        else:
            dcolors = death_sprite.get("colors")
            if isinstance(dcolors, dict):
                for k, v in dcolors.items():
                    if not _is_hex_color(v):
                        errors.append(f"death_sprite.colors.{k} must be #RRGGBB")
            dframes = death_sprite.get("frames")
            if not isinstance(dframes, list) or len(dframes) < 1:
                errors.append("death_sprite.frames must be a non-empty list")

    return errors


def validate_tile(data: dict) -> list[str]:
    """Validate a tile recipe. Returns a list of error strings (empty = valid).

    Expected shape:
      id: str
      walkable: bool (optional, defaults to False)
      colors: {key: "#hex"}
      operations: [{op: "fill"|"noise"|..., ...}, ...]
    """
    errors = []

    tile_id = data.get("id")
    if not isinstance(tile_id, str) or not tile_id:
        errors.append("id must be a non-empty string")
    elif not _re.match(r'^[a-z][a-z0-9_]*$', tile_id):
        errors.append("id must be lowercase alphanumeric with underscores")

    colors = data.get("colors")
    if not isinstance(colors, dict):
        errors.append("colors must be a dict")
    else:
        for k, v in colors.items():
            if not _is_hex_color(v):
                errors.append(f"colors.{k} must be #RRGGBB, got {v!r}")

    ops = data.get("operations")
    if not isinstance(ops, list):
        errors.append("operations must be a list")
    else:
        for oi, op in enumerate(ops):
            if not isinstance(op, dict):
                errors.append(f"operations[{oi}] must be a dict")
                continue
            op_name = op.get("op")
            if op_name not in VALID_TILE_OPS:
                errors.append(f"operations[{oi}] unknown op: {op_name}")
            # Validate rect coordinates for rects op
            if op_name == "rects":
                for ri, rect in enumerate(op.get("rects", [])):
                    if not isinstance(rect, list) or len(rect) != 5:
                        errors.append(f"operations[{oi}].rects[{ri}] must be [colorKey, x, y, w, h]")
                        continue
                    _, x, y, w, h = rect
                    if not all(isinstance(v, (int, float)) for v in (x, y, w, h)):
                        errors.append(f"operations[{oi}].rects[{ri}] x/y/w/h must be numbers")
                    elif x < 0 or y < 0 or x + w > 16 or y + h > 16:
                        errors.append(f"operations[{oi}].rects[{ri}] out of 0-15 grid")
            # Validate pixel coordinates for pixels op
            if op_name == "pixels":
                for pi, px in enumerate(op.get("pixels", [])):
                    if not isinstance(px, list) or len(px) != 3:
                        errors.append(f"operations[{oi}].pixels[{pi}] must be [colorKey, x, y]")
                        continue
                    _, x, y = px
                    if not all(isinstance(v, (int, float)) for v in (x, y)):
                        errors.append(f"operations[{oi}].pixels[{pi}] x/y must be numbers")
                    elif x < 0 or x > 15 or y < 0 or y > 15:
                        errors.append(f"operations[{oi}].pixels[{pi}] out of 0-15 grid")

    return errors


def register_monster_type(data: dict) -> tuple[bool, list[str]]:
    """Register a new monster type at runtime. Returns (success, errors)."""
    errors = validate_monster(data)
    if errors:
        return False, errors

    kind = data["kind"]
    stats = data["stats"]
    sprite = data["sprite"]

    # Register stats
    MONSTER_STATS[kind] = {
        "hp": int(stats["hp"]),
        "hop_interval": float(stats["hop_interval"]),
        "damage": int(stats["damage"]),
    }

    # Register sprite
    CUSTOM_SPRITES[kind] = sprite

    # Register death sprite (optional — client auto-generates a generic splat if absent)
    death_sprite = data.get("death_sprite")
    if death_sprite:
        CUSTOM_DEATH_SPRITES[kind] = death_sprite

    # Register behavior (optional — monsters without it default to wander)
    behavior = data.get("behavior")
    if behavior:
        MONSTER_BEHAVIORS[kind] = behavior

    print(f"[REG] Monster type registered: {kind} "
          f"(hp={stats['hp']}, dmg={stats['damage']}, hop={stats['hop_interval']})")
    return True, []


def register_tile_type(data: dict) -> tuple[bool, list[str]]:
    """Register a new custom tile type at runtime. Returns (success, errors)."""
    errors = validate_tile(data)
    if errors:
        return False, errors

    tile_id = data["id"]
    CUSTOM_TILE_RECIPES[tile_id] = {
        "colors": data["colors"],
        "operations": data["operations"],
    }

    if data.get("walkable", False):
        CUSTOM_WALKABLE_TILES.add(tile_id)
    else:
        CUSTOM_WALKABLE_TILES.discard(tile_id)

    print(f"[REG] Tile type registered: {tile_id} (walkable={data.get('walkable', False)})")
    return True, []


HEART_DROP_CHANCE = 0.1
INVINCIBILITY_DURATION = 1.5

import random

class Monster:
    def __init__(self, x, y, kind="slime"):
        self.x = x
        self.y = y
        self.spawn_x = x
        self.spawn_y = y
        self.kind = kind
        self.alive = True
        self.last_hop_time = time.monotonic()
        stats = MONSTER_STATS.get(kind, {"hp": 1, "hop_interval": 2.0, "damage": 1})
        self.hp = stats["hp"]
        self.max_hp = stats["hp"]
        self.hop_interval = stats["hop_interval"]
        self.damage = stats.get("damage", 1)
        # Behavior engine data (None = use default wander)
        self.behavior = MONSTER_BEHAVIORS.get(kind)
        # Attack cooldown tracking: attack_index -> last_used_time
        self._attack_cooldowns = {}
        # Teleporting state (monster is invisible during teleport)
        self._teleporting = False
        # Charge prep state: {dx, dy, atk_index, atk} or None
        self._charge_prep = None
        # Patrol state
        if self.behavior:
            patrol_wps = self.behavior.get("patrol_waypoints")
            if patrol_wps:
                self._patrol_waypoints = patrol_wps
                self._patrol_index = 0

# Templates — define what monsters belong in each room (never mutated)
MONSTER_TEMPLATES = {}  # Populated from .room files by load_room_files()

# Live monster instances per room — only populated while players are present
# room_id -> [Monster, ...]
room_monsters: dict[str, list[Monster]] = {}

# Room cooldown — when all monsters were killed and all players left
# room_id -> timestamp when cooldown started
room_cooldowns: dict[str, float] = {}

# ---------------------------------------------------------------------------
# Projectile tracking (Stage 5: monster ranged attacks)
# ---------------------------------------------------------------------------

class Projectile:
    def __init__(self, x, y, dx, dy, damage, color, room_id, speed=1, piercing=False):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.damage = damage
        self.color = color
        self.room_id = room_id
        self.speed = speed        # tiles per move tick
        self.piercing = piercing  # pass through players (hit all in path)

room_projectiles: dict[str, dict[int, Projectile]] = {}  # room_id -> {proj_id: Projectile}
_next_projectile_id = 0


def spawn_monsters(room_id: str) -> list[Monster]:
    """Create fresh Monster instances from templates for a room."""
    templates = MONSTER_TEMPLATES.get(room_id, [])
    now = time.monotonic()
    monsters = []
    for t in templates:
        m = Monster(t["x"], t["y"], t["kind"])
        # Stagger first hop by 0-4 ticks (0.25s each) so monsters don't move in sync
        m.last_hop_time = now + random.randint(0, 4) * 0.25
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
    room_projectiles.pop(room_id, None)

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

from server.dungeon_layouts import DUNGEON_LAYOUTS

DUNGEON_MUSIC_TRACKS = ["dungeon1", "dungeon2", "dungeon3", "dungeon4", "dungeon5", "dungeon6", "dungeon7"]

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
    msg = {
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
    }

    # Attach custom sprite/tile data for any AI-generated content in this room
    custom_sprites = {}
    custom_death_sprites = {}
    for m in monsters:
        kind = m["kind"]
        if kind in CUSTOM_SPRITES:
            custom_sprites[kind] = CUSTOM_SPRITES[kind]
        if kind in CUSTOM_DEATH_SPRITES:
            custom_death_sprites[kind] = CUSTOM_DEATH_SPRITES[kind]
    custom_tiles = {}
    tilemap = room["tilemap"]
    for row in tilemap:
        for tid in row:
            if isinstance(tid, str) and tid in CUSTOM_TILE_RECIPES:
                custom_tiles[tid] = CUSTOM_TILE_RECIPES[tid]

    if custom_sprites:
        msg["custom_sprites"] = custom_sprites
    if custom_death_sprites:
        msg["custom_death_sprites"] = custom_death_sprites
    if custom_tiles:
        msg["custom_tiles"] = custom_tiles

    await send_to(player, msg)

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
        if 0 <= kx < ROOM_COLS and 0 <= ky < ROOM_ROWS and is_walkable_tile(tilemap[ky][kx]):
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
    if not is_walkable_tile(tile):
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
# Monster attack execution (Stage 5)
# ---------------------------------------------------------------------------

PROJECTILE_TICK_RATE = 0.15  # seconds between projectile moves


async def execute_monster_attack(monster, room_id, monster_idx):
    """Select and execute the best available attack for a monster."""
    behavior = getattr(monster, "behavior", None)
    if not behavior:
        return
    attacks = behavior.get("attacks", [])
    if not attacks:
        return

    cooldowns = monster._attack_cooldowns
    now = time.monotonic()
    player, player_dist = behavior_engine._nearest_player(monster, room_id)
    if player is None:
        return

    for i, atk in enumerate(attacks):
        last_used = cooldowns.get(i, 0)
        cd = atk.get("cooldown", 1.0)
        if now - last_used < cd:
            continue
        if player_dist > atk.get("range", 1):
            continue
        if atk.get("type") == "charge" and monster.x != player.x and monster.y != player.y:
            continue

        # This attack is usable — execute it
        monster._attack_cooldowns[i] = now
        atype = atk["type"]

        if atype == "melee":
            await attack_melee(monster, room_id, monster_idx, atk, player)
        elif atype == "projectile":
            await attack_projectile(monster, room_id, monster_idx, atk, player)
        elif atype == "charge":
            await attack_charge(monster, room_id, monster_idx, atk, player)
        elif atype == "teleport":
            await attack_teleport(monster, room_id, monster_idx, atk, player)
        elif atype == "area":
            await attack_area(monster, room_id, monster_idx, atk)
        return  # one attack per tick


async def attack_melee(monster, room_id, monster_idx, atk, target):
    """Enhanced melee — strike adjacent player without moving onto them."""
    damage = atk.get("damage", monster.damage)
    await broadcast_to_room(room_id, {
        "type": "monster_attack",
        "id": monster_idx,
        "attack_type": "melee",
        "target_x": target.x,
        "target_y": target.y,
    })
    await damage_player(target, damage, room_id)


async def attack_projectile(monster, room_id, monster_idx, atk, target):
    """Fire a projectile toward the nearest player in a cardinal direction."""
    global _next_projectile_id

    dx_raw = target.x - monster.x
    dy_raw = target.y - monster.y
    if dx_raw == 0 and dy_raw == 0:
        return
    if abs(dx_raw) >= abs(dy_raw):
        dx, dy = (1 if dx_raw > 0 else -1), 0
    else:
        dx, dy = 0, (1 if dy_raw > 0 else -1)

    color = atk.get("sprite_color", "#ff0000")
    damage = atk.get("damage", 1)
    speed = atk.get("speed", 1)
    piercing = atk.get("piercing", False)

    # Projectile starts one tile away from monster
    start_x = monster.x + dx
    start_y = monster.y + dy
    if start_x < 0 or start_x >= ROOM_COLS or start_y < 0 or start_y >= ROOM_ROWS:
        return
    if not is_walkable_tile(ROOMS[room_id]["tilemap"][start_y][start_x]):
        return

    proj_id = _next_projectile_id
    _next_projectile_id += 1
    proj = Projectile(start_x, start_y, dx, dy, damage, color, room_id, speed, piercing)

    if room_id not in room_projectiles:
        room_projectiles[room_id] = {}
    room_projectiles[room_id][proj_id] = proj

    await broadcast_to_room(room_id, {
        "type": "projectile_spawned",
        "id": proj_id,
        "x": start_x,
        "y": start_y,
        "dx": dx,
        "dy": dy,
        "color": color,
    })

    # Check if a player is already at the spawn tile
    for p in players_in_room(room_id):
        if p.hp > 0 and p.x == start_x and p.y == start_y:
            await broadcast_to_room(room_id, {"type": "projectile_hit", "id": proj_id, "x": start_x, "y": start_y})
            await damage_player(p, damage, room_id)
            room_projectiles.get(room_id, {}).pop(proj_id, None)
            return


async def attack_charge(monster, room_id, monster_idx, atk, target):
    """Lock in charge direction and enter prep state. Actual dash happens next tick."""
    dx_raw = target.x - monster.x
    dy_raw = target.y - monster.y
    if dx_raw == 0 and dy_raw == 0:
        return
    if abs(dx_raw) >= abs(dy_raw):
        dx, dy = (1 if dx_raw > 0 else -1), 0
    else:
        dx, dy = 0, (1 if dy_raw > 0 else -1)

    # Store prep — direction is locked, charge fires next tick
    monster._charge_prep = {"dx": dx, "dy": dy, "atk": atk}

    # Build the preview lane (what the charge path would be right now)
    max_range = atk.get("range", 3)
    lane = []
    nx, ny = monster.x, monster.y
    for _ in range(max_range):
        nx += dx
        ny += dy
        if not behavior_engine._is_walkable(nx, ny, room_id):
            break
        lane.append([nx, ny])

    await broadcast_to_room(room_id, {
        "type": "charge_prep",
        "id": monster_idx,
        "dx": dx,
        "dy": dy,
        "lane": lane,
    })


async def execute_charge_from_prep(monster, room_id, monster_idx, prep):
    """Execute the actual charge dash from a prepped direction."""
    dx = prep["dx"]
    dy = prep["dy"]
    atk = prep["atk"]
    max_range = atk.get("range", 3)
    damage = atk.get("damage", monster.damage)
    path = []

    nx, ny = monster.x, monster.y
    for _ in range(max_range):
        nx += dx
        ny += dy
        if not behavior_engine._is_walkable(nx, ny, room_id):
            break
        path.append([nx, ny])

    if not path:
        return

    end_x, end_y = path[-1]
    monster.x = end_x
    monster.y = end_y

    await broadcast_to_room(room_id, {
        "type": "monster_charged",
        "id": monster_idx,
        "path": path,
        "x": end_x,
        "y": end_y,
    })

    for p in players_in_room(room_id):
        if p.hp > 0 and any(p.x == px and p.y == py for px, py in path):
            await damage_player(p, damage, room_id)


async def attack_teleport(monster, room_id, monster_idx, atk, target):
    """Disappear, then reappear near the target player after a brief delay."""
    damage = atk.get("damage", monster.damage)
    delay = atk.get("delay", 0.5)

    # Find a walkable tile adjacent to the target
    target_pos = None
    candidates = [(1,0), (-1,0), (0,1), (0,-1)]
    random.shuffle(candidates)
    for ddx, ddy in candidates:
        nx, ny = target.x + ddx, target.y + ddy
        if behavior_engine._is_walkable(nx, ny, room_id):
            target_pos = (nx, ny)
            break
    if target_pos is None:
        return

    monster._teleporting = True
    await broadcast_to_room(room_id, {
        "type": "teleport_start",
        "id": monster_idx,
        "target_x": target_pos[0],
        "target_y": target_pos[1],
        "delay": delay,
    })

    async def complete_teleport():
        await asyncio.sleep(delay)
        if not monster.alive:
            monster._teleporting = False
            return
        monster.x = target_pos[0]
        monster.y = target_pos[1]
        monster._teleporting = False
        await broadcast_to_room(room_id, {
            "type": "teleport_end",
            "id": monster_idx,
            "x": target_pos[0],
            "y": target_pos[1],
        })
        # Damage any adjacent player after landing
        for p in players_in_room(room_id):
            if p.hp > 0 and abs(p.x - monster.x) + abs(p.y - monster.y) <= 1:
                await damage_player(p, damage, room_id)

    asyncio.create_task(complete_teleport())


async def attack_area(monster, room_id, monster_idx, atk):
    """Ground slam — warning indicator, then damage all players within range."""
    damage = atk.get("damage", monster.damage)
    range_val = atk.get("range", 2)
    warning_duration = atk.get("warning_duration", 0.75)

    await broadcast_to_room(room_id, {
        "type": "area_warning",
        "id": monster_idx,
        "x": monster.x,
        "y": monster.y,
        "range": range_val,
        "duration": warning_duration,
    })

    async def execute_area():
        await asyncio.sleep(warning_duration)
        if not monster.alive:
            return
        await broadcast_to_room(room_id, {
            "type": "area_attack",
            "id": monster_idx,
            "x": monster.x,
            "y": monster.y,
            "range": range_val,
        })
        for p in players_in_room(room_id):
            if p.hp > 0:
                dist = abs(p.x - monster.x) + abs(p.y - monster.y)
                if dist <= range_val:
                    await damage_player(p, damage, room_id)

    asyncio.create_task(execute_area())


async def projectile_tick():
    """Background loop — moves projectiles and checks collisions."""
    while True:
        await asyncio.sleep(PROJECTILE_TICK_RATE)
        for room_id in list(room_projectiles.keys()):
            projs = room_projectiles[room_id]
            to_remove = []
            for proj_id, proj in list(projs.items()):
                # Move by speed tiles per tick
                for _ in range(proj.speed):
                    proj.x += proj.dx
                    proj.y += proj.dy

                    # Out of bounds or hit a wall
                    if (proj.x < 0 or proj.x >= ROOM_COLS or
                            proj.y < 0 or proj.y >= ROOM_ROWS or
                            not is_walkable_tile(ROOMS[room_id]["tilemap"][proj.y][proj.x])):
                        to_remove.append(proj_id)
                        await broadcast_to_room(room_id, {"type": "projectile_gone", "id": proj_id})
                        break

                    # Check player collision
                    hit_player = False
                    for p in players_in_room(room_id):
                        if p.hp > 0 and p.x == proj.x and p.y == proj.y:
                            await broadcast_to_room(room_id, {
                                "type": "projectile_hit", "id": proj_id,
                                "x": proj.x, "y": proj.y,
                            })
                            await damage_player(p, proj.damage, room_id)
                            hit_player = True
                            if not proj.piercing:
                                to_remove.append(proj_id)
                                break
                    if hit_player and not proj.piercing:
                        break
                else:
                    # No wall hit during multi-step move — send position update
                    if proj_id not in to_remove:
                        await broadcast_to_room(room_id, {
                            "type": "projectile_moved", "id": proj_id,
                            "x": proj.x, "y": proj.y,
                        })

            for pid in to_remove:
                projs.pop(pid, None)
            if not projs:
                room_projectiles.pop(room_id, None)


# ---------------------------------------------------------------------------
# Monster AI tick
# ---------------------------------------------------------------------------

async def monster_tick():
    """Background loop — hops alive monsters in rooms that have players."""
    while True:
        await asyncio.sleep(0.25)
        now = time.monotonic()
        for room_id, monster_list in list(room_monsters.items()):
            # Only simulate rooms with players
            if not players_in_room(room_id):
                continue
            for i, monster in enumerate(monster_list):
                if not monster.alive or monster._teleporting:
                    continue
                if now - monster.last_hop_time < monster.hop_interval:
                    continue
                monster.last_hop_time = now

                # Execute pending charge prep (locked direction from previous tick)
                if monster._charge_prep is not None:
                    prep = monster._charge_prep
                    monster._charge_prep = None
                    await execute_charge_from_prep(monster, room_id, i, prep)
                    continue

                # Evaluate behavior rules → pick action → execute
                action = behavior_engine.evaluate_rules(monster, room_id)

                if action == "attack":
                    await execute_monster_attack(monster, room_id, i)
                else:
                    result = behavior_engine.execute_action(action, monster, room_id)
                    if result is not None:
                        nx, ny = result
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

# ---------------------------------------------------------------------------
# Debug spawn — register + spawn a test monster (admin only for now)
# ---------------------------------------------------------------------------

# A few built-in test monster definitions for /debug_spawn
_DEBUG_MONSTERS = {
    "fire_slime": {
        "kind": "fire_slime",
        "stats": {"hp": 2, "hop_interval": 1.5, "damage": 2},
        "behavior": {
            "rules": [
                {"if": "hp_below_pct", "value": 30, "do": "flee"},
                {"if": "player_within", "range": 5, "do": "chase"},
                {"default": "wander"},
            ],
        },
        "sprite": {
            "colors": {"body": "#ff6600", "dark": "#cc3300", "eyes": "#222222", "highlight": "#ffaa00"},
            "frames": [
                [
                    ["dark",      2, 9,12, 6],
                    ["body",      3, 8,10, 6],
                    ["body",      4, 7, 8, 1],
                    ["eyes",      5, 9, 2, 2],
                    ["eyes",      9, 9, 2, 2],
                    ["highlight", 5, 8, 2, 1],
                ],
                [
                    ["dark",      4,12, 8, 2],
                    ["body",      4, 4, 8, 9],
                    ["body",      5, 3, 6, 1],
                    ["body",      5,13, 6, 1],
                    ["dark",      4,11, 8, 2],
                    ["eyes",      5, 6, 2, 2],
                    ["eyes",      9, 6, 2, 2],
                    ["highlight", 5, 4, 2, 1],
                ],
            ],
        },
    },
    "ice_bat": {
        "kind": "ice_bat",
        "stats": {"hp": 1, "hop_interval": 0.8, "damage": 1},
        "behavior": {
            "rules": [
                {"if": "player_within", "range": 3, "do": "flee"},
                {"if": "player_within", "range": 7, "do": "hold"},
                {"default": "wander"},
            ],
        },
        "sprite": {
            "colors": {"body": "#4a6a8a", "wing": "#7ab0dd", "eyes": "#00ffff"},
            "frames": [
                [
                    ["body",  6, 6, 4, 4],
                    ["wing",  1, 3, 5, 4],
                    ["wing", 10, 3, 5, 4],
                    ["wing",  2, 2, 3, 1],
                    ["wing", 11, 2, 3, 1],
                    ["eyes",  6, 7, 1, 1],
                    ["eyes",  9, 7, 1, 1],
                ],
                [
                    ["body",  6, 5, 4, 4],
                    ["wing",  1, 7, 5, 4],
                    ["wing", 10, 7, 5, 4],
                    ["wing",  2,11, 3, 1],
                    ["wing", 11,11, 3, 1],
                    ["eyes",  6, 6, 1, 1],
                    ["eyes",  9, 6, 1, 1],
                ],
            ],
        },
    },
    "shadow_skull": {
        "kind": "shadow_skull",
        "stats": {"hp": 3, "hop_interval": 2.0, "damage": 3},
        "behavior": {
            "rules": [
                {"if": "hp_below_pct", "value": 50, "do": "flee"},
                {"if": "player_within", "range": 4, "do": "chase"},
                {"if": "random_chance", "value": 30, "do": "wander"},
                {"default": "hold"},
            ],
        },
        "sprite": {
            "colors": {"bone": "#e0d8c0", "dark": "#2a1a2a", "eyes": "#ff0044", "shadow": "#4a2a4a"},
            "frames": [
                [
                    ["shadow",  4, 9, 8, 5],
                    ["bone",    5, 3, 6, 6],
                    ["bone",    4, 4, 8, 4],
                    ["dark",    6, 5, 2, 2],
                    ["dark",    8, 5, 2, 2],
                    ["eyes",    6, 5, 1, 1],
                    ["eyes",    9, 5, 1, 1],
                    ["dark",    7, 7, 2, 1],
                ],
                [
                    ["shadow",  4, 8, 8, 5],
                    ["bone",    5, 2, 6, 6],
                    ["bone",    4, 3, 8, 4],
                    ["dark",    6, 4, 2, 2],
                    ["dark",    8, 4, 2, 2],
                    ["eyes",    6, 4, 1, 1],
                    ["eyes",    9, 4, 1, 1],
                    ["dark",    7, 6, 2, 1],
                ],
            ],
        },
    },
    # --- Stage 5: Debug monsters with attacks ---
    "skeleton_archer": {
        "kind": "skeleton_archer",
        "stats": {"hp": 2, "hop_interval": 2.0, "damage": 1},
        "behavior": {
            "rules": [
                {"if": "hp_below_pct", "value": 30, "do": "flee"},
                {"if": "can_attack", "do": "attack"},
                {"if": "player_within", "range": 3, "do": "flee"},
                {"if": "player_within", "range": 8, "do": "hold"},
                {"default": "wander"},
            ],
            "attacks": [
                {"type": "projectile", "range": 6, "damage": 1, "cooldown": 2.0, "sprite_color": "#ccbb88"},
            ],
        },
        "sprite": {
            "colors": {"bone": "#d8d0b8", "dark": "#5a4a3a", "eyes": "#cc2200", "bow": "#8b6914"},
            "frames": [
                [
                    ["dark",  5,10, 6, 4],
                    ["bone",  6, 3, 4, 8],
                    ["bone",  5, 4, 6, 5],
                    ["dark",  7, 5, 2, 2],
                    ["eyes",  7, 5, 1, 1],
                    ["eyes",  9, 5, 1, 1],
                    ["bone",  6, 9, 1, 3],
                    ["bone",  9, 9, 1, 3],
                    ["bow",   3, 4, 2, 6],
                ],
                [
                    ["dark",  5, 9, 6, 4],
                    ["bone",  6, 2, 4, 8],
                    ["bone",  5, 3, 6, 5],
                    ["dark",  7, 4, 2, 2],
                    ["eyes",  7, 4, 1, 1],
                    ["eyes",  9, 4, 1, 1],
                    ["bone",  6, 8, 1, 3],
                    ["bone",  9, 8, 1, 3],
                    ["bow",   3, 3, 2, 6],
                ],
            ],
        },
    },
    "ghost_teleporter": {
        "kind": "ghost_teleporter",
        "stats": {"hp": 2, "hop_interval": 2.5, "damage": 2},
        "behavior": {
            "rules": [
                {"if": "can_attack", "do": "attack"},
                {"if": "player_within", "range": 3, "do": "flee"},
                {"default": "wander"},
            ],
            "attacks": [
                {"type": "teleport", "range": 8, "damage": 2, "cooldown": 4.0},
            ],
        },
        "sprite": {
            "colors": {"body": "#6a7a9a", "glow": "#aabbdd", "eyes": "#ffffff", "dark": "#3a4a6a"},
            "frames": [
                [
                    ["dark",  5, 9, 6, 5],
                    ["body",  5, 4, 6, 7],
                    ["body",  6, 3, 4, 1],
                    ["glow",  6, 5, 1, 1],
                    ["glow",  9, 5, 1, 1],
                    ["eyes",  6, 5, 1, 1],
                    ["eyes",  9, 5, 1, 1],
                ],
                [
                    ["dark",  5, 8, 6, 5],
                    ["body",  5, 3, 6, 7],
                    ["body",  6, 2, 4, 1],
                    ["glow",  6, 4, 1, 1],
                    ["glow",  9, 4, 1, 1],
                    ["eyes",  6, 4, 1, 1],
                    ["eyes",  9, 4, 1, 1],
                ],
            ],
        },
    },
    "war_boar": {
        "kind": "war_boar",
        "stats": {"hp": 4, "hop_interval": 1.5, "damage": 2},
        "behavior": {
            "rules": [
                {"if": "can_attack", "do": "attack"},
                {"if": "player_within", "range": 6, "do": "chase"},
                {"default": "wander"},
            ],
            "attacks": [
                {"type": "charge", "range": 4, "damage": 3, "cooldown": 3.0},
            ],
        },
        "sprite": {
            "colors": {"body": "#8b5e3c", "dark": "#5a3a1e", "snout": "#dda488", "eyes": "#220000", "tusk": "#f0e8d0"},
            "frames": [
                [
                    ["dark",   3,10, 10, 4],
                    ["body",   3, 5, 10, 7],
                    ["body",   4, 4,  8, 1],
                    ["dark",   4, 9, 8,  2],
                    ["snout",  5, 6,  3, 3],
                    ["eyes",   5, 5,  1, 1],
                    ["eyes",   8, 5,  1, 1],
                    ["tusk",   5, 9,  1, 2],
                    ["tusk",   7, 9,  1, 2],
                ],
                [
                    ["dark",   3, 9, 10, 4],
                    ["body",   3, 4, 10, 7],
                    ["body",   4, 3,  8, 1],
                    ["dark",   4, 8, 8,  2],
                    ["snout",  5, 5,  3, 3],
                    ["eyes",   5, 4,  1, 1],
                    ["eyes",   8, 4,  1, 1],
                    ["tusk",   5, 8,  1, 2],
                    ["tusk",   7, 8,  1, 2],
                ],
            ],
        },
    },
    "flame_mage": {
        "kind": "flame_mage",
        "stats": {"hp": 3, "hop_interval": 2.5, "damage": 2},
        "behavior": {
            "rules": [
                {"if": "hp_below_pct", "value": 30, "do": "flee"},
                {"if": "can_attack", "do": "attack"},
                {"if": "player_within", "range": 3, "do": "flee"},
                {"if": "player_within", "range": 7, "do": "hold"},
                {"default": "wander"},
            ],
            "attacks": [
                {"type": "area", "range": 2, "damage": 2, "cooldown": 4.0},
                {"type": "projectile", "range": 5, "damage": 1, "cooldown": 2.5, "sprite_color": "#ff6600"},
            ],
        },
        "sprite": {
            "colors": {"robe": "#8b2500", "dark": "#4a1200", "skin": "#dda488", "fire": "#ff6600", "glow": "#ffaa00"},
            "frames": [
                [
                    ["dark",  4,10, 8, 4],
                    ["robe",  4, 5, 8, 8],
                    ["robe",  5, 4, 6, 1],
                    ["skin",  6, 3, 4, 2],
                    ["dark",  7, 4, 1, 1],
                    ["dark",  9, 4, 1, 1],
                    ["fire",  5, 2, 2, 2],
                    ["glow",  5, 1, 1, 1],
                ],
                [
                    ["dark",  4, 9, 8, 4],
                    ["robe",  4, 4, 8, 8],
                    ["robe",  5, 3, 6, 1],
                    ["skin",  6, 2, 4, 2],
                    ["dark",  7, 3, 1, 1],
                    ["dark",  9, 3, 1, 1],
                    ["fire",  5, 1, 2, 2],
                    ["glow",  6, 0, 1, 1],
                ],
            ],
        },
    },
}


async def handle_debug_spawn(player: Player, args: str):
    """Handle /debug_spawn <kind> — register and spawn a test monster near the player."""
    args = args.strip()
    if not args:
        available = list(_DEBUG_MONSTERS.keys()) + [k for k in CUSTOM_SPRITES if k not in _DEBUG_MONSTERS]
        existing_custom = [k for k in MONSTER_STATS if k not in ("slime", "bat", "scorpion", "skeleton", "swamp_blob")]
        msg = "Usage: /debug_spawn <kind>\n"
        msg += f"Built-in test monsters: {', '.join(_DEBUG_MONSTERS.keys())}\n"
        if existing_custom:
            msg += f"Registered custom: {', '.join(existing_custom)}\n"
        msg += "Also works with any built-in kind: slime, bat, scorpion, skeleton, swamp_blob"
        await send_to(player, {"type": "info", "text": msg})
        return

    kind = args.split()[0].lower()

    # If it's a debug monster that isn't registered yet, register it
    if kind in _DEBUG_MONSTERS and kind not in MONSTER_STATS:
        ok, errors = register_monster_type(_DEBUG_MONSTERS[kind])
        if not ok:
            await send_to(player, {"type": "info", "text": f"Registration failed: {'; '.join(errors)}"})
            return

    # Check the kind exists (built-in or custom)
    if kind not in MONSTER_STATS:
        await send_to(player, {"type": "info", "text": f"Unknown monster kind: {kind}"})
        return

    # Find a walkable tile near the player
    room = ROOMS[player.room]
    tilemap = room["tilemap"]
    guards = GUARDS.get(player.room, [])
    spawn_x, spawn_y = None, None
    for dx, dy in [(1,0), (-1,0), (0,1), (0,-1), (2,0), (-2,0), (0,2), (0,-2)]:
        nx, ny = player.x + dx, player.y + dy
        if 0 <= nx < ROOM_COLS and 0 <= ny < ROOM_ROWS:
            if is_walkable_tile(tilemap[ny][nx]):
                if not any(g["x"] == nx and g["y"] == ny for g in guards):
                    spawn_x, spawn_y = nx, ny
                    break

    if spawn_x is None:
        await send_to(player, {"type": "info", "text": "No walkable tile nearby to spawn monster."})
        return

    # Create and add the monster
    monster = Monster(spawn_x, spawn_y, kind)
    monster.last_hop_time = time.monotonic()
    if player.room not in room_monsters:
        room_monsters[player.room] = []
    monster_list = room_monsters[player.room]
    monster_id = len(monster_list)
    monster_list.append(monster)

    # Build the spawn message with custom sprite data if needed
    spawn_msg = {
        "type": "monster_spawned",
        "id": monster_id,
        "kind": kind,
        "x": spawn_x,
        "y": spawn_y,
    }
    if kind in CUSTOM_SPRITES:
        spawn_msg["custom_sprites"] = {kind: CUSTOM_SPRITES[kind]}
    if kind in CUSTOM_DEATH_SPRITES:
        spawn_msg["custom_death_sprites"] = {kind: CUSTOM_DEATH_SPRITES[kind]}

    await broadcast_to_room(player.room, spawn_msg)
    await send_to(player, {"type": "info", "text": f"Spawned {kind} at ({spawn_x}, {spawn_y})"})


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
        elif cmd == "debug_spawn":
            await handle_debug_spawn(player, parts[1] if len(parts) > 1 else "")
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

ROOT_DIR = Path(__file__).parent

# Static files that the client can request
STATIC_FILES = {
    "/":            ("client/client.html", "text/html; charset=utf-8"),
    "/index.html":  ("client/client.html", "text/html; charset=utf-8"),
    "/sprite_data.js": ("client/sprite_data.js", "application/javascript; charset=utf-8"),
    "/sprites.js":  ("client/sprites.js",  "application/javascript; charset=utf-8"),
    "/tiles.js":    ("client/tiles.js",    "application/javascript; charset=utf-8"),
    "/music.js":    ("client/music.js",    "application/javascript; charset=utf-8"),
    "/music.mp3":         ("music/village.mp3", "audio/mpeg"),
    "/music_tavern.mp3":  ("music/tavern.mp3", "audio/mpeg"),
    "/music_chapel.mp3":  ("music/chapel.mp3", "audio/mpeg"),
    "/music_overworld.mp3": ("music/overworld.mp3", "audio/mpeg"),
    "/music_dungeon1.mp3": ("music/dungeon_a.mp3", "audio/mpeg"),
    "/music_dungeon2.mp3": ("music/dungeon_b.mp3", "audio/mpeg"),
    "/music_dungeon3.mp3": ("music/dungeon_c.mp3", "audio/mpeg"),
    "/music_dungeon4.mp3": ("music/dungeon_d.mp3", "audio/mpeg"),
    "/music_dungeon5.mp3": ("music/dungeon_e.mp3", "audio/mpeg"),
    "/music_dungeon6.mp3": ("music/dungeon_f.mp3", "audio/mpeg"),
    "/music_dungeon7.mp3": ("music/dungeon_g.mp3", "audio/mpeg"),
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
        body = (ROOT_DIR / filename).read_bytes()
        return HTTPStatus.OK, [("Content-Type", content_type)], body
    return HTTPStatus.NOT_FOUND, [], b"Not Found"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _auto_register_debug_monsters():
    """Register any _DEBUG_MONSTERS that appear in room templates."""
    needed = set()
    for room_id, templates in MONSTER_TEMPLATES.items():
        for t in templates:
            kind = t["kind"]
            if kind in _DEBUG_MONSTERS and kind not in MONSTER_STATS:
                needed.add(kind)
    for kind in sorted(needed):
        register_monster_type(_DEBUG_MONSTERS[kind])


async def main():
    load_room_files()
    load_dungeon_templates()
    _auto_register_debug_monsters()
    behavior_engine.init(players_in_room, ROOM_COLS, ROOM_ROWS, is_walkable_tile, GUARDS, ROOMS)
    port = 8080
    server = await websockets.serve(
        handle_connection, "0.0.0.0", port,
        process_request=process_request,
        ping_interval=30,    # send WebSocket ping every 30s
        ping_timeout=60,     # close if no pong within 60s (lenient for mobile)
    )
    asyncio.create_task(monster_tick())
    asyncio.create_task(projectile_tick())
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
