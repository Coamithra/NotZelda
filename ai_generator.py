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
import re as _re
from collections import deque
from pathlib import Path
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
GENERATION_TIMEOUT = 15.0       # seconds before giving up on API call
CLI_TIMEOUT = 600.0             # CLI is much slower than API
# TODO(2026-03-14): Revisit this flag — try removing the few-shot example
# permanently if generation quality is acceptable without it.
USE_FEW_SHOT = False            # Set True to include few-shot example in prompts
MAX_API_CALLS_PER_MINUTE = 5
MAX_API_CALLS_PER_DAY = 200
MAX_RETRIES = 1                 # single retry on validation failure

# Backend: "api" uses Anthropic SDK (needs ANTHROPIC_API_KEY),
#          "cli" shells out to local `claude` CLI (uses your subscription)
AI_BACKEND = os.environ.get("AI_BACKEND", "cli").lower()

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

# Per-million-token pricing by model
MODEL_PRICING = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-sonnet-4-6":        (3.00, 15.00),
    "claude-opus-4-6":          (15.00, 75.00),
}


@dataclass
class UsageTracker:
    """Tracks API token usage and cost (all-time persisted + per-session)."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_calls: int = 0
    session_input_tokens: int = 0
    session_output_tokens: int = 0
    session_calls: int = 0
    _file: Path = field(default_factory=lambda: DATA_DIR / "api_usage.json")

    def record(self, input_tokens: int, output_tokens: int):
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.total_calls += 1
        self.session_input_tokens += input_tokens
        self.session_output_tokens += output_tokens
        self.session_calls += 1
        self._save()

    def _cost(self, input_tokens: int, output_tokens: int) -> float:
        price_in, price_out = MODEL_PRICING.get(ANTHROPIC_MODEL, (1.00, 5.00))
        return (input_tokens * price_in / 1_000_000 +
                output_tokens * price_out / 1_000_000)

    def estimated_cost(self) -> float:
        return self._cost(self.total_input_tokens, self.total_output_tokens)

    def session_cost(self) -> float:
        return self._cost(self.session_input_tokens, self.session_output_tokens)

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
- Each cell is a tile code from the available tiles list (provided in the user message)
- Tiles are either walkable (players/monsters can traverse) or non-walkable (walls/obstacles)
- Row 0 (top) and row 10 (bottom): columns 0-5 and 9-14 MUST be non-walkable. Columns 6-8 MUST be walkable for north/south doorways
- Column 0 (left) and column 14 (right): rows 0-3 and 7-10 MUST be non-walkable. Rows 4-6 MUST be walkable for east/west doorways
- Interior (rows 1-9, cols 1-13) is your creative space
- IMPORTANT: Use wall tiles INSIDE the room to create interesting shapes:
  - L-corridors, T-junctions, winding paths, chokepoints, alcoves, divided chambers
  - Only 30-60% of interior should be walkable — walls create character
  - Mix it up: some symmetric, some asymmetric
  - ALL four doorways must be connected by walkable tiles (flood-fill reachable)
- Monsters must be placed only on walkable tiles, away from doorways (not on row 0, row 10, col 0, or col 14). Use interior positions (rows 2-9, cols 2-13) so players aren't ambushed at entrances
- Use a MIX of available tiles and custom tiles. Pick a dominant walkable tile for most floors and a dominant non-walkable tile for most interior walls. Scatter other tile types for variety

## MONSTER DEFINITION FORMAT
Each new monster needs:
```
{
  "kind": "lowercase_name",
  "tags": ["fire", "melee"],
  "stats": {"hp": 2, "hop_interval": 1.2, "damage": 1},
  "sprite": {
    "colors": {"body": "#cc3300", "eyes": "#ffcc00", ...},
    "frames": [
      [["body", 5, 4, 6, 7], ["eyes", 6, 6, 2, 1], ...],
      [["body", 5, 3, 6, 7], ["eyes", 6, 5, 2, 1], ...]
    ]
  },
  "behavior": {
    "rules": [
      {"if": "player_within", "range": 4, "do": "chase"},
      {"if": "hp_below_pct", "value": 30, "do": "flee"},
      {"default": "wander"}
    ],
    "attacks": [
      {"type": "melee", "range": 1, "damage": 1, "cooldown": 2.0}
    ]
  }
}
```

Sprite grid is 16x16. Each layer is [colorKey, x, y, w, h] where x+w<=16, y+h<=16.
Layers render in array order — first layer is the back, last layer is the front. Put shadows/bases first, details/eyes last.
Sprites need 2-4 frames showing interesting animation: stretching, pulsing, limb movement, shape changes, eye blinks, wing flaps, etc. Each frame should have meaningfully different shapes/positions — NOT just a y-offset hop.
Good examples: a slime that squishes wide (x=3,w=10,y=8) then stretches tall (x=4,w=8,y=4); a bat whose wings go from up (y=3) to down (y=7) with completely different wing positions.
Use 3-6 color keys per sprite. Build recognizable silhouettes with 5-12 layers per frame.
Tips: place eyes near the top third, use a dark color for the base/shadow, make the shape asymmetric or distinctive.

Behavior rules are evaluated top-to-bottom, first match wins. Put urgent conditions first (low HP → flee), then combat (can_attack → attack), then approach (player_within → chase), then default.
- `default` is the fallback condition (always matches). Use it for the last rule. `always` is identical to `default`.

Behavior conditions with their parameter name:
- player_within: "range" (tiles)
- player_beyond: "range" (tiles)
- hp_below_pct: "value" (0-100)
- hp_above_pct: "value" (0-100)
- random_chance: "value" (0-100, percent chance)
- can_attack: (no param — true when any attack is off cooldown and player in range)
- player_in_attack_range: (no param)
- default: (no param, always matches)

Behavior actions: wander, chase, flee, patrol, hold, attack

`stats.damage` is **contact damage** when the monster touches a player. `attacks[].damage` is separate per-attack damage. Both can coexist.

Attacks are tried in array order — first usable attack fires. Put preferred/ranged attacks first, close-range fallbacks last.

Attack types and their extra fields:
- melee: range MUST be 1, strikes adjacent player
- projectile: range 1-10 (travel distance), requires "sprite_color": "#RRGGBB"
- charge: range 2-6 (dash distance), 2-tick windup with warning
- teleport: range 1-8 (max teleport distance), requires "delay": 0.2-3.0
- area: range 1-4 (AoE radius), requires "warning_duration": 0.3-3.0
All attacks need: "type", "range", "damage" (1-20), "cooldown" (0.5-30.0 seconds)

## CUSTOM TILE FORMAT
```
{
  "id": "lava_floor",
  "walkable": true,
  "tags": ["fire", "floor"],
  "colors": {"base": "#3a1a0a", "alt": "#2a0a00", "glow": "#cc4400"},
  "operations": [
    {"op": "fill", "color": "base"},
    {"op": "noise", "color": "alt", "density": 0.4},
    {"op": "pixels", "pixels": [["glow", 3, 7], ["glow", 10, 4]]}
  ]
}
```
Tile grid is 16x16. Operations execute in order. Start with "fill" for base color.
The "walkable" field is REQUIRED — it determines if players/monsters can walk on this tile.
Create 1-2 new custom tiles that fit the theme. Use 3-5 tags per monster and per tile.
IMPORTANT: The "base" and "alt" color keys have special roles:
- "base" is used as the automatic background fill
- "alt" is used by bricks, grid_lines, hstripes, vstripes, wave, and ripple as their drawing color
- You MUST define both "base" and "alt" in your colors dict if you use any of those operations

Available operations:
- fill: {"op": "fill", "color": "colorKey"} — fill entire tile with a color
- noise: {"op": "noise", "color": "colorKey", "density": 0.0-1.0} — random scattered pixels
- bricks: {"op": "bricks"} — brick mortar pattern drawn in "alt" color
- grid_lines: {"op": "grid_lines", "spacing": 2-8} — grid drawn in "alt" color
- hstripes: {"op": "hstripes", "spacing": 2-8} — horizontal stripes in "alt" color
- vstripes: {"op": "vstripes", "spacing": 2-8} — vertical stripes in "alt" color
- wave: {"op": "wave"} — diagonal wave pattern in "alt" color
- ripple: {"op": "ripple"} — alternating dot pattern using "base" and "alt"
- rects: {"op": "rects", "rects": [["colorKey", x, y, w, h], ...]} — colored rectangles
- pixels: {"op": "pixels", "pixels": [["colorKey", x, y], ...]} — individual pixel placement

## RESPONSE FORMAT
Return ONLY valid JSON (no markdown, no explanation).
Assume X is a non-walkable tile and Y is a walkable tile from the available list:
```
{
  "name": "Room Name",
  "tilemap": [
    ["X","X","X","X","X","X","Y","Y","Y","X","X","X","X","X","X"],
    ...11 rows total, 15 columns each...
  ],
  "new_tiles": [...],
  "new_monsters": [...],
  "monster_placements": [
    {"kind": "monster_name", "x": 5, "y": 3}
  ]
}
```

## DIFFICULTY GUIDELINES
- Easy (1-3): 1-2 monsters, hp 1-2, damage 1, hop_interval 1.5-2.5, no attacks
- Medium (4-6): 2-4 monsters, hp 2-4, damage 1-2, hop_interval 1.0-1.8, 1 simple attack (melee or projectile)
- Hard (7-9): 3-5 monsters, hp 3-6, damage 2-3, hop_interval 0.6-1.2, 1-2 varied attacks
- Boss (10): 1 boss + 2-3 fodder, boss hp 6-10, damage 3-4, hop_interval 0.8-1.5, 2-3 attack types

## EXAMPLE LAYOUTS
Legend: x=non-walkable (common/structural), o=non-walkable (uncommon/decorative), .=walkable (common), _=walkable (decorative)
Each row is exactly 15 characters. All 4 doorways must be connected via walkable tiles.
Asymmetric:
xxxxxx...xxxxxx
xxx..xx..xxx_.x
xxx..xx..x_...x
xxxx....xx....x
...xxx..xxo..x.
.._....xxx.....
.......xx.xxx..
x..xxx.._.....x
x..xxxx..xx...x
x..._....xx.o.x
xxxxxx...xxxxxx
Symmetric:
xxxxxx...xxxxxx
xo.xxx...xxx.ox
x..xxx...xxx..x
x..x.._._..x.x
...xx..o..xx...
.._.........._.
...xx..o..xx...
x..x.._._..x.x
x..xxx...xxx..x
xo.xxx...xxx.ox
xxxxxx...xxxxxx

## IMPORTANT RULES
1. All tile codes in the tilemap must be part of the available tiles list or defined in new_tiles
2. All monster kinds in monster_placements must be either in the existing monsters list or defined in new_monsters
3. Place monsters only on walkable tiles, in the interior (rows 2-9, cols 2-13) — not on doorway or border tiles
4. Monster x must be 0-14, y must be 0-10
5. All IDs MUST be lowercase_snake_case [a-z][a-z0-9_]*
6. Give monsters thematic names (fire_imp, frost_archer, shadow_wraith — not monster_1)
7. Sprite colors should be thematically appropriate and visually distinct
8. Room names should be evocative and unique (2-3 words)"""


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

    # Tiles summary — base dungeon tiles + any from the library
    base_tile_parts = [
        "DW (non-walkable, tags: dungeon, wall, stone)",
        "DF (walkable, tags: dungeon, floor, stone)",
        "PL (non-walkable, tags: dungeon, wall, decorative)",
        "SC (non-walkable, tags: dungeon, wall, light)",
    ]
    custom_tile_parts = [
        f"{t['id']} ({'walkable' if t.get('walkable', False) else 'non-walkable'}, tags: {', '.join(t.get('tags', []))})"
        for t in (existing_tiles or [])[:20]
    ]
    tile_summary = ", ".join(base_tile_parts + custom_tile_parts)

    if tile_library_full:
        parts.append(f"\nAvailable tiles (library FULL — use ONLY these, do NOT create new ones): {tile_summary}")
    elif existing_tiles:
        parts.append(f"\nAvailable tiles: {tile_summary}")
        parts.append("Create 1-2 new custom tiles in new_tiles that fit the theme.")
    else:
        parts.append(f"\nAvailable tiles: {tile_summary}")
        parts.append("Create at least 2 new custom tiles in new_tiles: one walkable floor AND one non-walkable wall.")

    if not tile_library_full:
        parts.append("Pick a dominant walkable tile for most floors and a dominant non-walkable tile for most interior walls — these can be existing or newly created tiles.")

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
            'Generate a dungeon room with theme "dungeon" and difficulty 5/10.\n\n'
            'No existing monsters — you MUST create new ones (define them in new_monsters). '
            'Design at least 1-2 unique monsters with thematic sprites and interesting behavior rules.\n\n'
            'Available tiles: stone_wall (non-walkable, tags: dungeon, wall, stone), '
            'stone_floor (walkable, tags: dungeon, floor, stone), '
            'pillar (non-walkable, tags: dungeon, wall, decorative), '
            'wall_light (non-walkable, tags: dungeon, wall, light)\n'
            'Create at least 2 new custom tiles in new_tiles: one walkable floor AND one non-walkable wall.\n'
            'Pick a dominant walkable tile for most floors and a dominant non-walkable tile for most '
            'interior walls — these can be existing or newly created tiles.'
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "name": "Sunken Hall",
            "tilemap": [
                ["stone_wall","stone_wall","stone_wall","stone_wall","stone_wall","stone_wall","alt_floor","alt_floor","alt_floor","stone_wall","stone_wall","stone_wall","stone_wall","stone_wall","stone_wall"],
                ["stone_wall","alt_floor","alt_floor","stone_wall","stone_wall","stone_wall","alt_floor","alt_floor","stone_wall","stone_wall","stone_wall","stone_wall","stone_wall","wall_light","stone_wall"],
                ["stone_wall","alt_floor","alt_floor","stone_wall","stone_wall","stone_wall","alt_floor","alt_floor","alt_floor","stone_wall","stone_wall","stone_wall","stone_wall","stone_wall","stone_wall"],
                ["stone_wall","alt_floor","alt_floor","alt_floor","alt_floor","alt_floor","alt_floor","stone_wall","alt_floor","alt_floor","alt_floor","alt_floor","stone_wall","stone_wall","stone_wall"],
                ["alt_floor","alt_floor","alt_floor","alt_floor","pillar","stone_wall","stone_wall","stone_wall","stone_wall","alt_floor","alt_floor","alt_floor","pillar","alt_floor","alt_floor"],
                ["alt_floor","alt_floor","stone_wall","alt_wall","stone_wall","alt_floor","alt_floor","alt_floor","alt_floor","alt_floor","stone_wall","alt_wall","stone_wall","alt_floor","alt_floor"],
                ["alt_floor","alt_floor","stone_wall","stone_wall","pillar","alt_floor","alt_floor","alt_floor","alt_floor","stone_wall","stone_wall","alt_floor","alt_floor","alt_floor","alt_floor"],
                ["stone_wall","alt_floor","alt_floor","stone_wall","stone_wall","stone_wall","alt_floor","alt_floor","stone_wall","stone_wall","alt_floor","alt_floor","stone_wall","stone_wall","stone_wall"],
                ["stone_wall","stone_wall","alt_floor","alt_floor","stone_wall","stone_wall","alt_floor","alt_floor","alt_floor","stone_wall","stone_wall","alt_floor","alt_floor","wall_light","stone_wall"],
                ["stone_wall","stone_wall","alt_floor","alt_floor","alt_floor","stone_wall","alt_floor","alt_floor","alt_floor","alt_floor","alt_floor","alt_floor","stone_wall","stone_wall","stone_wall"],
                ["stone_wall","stone_wall","stone_wall","stone_wall","stone_wall","stone_wall","alt_floor","alt_floor","alt_floor","stone_wall","stone_wall","stone_wall","stone_wall","stone_wall","stone_wall"],
            ],
            "new_tiles": [
                {
                    "id": "alt_floor",
                    "walkable": True,
                    "tags": ["dungeon", "floor", "worn", "stone"],
                    "colors": {"base": "#3a3a3a", "alt": "#2a2a2a", "crack": "#222222"},
                    "operations": [
                        {"op": "fill", "color": "base"},
                        {"op": "noise", "color": "alt", "density": 0.4},
                        {"op": "pixels", "pixels": [["crack",3,7],["crack",10,4],["crack",6,12],["crack",13,9]]},
                    ],
                },
                {
                    "id": "alt_wall",
                    "walkable": False,
                    "tags": ["dungeon", "wall", "decorative", "stone"],
                    "colors": {"base": "#4a4040", "alt": "#332a2a", "mortar": "#2a2222"},
                    "operations": [
                        {"op": "fill", "color": "base"},
                        {"op": "bricks"},
                        {"op": "noise", "color": "mortar", "density": 0.15},
                    ],
                },
            ],
            "new_monsters": [
                {
                    "kind": "cave_creeper",
                    "tags": ["dungeon", "melee", "fast", "beast"],
                    "stats": {"hp": 3, "hop_interval": 1.2, "damage": 1},
                    "sprite": {
                        "colors": {"body": "#6a5a4a", "dark": "#3a2a1a", "eyes": "#ccff44", "legs": "#554433"},
                        "frames": [
                            [
                                ["dark",  3,11,10, 3],
                                ["body",  3, 6,10, 6],
                                ["body",  4, 5, 8, 1],
                                ["legs",  2, 9, 2, 5],
                                ["legs", 12, 9, 2, 5],
                                ["eyes",  5, 7, 2, 1],
                                ["eyes",  9, 7, 2, 1],
                            ],
                            [
                                ["dark",  4,12, 8, 2],
                                ["body",  4, 4, 8,10],
                                ["body",  5, 3, 6, 1],
                                ["legs",  3,10, 2, 4],
                                ["legs", 11,10, 2, 4],
                                ["eyes",  6, 5, 2, 1],
                                ["eyes",  9, 5, 2, 1],
                            ],
                        ],
                    },
                    "behavior": {
                        "rules": [
                            {"if": "hp_below_pct", "value": 30, "do": "flee"},
                            {"if": "can_attack", "do": "attack"},
                            {"if": "player_within", "range": 5, "do": "chase"},
                            {"default": "wander"},
                        ],
                        "attacks": [
                            {"type": "melee", "range": 1, "damage": 1, "cooldown": 2.0},
                        ],
                    },
                },
                {
                    "kind": "tunnel_spitter",
                    "tags": ["dungeon", "ranged", "slow"],
                    "stats": {"hp": 2, "hop_interval": 1.8, "damage": 1},
                    "sprite": {
                        "colors": {"shell": "#5a5a5a", "dark": "#333333", "eye": "#88aaff", "mouth": "#aa3333", "glow": "#6688cc"},
                        "frames": [
                            [
                                ["dark",  4,10, 8, 4],
                                ["shell", 4, 4, 8, 8],
                                ["shell", 5, 3, 6, 1],
                                ["eye",   6, 5, 2, 2],
                                ["eye",   9, 5, 2, 2],
                                ["mouth", 6, 8, 4, 2],
                                ["glow",  7, 9, 2, 1],
                            ],
                            [
                                ["dark",  4,10, 8, 4],
                                ["shell", 3, 5,10, 7],
                                ["shell", 4, 4, 8, 1],
                                ["eye",   5, 6, 3, 2],
                                ["eye",   9, 6, 3, 2],
                                ["mouth", 6, 9, 4, 3],
                                ["glow",  7,10, 2, 2],
                            ],
                        ],
                    },
                    "behavior": {
                        "rules": [
                            {"if": "can_attack", "do": "attack"},
                            {"if": "player_within", "range": 2, "do": "flee"},
                            {"default": "hold"},
                        ],
                        "attacks": [
                            {"type": "projectile", "range": 6, "damage": 2, "cooldown": 3.0, "sprite_color": "#6688cc"},
                        ],
                    },
                },
            ],
            "monster_placements": [
                {"kind": "cave_creeper", "x": 3, "y": 3},
                {"kind": "cave_creeper", "x": 11, "y": 8},
                {"kind": "tunnel_spitter", "x": 9, "y": 5},
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

        if y < 0 or y > 10 or x < 0 or x > 14:
            reason = "out_of_bounds"
        else:
            reason = "non-walkable" if tilemap[y][x] not in walkable else "unreachable"

        # Find nearest reachable tile (BFS from original position)
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

    # Find the dominant walkable tile to use for carving (instead of hardcoded "DF")
    walkable_counts = {}
    for row in tilemap:
        for cell in row:
            if cell in walkable:
                walkable_counts[cell] = walkable_counts.get(cell, 0) + 1
    carve_tile = max(walkable_counts, key=walkable_counts.get) if walkable_counts else "DF"

    unreachable = [(r, c) for r, c in doorways if (r, c) not in reachable]

    if not unreachable:
        return patches

    # For each unreachable doorway, BFS from it through ALL tiles to find
    # nearest reachable tile, then carve the path
    for dr, dc in unreachable:
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
                    tilemap[r][c] = carve_tile
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
    walkable_for_doorway = {"DF"} | new_walkable_tiles | existing_walkable_tiles
    if len(tilemap) == 11 and all(isinstance(r, list) and len(r) == 15 for r in tilemap):
        # Top/bottom rows: cols 0-5 and 9-14 = non-walkable, cols 6-8 = walkable
        for row_idx in (0, 10):
            for col_idx in range(15):
                actual = tilemap[row_idx][col_idx]
                if 6 <= col_idx <= 8:
                    if actual not in walkable_for_doorway:
                        errors.append(f"tilemap[{row_idx}][{col_idx}] must be walkable (doorway), got {actual!r}")
                else:
                    if actual in walkable_for_doorway:
                        errors.append(f"tilemap[{row_idx}][{col_idx}] must be non-walkable (border), got {actual!r}")
        # Left/right columns: rows 0-3 and 7-10 = non-walkable, rows 4-6 = walkable
        for col_idx in (0, 14):
            for row_idx in range(11):
                actual = tilemap[row_idx][col_idx]
                if 4 <= row_idx <= 6:
                    if actual not in walkable_for_doorway:
                        errors.append(f"tilemap[{row_idx}][{col_idx}] must be walkable (doorway), got {actual!r}")
                else:
                    if actual in walkable_for_doorway:
                        errors.append(f"tilemap[{row_idx}][{col_idx}] must be non-walkable (border), got {actual!r}")

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
                    walkable_tiles = {"DF"} | new_walkable_tiles | existing_walkable_tiles
                    if tile_at not in walkable_tiles:
                        errors.append(f"monster_placements[{pi}] at ({ix},{iy}) is on non-walkable tile {tile_at!r}")

    # Cap total errors to avoid huge retry prompts
    if len(errors) > 15:
        errors = errors[:15] + [f"... and {len(errors) - 15} more errors"]

    return errors


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------

_PROMPT_DIR = Path(__file__).parent / "tmp_prompts"


def _dump_text(text: str, prefix: str, label: str = "") -> str:
    """Save text to a timestamped file in tmp_prompts/. Returns the filename."""
    from datetime import datetime
    _PROMPT_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{ts}.txt"
    filepath = _PROMPT_DIR / filename
    filepath.write_text(text, encoding="utf-8")
    suffix = f" ({label})" if label else ""
    print(f"[GEN] Saved {filepath.name}{suffix}")
    return filename


def _dump_ai_output(raw_text: str, label: str = "failed") -> str:
    """Save raw AI output for debugging."""
    return _dump_text(raw_text, "response", label)


def _dump_prompt(system: str, messages: list, label: str = "") -> str:
    """Save the full prompt (system + messages) for debugging."""
    parts = [f"=== SYSTEM PROMPT ===\n{system}\n"]
    for msg in messages:
        parts.append(f"=== {msg['role'].upper()} ===\n{msg['content']}\n")
    return _dump_text("\n".join(parts), "prompt", label)


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


async def _call_cli(system_prompt: str, messages: list[dict]) -> str:
    """Call the local Claude CLI and return the raw text response.

    Builds a single prompt from system + messages and invokes:
      claude -p "..." --output-format json
    """
    import subprocess

    # Build a combined prompt: system instructions + conversation
    parts = [system_prompt, ""]
    for msg in messages:
        if msg["role"] == "user":
            parts.append(f"User: {msg['content']}")
        else:
            parts.append(f"Assistant: {msg['content']}")
    combined_prompt = "\n\n".join(parts)

    print(f"[GEN] Calling Claude CLI ({len(combined_prompt)} chars)...")

    # Build a clean env without CLAUDECODE to avoid nested-session detection
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    proc = await asyncio.wait_for(
        asyncio.get_running_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                ["claude", "-p", combined_prompt, "--output-format", "json", "--model", ANTHROPIC_MODEL],
                capture_output=True, text=True, timeout=int(CLI_TIMEOUT),
                env=env,
            )
        ),
        timeout=CLI_TIMEOUT + 5,
    )

    if proc.returncode != 0:
        raise RuntimeError(f"Claude CLI exited with code {proc.returncode}: {proc.stderr[:500]}")

    # CLI with --output-format json returns {"type":"result", "result":"...", "usage":{...}, ...}
    try:
        cli_output = json.loads(proc.stdout)
    except json.JSONDecodeError:
        # Fallback: raw stdout is the response text
        return proc.stdout

    # Extract token usage for tracking
    usage = cli_output.get("usage", {})
    input_tokens = usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)
    if input_tokens or output_tokens:
        print(f"[GEN] CLI tokens: {input_tokens} in + {output_tokens} out (cost: ${cli_output.get('total_cost_usd', 0):.4f})")
        usage_tracker.record(input_tokens, output_tokens)

    return cli_output.get("result", proc.stdout)


# Module-level instances
rate_limiter = RateLimiter()
usage_tracker = UsageTracker()


def init():
    """Load persisted usage data on startup."""
    usage_tracker.load()
    print(f"[GEN] Backend: {AI_BACKEND}" + (" (Claude CLI — uses subscription)" if AI_BACKEND == "cli" else " (Anthropic API)"))


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
    if AI_BACKEND == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
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
        input_tokens = output_tokens = 0
        prompt = _build_prompt(
            theme, difficulty,
            existing_monsters, existing_tiles,
            monster_library_full, tile_library_full,
            validation_error=validation_error,
            existing_room_names=existing_room_names,
        )

        messages = (FEW_SHOT_EXAMPLES if USE_FEW_SHOT else []) + [{"role": "user", "content": prompt}]

        # Dump the prompt for debugging
        _dump_prompt(SYSTEM_PROMPT, messages, f"attempt {attempt + 1}")

        raw_text = None  # captured for debug dump on failure
        try:
            rate_limiter.record_call()
            start_time = time.time()

            if AI_BACKEND == "cli":
                # Shell out to local Claude CLI (uses subscription)
                raw_text = await _call_cli(SYSTEM_PROMPT, messages)
                raw_text = raw_text.strip()
                elapsed = time.time() - start_time
                print(f"[GEN] CLI responded in {elapsed:.1f}s ({len(raw_text)} chars)")
            else:
                # Use Anthropic SDK (API key + pay-per-token)
                client = _get_client()
                response = await asyncio.wait_for(
                    asyncio.get_running_loop().run_in_executor(
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

            # Always dump for debugging
            _dump_ai_output(raw_text, "raw response")

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
            token_info = f"{input_tokens}+{output_tokens} tokens, " if AI_BACKEND == "api" else ""
            print(f"[GEN] Try {attempt + 1}/{total_attempts} SUCCESS — \"{data.get('name', '?')}\" "
                  f"({elapsed:.1f}s, {token_info}"
                  f"{len(data.get('new_monsters', []))} new monsters, "
                  f"{len(data.get('new_tiles', []))} new tiles)")
            return data

        except asyncio.TimeoutError:
            timeout_val = CLI_TIMEOUT if AI_BACKEND == "cli" else GENERATION_TIMEOUT
            print(f"[GEN] Try {attempt + 1}/{total_attempts} FAILED — timeout after {timeout_val}s")
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
