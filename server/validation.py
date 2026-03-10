"""Validation and registration for dynamic content (AI-generated monsters and tiles)."""

import re

from server.state import game

_HEX_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{6}$')

VALID_BEHAVIOR_CONDITIONS = frozenset({
    "player_within", "player_beyond", "player_in_range_line",
    "hp_below", "hp_above", "random_chance", "always",
})

VALID_BEHAVIOR_ACTIONS = frozenset({
    "move", "hold", "projectile", "charge", "teleport", "area",
})

VALID_DIRECTIONS = frozenset({
    "up", "down", "left", "right", "player", "away", "random", "patrol",
})

VALID_TELEPORT_TARGETS = frozenset({"player", "random", "away"})


def _is_hex_color(s) -> bool:
    """Check if a string is a valid #RRGGBB hex color."""
    return isinstance(s, str) and bool(_HEX_COLOR_RE.match(s))


def validate_monster(data: dict) -> list[str]:
    """Validate a monster definition. Returns a list of error strings (empty = valid).

    Expected shape:
      kind: str
      stats: {hp: int, tick_rate: float, damage: int}
      sprite: {colors: {key: "#hex"}, frames: [[[colorKey, x, y, w, h], ...], ...]}
      behavior: {rules: [...]}  (optional)
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
        tick = stats.get("tick_rate")
        if not isinstance(tick, (int, float)) or tick < 0.1 or tick > 5.0:
            errors.append("stats.tick_rate must be 0.1-5.0")
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
            errors.extend(_validate_behavior(behavior))

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


def _validate_behavior(behavior: dict) -> list[str]:
    """Validate behavior rules. Returns error list."""
    errors = []
    rules = behavior.get("rules", [])
    if not isinstance(rules, list):
        errors.append("behavior.rules must be a list")
        return errors

    for ri, rule in enumerate(rules):
        if not isinstance(rule, dict):
            errors.append(f"behavior.rules[{ri}] must be a dict")
            continue

        # Condition
        cond = rule.get("if")
        if not cond:
            errors.append(f"behavior.rules[{ri}] missing 'if' condition")
            continue
        if cond not in VALID_BEHAVIOR_CONDITIONS:
            errors.append(f"behavior.rules[{ri}] unknown condition: {cond}")

        # Action
        action = rule.get("do")
        if not isinstance(action, str):
            errors.append(f"behavior.rules[{ri}] missing 'do' action")
            continue
        if action not in VALID_BEHAVIOR_ACTIONS:
            errors.append(f"behavior.rules[{ri}] unknown action: {action}")

        # Direction (for actions that use it)
        direction = rule.get("direction")
        if direction is not None and direction not in VALID_DIRECTIONS:
            errors.append(f"behavior.rules[{ri}] unknown direction: {direction}")

        # Patrol route (required when direction is "patrol")
        if direction == "patrol":
            patrol_route = rule.get("patrol_route")
            if not isinstance(patrol_route, str) or not patrol_route:
                errors.append(f"behavior.rules[{ri}] patrol requires 'patrol_route' string (e.g. 'RRDDLLUU')")
            elif not all(c in "UDLRudlr" for c in patrol_route):
                errors.append(f"behavior.rules[{ri}] patrol_route must contain only U/D/L/R characters")

        # Warmup / cooldown
        warmup = rule.get("warmup")
        if warmup is not None and (not isinstance(warmup, (int, float)) or warmup < 0 or warmup > 20):
            errors.append(f"behavior.rules[{ri}] warmup must be 0-20")
        cooldown = rule.get("cooldown")
        if cooldown is not None and (not isinstance(cooldown, (int, float)) or cooldown < 0 or cooldown > 50):
            errors.append(f"behavior.rules[{ri}] cooldown must be 0-50")

        # Action-specific params
        if action == "projectile":
            sc = rule.get("sprite_color")
            if sc is not None and not _is_hex_color(sc):
                errors.append(f"behavior.rules[{ri}] sprite_color must be #RRGGBB")
            spd = rule.get("speed")
            if spd is not None and (not isinstance(spd, (int, float)) or spd < 1 or spd > 5):
                errors.append(f"behavior.rules[{ri}] speed must be 1-5")
            prc = rule.get("piercing")
            if prc is not None and not isinstance(prc, bool):
                errors.append(f"behavior.rules[{ri}] piercing must be boolean")
        elif action == "charge":
            rng = rule.get("range")
            if rng is not None and (not isinstance(rng, (int, float)) or rng < 1 or rng > 15):
                errors.append(f"behavior.rules[{ri}] range must be 1-15")
        elif action == "teleport":
            target = rule.get("target")
            if target is not None and target not in VALID_TELEPORT_TARGETS:
                errors.append(f"behavior.rules[{ri}] target must be player/random/away")
            drift = rule.get("drift")
            if drift is not None and (not isinstance(drift, (int, float)) or drift < 0 or drift > 10):
                errors.append(f"behavior.rules[{ri}] drift must be 0-10")
            rng = rule.get("range")
            if rng is not None and (not isinstance(rng, (int, float)) or rng < 1 or rng > 15):
                errors.append(f"behavior.rules[{ri}] range must be 1-15")
            dr = rule.get("damage_radius")
            if dr is not None and (not isinstance(dr, (int, float)) or dr < 0 or dr > 6):
                errors.append(f"behavior.rules[{ri}] damage_radius must be 0-6")
        elif action == "area":
            rng = rule.get("range")
            if rng is not None and (not isinstance(rng, (int, float)) or rng < 1 or rng > 6):
                errors.append(f"behavior.rules[{ri}] range must be 1-6")

        # Damage (for attack actions)
        if action in ("projectile", "charge", "teleport", "area"):
            dmg = rule.get("damage")
            if dmg is not None and (not isinstance(dmg, (int, float)) or dmg < 1 or dmg > 20):
                errors.append(f"behavior.rules[{ri}] damage must be 1-20")

    return errors


def validate_tile(data: dict) -> list[str]:
    """Validate a tile definition. Returns a list of error strings (empty = valid).

    Expected shape:
      id: str
      walkable: bool (optional, defaults to False)
      colors: {key: "#hex"}
      layers: [[colorKey, x, y, w, h], ...]
    """
    errors = []

    tile_id = data.get("id")
    if not isinstance(tile_id, str) or not tile_id:
        errors.append("id must be a non-empty string")
    elif not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', tile_id):
        errors.append("id must be alphanumeric with underscores")

    colors = data.get("colors")
    if not isinstance(colors, dict):
        errors.append("colors must be a dict")
    else:
        for k, v in colors.items():
            if not _is_hex_color(v):
                errors.append(f"colors.{k} must be #RRGGBB, got {v!r}")

    layers = data.get("layers")
    if not isinstance(layers, list):
        errors.append("layers must be a list")
    else:
        for li, layer in enumerate(layers):
            if not isinstance(layer, list) or len(layer) != 5:
                errors.append(f"layers[{li}] must be [colorKey, x, y, w, h]")
                continue
            _, x, y, w, h = layer
            if not all(isinstance(v, (int, float)) for v in (x, y, w, h)):
                errors.append(f"layers[{li}] x/y/w/h must be numbers")
            elif x < 0 or y < 0 or x + w > 16 or y + h > 16:
                errors.append(f"layers[{li}] out of 16x16 bounds")

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
        "tick_rate": float(stats["tick_rate"]),
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
          f"(hp={stats['hp']}, dmg={stats['damage']}, tick={stats['tick_rate']})")
    return True, []


def register_tile_type(data: dict) -> tuple[bool, list[str]]:
    """Register a new custom tile type at runtime. Returns (success, errors)."""
    errors = validate_tile(data)
    if errors:
        return False, errors

    tile_id = data["id"]
    game.custom_tile_recipes[tile_id] = {
        "colors": data["colors"],
        "layers": data["layers"],
    }

    if data.get("walkable", False):
        game.custom_walkable_tiles.add(tile_id)
    else:
        game.custom_walkable_tiles.discard(tile_id)

    print(f"[REG] Tile type registered: {tile_id} (walkable={data.get('walkable', False)})")
    return True, []
