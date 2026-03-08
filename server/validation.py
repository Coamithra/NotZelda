"""Validation and registration for dynamic content (AI-generated monsters and tiles)."""

import re

from server.state import game

_HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')

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
    elif not re.match(r'^[a-z][a-z0-9_]*$', kind):
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
    elif not re.match(r'^[a-z][a-z0-9_]*$', tile_id):
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

    game.monster_stats[kind] = {
        "hp": int(stats["hp"]),
        "hop_interval": float(stats["hop_interval"]),
        "damage": int(stats["damage"]),
    }

    game.custom_sprites[kind] = sprite

    death_sprite = data.get("death_sprite")
    if death_sprite:
        game.custom_death_sprites[kind] = death_sprite

    behavior = data.get("behavior")
    if behavior:
        game.monster_behaviors[kind] = behavior

    print(f"[REG] Monster type registered: {kind} "
          f"(hp={stats['hp']}, dmg={stats['damage']}, hop={stats['hop_interval']})")
    return True, []


def register_tile_type(data: dict) -> tuple[bool, list[str]]:
    """Register a new custom tile type at runtime. Returns (success, errors)."""
    errors = validate_tile(data)
    if errors:
        return False, errors

    tile_id = data["id"]
    game.custom_tile_recipes[tile_id] = {
        "colors": data["colors"],
        "operations": data["operations"],
    }

    if data.get("walkable", False):
        game.custom_walkable_tiles.add(tile_id)
    else:
        game.custom_walkable_tiles.discard(tile_id)

    print(f"[REG] Tile type registered: {tile_id} (walkable={data.get('walkable', False)})")
    return True, []
