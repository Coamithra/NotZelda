"""Programmatic monster variant system — creates stronger recolored versions of existing monsters.

Takes a base monster's full data dict and produces a new monster with:
  - Scaled stats (HP, damage, tick_rate)
  - Hue-shifted sprite colors (all sprite + death sprite + projectile colors)
  - Scaled behavior (attack damage up, cooldowns down)
  - A prefix name (e.g. "elder_flame_wyrm") and `based_on` lineage field
"""

import colorsys
import copy
import math
import random


# ---------------------------------------------------------------------------
# Variant tier definitions — index 0 (weakest) to 4 (strongest)
# ---------------------------------------------------------------------------

VARIANT_TIERS = [
    {"prefixes": ["swift", "keen"],       "hp_mult": 1.0,  "dmg_add": 0, "tick_mult": 1.3, "cd_mult": 0.85},
    {"prefixes": ["tough", "hardened"],   "hp_mult": 1.5,  "dmg_add": 1, "tick_mult": 1.05, "cd_mult": 1.0},
    {"prefixes": ["elder", "greater"],    "hp_mult": 1.75, "dmg_add": 1, "tick_mult": 1.15, "cd_mult": 0.8},
    {"prefixes": ["ancient", "dire"],     "hp_mult": 2.0,  "dmg_add": 2, "tick_mult": 1.2,  "cd_mult": 0.7},
    {"prefixes": ["frenzied", "void"],    "hp_mult": 2.5,  "dmg_add": 3, "tick_mult": 1.4,  "cd_mult": 0.6},
]


# ---------------------------------------------------------------------------
# Color hue shifting
# ---------------------------------------------------------------------------

def _shift_hex_hue(hex_color: str, hue_offset: float) -> str:
    """Shift the hue of a #RRGGBB color by hue_offset (0.0–1.0 wraps)."""
    h_str = hex_color.lstrip("#")
    if len(h_str) != 6:
        return hex_color
    try:
        r = int(h_str[0:2], 16) / 255
        g = int(h_str[2:4], 16) / 255
        b = int(h_str[4:6], 16) / 255
    except ValueError:
        return hex_color
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    h = (h + hue_offset) % 1.0
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r2 * 255 + 0.5):02x}{int(g2 * 255 + 0.5):02x}{int(b2 * 255 + 0.5):02x}"


def _shift_sprite_colors(sprite: dict, hue_offset: float) -> dict:
    """Return a copy of the sprite dict with all color values hue-shifted."""
    new_sprite = copy.deepcopy(sprite)
    colors = new_sprite.get("colors", {})
    for key in colors:
        v = colors[key]
        if isinstance(v, str) and v.startswith("#") and len(v) == 7:
            colors[key] = _shift_hex_hue(v, hue_offset)
    return new_sprite


# ---------------------------------------------------------------------------
# Behavior scaling
# ---------------------------------------------------------------------------

_ATTACK_ACTIONS = {"projectile", "charge", "teleport", "area"}


def _scale_behavior(behavior: dict, dmg_add: int, cd_mult: float,
                    hue_offset: float) -> dict:
    """Return a copy of the behavior with scaled damage, cooldowns, and colors."""
    new_behavior = copy.deepcopy(behavior)
    for rule in new_behavior.get("rules", []):
        # Scale attack damage
        if rule.get("do") in _ATTACK_ACTIONS and "damage" in rule:
            rule["damage"] = min(20, rule["damage"] + dmg_add)
        # Scale cooldowns (shorter = more aggressive)
        if "cooldown" in rule:
            rule["cooldown"] = max(1, round(rule["cooldown"] * cd_mult))
        # Hue-shift projectile colors
        if "sprite_color" in rule:
            v = rule["sprite_color"]
            if isinstance(v, str) and v.startswith("#") and len(v) == 7:
                rule["sprite_color"] = _shift_hex_hue(v, hue_offset)
    return new_behavior


# ---------------------------------------------------------------------------
# Lookup helper
# ---------------------------------------------------------------------------

def get_monster_data(kind: str) -> dict | None:
    """Look up full monster data from the monster library."""
    from server.state import game
    if game.monster_library:
        for entry in game.monster_library.real_entries:
            if entry.id == kind:
                return entry.data
    return None


# ---------------------------------------------------------------------------
# Main variant creator
# ---------------------------------------------------------------------------

def create_variant(base_monster: dict, tier: int | None = None) -> dict:
    """Create a stronger, recolored variant of a base monster.

    Args:
        base_monster: Full monster data dict (kind, stats, sprite, behavior, etc.)
        tier: 0–4 (weakest to strongest). Random if None.

    Returns:
        New monster data dict ready for register_monster_type(), with `based_on` field.
    """
    if tier is None:
        tier = random.randint(0, len(VARIANT_TIERS) - 1)
    tier = max(0, min(tier, len(VARIANT_TIERS) - 1))
    t = VARIANT_TIERS[tier]

    base_kind = base_monster.get("kind", "unknown")
    prefix = random.choice(t["prefixes"])
    new_kind = f"{prefix}_{base_kind}"

    # --- Scale stats (clamped to validation limits) ---
    base_stats = base_monster.get("stats", {})
    new_stats = {
        "hp": min(100, max(1, math.ceil(base_stats.get("hp", 2) * t["hp_mult"]))),
        "damage": min(20, max(1, base_stats.get("damage", 1) + t["dmg_add"])),
        "tick_rate": min(5.0, round(base_stats.get("tick_rate", 0.5) * t["tick_mult"], 2)),
    }

    # --- Random hue shift (avoid shifts too small to notice) ---
    hue_offset = random.uniform(0.15, 0.85)

    # --- Build the variant ---
    new_sprite = _shift_sprite_colors(base_monster.get("sprite", {}), hue_offset)

    default_behavior = {"rules": [{"if": "always", "do": "move", "direction": "random"}]}
    new_behavior = _scale_behavior(
        base_monster.get("behavior", default_behavior),
        t["dmg_add"], t["cd_mult"], hue_offset,
    )

    new_tags = list(base_monster.get("tags", []))
    if "variant" not in new_tags:
        new_tags.append("variant")

    result = {
        "kind": new_kind,
        "tags": new_tags,
        "stats": new_stats,
        "sprite": new_sprite,
        "behavior": new_behavior,
        "based_on": base_kind,
    }

    # Hue-shift death sprite if the base has one
    if "death_sprite" in base_monster:
        result["death_sprite"] = _shift_sprite_colors(base_monster["death_sprite"], hue_offset)

    return result
