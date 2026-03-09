"""
Behavior Engine — data-driven monster AI with tick-based warmup/cooldown.

Rules are evaluated top-to-bottom; first match wins.
Each rule has a condition ("if") and an action ("do") with parameters.
Rules can have warmup (delay before execution) and cooldown (delay before
re-evaluation).

Actions include movement and attacks — no separate attack system.

Example behavior:
    {
        "rules": [
            {"if": "hp_below", "value": 2, "do": "move", "direction": "away"},
            {"if": "player_in_range_line", "range": 6, "los": true,
             "do": "projectile", "direction": "player", "damage": 1,
             "sprite_color": "#ff0000", "warmup": 1, "cooldown": 5},
            {"if": "always", "do": "move", "direction": "random"}
        ]
    }
"""

import random

# Injected by mud_server at startup to avoid circular imports
_players_in_room = None
_ROOM_COLS = None
_ROOM_ROWS = None
_is_walkable_tile = None
_GUARDS = None
_ROOMS = None


def init(players_in_room, ROOM_COLS, ROOM_ROWS, is_walkable_tile, GUARDS, ROOMS):
    """Called once by mud_server to inject shared state references."""
    global _players_in_room, _ROOM_COLS, _ROOM_ROWS, _is_walkable_tile, _GUARDS, _ROOMS
    _players_in_room = players_in_room
    _ROOM_COLS = ROOM_COLS
    _ROOM_ROWS = ROOM_ROWS
    _is_walkable_tile = is_walkable_tile
    _GUARDS = GUARDS
    _ROOMS = ROOMS


DEFAULT_BEHAVIOR = {"rules": [{"if": "always", "do": "move", "direction": "random"}]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nearest_player(monster, room_id):
    """Find the nearest living player (Manhattan distance). Returns (player, dist) or (None, inf)."""
    players = _players_in_room(room_id)
    best = None
    best_dist = float("inf")
    for p in players:
        if p.hp <= 0:
            continue
        dist = abs(p.x - monster.x) + abs(p.y - monster.y)
        if dist < best_dist:
            best_dist = dist
            best = p
    return best, best_dist


def _is_walkable(x, y, room_id):
    """Check if a tile is in bounds, walkable, and not occupied by an NPC."""
    if x < 0 or x >= _ROOM_COLS or y < 0 or y >= _ROOM_ROWS:
        return False
    tilemap = _ROOMS[room_id]["tilemap"]
    if not _is_walkable_tile(tilemap[y][x]):
        return False
    guards = _GUARDS.get(room_id, [])
    if any(g["x"] == x and g["y"] == y for g in guards):
        return False
    return True


def _has_los(x1, y1, x2, y2, room_id):
    """Check line of sight between two points on the same row or column."""
    if x1 == x2:
        step = 1 if y2 > y1 else -1
        for y in range(y1 + step, y2, step):
            if not _is_walkable(x1, y, room_id):
                return False
    elif y1 == y2:
        step = 1 if x2 > x1 else -1
        for x in range(x1 + step, x2, step):
            if not _is_walkable(x, y1, room_id):
                return False
    return True


# ---------------------------------------------------------------------------
# Condition evaluators — return True/False
# ---------------------------------------------------------------------------

def cond_player_within(monster, room_id, rule):
    """True if nearest living player is within `range` tiles (Manhattan)."""
    _, dist = _nearest_player(monster, room_id)
    return dist <= rule.get("range", 3)


def cond_player_beyond(monster, room_id, rule):
    """True if nearest living player is farther than `range` tiles (Manhattan)."""
    _, dist = _nearest_player(monster, room_id)
    return dist > rule.get("range", 3)


def cond_player_in_range_line(monster, room_id, rule):
    """True if a player is on the same row or column within `range` tiles.

    If `los` is true, obstacles between monster and player block the check.
    """
    max_range = rule.get("range", 3)
    check_los = rule.get("los", False)
    player, _ = _nearest_player(monster, room_id)
    if player is None:
        return False
    dx = abs(player.x - monster.x)
    dy = abs(player.y - monster.y)
    if player.x == monster.x and dy <= max_range:
        if check_los and not _has_los(monster.x, monster.y, player.x, player.y, room_id):
            return False
        return True
    if player.y == monster.y and dx <= max_range:
        if check_los and not _has_los(monster.x, monster.y, player.x, player.y, room_id):
            return False
        return True
    return False


def cond_hp_below(monster, room_id, rule):
    """True if monster HP is below `value` hit points."""
    return monster.hp < rule.get("value", 2)


def cond_hp_above(monster, room_id, rule):
    """True if monster HP is above `value` hit points."""
    return monster.hp > rule.get("value", 1)


def cond_random_chance(monster, room_id, rule):
    """True with `value`% probability per tick."""
    return random.random() * 100 < rule.get("value", 50)


def cond_always(monster, room_id, rule):
    return True


CONDITION_MAP = {
    "player_within": cond_player_within,
    "player_beyond": cond_player_beyond,
    "player_in_range_line": cond_player_in_range_line,
    "hp_below": cond_hp_below,
    "hp_above": cond_hp_above,
    "random_chance": cond_random_chance,
    "always": cond_always,
}


# ---------------------------------------------------------------------------
# Direction resolution
# ---------------------------------------------------------------------------

CARDINAL_DIRS = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": (1,  0),
}


def _resolve_direction(direction, monster, room_id):
    """Resolve a direction string to (dx, dy).

    Returns (dx, dy) or None if no valid direction.
    """
    if direction in CARDINAL_DIRS:
        return CARDINAL_DIRS[direction]

    player, _ = _nearest_player(monster, room_id)

    if direction == "player":
        if player is None:
            return None
        dx = player.x - monster.x
        dy = player.y - monster.y
        if dx == 0 and dy == 0:
            return None
        if abs(dx) >= abs(dy):
            return (1 if dx > 0 else -1, 0)
        else:
            return (0, 1 if dy > 0 else -1)

    if direction == "away":
        if player is None:
            return None
        dx = monster.x - player.x
        dy = monster.y - player.y
        if dx == 0 and dy == 0:
            # Pick random direction to flee
            dirs = list(CARDINAL_DIRS.values())
            random.shuffle(dirs)
            return dirs[0]
        if abs(dx) >= abs(dy):
            return (1 if dx > 0 else -1, 0)
        else:
            return (0, 1 if dy > 0 else -1)

    if direction == "random":
        dirs = list(CARDINAL_DIRS.values())
        random.shuffle(dirs)
        return dirs[0]

    return None


# ---------------------------------------------------------------------------
# Action resolution — build action dicts with locked-in parameters
# ---------------------------------------------------------------------------

def _resolve_move(rule, monster, room_id):
    """Resolve a move action. Returns {"action": "move", "x", "y"} or None."""
    direction = rule.get("direction", "random")

    if direction == "patrol":
        return _resolve_patrol_move(rule, monster, room_id)

    if direction == "random":
        # Wander: try random adjacent walkable tiles
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = monster.x + dx, monster.y + dy
            if _is_walkable(nx, ny, room_id):
                return {"action": "move", "x": nx, "y": ny}
        return None

    if direction == "player":
        # Chase: greedy move toward nearest player
        target, _ = _nearest_player(monster, room_id)
        if target is None:
            return _resolve_move({"direction": "random"}, monster, room_id)
        best = None
        best_dist = float("inf")
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = monster.x + dx, monster.y + dy
            if not _is_walkable(nx, ny, room_id):
                continue
            dist = abs(target.x - nx) + abs(target.y - ny)
            if dist < best_dist:
                best_dist = dist
                best = (nx, ny)
        if best:
            return {"action": "move", "x": best[0], "y": best[1]}
        return None

    if direction == "away":
        # Flee: greedy move away from nearest player
        target, _ = _nearest_player(monster, room_id)
        if target is None:
            return _resolve_move({"direction": "random"}, monster, room_id)
        best = None
        best_dist = -1
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = monster.x + dx, monster.y + dy
            if not _is_walkable(nx, ny, room_id):
                continue
            dist = abs(target.x - nx) + abs(target.y - ny)
            if dist > best_dist:
                best_dist = dist
                best = (nx, ny)
        if best:
            return {"action": "move", "x": best[0], "y": best[1]}
        return None

    # Cardinal direction
    d = CARDINAL_DIRS.get(direction)
    if d:
        nx, ny = monster.x + d[0], monster.y + d[1]
        if _is_walkable(nx, ny, room_id):
            return {"action": "move", "x": nx, "y": ny}
    return None


_PATROL_DIRS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}


def _resolve_patrol_move(rule, monster, room_id):
    """Move along a patrol route string (e.g. 'RRDDLLUU'). Falls back to random wander."""
    route = rule.get("patrol_route", "")
    if not route:
        return _resolve_move({"direction": "random"}, monster, room_id)

    idx = getattr(monster, "_patrol_index", 0) % len(route)
    step = route[idx].upper()
    d = _PATROL_DIRS.get(step)
    if not d:
        return _resolve_move({"direction": "random"}, monster, room_id)

    nx, ny = monster.x + d[0], monster.y + d[1]
    monster._patrol_index = (idx + 1) % len(route)
    if _is_walkable(nx, ny, room_id):
        return {"action": "move", "x": nx, "y": ny}
    return None


def _resolve_projectile(rule, monster, room_id):
    """Resolve projectile action. Returns action dict or None."""
    direction = rule.get("direction", "player")
    d = _resolve_direction(direction, monster, room_id)
    if d is None:
        return None
    return {
        "action": "projectile",
        "dx": d[0], "dy": d[1],
        "damage": rule.get("damage", 1),
        "sprite_color": rule.get("sprite_color", "#ff0000"),
        "speed": rule.get("speed", 1),
        "piercing": rule.get("piercing", False),
    }


def _resolve_charge(rule, monster, room_id):
    """Resolve charge action. Returns action dict or None."""
    direction = rule.get("direction", "player")
    d = _resolve_direction(direction, monster, room_id)
    if d is None:
        return None
    return {
        "action": "charge",
        "dx": d[0], "dy": d[1],
        "range": rule.get("range", 3),
        "damage": rule.get("damage", monster.damage),
    }


def _resolve_teleport(rule, monster, room_id):
    """Resolve teleport action. Returns action dict or None.

    target: "player" | "random" | "away" — determines center point.
    drift: 0-N — random offset from target tile.
    range: max teleport distance from monster.
    """
    target_mode = rule.get("target", "player")
    drift = rule.get("drift", 1)
    max_range = rule.get("range", 8)
    damage = rule.get("damage", monster.damage)

    # Determine center point
    if target_mode == "player":
        player, player_dist = _nearest_player(monster, room_id)
        if player is None:
            return None
        if player_dist > max_range:
            return None
        cx, cy = player.x, player.y
    elif target_mode == "away":
        player, _ = _nearest_player(monster, room_id)
        if player is None:
            cx, cy = monster.x, monster.y
        else:
            dx = monster.x - player.x
            dy = monster.y - player.y
            length = max(abs(dx), abs(dy), 1)
            cx = monster.x + int(dx / length * max_range)
            cy = monster.y + int(dy / length * max_range)
            cx = max(0, min(_ROOM_COLS - 1, cx))
            cy = max(0, min(_ROOM_ROWS - 1, cy))
    else:  # "random"
        cx = random.randint(0, _ROOM_COLS - 1)
        cy = random.randint(0, _ROOM_ROWS - 1)

    # Find a walkable tile within drift of the center point
    candidates = []
    for ddx in range(-drift, drift + 1):
        for ddy in range(-drift, drift + 1):
            tx, ty = cx + ddx, cy + ddy
            dist_from_monster = abs(tx - monster.x) + abs(ty - monster.y)
            if dist_from_monster > max_range:
                continue
            if dist_from_monster == 0:
                continue  # don't teleport to self
            if _is_walkable(tx, ty, room_id):
                candidates.append((tx, ty))
    if not candidates:
        return None
    target_pos = random.choice(candidates)

    return {
        "action": "teleport",
        "target_x": target_pos[0],
        "target_y": target_pos[1],
        "damage": damage,
        "damage_radius": rule.get("damage_radius", 1),
    }


def _resolve_area(rule, monster, room_id):
    """Resolve area attack action. Returns action dict."""
    return {
        "action": "area",
        "x": monster.x,
        "y": monster.y,
        "range": rule.get("range", 2),
        "damage": rule.get("damage", monster.damage),
    }


ACTION_RESOLVERS = {
    "move": _resolve_move,
    "hold": lambda rule, monster, room_id: {"action": "hold"},
    "projectile": _resolve_projectile,
    "charge": _resolve_charge,
    "teleport": _resolve_teleport,
    "area": _resolve_area,
}


# ---------------------------------------------------------------------------
# Main tick function
# ---------------------------------------------------------------------------

def monster_tick(monster, room_id):
    """Process one behavior tick for a monster.

    Returns:
        {"phase": "execute", "action": ..., ...params}  — execute this action now
        {"phase": "warmup", "action": ..., ...params}   — warmup just started (send visuals)
        None — nothing to do (mid-warmup or no matching rule)
    """
    # --- Handle pending warmup ---
    if monster._pending_warmup is not None:
        monster._pending_warmup["ticks"] -= 1
        if monster._pending_warmup["ticks"] <= 0:
            action = monster._pending_warmup["action"]
            rule_idx = monster._pending_warmup["rule_index"]
            cooldown = monster._pending_warmup.get("cooldown", 0)
            if cooldown > 0:
                monster._rule_cooldowns[rule_idx] = cooldown
            monster._pending_warmup = None
            return {"phase": "execute", **action}
        return None  # still warming up

    # --- Evaluate rules (cooldowns are checked then decremented after) ---
    behavior = getattr(monster, "behavior", None) or DEFAULT_BEHAVIOR
    rules = behavior.get("rules", [])

    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue

        # Skip if on cooldown
        if monster._rule_cooldowns.get(i, 0) > 0:
            continue

        # Evaluate condition
        cond_name = rule.get("if")
        if not cond_name:
            continue
        cond_fn = CONDITION_MAP.get(cond_name)
        if not cond_fn:
            continue
        if not cond_fn(monster, room_id, rule):
            continue

        # Condition matched — resolve action parameters
        action_name = rule.get("do", "hold")
        resolver = ACTION_RESOLVERS.get(action_name)
        if not resolver:
            continue
        action = resolver(rule, monster, room_id)
        if action is None:
            continue  # resolution failed (e.g. no walkable tile), try next rule

        warmup = rule.get("warmup", 0)
        cooldown = rule.get("cooldown", 0)

        if warmup > 0:
            # Start warmup — lock in params, pause evaluation
            monster._pending_warmup = {
                "rule_index": i,
                "ticks": warmup,
                "cooldown": cooldown,
                "action": action,
            }
            return {"phase": "warmup", **action, "ticks": warmup}

        # No warmup — execute immediately
        if cooldown > 0:
            monster._rule_cooldowns[i] = cooldown
        _decrement_cooldowns(monster)
        return {"phase": "execute", **action}

    _decrement_cooldowns(monster)
    return None  # no matching rule


def _decrement_cooldowns(monster):
    """Decrement all rule cooldowns by 1, removing expired ones."""
    expired = []
    for k in monster._rule_cooldowns:
        monster._rule_cooldowns[k] -= 1
        if monster._rule_cooldowns[k] <= 0:
            expired.append(k)
    for k in expired:
        del monster._rule_cooldowns[k]
