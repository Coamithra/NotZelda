"""
AI Room Generator — Claude API integration for procedural dungeon content.

Generates complete dungeon rooms (tilemap + monsters + tiles) via a single
API call. Adapts prompts based on library fullness: sparse libraries get
creative freedom, full libraries get "use only these" constraints.

Key design: one API call per room. The AI returns a complete room with
inline new content definitions + references to existing library content.
"""

import json
import os
import time
import asyncio
from pathlib import Path
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ANTHROPIC_MODEL = "claude-sonnet-4-6"
GENERATION_TIMEOUT = 30.0       # seconds before giving up on API call
MAX_API_CALLS_PER_MINUTE = 5
MAX_API_CALLS_PER_DAY = 200
MAX_RETRIES = 1                 # single retry on validation failure

DATA_DIR = Path(__file__).parent / "data"

# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Simple sliding-window rate limiter for API calls."""

    def __init__(self, per_minute: int = MAX_API_CALLS_PER_MINUTE,
                 per_day: int = MAX_API_CALLS_PER_DAY):
        self.per_minute = per_minute
        self.per_day = per_day
        self._minute_timestamps: list[float] = []
        self._day_count = 0
        self._day_start = time.time()

    def can_call(self) -> bool:
        now = time.time()
        # Reset daily counter if new day
        if now - self._day_start > 86400:
            self._day_count = 0
            self._day_start = now
        # Prune old minute timestamps
        self._minute_timestamps = [t for t in self._minute_timestamps if now - t < 60]
        return (len(self._minute_timestamps) < self.per_minute and
                self._day_count < self.per_day)

    def record_call(self):
        self._minute_timestamps.append(time.time())
        self._day_count += 1

    @property
    def daily_calls(self) -> int:
        return self._day_count


# ---------------------------------------------------------------------------
# Token usage tracking
# ---------------------------------------------------------------------------

@dataclass
class UsageTracker:
    """Tracks API token usage and cost."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_calls: int = 0
    _file: Path = field(default_factory=lambda: DATA_DIR / "api_usage.json")

    def record(self, input_tokens: int, output_tokens: int):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_calls += 1
        self._save()

    def estimated_cost(self) -> float:
        # Sonnet pricing: $3.00/M input, $15.00/M output
        return (self.total_input_tokens * 3.00 / 1_000_000 +
                self.total_output_tokens * 15.00 / 1_000_000)

    def _save(self):
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(json.dumps({
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "calls": self.total_calls,
            "estimated_cost_usd": round(self.estimated_cost(), 4),
        }, indent=2))

    def load(self):
        if self._file.exists():
            data = json.loads(self._file.read_text())
            self.total_input_tokens = data.get("input_tokens", 0)
            self.total_output_tokens = data.get("output_tokens", 0)
            self.total_calls = data.get("calls", 0)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a dungeon room generator for a Zelda-style top-down MUD game.
You generate complete dungeon rooms as JSON. Each room has a 15x11 tilemap, monster placements, and optionally new monster/tile definitions.

## TILEMAP FORMAT
- 15 columns x 11 rows grid
- Each cell is a 2-character tile code OR a custom tile string ID
- Built-in dungeon tile codes: DW (dungeon wall), DF (dungeon floor), PL (pillar), SC (sconce wall)
- Custom tiles use their string ID (e.g. "lava_crack")
- Row 0 (top) and row 10 (bottom): columns 0-5 and 9-14 MUST be DW. Columns 6-8 MUST be DF (for north/south doorways)
- Column 0 (left) and column 14 (right): rows 0-3 and 7-10 MUST be DW. Rows 4-6 MUST be DF (for east/west doorways)
- Interior (rows 1-9, cols 1-13 excluding doorway edges) is your creative space
- IMPORTANT: Use DW tiles INSIDE the room for interesting shapes:
  - L-corridors, T-junctions, winding paths, chokepoints, alcoves, divided chambers
  - Only 30-60% of interior walkable — walls create character
  - Mix it up: some symmetric, some asymmetric
  - ALL four doorways must be connected by walkable tiles
- Monsters and players must be placed only on walkable tiles (DF or walkable custom tiles; PL, SC are NOT walkable)

## MONSTER DEFINITION FORMAT
Each new monster needs:
```
{
  "kind": "lowercase_name",
  "tags": ["theme", "combat_style"],
  "stats": {"hp": 1-100, "hop_interval": 0.2-10.0, "damage": 1-20},
  "sprite": {
    "colors": {"colorKey": "#RRGGBB", ...},
    "frames": [
      [["colorKey", x, y, w, h], ...],
      [["colorKey", x, y, w, h], ...]
    ]
  },
  "behavior": {
    "rules": [
      {"if": "condition", "value": N, "do": "action"},
      {"default": "action"}
    ],
    "attacks": [
      {"type": "attack_type", "range": 1-15, "damage": 1-20, "cooldown": 0.5-30.0, ...}
    ]
  }
}
```

Sprite grid is 16x16. Each layer is [colorKey, x, y, w, h] where x+w<=16, y+h<=16.
Sprites need exactly 2 frames. Frame 1 is the "hop" frame (shifted up 1-2px typically).
Use 3-6 color keys per sprite. Build recognizable silhouettes with 5-12 layers per frame.

Behavior conditions: player_within (range), player_beyond (range), hp_below_pct (value), hp_above_pct (value), random_chance (value 0-100), can_attack, player_in_attack_range, always, default
Behavior actions: wander, chase, flee, patrol, hold, attack
Attack types: melee (range 1), projectile (+ sprite_color "#RRGGBB"), charge (range 2-6), teleport (+ delay 0.2-3.0), area (+ warning_duration 0.3-3.0)

## CUSTOM TILE FORMAT
```
{
  "id": "lowercase_name",
  "walkable": true,
  "tags": ["theme", "category"],
  "colors": {"base": "#RRGGBB", "colorKey": "#RRGGBB", ...},
  "operations": [
    {"op": "fill", "color": "colorKey"},
    {"op": "noise", "color": "colorKey", "density": 0.0-1.0},
    {"op": "bricks"},
    {"op": "grid_lines", "spacing": 2-8},
    {"op": "hstripes", "spacing": 2-8},
    {"op": "vstripes", "spacing": 2-8},
    {"op": "wave"},
    {"op": "ripple"},
    {"op": "rects", "rects": [["colorKey", x, y, w, h], ...]},
    {"op": "pixels", "pixels": [["colorKey", x, y], ...]}
  ]
}
```
Tile grid is 16x16. Operations execute in order. Start with "fill" for base color.
The "walkable" field determines if players/monsters can walk on this tile.

## RESPONSE FORMAT
Return ONLY valid JSON (no markdown, no explanation):
```
{
  "name": "Room Name",
  "tilemap": [
    ["DW","DW","DW","DW","DW","DW","DF","DF","DF","DW","DW","DW","DW","DW","DW"],
    ...11 rows total...
  ],
  "new_tiles": [],
  "new_monsters": [],
  "monster_placements": [
    {"kind": "skeleton", "x": 5, "y": 3}
  ]
}
```

## DIFFICULTY GUIDELINES
- Easy (1-3): 1-2 monsters, hp 1-2, damage 1
- Medium (4-6): 2-4 monsters, hp 2-4, damage 1-2, simple attacks
- Hard (7-9): 3-5 monsters, hp 3-6, damage 2-3, varied attacks
- Boss (10): 1 boss + 2-3 fodder, boss hp 6-10, damage 3-4, multiple attack types

## THEME GUIDELINES
- fire: oranges/reds, flame creatures, lava tiles
- ice: blues/whites, frozen creatures, frost tiles
- shadow: purples/blacks, spectral creatures, dark tiles
- undead: grays/greens, skeletal/zombie creatures
- beast: browns/greens, animal creatures
- poison: greens/purples, toxic creatures, acid tiles
- dungeon: grays/browns, classic dungeon creatures

## EXAMPLE LAYOUTS (ascii: x=wall, .=walkable, P=pillar, S=sconce)
Asymmetric:
xxxxxx...xxxxxx
x.....x..xSx.x
x.....xx.x...x
xxx......x...x
...x.xx......x
.....x.......x
..P......x...x
x.......xxx..x
x...xx....xx.x
x..xx........x
xxxxxx...xxxxxx
Symmetric:
xxxxxx...xxxxxx
x..Sxx...xxS..x
x....x...x....x
x..............x
...x...P...x...
...x.......x...
...x...P...x...
x..............x
x....x...x....x
x..Sxx...xxS..x
xxxxxx...xxxxxx

## IMPORTANT RULES
1. All tile codes in the tilemap must be either a built-in code (DW, DF, PL, SC) or defined in new_tiles or in the available tiles list
2. All monster kinds in monster_placements must be either in the existing monsters list or defined in new_monsters
3. Place monsters only on walkable tiles (DF or walkable custom tiles), not on walls, pillars, or sconces
4. Monster x must be 0-14, y must be 0-10
5. All IDs MUST be lowercase_snake_case [a-z][a-z0-9_]*
6. Give monsters thematic names (fire_imp, frost_archer, shadow_wraith — not monster_1)
7. Sprite colors should be thematically appropriate and visually distinct"""


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(theme: str, difficulty: int,
                  existing_monsters: list[dict],
                  existing_tiles: list[dict],
                  monster_library_full: bool,
                  tile_library_full: bool,
                  validation_error: str | None = None,
                  existing_room_names: list[str] | None = None) -> str:
    """Build the user prompt for room generation."""

    parts = []

    # Theme and difficulty
    parts.append(f"Generate a dungeon room with theme \"{theme}\" and difficulty {difficulty}/10.")

    # Avoid duplicate room names
    if existing_room_names:
        parts.append(f"\nDo NOT reuse these room names (already taken): {', '.join(existing_room_names[:30])}")

    # Existing monsters summary
    if existing_monsters:
        monster_summary = ", ".join(
            f"{m['kind']} (tags: {', '.join(m.get('tags', []))})"
            for m in existing_monsters[:20]  # Cap at 20 to save tokens
        )
        if monster_library_full:
            parts.append(f"\nAvailable monsters (library FULL — use ONLY these, do NOT create new ones): {monster_summary}")
        else:
            parts.append(f"\nExisting monsters: {monster_summary}")
            parts.append("You MUST create at least 1 new monster (in new_monsters) with a unique thematic design, sprite, and behavior. You may also reuse existing ones alongside your new creation.")
    else:
        parts.append("\nNo existing monsters — you MUST create new ones (define them in new_monsters). Design at least 1-2 unique monsters with thematic sprites and interesting behavior rules.")

    # Tiles summary (always includes built-ins)
    builtin_tiles = [
        "DW (dungeon wall, non-walkable)",
        "DF (dungeon floor, walkable)",
        "PL (pillar, non-walkable)",
        "SC (sconce wall, non-walkable)",
    ]
    custom_tile_parts = [
        f"{t['id']} ({'walkable' if t.get('walkable', False) else 'non-walkable'}, tags: {', '.join(t.get('tags', []))})"
        for t in (existing_tiles or [])[:20]
    ]
    tile_summary = ", ".join(builtin_tiles + custom_tile_parts)

    if existing_tiles:
        if tile_library_full:
            parts.append(f"\nAvailable tiles (library FULL — use ONLY these, do NOT create new ones): {tile_summary}")
        else:
            parts.append(f"\nAvailable tiles: {tile_summary}")
            parts.append("You MUST create at least 1 new custom tile (in new_tiles) that fits the theme — either a walkable floor or a non-walkable wall. Use it in your tilemap for visual variety.")
    else:
        parts.append(f"\nAvailable tiles: {tile_summary}")
        parts.append("You MUST create at least 1 new custom tile (in new_tiles) that fits the theme — either a walkable floor or a non-walkable wall. Use it in your tilemap for visual variety.")

    # Retry with validation error
    if validation_error:
        parts.append(f"\n\nYour previous response had validation errors. Fix them:\n{validation_error}")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------

FEW_SHOT_EXAMPLES = [
    {
        "role": "user",
        "content": (
            'Generate a dungeon room with theme "fire" and difficulty 4/10.\n\n'
            'No existing monsters — you MUST create new ones (define them in new_monsters). '
            'Design at least 1-2 unique monsters with thematic sprites and interesting behavior rules.\n\n'
            'Available tiles: DW (dungeon wall, non-walkable), DF (dungeon floor, walkable), '
            'PL (pillar, non-walkable), SC (sconce wall, non-walkable)\n'
            'You MUST create at least 1 new custom tile that fits the theme — '
            'either a walkable floor or a non-walkable wall. Use it in your tilemap for visual variety.'
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "name": "Ember Chamber",
            "tilemap": [
                ["DW","DW","DW","DW","DW","DW","DF","DF","DF","DW","DW","DW","DW","DW","DW"],
                ["DW","DF","DF","DF","DF","DF","DF","DF","DF","DW","DW","SC","DF","DF","DW"],
                ["DW","DF","DF","DF","DF","DF","DF","DF","DW","DW","DF","DF","DF","DF","DW"],
                ["DW","DW","DW","DF","DF","DF","DF","DF","DF","DF","DF","DF","DF","DF","DW"],
                ["DF","DF","DF","DF","DF","DW","DW","DF","DF","DF","DF","PL","DF","DF","DF"],
                ["DF","DF","DF","DF","DF","DF","DW","DF","ember_floor","DF","DF","DF","DF","DF","DF"],
                ["DF","DF","PL","DF","DF","DF","DF","DF","DF","DW","DF","DF","DF","DF","DF"],
                ["DW","DF","DF","DF","DF","DF","DF","ember_floor","DW","DW","DW","DF","DF","DF","DW"],
                ["DW","DF","DF","DF","DW","DW","DF","DF","DF","DF","DW","DW","DF","DF","DW"],
                ["DW","DF","DF","DW","DW","DF","DF","DF","DF","DF","DF","DF","DF","DF","DW"],
                ["DW","DW","DW","DW","DW","DW","DF","DF","DF","DW","DW","DW","DW","DW","DW"],
            ],
            "new_tiles": [
                {
                    "id": "ember_floor",
                    "walkable": True,
                    "tags": ["fire", "floor"],
                    "colors": {"base": "#3a2a1a", "alt": "#2a1a0a", "glow": "#cc4400"},
                    "operations": [
                        {"op": "fill", "color": "base"},
                        {"op": "noise", "color": "alt", "density": 0.4},
                        {"op": "pixels", "pixels": [["glow",3,7],["glow",10,4],["glow",6,12],["glow",13,9]]},
                    ],
                },
            ],
            "new_monsters": [
                {
                    "kind": "fire_imp",
                    "tags": ["fire", "dungeon", "melee"],
                    "stats": {"hp": 2, "hop_interval": 1.2, "damage": 1},
                    "sprite": {
                        "colors": {"body": "#cc3300", "dark": "#881100", "eyes": "#ffcc00", "flame": "#ff6600"},
                        "frames": [
                            [
                                ["dark",  5, 9, 6, 5],
                                ["body",  5, 4, 6, 7],
                                ["body",  6, 3, 4, 1],
                                ["eyes",  6, 6, 2, 1],
                                ["eyes",  9, 6, 2, 1],
                                ["flame", 6, 2, 4, 2],
                            ],
                            [
                                ["dark",  5, 8, 6, 5],
                                ["body",  5, 3, 6, 7],
                                ["body",  6, 2, 4, 1],
                                ["eyes",  6, 5, 2, 1],
                                ["eyes",  9, 5, 2, 1],
                                ["flame", 6, 1, 4, 2],
                            ],
                        ],
                    },
                    "behavior": {
                        "rules": [
                            {"if": "hp_below_pct", "value": 30, "do": "flee"},
                            {"if": "player_within", "range": 4, "do": "chase"},
                            {"default": "wander"},
                        ],
                        "attacks": [],
                    },
                },
            ],
            "monster_placements": [
                {"kind": "fire_imp", "x": 4, "y": 2},
                {"kind": "fire_imp", "x": 12, "y": 4},
            ],
        }),
    },
]


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------

# Built-in dungeon tile codes
BUILTIN_TILES = {"DW", "DF", "PL", "SC"}

# Non-walkable tiles (monsters can't be placed here)
NON_WALKABLE = {"DW", "PL", "SC"}

# Valid sets (imported from mud_server at runtime, but defined here as fallback)
VALID_BEHAVIOR_CONDITIONS = {
    "player_within", "player_beyond", "hp_below_pct", "hp_above_pct",
    "random_chance", "always", "default", "can_attack", "player_in_attack_range",
}
VALID_BEHAVIOR_ACTIONS = {"wander", "chase", "flee", "patrol", "hold", "attack"}
VALID_ATTACK_TYPES = {"melee", "projectile", "charge", "teleport", "area"}
VALID_TILE_OPS = {"fill", "noise", "bricks", "grid_lines", "hstripes", "vstripes",
                  "wave", "ripple", "rects", "pixels"}

import re as _re

def _is_hex_color(v: str) -> bool:
    return isinstance(v, str) and bool(_re.match(r'^#[0-9a-fA-F]{6}$', v))


# ---------------------------------------------------------------------------
# Auto-patching — fix common AI mistakes locally to avoid costly retries
# ---------------------------------------------------------------------------

def _build_walkability_set(data: dict, existing_walkable: set[str]) -> set[str]:
    """Build the set of all walkable tile codes for this room."""
    walkable = {"DF"} | existing_walkable
    for t in data.get("new_tiles", []):
        if isinstance(t, dict) and t.get("walkable", False):
            walkable.add(t.get("id", ""))
    return walkable


def patch_monster_placements(data: dict, existing_walkable: set[str]) -> list[str]:
    """Move monsters to reachable walkable tiles (connected to doorways).
    Handles: non-walkable placement, walled-off placement.
    Returns list of patch descriptions."""
    patches = []
    tilemap = data.get("tilemap")
    placements = data.get("monster_placements")
    if not tilemap or not placements or len(tilemap) != 11:
        return patches
    if not all(isinstance(r, list) and len(r) == 15 for r in tilemap):
        return patches

    walkable = _build_walkability_set(data, existing_walkable)

    # Flood fill from north doorway to find reachable walkable tiles
    reachable = set()
    stack = [(0, 7)]  # center of north doorway
    while stack:
        r, c = stack.pop()
        if (r, c) in reachable:
            continue
        if r < 0 or r > 10 or c < 0 or c > 14:
            continue
        if tilemap[r][c] not in walkable:
            continue
        reachable.add((r, c))
        stack.extend([(r-1,c),(r+1,c),(r,c-1),(r,c+1)])

    # Track occupied tiles
    occupied = set()

    for pi, p in enumerate(placements):
        if not isinstance(p, dict):
            continue
        x, y = int(p.get("x", 0)), int(p.get("y", 0))

        if (y, x) in reachable and (y, x) not in occupied:
            occupied.add((y, x))
            continue

        reason = "non-walkable" if tilemap[y][x] not in walkable else "unreachable"

        # Find nearest reachable tile (BFS from original position)
        from collections import deque
        visited = set()
        queue = deque([(y, x)])
        found = None
        while queue:
            ry, rx = queue.popleft()
            if (ry, rx) in visited:
                continue
            visited.add((ry, rx))
            if (ry, rx) in reachable and (ry, rx) not in occupied:
                found = (ry, rx)
                break
            for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                ny, nx = ry+dy, rx+dx
                if 0 <= ny <= 10 and 0 <= nx <= 14 and (ny, nx) not in visited:
                    queue.append((ny, nx))

        if found:
            patches.append(f"Moved {p.get('kind','?')} from ({x},{y}) [{reason}] to ({found[1]},{found[0]})")
            p["x"] = found[1]
            p["y"] = found[0]
            occupied.add(found)
        else:
            patches.append(f"Removed {p.get('kind','?')} at ({x},{y}) — {reason}, no reachable tile found")
            placements[pi] = None

    # Remove None entries
    data["monster_placements"] = [p for p in placements if p is not None]
    return patches


def patch_unreachable_doorways(data: dict, existing_walkable: set[str]) -> list[str]:
    """Carve walkable paths to connect unreachable doorways.
    Returns list of patch descriptions."""
    patches = []
    tilemap = data.get("tilemap")
    if not tilemap or len(tilemap) != 11:
        return patches
    if not all(isinstance(r, list) and len(r) == 15 for r in tilemap):
        return patches

    walkable = _build_walkability_set(data, existing_walkable)
    non_walkable_codes = {"DW", "PL", "SC"}

    # Identify doorway cells
    doorways = []
    for c in range(6, 9):
        doorways.append((0, c))
        doorways.append((10, c))
    for r in range(4, 7):
        doorways.append((r, 0))
        doorways.append((r, 14))

    # Flood fill from first doorway
    def flood_fill():
        visited = set()
        stack = [doorways[0]]
        while stack:
            row, col = stack.pop()
            if (row, col) in visited:
                continue
            if row < 0 or row > 10 or col < 0 or col > 14:
                continue
            if tilemap[row][col] not in walkable:
                continue
            visited.add((row, col))
            stack.extend([(row-1,col),(row+1,col),(row,col-1),(row,col+1)])
        return visited

    reachable = flood_fill()
    unreachable = [(r, c) for r, c in doorways if (r, c) not in reachable]

    if not unreachable:
        return patches

    # For each unreachable doorway, BFS from it through ALL tiles to find
    # nearest reachable tile, then carve the path
    for dr, dc in unreachable:
        from collections import deque
        visited = {}  # (r,c) -> parent (r,c)
        queue = deque([(dr, dc, None)])
        target = None

        while queue:
            r, c, parent = queue.popleft()
            if (r, c) in visited:
                continue
            if r < 0 or r > 10 or c < 0 or c > 14:
                continue
            visited[(r, c)] = parent
            if (r, c) in reachable:
                target = (r, c)
                break
            for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                queue.append((r+dy, c+dx, (r, c)))

        if target:
            # Trace path back and carve
            carved = []
            pos = target
            while pos is not None:
                r, c = pos
                if tilemap[r][c] not in walkable:
                    tilemap[r][c] = "DF"
                    carved.append(f"({c},{r})")
                pos = visited.get(pos)
            if carved:
                patches.append(f"Carved path to doorway ({dc},{dr}): {', '.join(carved)}")
                # Update reachable set
                reachable = flood_fill()

    return patches


def patch_duplicate_name(data: dict, existing_names: list[str]) -> list[str]:
    """Append roman numeral suffix if room name is already taken.
    Returns list of patch descriptions."""
    if not existing_names:
        return []
    name = data.get("name", "")
    if not name or name not in existing_names:
        return []

    numerals = ["II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
                "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX"]
    taken = set(existing_names)
    for num in numerals:
        candidate = f"{name} {num}"
        if candidate not in taken:
            data["name"] = candidate
            return [f"Renamed \"{name}\" to \"{candidate}\" (duplicate)"]
    # Fallback
    import random
    suffix = random.randint(100, 999)
    data["name"] = f"{name} #{suffix}"
    return [f"Renamed \"{name}\" to \"{data['name']}\" (duplicate)"]


def patch_monster_attacks(data: dict) -> list[str]:
    """Clamp out-of-range attack stats to valid bounds.
    Returns list of patch descriptions."""
    patches = []
    for m in data.get("new_monsters", []):
        if not isinstance(m, dict):
            continue
        kind = m.get("kind", "?")
        behavior = m.get("behavior")
        if not isinstance(behavior, dict):
            continue
        for ai, atk in enumerate(behavior.get("attacks", [])):
            if not isinstance(atk, dict):
                continue
            cd = atk.get("cooldown")
            if isinstance(cd, (int, float)) and (cd < 0.5 or cd > 30.0):
                clamped = max(0.5, min(30.0, cd))
                patches.append(f"Clamped {kind} attack[{ai}] cooldown {cd} -> {clamped}")
                atk["cooldown"] = clamped
            rng = atk.get("range")
            if isinstance(rng, (int, float)) and (rng < 1 or rng > 15):
                clamped = max(1, min(15, int(rng)))
                patches.append(f"Clamped {kind} attack[{ai}] range {rng} -> {clamped}")
                atk["range"] = clamped
    return patches


def auto_patch(data: dict, existing_walkable: set[str],
               existing_room_names: list[str] | None = None) -> list[str]:
    """Apply all auto-patches. Returns list of patch descriptions."""
    patches = []
    patches.extend(patch_duplicate_name(data, existing_room_names or []))
    patches.extend(patch_unreachable_doorways(data, existing_walkable))
    patches.extend(patch_monster_placements(data, existing_walkable))
    patches.extend(patch_monster_attacks(data))
    return patches


def validate_room_response(data: dict, existing_tile_ids: set[str] | None = None,
                           existing_walkable_tiles: set[str] | None = None) -> list[str]:
    """Validate the AI's room response. Returns list of error strings."""
    errors = []
    existing_tile_ids = existing_tile_ids or set()
    existing_walkable_tiles = existing_walkable_tiles or set()

    # -- name --
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name must be a non-empty string")

    # -- tilemap --
    tilemap = data.get("tilemap")
    if not isinstance(tilemap, list) or len(tilemap) != 11:
        errors.append(f"tilemap must be 11 rows, got {len(tilemap) if isinstance(tilemap, list) else 'non-list'}")
        return errors  # Can't validate further without correct dimensions

    # Collect custom tile IDs defined in new_tiles and track walkability
    new_tile_ids = set()
    new_walkable_tiles = set()
    for t in data.get("new_tiles", []):
        if isinstance(t, dict) and isinstance(t.get("id"), str):
            new_tile_ids.add(t["id"])
            if t.get("walkable", False):
                new_walkable_tiles.add(t["id"])

    all_valid_tiles = BUILTIN_TILES | new_tile_ids | existing_tile_ids

    for row_idx, row in enumerate(tilemap):
        if not isinstance(row, list) or len(row) != 15:
            errors.append(f"tilemap[{row_idx}] must be 15 columns, got {len(row) if isinstance(row, list) else 'non-list'}")
            continue
        for col_idx, tile in enumerate(row):
            if tile not in all_valid_tiles:
                errors.append(f"tilemap[{row_idx}][{col_idx}] unknown tile: {tile!r}")

    # Validate doorway constraints (borders must have correct tiles)
    if len(tilemap) == 11 and all(isinstance(r, list) and len(r) == 15 for r in tilemap):
        # Top/bottom rows: cols 0-5 and 9-14 = DW, cols 6-8 = DF
        for row_idx in (0, 10):
            for col_idx in range(15):
                expected = "DF" if 6 <= col_idx <= 8 else "DW"
                actual = tilemap[row_idx][col_idx]
                if actual != expected:
                    errors.append(f"tilemap[{row_idx}][{col_idx}] must be {expected} (doorway edge), got {actual!r}")
        # Left/right columns: rows 0-3 and 7-10 = DW, rows 4-6 = DF
        for col_idx in (0, 14):
            for row_idx in range(11):
                expected = "DF" if 4 <= row_idx <= 6 else "DW"
                actual = tilemap[row_idx][col_idx]
                if actual != expected:
                    errors.append(f"tilemap[{row_idx}][{col_idx}] must be {expected} (doorway edge), got {actual!r}")

    # -- doorway reachability (flood fill) --
    if len(tilemap) == 11 and all(isinstance(r, list) and len(r) == 15 for r in tilemap):
        walkable_set = {"DF"} | new_walkable_tiles | existing_walkable_tiles
        # Identify all doorway cells
        doorways = []
        for c in range(6, 9):
            doorways.append((0, c))    # north
            doorways.append((10, c))   # south
        for r in range(4, 7):
            doorways.append((r, 0))    # west
            doorways.append((r, 14))   # east

        # Flood fill from the first doorway
        visited = set()
        stack = [doorways[0]]
        while stack:
            row, col = stack.pop()
            if (row, col) in visited:
                continue
            if row < 0 or row > 10 or col < 0 or col > 14:
                continue
            tile = tilemap[row][col]
            if tile not in walkable_set:
                continue
            visited.add((row, col))
            stack.extend([(row-1, col), (row+1, col), (row, col-1), (row, col+1)])

        # Check all doorways are reachable
        unreachable = [f"({r},{c})" for r, c in doorways if (r, c) not in visited]
        if unreachable:
            errors.append(f"Doorways not connected — unreachable: {', '.join(unreachable)}")

    # -- new_tiles --
    new_tiles = data.get("new_tiles", [])
    if not isinstance(new_tiles, list):
        errors.append("new_tiles must be a list")
    else:
        for ti, tile in enumerate(new_tiles):
            if not isinstance(tile, dict):
                errors.append(f"new_tiles[{ti}] must be a dict")
                continue
            tid = tile.get("id")
            if not isinstance(tid, str) or not _re.match(r'^[a-z][a-z0-9_]*$', tid):
                errors.append(f"new_tiles[{ti}].id must be lowercase alphanumeric")
            walkable = tile.get("walkable")
            if walkable is not None and not isinstance(walkable, bool):
                errors.append(f"new_tiles[{ti}].walkable must be a boolean")
            colors = tile.get("colors")
            if not isinstance(colors, dict):
                errors.append(f"new_tiles[{ti}].colors must be a dict")
            else:
                for k, v in colors.items():
                    if not _is_hex_color(v):
                        errors.append(f"new_tiles[{ti}].colors.{k} invalid hex: {v!r}")
            ops = tile.get("operations")
            if not isinstance(ops, list) or len(ops) < 1:
                errors.append(f"new_tiles[{ti}].operations must be non-empty list")
            else:
                for oi, op in enumerate(ops):
                    if not isinstance(op, dict):
                        continue
                    if op.get("op") not in VALID_TILE_OPS:
                        errors.append(f"new_tiles[{ti}].operations[{oi}] unknown op: {op.get('op')}")
                    if op.get("op") == "rects":
                        for ri, rect in enumerate(op.get("rects", [])):
                            if isinstance(rect, list) and len(rect) == 5:
                                _, x, y, w, h = rect
                                if any(not isinstance(v, (int, float)) for v in (x, y, w, h)):
                                    errors.append(f"new_tiles[{ti}].ops[{oi}].rects[{ri}] coords must be numbers")
                                elif x < 0 or y < 0 or x + w > 16 or y + h > 16:
                                    errors.append(f"new_tiles[{ti}].ops[{oi}].rects[{ri}] out of bounds")
                    if op.get("op") == "pixels":
                        for pi, px in enumerate(op.get("pixels", [])):
                            if isinstance(px, list) and len(px) == 3:
                                _, x, y = px
                                if x < 0 or x > 15 or y < 0 or y > 15:
                                    errors.append(f"new_tiles[{ti}].ops[{oi}].pixels[{pi}] out of bounds")

    # -- new_monsters --
    new_monsters = data.get("new_monsters", [])
    if not isinstance(new_monsters, list):
        errors.append("new_monsters must be a list")
    else:
        for mi, mon in enumerate(new_monsters):
            if not isinstance(mon, dict):
                errors.append(f"new_monsters[{mi}] must be a dict")
                continue
            kind = mon.get("kind")
            if not isinstance(kind, str) or not _re.match(r'^[a-z][a-z0-9_]*$', kind):
                errors.append(f"new_monsters[{mi}].kind must be lowercase alphanumeric")

            # Stats
            stats = mon.get("stats")
            if not isinstance(stats, dict):
                errors.append(f"new_monsters[{mi}].stats must be a dict")
            else:
                hp = stats.get("hp")
                if not isinstance(hp, (int, float)) or hp < 1 or hp > 100:
                    errors.append(f"new_monsters[{mi}].stats.hp must be 1-100")
                hop = stats.get("hop_interval")
                if not isinstance(hop, (int, float)) or hop < 0.2 or hop > 10.0:
                    errors.append(f"new_monsters[{mi}].stats.hop_interval must be 0.2-10.0")
                dmg = stats.get("damage")
                if not isinstance(dmg, (int, float)) or dmg < 1 or dmg > 20:
                    errors.append(f"new_monsters[{mi}].stats.damage must be 1-20")

            # Sprite
            sprite = mon.get("sprite")
            if not isinstance(sprite, dict):
                errors.append(f"new_monsters[{mi}].sprite must be a dict")
            else:
                colors = sprite.get("colors")
                if not isinstance(colors, dict):
                    errors.append(f"new_monsters[{mi}].sprite.colors must be a dict")
                else:
                    for k, v in colors.items():
                        if not _is_hex_color(v):
                            errors.append(f"new_monsters[{mi}].sprite.colors.{k} invalid: {v!r}")
                frames = sprite.get("frames")
                if not isinstance(frames, list) or len(frames) < 1:
                    errors.append(f"new_monsters[{mi}].sprite.frames must be non-empty")
                else:
                    for fi, frame in enumerate(frames):
                        if not isinstance(frame, list):
                            continue
                        for li, layer in enumerate(frame):
                            if not isinstance(layer, list) or len(layer) != 5:
                                errors.append(f"new_monsters[{mi}].sprite.frames[{fi}][{li}] must be [colorKey, x, y, w, h]")
                                continue
                            _, x, y, w, h = layer
                            if not all(isinstance(v, (int, float)) for v in (x, y, w, h)):
                                errors.append(f"new_monsters[{mi}].sprite.frames[{fi}][{li}] coords must be numbers")
                            elif x < 0 or y < 0 or x + w > 16 or y + h > 16:
                                errors.append(f"new_monsters[{mi}].sprite.frames[{fi}][{li}] out of 16x16 bounds")

            # Behavior (optional but expected)
            behavior = mon.get("behavior")
            if behavior is not None:
                if not isinstance(behavior, dict):
                    errors.append(f"new_monsters[{mi}].behavior must be a dict")
                else:
                    rules = behavior.get("rules", [])
                    for ri, rule in enumerate(rules):
                        if not isinstance(rule, dict):
                            continue
                        cond = rule.get("if") or (rule.get("default") and "default")
                        if cond and cond not in VALID_BEHAVIOR_CONDITIONS:
                            errors.append(f"new_monsters[{mi}].behavior.rules[{ri}] unknown condition: {cond}")
                        action = rule.get("do") or (rule.get("default") if "default" in rule else None)
                        if isinstance(action, str) and action not in VALID_BEHAVIOR_ACTIONS:
                            errors.append(f"new_monsters[{mi}].behavior.rules[{ri}] unknown action: {action}")
                    attacks = behavior.get("attacks", [])
                    for ai, atk in enumerate(attacks):
                        if not isinstance(atk, dict):
                            continue
                        atype = atk.get("type")
                        if atype not in VALID_ATTACK_TYPES:
                            errors.append(f"new_monsters[{mi}].behavior.attacks[{ai}] unknown type: {atype}")
                        rng = atk.get("range")
                        if not isinstance(rng, (int, float)) or rng < 1 or rng > 15:
                            errors.append(f"new_monsters[{mi}].behavior.attacks[{ai}] range must be 1-15")
                        cd = atk.get("cooldown")
                        if cd is not None and (not isinstance(cd, (int, float)) or cd < 0.5 or cd > 30.0):
                            errors.append(f"new_monsters[{mi}].behavior.attacks[{ai}] cooldown must be 0.5-30.0")

    # -- monster_placements --
    placements = data.get("monster_placements", [])
    if not isinstance(placements, list):
        errors.append("monster_placements must be a list")
    else:
        # Build set of valid monster kinds
        new_monster_kinds = set()
        for m in new_monsters if isinstance(new_monsters, list) else []:
            if isinstance(m, dict) and isinstance(m.get("kind"), str):
                new_monster_kinds.add(m["kind"])

        for pi, p in enumerate(placements):
            if not isinstance(p, dict):
                errors.append(f"monster_placements[{pi}] must be a dict")
                continue
            x = p.get("x")
            y = p.get("y")
            if not isinstance(x, (int, float)) or x < 0 or x > 14:
                errors.append(f"monster_placements[{pi}].x must be 0-14")
            if not isinstance(y, (int, float)) or y < 0 or y > 10:
                errors.append(f"monster_placements[{pi}].y must be 0-10")
            # Check placement is on a walkable tile
            if (isinstance(x, (int, float)) and isinstance(y, (int, float)) and
                    isinstance(tilemap, list) and len(tilemap) == 11):
                ix, iy = int(x), int(y)
                if 0 <= iy < 11 and 0 <= ix < 15:
                    tile_at = tilemap[iy][ix]
                    if tile_at in NON_WALKABLE and tile_at not in new_walkable_tiles and tile_at not in existing_walkable_tiles:
                        errors.append(f"monster_placements[{pi}] at ({ix},{iy}) is on non-walkable tile {tile_at!r}")

    # Cap total errors to avoid huge retry prompts
    if len(errors) > 15:
        errors = errors[:15] + [f"... and {len(errors) - 15} more errors"]

    return errors


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------

def _dump_ai_output(raw_text: str, label: str = "failed") -> str:
    """Save raw AI output to a timestamped file for debugging. Returns the filename."""
    from datetime import datetime
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"ai_output_{ts}.txt"
    filepath = Path(__file__).parent / filename
    filepath.write_text(raw_text, encoding="utf-8")
    print(f"[GEN] Raw AI output saved to {filename} ({label})")
    return filename


_client = None

def _get_client():
    """Lazy-initialize the Anthropic client."""
    global _client
    if _client is None:
        import anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


# Module-level instances
rate_limiter = RateLimiter()
usage_tracker = UsageTracker()


def init():
    """Load persisted usage data on startup."""
    usage_tracker.load()


async def generate_room(
    theme: str = "dungeon",
    difficulty: int = 5,
    existing_monsters: list[dict] | None = None,
    existing_tiles: list[dict] | None = None,
    monster_library_full: bool = False,
    tile_library_full: bool = False,
    existing_room_names: list[str] | None = None,
) -> dict | None:
    """Generate a complete dungeon room via Claude API.

    Returns the validated room dict, or None on failure.
    Each dict has: name, tilemap, new_tiles, new_monsters, monster_placements.
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[GEN] No ANTHROPIC_API_KEY set — skipping generation")
        return None

    if not rate_limiter.can_call():
        print("[GEN] Rate limit reached — skipping generation")
        return None

    existing_monsters = existing_monsters or []
    existing_tiles = existing_tiles or []
    validation_error = None

    total_attempts = 1 + MAX_RETRIES
    for attempt in range(total_attempts):
        print(f"[GEN] Try {attempt + 1}/{total_attempts}...")
        prompt = _build_prompt(
            theme, difficulty,
            existing_monsters, existing_tiles,
            monster_library_full, tile_library_full,
            validation_error=validation_error,
            existing_room_names=existing_room_names,
        )

        messages = FEW_SHOT_EXAMPLES + [{"role": "user", "content": prompt}]

        raw_text = None  # captured for debug dump on failure
        try:
            client = _get_client()
            rate_limiter.record_call()

            # Run the synchronous API call in a thread to not block asyncio
            start_time = time.time()
            response = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.messages.create(
                        model=ANTHROPIC_MODEL,
                        max_tokens=4096,
                        system=SYSTEM_PROMPT,
                        messages=messages,
                    )
                ),
                timeout=GENERATION_TIMEOUT,
            )
            elapsed = time.time() - start_time

            # Track usage
            input_tokens = response.usage.input_tokens
            output_tokens = response.usage.output_tokens
            usage_tracker.record(input_tokens, output_tokens)

            # Parse response
            raw_text = response.content[0].text.strip()

            # Strip markdown code fences if present
            if raw_text.startswith("```"):
                raw_lines = raw_text.split("\n")
                if raw_lines[-1].strip() == "```":
                    raw_lines = raw_lines[1:-1]
                else:
                    raw_lines = raw_lines[1:]
                raw_text = "\n".join(raw_lines)

            data = json.loads(raw_text)

            # Auto-patch common issues before validation
            ext_tile_ids = {t["id"] for t in existing_tiles if isinstance(t, dict) and "id" in t}
            ext_walkable = {t["id"] for t in existing_tiles if isinstance(t, dict) and t.get("walkable", False)}
            patch_log = auto_patch(data, ext_walkable, existing_room_names)
            if patch_log:
                print(f"[GEN] Auto-patched {len(patch_log)} issues:")
                for p in patch_log:
                    print(f"[GEN]   {p}")

            # Validate — pass existing library tile IDs so they're recognized
            errors = validate_room_response(data, existing_tile_ids=ext_tile_ids,
                                            existing_walkable_tiles=ext_walkable)

            # Also check that placed monsters reference valid kinds
            existing_kinds = {m["kind"] for m in existing_monsters if isinstance(m, dict)}
            new_kinds = set()
            for m in data.get("new_monsters", []):
                if isinstance(m, dict) and isinstance(m.get("kind"), str):
                    new_kinds.add(m["kind"])
            all_kinds = existing_kinds | new_kinds | _BUILTIN_KINDS
            for pi, p in enumerate(data.get("monster_placements", [])):
                if isinstance(p, dict):
                    k = p.get("kind")
                    if k and k not in all_kinds:
                        errors.append(f"monster_placements[{pi}].kind {k!r} not in existing or new monsters")

            if errors:
                validation_error = "\n".join(f"- {e}" for e in errors)
                print(f"[GEN] Try {attempt + 1}/{total_attempts} FAILED — {len(errors)} validation errors:")
                for e in errors:
                    print(f"[GEN]   {e}")
                if raw_text:
                    _dump_ai_output(raw_text, "validation failed")
                if attempt < MAX_RETRIES:
                    print(f"[GEN] Retrying with error feedback...")
                    continue
                else:
                    print(f"[GEN] Max retries reached, giving up")
                    return None

            # Success
            print(f"[GEN] Try {attempt + 1}/{total_attempts} SUCCESS — \"{data.get('name', '?')}\" "
                  f"({elapsed:.1f}s, {input_tokens}+{output_tokens} tokens, "
                  f"{len(data.get('new_monsters', []))} new monsters, "
                  f"{len(data.get('new_tiles', []))} new tiles)")
            return data

        except asyncio.TimeoutError:
            print(f"[GEN] Try {attempt + 1}/{total_attempts} FAILED — API timeout after {GENERATION_TIMEOUT}s")
            return None
        except json.JSONDecodeError as e:
            print(f"[GEN] Try {attempt + 1}/{total_attempts} FAILED — parse error: {e}")
            if raw_text:
                _dump_ai_output(raw_text, "JSON parse error")
            if attempt < MAX_RETRIES:
                validation_error = f"Response was not valid JSON: {e}. Return ONLY a JSON object, no markdown or explanation."
                print(f"[GEN] Retrying with error feedback...")
                continue
            return None
        except Exception as e:
            print(f"[GEN] Try {attempt + 1}/{total_attempts} FAILED — {type(e).__name__}: {e}")
            if raw_text:
                _dump_ai_output(raw_text, f"{type(e).__name__}: {e}")
            return None

    return None


# Built-in monster kinds that don't need to be in existing_monsters
_BUILTIN_KINDS = {"slime", "bat", "scorpion", "skeleton", "swamp_blob"}


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

async def _test_standalone():
    """Run a standalone test — generate rooms with empty and populated libraries."""
    print("=" * 60)
    print("AI Generator — Standalone Test")
    print("=" * 60)

    # Test 1: Empty library (brand new content)
    print("\n--- Test 1: Empty library, fire theme, difficulty 5 ---")
    result = await generate_room(
        theme="fire",
        difficulty=5,
        existing_monsters=[],
        existing_tiles=[],
    )
    if result:
        print(f"  Name: {result['name']}")
        print(f"  Tilemap: {len(result['tilemap'])} rows x {len(result['tilemap'][0])} cols")
        print(f"  New monsters: {[m['kind'] for m in result.get('new_monsters', [])]}")
        print(f"  New tiles: {[t['id'] for t in result.get('new_tiles', [])]}")
        print(f"  Placements: {result.get('monster_placements', [])}")
    else:
        print("  FAILED — no result returned")

    # Test 2: With some existing monsters
    print("\n--- Test 2: Some existing content, shadow theme, difficulty 7 ---")
    result2 = await generate_room(
        theme="shadow",
        difficulty=7,
        existing_monsters=[
            {"kind": "shadow_wraith", "tags": ["shadow", "undead"]},
            {"kind": "dark_bat", "tags": ["shadow", "flying"]},
        ],
        existing_tiles=[
            {"id": "dark_stone", "walkable": True, "tags": ["shadow", "dungeon"]},
        ],
    )
    if result2:
        print(f"  Name: {result2['name']}")
        print(f"  New monsters: {[m['kind'] for m in result2.get('new_monsters', [])]}")
        print(f"  Placements: {result2.get('monster_placements', [])}")
    else:
        print("  FAILED — no result returned")

    # Test 3: Full library (no new content)
    print("\n--- Test 3: Full library, dungeon theme, difficulty 3 ---")
    result3 = await generate_room(
        theme="dungeon",
        difficulty=3,
        existing_monsters=[
            {"kind": "skeleton", "tags": ["undead"]},
            {"kind": "slime", "tags": ["dungeon"]},
            {"kind": "bat", "tags": ["flying"]},
        ],
        existing_tiles=[],
        monster_library_full=True,
        tile_library_full=True,
    )
    if result3:
        print(f"  Name: {result3['name']}")
        print(f"  New monsters (should be 0): {[m['kind'] for m in result3.get('new_monsters', [])]}")
        print(f"  Placements: {result3.get('monster_placements', [])}")
    else:
        print("  FAILED — no result returned")

    print(f"\n--- Usage stats ---")
    print(f"  Total calls: {usage_tracker.total_calls}")
    print(f"  Input tokens: {usage_tracker.total_input_tokens}")
    print(f"  Output tokens: {usage_tracker.total_output_tokens}")
    print(f"  Estimated cost: ${usage_tracker.estimated_cost():.4f}")


if __name__ == "__main__":
    asyncio.run(_test_standalone())
