"""
AI Room Generator — Claude integration for procedural dungeon content.

Generates dungeon rooms via multiple focused AI calls:
  1. generate_monster_sprite() — kind, tags, stats, sprite frames
  2. generate_monster_behavior() — behavior rules + attacks
  3. generate_tiles() — custom tile definitions
  4. generate_layout() — room name + tilemap + monster placements

The orchestrator generate_room() rolls for 0-2 new monsters and 0-2 new
tiles (based on library fullness + random chance), generates them first,
then calls generate_layout() with the full inventory — flagging newly
created content as preferred.
"""

import json
import os
import random
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
MAX_API_CALLS_PER_MINUTE = 15   # higher limit: one room = multiple calls
MAX_API_CALLS_PER_DAY = 600
MAX_RETRIES = 1                 # single retry on validation failure per step

# Backend: "api" uses Anthropic SDK (needs ANTHROPIC_API_KEY),
#          "cli" shells out to local `claude` CLI (uses your subscription)
AI_BACKEND = os.environ.get("AI_BACKEND", "cli").lower()

DATA_DIR = Path(__file__).parent.parent / "data"

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
        if now - self._day_start > 86400:
            self._day_count = 0
            self._day_start = now
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
# Module-level instances
# ---------------------------------------------------------------------------

rate_limiter = RateLimiter()
usage_tracker = UsageTracker()


# ---------------------------------------------------------------------------
# System prompts — one per generation step
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_MONSTER_DESIGN = """You are a monster designer for a Zelda-style top-down MUD game.
You create a single monster: its name, tags, stats, and behavior (AI rules + attacks).
You do NOT create the sprite — that is a separate step.

## STATS
- hp: hit points (1-100)
- hop_interval: seconds between movement hops (0.2-10.0). Lower = faster
- damage: contact damage when the monster touches a player (1-20)

## BEHAVIOR RULES
Rules are evaluated top-to-bottom, first match wins. Put urgent conditions first (low HP → flee), then combat (can_attack → attack), then approach (player_within → chase), then default.

Conditions with their parameter name:
- player_within: "range" (tiles)
- player_beyond: "range" (tiles)
- hp_below_pct: "value" (0-100)
- hp_above_pct: "value" (0-100)
- random_chance: "value" (0-100, percent chance)
- can_attack: (no param — true when any attack is off cooldown and player in range)
- player_in_attack_range: (no param)
- default: (no param, always matches — use for the last rule)

Actions: wander, chase, flee, patrol, hold, attack

## ATTACK TYPES
Attacks are tried in array order — first usable attack fires. Put preferred/ranged attacks first, close-range fallbacks last.

Attack types and their extra fields:
- melee: range MUST be 1, strikes adjacent player
- projectile: range 1-10 (travel distance), requires "sprite_color": "#RRGGBB"
- charge: range 2-6 (dash distance), 2-tick windup with warning
- teleport: range 1-8 (max teleport distance), requires "delay": 0.2-3.0
- area: range 1-4 (AoE radius), requires "warning_duration": 0.3-3.0
All attacks need: "type", "range", "damage" (1-20), "cooldown" (0.5-30.0 seconds)

`stats.damage` is **contact damage** when the monster touches a player. `attacks[].damage` is separate per-attack damage. Both can coexist.

## DIFFICULTY GUIDELINES
- Easy (1-3): hp 1-2, damage 1, hop_interval 1.5-2.5, no attacks, just wander
- Medium (4-6): hp 2-4, damage 1-2, hop_interval 1.0-1.8, 1 simple attack (melee or projectile)
- Hard (7-9): hp 3-6, damage 2-3, hop_interval 0.6-1.2, 1-2 varied attacks, interesting behavior rules
- Boss (10): hp 6-10, damage 3-4, hop_interval 0.8-1.5, 2-3 attack types, complex behavior

## RESPONSE FORMAT
Return ONLY valid JSON (no markdown, no explanation):
```
{
  "kind": "lowercase_snake_case_name",
  "tags": ["fire", "melee", "beast"],
  "stats": {"hp": 2, "hop_interval": 1.2, "damage": 1},
  "behavior": {
    "rules": [
      {"if": "hp_below_pct", "value": 30, "do": "flee"},
      {"if": "can_attack", "do": "attack"},
      {"if": "player_within", "range": 4, "do": "chase"},
      {"default": "wander"}
    ],
    "attacks": [
      {"type": "melee", "range": 1, "damage": 1, "cooldown": 2.0}
    ]
  }
}
```

## RULES
1. kind MUST be lowercase_snake_case [a-z][a-z0-9_]*
2. Give monsters thematic names (fire_imp, frost_archer, shadow_wraith — not monster_1)
3. Use 3-5 tags per monster
4. Design interesting, varied behavior — not just "chase and hit" """

SYSTEM_PROMPT_MONSTER_SPRITE = """You are a pixel artist for a Zelda-style top-down MUD game.
Given a monster's name, tags, and attack types, you create its animated pixel sprite.

## SPRITE FORMAT
Sprite grid is 16x16. Each layer is [colorKey, x, y, w, h] where x+w<=16, y+h<=16.
Layers render in array order — first layer is the back, last layer is the front.
Put shadows/bases first, details/eyes last.

Sprites need 2-4 frames showing interesting animation: stretching, pulsing, limb movement, shape changes, eye blinks, wing flaps, etc. Each frame should have meaningfully different shapes/positions — NOT just a y-offset hop.
Good examples: a slime that squishes wide (x=3,w=10,y=8) then stretches tall (x=4,w=8,y=4); a bat whose wings go from up (y=3) to down (y=7) with completely different wing positions.

Use 3-6 color keys per sprite. Build recognizable silhouettes with 5-12 layers per frame.
Tips: place eyes near the top third, use a dark color for the base/shadow, make the shape asymmetric or distinctive.

## RESPONSE FORMAT
Return ONLY valid JSON (no markdown, no explanation):
```
{
  "sprite": {
    "colors": {"body": "#cc3300", "eyes": "#ffcc00", "shadow": "#331100"},
    "frames": [
      [["shadow", 4, 12, 8, 3], ["body", 5, 4, 6, 9], ["eyes", 6, 6, 2, 1]],
      [["shadow", 4, 12, 8, 3], ["body", 5, 3, 6, 10], ["eyes", 6, 5, 2, 1]]
    ]
  }
}
```

## RULES
1. Sprite colors should be thematically appropriate and visually distinct
2. The sprite should visually match the monster's concept — a ranged caster should look different from a melee brute
3. Make the silhouette recognizable and distinct from other monsters"""

SYSTEM_PROMPT_TILES = """You are a tile designer for a Zelda-style top-down MUD game.
You create custom tile definitions for dungeon rooms.

## TILE FORMAT
Tile grid is 16x16. Operations execute in order. Start with "fill" for base color.

The "walkable" field is REQUIRED — it determines if players/monsters can walk on this tile.

IMPORTANT: The "base" and "alt" color keys have special roles:
- "base" is used as the automatic background fill
- "alt" is used by bricks, grid_lines, hstripes, vstripes, wave, and ripple as their drawing color
- You MUST define both "base" and "alt" in your colors dict if you use any of those operations

## AVAILABLE OPERATIONS
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
Return ONLY valid JSON (no markdown, no explanation):
```
{
  "tiles": [
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
  ]
}
```

## RULES
1. IDs MUST be lowercase_snake_case [a-z][a-z0-9_]*
2. Use 3-5 tags per tile
3. Each tile MUST have a "walkable" boolean
4. Create visually distinct tiles that fit the requested theme"""

SYSTEM_PROMPT_LAYOUT = """You are a dungeon room layout designer for a Zelda-style top-down MUD game.
You create room layouts (tilemaps + monster placements) using available tiles and monsters.

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
- Use a MIX of available tiles. Pick a dominant walkable tile for most floors and a dominant non-walkable tile for most interior walls. Scatter other tile types for variety

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

## DIFFICULTY GUIDELINES (monster count)
- Easy (1-3): 1-2 monsters
- Medium (4-6): 2-4 monsters
- Hard (7-9): 3-5 monsters
- Boss (10): 1 boss + 2-3 fodder

## RESPONSE FORMAT
Return ONLY valid JSON (no markdown, no explanation):
```
{
  "name": "Room Name",
  "tilemap": [
    ["DW","DW","DW","DW","DW","DW","DF","DF","DF","DW","DW","DW","DW","DW","DW"],
    ...11 rows total, 15 columns each...
  ],
  "monster_placements": [
    {"kind": "monster_name", "x": 5, "y": 3}
  ]
}
```

## RULES
1. All tile codes in the tilemap must be from the available tiles list
2. All monster kinds in monster_placements must be from the available monsters list
3. Place monsters only on walkable tiles, in the interior (rows 2-9, cols 2-13)
4. Monster x must be 0-14, y must be 0-10
5. Room names should be evocative and unique (2-3 words)
6. All IDs MUST be lowercase_snake_case [a-z][a-z0-9_]*"""


# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

BUILTIN_TILES = {"DW", "DF", "PL", "SC"}
NON_WALKABLE = {"DW", "PL", "SC"}

VALID_BEHAVIOR_CONDITIONS = {
    "player_within", "player_beyond", "hp_below_pct", "hp_above_pct",
    "random_chance", "always", "default", "can_attack", "player_in_attack_range",
}
VALID_BEHAVIOR_ACTIONS = {"wander", "chase", "flee", "patrol", "hold", "attack"}
VALID_ATTACK_TYPES = {"melee", "projectile", "charge", "teleport", "area"}
VALID_TILE_OPS = {"fill", "noise", "bricks", "grid_lines", "hstripes", "vstripes",
                  "wave", "ripple", "rects", "pixels"}

_BUILTIN_KINDS = {"slime", "bat", "scorpion", "skeleton", "swamp_blob"}


def _is_hex_color(v: str) -> bool:
    return isinstance(v, str) and bool(_re.match(r'^#[0-9a-fA-F]{6}$', v))


# ---------------------------------------------------------------------------
# Focused validators
# ---------------------------------------------------------------------------

def validate_tile_definition(tile: dict, index: int = 0) -> list[str]:
    """Validate a single custom tile definition. Returns list of errors."""
    errors = []
    prefix = f"tile[{index}]"

    if not isinstance(tile, dict):
        return [f"{prefix} must be a dict"]

    tid = tile.get("id")
    if not isinstance(tid, str) or not _re.match(r'^[a-z][a-z0-9_]*$', tid):
        errors.append(f"{prefix}.id must be lowercase_snake_case")

    walkable = tile.get("walkable")
    if walkable is not None and not isinstance(walkable, bool):
        errors.append(f"{prefix}.walkable must be a boolean")

    colors = tile.get("colors")
    if not isinstance(colors, dict):
        errors.append(f"{prefix}.colors must be a dict")
    else:
        for k, v in colors.items():
            if not _is_hex_color(v):
                errors.append(f"{prefix}.colors.{k} invalid hex: {v!r}")

    ops = tile.get("operations")
    if not isinstance(ops, list) or len(ops) < 1:
        errors.append(f"{prefix}.operations must be non-empty list")
    else:
        for oi, op in enumerate(ops):
            if not isinstance(op, dict):
                continue
            if op.get("op") not in VALID_TILE_OPS:
                errors.append(f"{prefix}.ops[{oi}] unknown op: {op.get('op')}")
            if op.get("op") == "rects":
                for ri, rect in enumerate(op.get("rects", [])):
                    if isinstance(rect, list) and len(rect) == 5:
                        _, x, y, w, h = rect
                        if any(not isinstance(v, (int, float)) for v in (x, y, w, h)):
                            errors.append(f"{prefix}.ops[{oi}].rects[{ri}] coords must be numbers")
                        elif x < 0 or y < 0 or x + w > 16 or y + h > 16:
                            errors.append(f"{prefix}.ops[{oi}].rects[{ri}] out of bounds")
            if op.get("op") == "pixels":
                for pi, px in enumerate(op.get("pixels", [])):
                    if isinstance(px, list) and len(px) == 3:
                        _, x, y = px
                        if x < 0 or x > 15 or y < 0 or y > 15:
                            errors.append(f"{prefix}.ops[{oi}].pixels[{pi}] out of bounds")
    return errors


def validate_monster_design(monster: dict, index: int = 0) -> list[str]:
    """Validate a monster's kind, tags, stats, and behavior. Returns errors."""
    errors = []
    prefix = f"monster[{index}]"

    if not isinstance(monster, dict):
        return [f"{prefix} must be a dict"]

    kind = monster.get("kind")
    if not isinstance(kind, str) or not _re.match(r'^[a-z][a-z0-9_]*$', kind):
        errors.append(f"{prefix}.kind must be lowercase_snake_case")

    # Stats
    stats = monster.get("stats")
    if not isinstance(stats, dict):
        errors.append(f"{prefix}.stats must be a dict")
    else:
        hp = stats.get("hp")
        if not isinstance(hp, (int, float)) or hp < 1 or hp > 100:
            errors.append(f"{prefix}.stats.hp must be 1-100")
        hop = stats.get("hop_interval")
        if not isinstance(hop, (int, float)) or hop < 0.2 or hop > 10.0:
            errors.append(f"{prefix}.stats.hop_interval must be 0.2-10.0")
        dmg = stats.get("damage")
        if not isinstance(dmg, (int, float)) or dmg < 1 or dmg > 20:
            errors.append(f"{prefix}.stats.damage must be 1-20")

    # Behavior
    behavior = monster.get("behavior")
    if behavior is not None:
        errors.extend(validate_monster_behavior(behavior))

    return errors


def validate_monster_sprite(sprite_data: dict) -> list[str]:
    """Validate a sprite-only response: {"sprite": {colors, frames}}. Returns errors."""
    errors = []

    sprite = sprite_data.get("sprite")
    if not isinstance(sprite, dict):
        return ["sprite must be a dict"]

    colors = sprite.get("colors")
    if not isinstance(colors, dict):
        errors.append("sprite.colors must be a dict")
    else:
        for k, v in colors.items():
            if not _is_hex_color(v):
                errors.append(f"sprite.colors.{k} invalid: {v!r}")

    frames = sprite.get("frames")
    if not isinstance(frames, list) or len(frames) < 1:
        errors.append("sprite.frames must be non-empty")
    else:
        for fi, frame in enumerate(frames):
            if not isinstance(frame, list):
                continue
            for li, layer in enumerate(frame):
                if not isinstance(layer, list) or len(layer) != 5:
                    errors.append(f"sprite.frames[{fi}][{li}] must be [colorKey, x, y, w, h]")
                    continue
                _, x, y, w, h = layer
                if not all(isinstance(v, (int, float)) for v in (x, y, w, h)):
                    errors.append(f"sprite.frames[{fi}][{li}] coords must be numbers")
                elif x < 0 or y < 0 or x + w > 16 or y + h > 16:
                    errors.append(f"sprite.frames[{fi}][{li}] out of 16x16 bounds")
    return errors


def validate_monster_behavior(behavior: dict) -> list[str]:
    """Validate a monster's behavior rules and attacks. Returns errors."""
    errors = []

    if not isinstance(behavior, dict):
        return ["behavior must be a dict"]

    rules = behavior.get("rules", [])
    for ri, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        cond = rule.get("if") or (rule.get("default") and "default")
        if cond and cond not in VALID_BEHAVIOR_CONDITIONS:
            errors.append(f"behavior.rules[{ri}] unknown condition: {cond}")
        action = rule.get("do") or (rule.get("default") if "default" in rule else None)
        if isinstance(action, str) and action not in VALID_BEHAVIOR_ACTIONS:
            errors.append(f"behavior.rules[{ri}] unknown action: {action}")

    attacks = behavior.get("attacks", [])
    for ai, atk in enumerate(attacks):
        if not isinstance(atk, dict):
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

    return errors


def validate_layout(data: dict, valid_tile_ids: set[str],
                    walkable_tiles: set[str],
                    valid_monster_kinds: set[str]) -> list[str]:
    """Validate room layout: tilemap, doorways, monster placements. Returns errors."""
    errors = []

    # -- name --
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("name must be a non-empty string")

    # -- tilemap --
    tilemap = data.get("tilemap")
    if not isinstance(tilemap, list) or len(tilemap) != 11:
        errors.append(f"tilemap must be 11 rows, got {len(tilemap) if isinstance(tilemap, list) else 'non-list'}")
        return errors

    for row_idx, row in enumerate(tilemap):
        if not isinstance(row, list) or len(row) != 15:
            errors.append(f"tilemap[{row_idx}] must be 15 columns, got {len(row) if isinstance(row, list) else 'non-list'}")
            continue
        for col_idx, tile in enumerate(row):
            if tile not in valid_tile_ids:
                errors.append(f"tilemap[{row_idx}][{col_idx}] unknown tile: {tile!r}")

    if not all(isinstance(r, list) and len(r) == 15 for r in tilemap):
        return errors

    # Doorway constraints
    for row_idx in (0, 10):
        for col_idx in range(15):
            actual = tilemap[row_idx][col_idx]
            if 6 <= col_idx <= 8:
                if actual not in walkable_tiles:
                    errors.append(f"tilemap[{row_idx}][{col_idx}] must be walkable (doorway), got {actual!r}")
            else:
                if actual in walkable_tiles:
                    errors.append(f"tilemap[{row_idx}][{col_idx}] must be non-walkable (border), got {actual!r}")
    for col_idx in (0, 14):
        for row_idx in range(11):
            actual = tilemap[row_idx][col_idx]
            if 4 <= row_idx <= 6:
                if actual not in walkable_tiles:
                    errors.append(f"tilemap[{row_idx}][{col_idx}] must be walkable (doorway), got {actual!r}")
            else:
                if actual in walkable_tiles:
                    errors.append(f"tilemap[{row_idx}][{col_idx}] must be non-walkable (border), got {actual!r}")

    # Doorway reachability (flood fill)
    doorways = []
    for c in range(6, 9):
        doorways.append((0, c))
        doorways.append((10, c))
    for r in range(4, 7):
        doorways.append((r, 0))
        doorways.append((r, 14))

    visited = set()
    stack = [doorways[0]]
    while stack:
        row, col = stack.pop()
        if (row, col) in visited:
            continue
        if row < 0 or row > 10 or col < 0 or col > 14:
            continue
        if tilemap[row][col] not in walkable_tiles:
            continue
        visited.add((row, col))
        stack.extend([(row-1, col), (row+1, col), (row, col-1), (row, col+1)])

    unreachable = [f"({r},{c})" for r, c in doorways if (r, c) not in visited]
    if unreachable:
        errors.append(f"Doorways not connected — unreachable: {', '.join(unreachable)}")

    # -- monster_placements --
    placements = data.get("monster_placements", [])
    if not isinstance(placements, list):
        errors.append("monster_placements must be a list")
    else:
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
            if (isinstance(x, (int, float)) and isinstance(y, (int, float))):
                ix, iy = int(x), int(y)
                if 0 <= iy < 11 and 0 <= ix < 15:
                    tile_at = tilemap[iy][ix]
                    if tile_at not in walkable_tiles:
                        errors.append(f"monster_placements[{pi}] at ({ix},{iy}) is on non-walkable tile {tile_at!r}")
            k = p.get("kind")
            if k and k not in valid_monster_kinds:
                errors.append(f"monster_placements[{pi}].kind {k!r} not in available monsters")

    if len(errors) > 15:
        errors = errors[:15] + [f"... and {len(errors) - 15} more errors"]

    return errors


def validate_room_response(data: dict, existing_tile_ids: set[str] | None = None,
                           existing_walkable_tiles: set[str] | None = None) -> list[str]:
    """Validate a complete room response (backward compatibility wrapper).
    Returns list of error strings."""
    existing_tile_ids = existing_tile_ids or set()
    existing_walkable_tiles = existing_walkable_tiles or set()

    errors = []

    # Validate new tiles
    new_tile_ids = set()
    new_walkable = set()
    for ti, tile in enumerate(data.get("new_tiles", [])):
        errors.extend(validate_tile_definition(tile, ti))
        if isinstance(tile, dict) and isinstance(tile.get("id"), str):
            new_tile_ids.add(tile["id"])
            if tile.get("walkable", False):
                new_walkable.add(tile["id"])

    # Validate new monsters (design + sprite)
    for mi, mon in enumerate(data.get("new_monsters", [])):
        errors.extend(validate_monster_design(mon, mi))
        if isinstance(mon, dict) and isinstance(mon.get("sprite"), dict):
            errors.extend(validate_monster_sprite(mon))

    # Validate layout
    all_tile_ids = BUILTIN_TILES | new_tile_ids | existing_tile_ids
    all_walkable = {"DF"} | new_walkable | existing_walkable_tiles

    existing_kinds = set()  # caller would need to pass these for full validation
    new_kinds = set()
    for m in data.get("new_monsters", []):
        if isinstance(m, dict) and isinstance(m.get("kind"), str):
            new_kinds.add(m["kind"])
    all_kinds = existing_kinds | new_kinds | _BUILTIN_KINDS

    errors.extend(validate_layout(data, all_tile_ids, all_walkable, all_kinds))

    return errors


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


def patch_monster_placements(data: dict, walkable: set[str]) -> list[str]:
    """Move monsters to reachable walkable tiles (connected to doorways).
    Returns list of patch descriptions."""
    patches = []
    tilemap = data.get("tilemap")
    placements = data.get("monster_placements")
    if not tilemap or not placements or len(tilemap) != 11:
        return patches
    if not all(isinstance(r, list) and len(r) == 15 for r in tilemap):
        return patches

    # Flood fill from north doorway to find reachable walkable tiles
    reachable = set()
    stack = [(0, 7)]
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

    data["monster_placements"] = [p for p in placements if p is not None]
    return patches


def patch_unreachable_doorways(data: dict, walkable: set[str]) -> list[str]:
    """Carve walkable paths to connect unreachable doorways.
    Returns list of patch descriptions."""
    patches = []
    tilemap = data.get("tilemap")
    if not tilemap or len(tilemap) != 11:
        return patches
    if not all(isinstance(r, list) and len(r) == 15 for r in tilemap):
        return patches

    doorways = []
    for c in range(6, 9):
        doorways.append((0, c))
        doorways.append((10, c))
    for r in range(4, 7):
        doorways.append((r, 0))
        doorways.append((r, 14))

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

    # Find dominant walkable tile for carving
    walkable_counts = {}
    for row in tilemap:
        for cell in row:
            if cell in walkable:
                walkable_counts[cell] = walkable_counts.get(cell, 0) + 1
    carve_tile = max(walkable_counts, key=walkable_counts.get) if walkable_counts else "DF"

    unreachable = [(r, c) for r, c in doorways if (r, c) not in reachable]
    if not unreachable:
        return patches

    for dr, dc in unreachable:
        visited_bfs = {}
        queue = deque([(dr, dc, None)])
        target = None

        while queue:
            r, c, parent = queue.popleft()
            if (r, c) in visited_bfs:
                continue
            if r < 0 or r > 10 or c < 0 or c > 14:
                continue
            visited_bfs[(r, c)] = parent
            if (r, c) in reachable:
                target = (r, c)
                break
            for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                queue.append((r+dy, c+dx, (r, c)))

        if target:
            carved = []
            pos = target
            while pos is not None:
                r, c = pos
                if tilemap[r][c] not in walkable:
                    tilemap[r][c] = carve_tile
                    carved.append(f"({c},{r})")
                pos = visited_bfs.get(pos)
            if carved:
                patches.append(f"Carved path to doorway ({dc},{dr}): {', '.join(carved)}")
                reachable = flood_fill()

    return patches


def patch_duplicate_name(data: dict, existing_names: list[str]) -> list[str]:
    """Append roman numeral suffix if room name is already taken."""
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
    suffix = random.randint(100, 999)
    data["name"] = f"{name} #{suffix}"
    return [f"Renamed \"{name}\" to \"{data['name']}\" (duplicate)"]


def patch_monster_attacks(behavior: dict) -> list[str]:
    """Clamp out-of-range attack stats to valid bounds."""
    patches = []
    for ai, atk in enumerate(behavior.get("attacks", [])):
        if not isinstance(atk, dict):
            continue
        cd = atk.get("cooldown")
        if isinstance(cd, (int, float)) and (cd < 0.5 or cd > 30.0):
            clamped = max(0.5, min(30.0, cd))
            patches.append(f"Clamped attack[{ai}] cooldown {cd} -> {clamped}")
            atk["cooldown"] = clamped
        rng = atk.get("range")
        if isinstance(rng, (int, float)) and (rng < 1 or rng > 15):
            clamped = max(1, min(15, int(rng)))
            patches.append(f"Clamped attack[{ai}] range {rng} -> {clamped}")
            atk["range"] = clamped
    return patches


def auto_patch(data: dict, existing_walkable: set[str],
               existing_room_names: list[str] | None = None) -> list[str]:
    """Apply all auto-patches to a complete room. Backward compat wrapper."""
    walkable = _build_walkability_set(data, existing_walkable)
    patches = []
    patches.extend(patch_duplicate_name(data, existing_room_names or []))
    patches.extend(patch_unreachable_doorways(data, walkable))
    patches.extend(patch_monster_placements(data, walkable))
    for m in data.get("new_monsters", []):
        if isinstance(m, dict) and isinstance(m.get("behavior"), dict):
            patches.extend(patch_monster_attacks(m["behavior"]))
    return patches


# ---------------------------------------------------------------------------
# Debug helpers
# ---------------------------------------------------------------------------

_PROMPT_DIR = Path(__file__).parent.parent / "tmp_prompts"


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
    return _dump_text(raw_text, "response", label)


def _dump_prompt(system: str, user_prompt: str, label: str = "") -> str:
    parts = [f"=== SYSTEM PROMPT ===\n{system}\n",
             f"=== USER ===\n{user_prompt}\n"]
    return _dump_text("\n".join(parts), "prompt", label)


# ---------------------------------------------------------------------------
# Backend callers (API + CLI)
# ---------------------------------------------------------------------------

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


async def _call_cli(system_prompt: str, user_prompt: str) -> tuple[str, int, int]:
    """Call the local Claude CLI. Returns (response_text, input_tokens, output_tokens)."""
    import subprocess

    combined_prompt = f"{system_prompt}\n\nUser: {user_prompt}"

    print(f"[GEN] Calling Claude CLI ({len(combined_prompt)} chars)...")

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

    input_tokens = output_tokens = 0
    try:
        cli_output = json.loads(proc.stdout)
        usage = cli_output.get("usage", {})
        input_tokens = usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        if input_tokens or output_tokens:
            print(f"[GEN] CLI tokens: {input_tokens} in + {output_tokens} out (cost: ${cli_output.get('total_cost_usd', 0):.4f})")
        text = cli_output.get("result", proc.stdout)
    except json.JSONDecodeError:
        text = proc.stdout

    return text, input_tokens, output_tokens


async def _call_api(system_prompt: str, user_prompt: str) -> tuple[str, int, int]:
    """Call the Anthropic API. Returns (response_text, input_tokens, output_tokens)."""
    client = _get_client()
    response = await asyncio.wait_for(
        asyncio.get_running_loop().run_in_executor(
            None,
            lambda: client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        ),
        timeout=GENERATION_TIMEOUT,
    )
    return (response.content[0].text.strip(),
            response.usage.input_tokens,
            response.usage.output_tokens)


# ---------------------------------------------------------------------------
# Generic AI call helper with retry
# ---------------------------------------------------------------------------

async def _call_ai(
    system_prompt: str,
    user_prompt: str,
    validate_fn,
    patch_fn=None,
    label: str = "ai_call",
    max_retries: int = MAX_RETRIES,
) -> dict | None:
    """Make an AI call, parse JSON, validate, retry on failure.

    Args:
        system_prompt: The system prompt for this step.
        user_prompt: The user prompt for this step.
        validate_fn: callable(data) -> list[str] of errors.
        patch_fn: optional callable(data) -> list[str] of patch descriptions.
        label: label for debug output files.
        max_retries: number of retries on validation failure.

    Returns the validated dict, or None on failure.
    """
    if not rate_limiter.can_call():
        print(f"[GEN] Rate limit reached — skipping {label}")
        return None

    validation_error = None
    total_attempts = 1 + max_retries

    for attempt in range(total_attempts):
        print(f"[GEN] {label} try {attempt + 1}/{total_attempts}...")

        prompt = user_prompt
        if validation_error:
            prompt += f"\n\nYour previous response had validation errors. Fix them:\n{validation_error}"

        _dump_prompt(system_prompt, prompt, f"{label} attempt {attempt + 1}")

        raw_text = None
        try:
            rate_limiter.record_call()
            start_time = time.time()

            if AI_BACKEND == "cli":
                raw_text, input_tokens, output_tokens = await _call_cli(system_prompt, prompt)
            else:
                raw_text, input_tokens, output_tokens = await _call_api(system_prompt, prompt)

            if input_tokens or output_tokens:
                usage_tracker.record(input_tokens, output_tokens)

            elapsed = time.time() - start_time
            raw_text = raw_text.strip()
            print(f"[GEN] {label} responded in {elapsed:.1f}s ({len(raw_text)} chars)")

            # Strip markdown code fences if present
            if raw_text.startswith("```"):
                raw_lines = raw_text.split("\n")
                if raw_lines[-1].strip() == "```":
                    raw_lines = raw_lines[1:-1]
                else:
                    raw_lines = raw_lines[1:]
                raw_text = "\n".join(raw_lines)

            data = json.loads(raw_text)
            _dump_ai_output(raw_text, f"{label} raw")

            # Auto-patch
            if patch_fn:
                patch_log = patch_fn(data)
                if patch_log:
                    print(f"[GEN] {label} auto-patched {len(patch_log)} issues:")
                    for p in patch_log:
                        print(f"[GEN]   {p}")

            # Validate
            errors = validate_fn(data)
            if errors:
                validation_error = "\n".join(f"- {e}" for e in errors)
                print(f"[GEN] {label} try {attempt + 1} FAILED — {len(errors)} errors:")
                for e in errors:
                    print(f"[GEN]   {e}")
                _dump_ai_output(raw_text, f"{label} validation failed")
                if attempt < max_retries:
                    print(f"[GEN] Retrying {label}...")
                    continue
                return None

            print(f"[GEN] {label} try {attempt + 1} SUCCESS ({elapsed:.1f}s)")
            return data

        except asyncio.TimeoutError:
            timeout_val = CLI_TIMEOUT if AI_BACKEND == "cli" else GENERATION_TIMEOUT
            print(f"[GEN] {label} FAILED — timeout after {timeout_val}s")
            return None
        except json.JSONDecodeError as e:
            print(f"[GEN] {label} FAILED — parse error: {e}")
            if raw_text:
                _dump_ai_output(raw_text, f"{label} JSON parse error")
            if attempt < max_retries:
                validation_error = f"Response was not valid JSON: {e}. Return ONLY a JSON object, no markdown or explanation."
                continue
            return None
        except Exception as e:
            print(f"[GEN] {label} FAILED — {type(e).__name__}: {e}")
            if raw_text:
                _dump_ai_output(raw_text, f"{label} {type(e).__name__}")
            return None

    return None


# ---------------------------------------------------------------------------
# Step 1: Generate monster design (kind, tags, stats, behavior)
# ---------------------------------------------------------------------------

def _build_monster_design_prompt(theme: str, difficulty: int,
                                 existing_monsters: list[dict]) -> str:
    parts = [f"Create a monster for a \"{theme}\"-themed dungeon room at difficulty {difficulty}/10."]

    if existing_monsters:
        names = ", ".join(m.get("kind", "?") for m in existing_monsters[:20])
        parts.append(f"\nExisting monsters (avoid duplicating these): {names}")

    parts.append("\nDesign a unique monster with a thematic name, stats, tags, and behavior rules/attacks.")
    return "\n".join(parts)


async def generate_monster_design(
    theme: str = "dungeon",
    difficulty: int = 5,
    existing_monsters: list[dict] | None = None,
) -> dict | None:
    """Generate a monster's kind, tags, stats, and behavior. No sprite yet.

    Returns: {"kind", "tags", "stats", "behavior"} or None.
    """
    if AI_BACKEND == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[GEN] No ANTHROPIC_API_KEY set — skipping monster design generation")
        return None

    prompt = _build_monster_design_prompt(theme, difficulty, existing_monsters or [])

    def _validate(data):
        return validate_monster_design(data)

    def _patch(data):
        b = data.get("behavior")
        if isinstance(b, dict):
            return patch_monster_attacks(b)
        return []

    return await _call_ai(
        system_prompt=SYSTEM_PROMPT_MONSTER_DESIGN,
        user_prompt=prompt,
        validate_fn=_validate,
        patch_fn=_patch,
        label="monster_design",
    )


# ---------------------------------------------------------------------------
# Step 2: Generate monster sprite
# ---------------------------------------------------------------------------

def _build_monster_sprite_prompt(kind: str, tags: list[str],
                                 attack_types: list[str],
                                 theme: str) -> str:
    parts = [f"Create a pixel sprite for the monster \"{kind}\"."]
    if tags:
        parts.append(f"Tags: {', '.join(tags)}")
    if attack_types:
        parts.append(f"Attack types: {', '.join(attack_types)}")
    parts.append(f"Theme: {theme}")
    parts.append("\nDesign an animated sprite that visually fits this monster's concept.")
    return "\n".join(parts)


async def generate_monster_sprite(
    kind: str,
    tags: list[str] | None = None,
    attack_types: list[str] | None = None,
    theme: str = "dungeon",
) -> dict | None:
    """Generate a sprite for a monster, given its design context.

    Returns: {"sprite": {"colors": {...}, "frames": [...]}} or None.
    """
    if AI_BACKEND == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[GEN] No ANTHROPIC_API_KEY set — skipping monster sprite generation")
        return None

    prompt = _build_monster_sprite_prompt(kind, tags or [], attack_types or [], theme)

    return await _call_ai(
        system_prompt=SYSTEM_PROMPT_MONSTER_SPRITE,
        user_prompt=prompt,
        validate_fn=lambda d: validate_monster_sprite(d),
        label=f"monster_sprite({kind})",
    )


# ---------------------------------------------------------------------------
# Step 3: Generate tiles
# ---------------------------------------------------------------------------

def _build_tiles_prompt(theme: str, difficulty: int,
                        existing_tiles: list[dict],
                        count: int) -> str:
    parts = [f"Create {count} custom tile(s) for a \"{theme}\"-themed dungeon room at difficulty {difficulty}/10."]

    if existing_tiles:
        tile_summary = ", ".join(
            f"{t.get('id', '?')} ({'walkable' if t.get('walkable') else 'non-walkable'}, tags: {', '.join(t.get('tags', []))})"
            for t in existing_tiles[:20]
        )
        parts.append(f"\nExisting custom tiles (avoid duplicating): {tile_summary}")

    parts.append(f"\nCreate {count} new tile(s). Include at least one walkable floor tile. Make them visually distinct and thematically appropriate.")
    return "\n".join(parts)


async def generate_tiles(
    theme: str = "dungeon",
    difficulty: int = 5,
    existing_tiles: list[dict] | None = None,
    count: int = 2,
) -> list[dict] | None:
    """Generate custom tile definitions.

    Returns: list of tile dicts [{id, walkable, tags, colors, operations}], or None.
    """
    if AI_BACKEND == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[GEN] No ANTHROPIC_API_KEY set — skipping tile generation")
        return None

    prompt = _build_tiles_prompt(theme, difficulty, existing_tiles or [], count)

    def _validate(data):
        tiles = data.get("tiles")
        if not isinstance(tiles, list) or len(tiles) < 1:
            return ["response must contain a non-empty 'tiles' array"]
        errors = []
        for i, t in enumerate(tiles):
            errors.extend(validate_tile_definition(t, i))
        return errors

    result = await _call_ai(
        system_prompt=SYSTEM_PROMPT_TILES,
        user_prompt=prompt,
        validate_fn=_validate,
        label="tiles",
    )
    if result:
        return result.get("tiles", [])
    return None


# ---------------------------------------------------------------------------
# Step 4: Generate layout
# ---------------------------------------------------------------------------

def _build_layout_prompt(theme: str, difficulty: int,
                         available_tiles: list[dict],
                         available_monsters: list[dict],
                         new_tile_ids: list[str],
                         new_monster_kinds: list[str],
                         existing_room_names: list[str] | None = None) -> str:
    parts = [f"Generate a dungeon room layout with theme \"{theme}\" and difficulty {difficulty}/10."]

    if existing_room_names:
        parts.append(f"\nDo NOT reuse these room names (already taken): {', '.join(existing_room_names[:30])}")

    # Tiles
    base_tiles = [
        "DW (non-walkable, tags: dungeon, wall, stone)",
        "DF (walkable, tags: dungeon, floor, stone)",
        "PL (non-walkable, tags: dungeon, wall, decorative)",
        "SC (non-walkable, tags: dungeon, wall, light)",
    ]
    custom_tiles = [
        f"{t.get('id', '?')} ({'walkable' if t.get('walkable') else 'non-walkable'}, tags: {', '.join(t.get('tags', []))})"
        for t in available_tiles[:20]
    ]
    tile_summary = ", ".join(base_tiles + custom_tiles)
    parts.append(f"\nAvailable tiles: {tile_summary}")

    if new_tile_ids:
        parts.append(f"PREFER using these newly created tiles: {', '.join(new_tile_ids)}")

    # Monsters
    builtin_monsters = [
        "slime (tags: forest, melee)",
        "bat (tags: cave, flying)",
        "scorpion (tags: desert, melee)",
        "skeleton (tags: undead, melee)",
        "swamp_blob (tags: swamp, melee)",
    ]
    custom_monsters = [
        f"{m.get('kind', '?')} (tags: {', '.join(m.get('tags', []))})"
        for m in available_monsters[:20]
    ]
    monster_summary = ", ".join(builtin_monsters + custom_monsters)
    parts.append(f"\nAvailable monsters: {monster_summary}")

    if new_monster_kinds:
        parts.append(f"PREFER placing these newly created monsters: {', '.join(new_monster_kinds)}")

    return "\n".join(parts)


async def generate_layout(
    theme: str = "dungeon",
    difficulty: int = 5,
    available_tiles: list[dict] | None = None,
    available_monsters: list[dict] | None = None,
    new_tile_ids: list[str] | None = None,
    new_monster_kinds: list[str] | None = None,
    existing_room_names: list[str] | None = None,
) -> dict | None:
    """Generate a room layout: name, tilemap, monster placements.

    Returns: {"name", "tilemap", "monster_placements"} or None.
    """
    if AI_BACKEND == "api" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("[GEN] No ANTHROPIC_API_KEY set — skipping layout generation")
        return None

    available_tiles = available_tiles or []
    available_monsters = available_monsters or []

    prompt = _build_layout_prompt(
        theme, difficulty, available_tiles, available_monsters,
        new_tile_ids or [], new_monster_kinds or [],
        existing_room_names,
    )

    # Build tile/monster ID sets for validation
    all_tile_ids = set(BUILTIN_TILES)
    all_walkable = {"DF"}
    for t in available_tiles:
        tid = t.get("id", "")
        all_tile_ids.add(tid)
        if t.get("walkable", False):
            all_walkable.add(tid)

    all_monster_kinds = set(_BUILTIN_KINDS)
    for m in available_monsters:
        all_monster_kinds.add(m.get("kind", ""))

    def _validate(data):
        return validate_layout(data, all_tile_ids, all_walkable, all_monster_kinds)

    def _patch(data):
        patches = []
        patches.extend(patch_duplicate_name(data, existing_room_names or []))
        patches.extend(patch_unreachable_doorways(data, all_walkable))
        patches.extend(patch_monster_placements(data, all_walkable))
        return patches

    return await _call_ai(
        system_prompt=SYSTEM_PROMPT_LAYOUT,
        user_prompt=prompt,
        validate_fn=_validate,
        patch_fn=_patch,
        label="layout",
    )


# ---------------------------------------------------------------------------
# Orchestrator: generate_room()
# ---------------------------------------------------------------------------

def _roll_new_count(library_full: bool, library_count: int, library_capacity: int) -> int:
    """Decide how many new items to generate (0, 1, or 2).
    Empty libraries get more new content. Full libraries get none."""
    if library_full:
        return 0
    fullness = library_count / max(library_capacity, 1)
    if fullness < 0.25:
        # Sparse library: always create, likely 2
        return 2 if random.random() < 0.7 else 1
    elif fullness < 0.75:
        # Medium library: usually 1, sometimes 2
        r = random.random()
        if r < 0.3:
            return 2
        elif r < 0.8:
            return 1
        else:
            return 0
    else:
        # Nearly full: usually 0-1
        return 1 if random.random() < 0.4 else 0


async def generate_room(
    theme: str = "dungeon",
    difficulty: int = 5,
    existing_monsters: list[dict] | None = None,
    existing_tiles: list[dict] | None = None,
    monster_library_full: bool = False,
    tile_library_full: bool = False,
    existing_room_names: list[str] | None = None,
    monster_library_count: int = 0,
    monster_library_capacity: int = 20,
    tile_library_count: int = 0,
    tile_library_capacity: int = 20,
) -> dict | None:
    """Generate a complete dungeon room via multiple focused AI calls.

    Rolls for 0-2 new monsters and 0-2 new tiles, generates them first,
    then generates the layout with the full inventory.

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

    # --- Step 1: Roll and generate new monsters ---
    num_new_monsters = _roll_new_count(
        monster_library_full, monster_library_count, monster_library_capacity)
    print(f"[GEN] Rolling {num_new_monsters} new monster(s) for theme \"{theme}\", difficulty {difficulty}")

    new_monsters = []
    for i in range(num_new_monsters):
        # Step 1: Generate design (kind, tags, stats, behavior)
        design = await generate_monster_design(
            theme, difficulty,
            existing_monsters + [{"kind": m["kind"], "tags": m.get("tags", [])} for m in new_monsters],
        )
        if design is None:
            print(f"[GEN] Monster design {i+1}/{num_new_monsters} failed, continuing...")
            continue

        # Step 2: Generate sprite for this design
        attack_types = [a.get("type", "") for a in design.get("behavior", {}).get("attacks", [])]
        sprite_data = await generate_monster_sprite(
            design["kind"],
            tags=design.get("tags"),
            attack_types=attack_types,
            theme=theme,
        )
        if sprite_data and isinstance(sprite_data.get("sprite"), dict):
            design["sprite"] = sprite_data["sprite"]
        else:
            print(f"[GEN] Sprite generation failed for {design['kind']}, skipping monster")
            continue

        new_monsters.append(design)
        print(f"[GEN] Created monster: {design['kind']}")

    # --- Step 2: Roll and generate new tiles ---
    num_new_tiles = _roll_new_count(
        tile_library_full, tile_library_count, tile_library_capacity)
    print(f"[GEN] Rolling {num_new_tiles} new tile(s)")

    new_tiles = []
    if num_new_tiles > 0:
        tile_result = await generate_tiles(
            theme, difficulty, existing_tiles, count=num_new_tiles)
        if tile_result:
            new_tiles = tile_result
            print(f"[GEN] Created {len(new_tiles)} tile(s): {[t.get('id') for t in new_tiles]}")
        else:
            print("[GEN] Tile generation failed, continuing with existing tiles only")

    # --- Step 3: Generate layout ---
    all_monsters = existing_monsters + [
        {"kind": m["kind"], "tags": m.get("tags", [])} for m in new_monsters
    ]
    all_tiles = existing_tiles + [
        {"id": t["id"], "walkable": t.get("walkable", False), "tags": t.get("tags", [])}
        for t in new_tiles
    ]
    new_tile_ids = [t["id"] for t in new_tiles]
    new_monster_kinds = [m["kind"] for m in new_monsters]

    layout = await generate_layout(
        theme, difficulty,
        available_tiles=all_tiles,
        available_monsters=all_monsters,
        new_tile_ids=new_tile_ids,
        new_monster_kinds=new_monster_kinds,
        existing_room_names=existing_room_names,
    )
    if layout is None:
        print("[GEN] Layout generation failed — giving up")
        return None

    # Assemble final result (same format as before)
    result = {
        "name": layout["name"],
        "tilemap": layout["tilemap"],
        "new_tiles": new_tiles,
        "new_monsters": new_monsters,
        "monster_placements": layout["monster_placements"],
    }
    print(f"[GEN] Room complete: \"{result['name']}\" "
          f"({len(new_monsters)} new monsters, {len(new_tiles)} new tiles, "
          f"{len(result['monster_placements'])} placements)")
    return result


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------

def init():
    """Load persisted usage data on startup."""
    usage_tracker.load()
    print(f"[GEN] Backend: {AI_BACKEND}" + (" (Claude CLI — uses subscription)" if AI_BACKEND == "cli" else " (Anthropic API)"))


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

async def _test_standalone():
    """Run a standalone test of each generation step."""
    print("=" * 60)
    print("AI Generator — Standalone Test (multi-step)")
    print("=" * 60)

    # Test 1: Monster design (kind, tags, stats, behavior)
    print("\n--- Test 1: Monster design (fire theme, difficulty 5) ---")
    design = await generate_monster_design("fire", 5, [])
    if design:
        print(f"  Kind: {design['kind']}")
        print(f"  Tags: {design.get('tags', [])}")
        print(f"  Stats: {design.get('stats', {})}")
        b = design.get("behavior", {})
        print(f"  Rules: {len(b.get('rules', []))}")
        print(f"  Attacks: {len(b.get('attacks', []))}")
    else:
        print("  FAILED")

    # Test 2: Monster sprite (given design)
    if design:
        print(f"\n--- Test 2: Monster sprite for {design['kind']} ---")
        attack_types = [a.get("type", "") for a in design.get("behavior", {}).get("attacks", [])]
        sprite_result = await generate_monster_sprite(
            design["kind"], tags=design.get("tags"), attack_types=attack_types, theme="fire")
        if sprite_result:
            frames = sprite_result.get("sprite", {}).get("frames", [])
            colors = sprite_result.get("sprite", {}).get("colors", {})
            print(f"  Frames: {len(frames)}, Colors: {list(colors.keys())}")
        else:
            print("  FAILED")

    # Test 3: Tiles
    print("\n--- Test 3: Generate 2 tiles (shadow theme) ---")
    tiles = await generate_tiles("shadow", 5, [], count=2)
    if tiles:
        for t in tiles:
            print(f"  {t.get('id')}: walkable={t.get('walkable')}, tags={t.get('tags', [])}")
    else:
        print("  FAILED")

    # Test 4: Layout
    print("\n--- Test 4: Layout (fire theme, difficulty 5) ---")
    available_monsters = [{"kind": design["kind"], "tags": design.get("tags", [])}] if design else []
    available_tiles = [{"id": t["id"], "walkable": t.get("walkable", False), "tags": t.get("tags", [])} for t in (tiles or [])]

    layout = await generate_layout(
        "fire", 5,
        available_tiles=available_tiles,
        available_monsters=available_monsters,
        new_tile_ids=[t["id"] for t in (tiles or [])],
        new_monster_kinds=[design["kind"]] if design else [],
    )
    if layout:
        print(f"  Name: {layout['name']}")
        print(f"  Tilemap: {len(layout['tilemap'])} rows")
        print(f"  Placements: {layout.get('monster_placements', [])}")
    else:
        print("  FAILED")

    # Test 5: Full orchestrated generate_room
    print("\n--- Test 5: Full generate_room orchestration ---")
    result = await generate_room(theme="ice", difficulty=6)
    if result:
        print(f"  Name: {result['name']}")
        print(f"  New monsters: {[m['kind'] for m in result.get('new_monsters', [])]}")
        print(f"  New tiles: {[t['id'] for t in result.get('new_tiles', [])]}")
        print(f"  Placements: {result.get('monster_placements', [])}")
    else:
        print("  FAILED")

    print(f"\n--- Usage stats ---")
    print(f"  Total calls: {usage_tracker.total_calls}")
    print(f"  Input tokens: {usage_tracker.total_input_tokens}")
    print(f"  Output tokens: {usage_tracker.total_output_tokens}")
    print(f"  Estimated cost: ${usage_tracker.estimated_cost():.4f}")


if __name__ == "__main__":
    asyncio.run(_test_standalone())
