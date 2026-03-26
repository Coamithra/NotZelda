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
    """Find the nearest living player (Manhattan distance from closest tile).

    For multi-tile monsters, distance is measured from the closest occupied tile.
    Returns (player, dist) or (None, inf).
    """
    best = None
    best_dist = float("inf")
    w = getattr(monster, "width", 1)
    h = getattr(monster, "height", 1)
    for p, a in _players_in_room(room_id):
        if p.hp <= 0:
            continue
        # Clamp player position to the monster's footprint for distance calc
        cx = max(monster.x, min(a.x, monster.x + w - 1))
        cy = max(monster.y, min(a.y, monster.y + h - 1))
        dist = abs(a.x - cx) + abs(a.y - cy)
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


def _is_walkable_multi(x, y, w, h, room_id):
    """Check if all tiles in a w x h footprint at (x, y) are walkable."""
    for dy in range(h):
        for dx in range(w):
            if not _is_walkable(x + dx, y + dy, room_id):
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

    For multi-tile monsters, checks if the player shares a row/column with
    any tile of the monster's footprint. If `los` is true, obstacles between
    monster and player block the check.
    """
    max_range = rule.get("range", 3)
    check_los = rule.get("los", False)
    player, dist = _nearest_player(monster, room_id)
    if player is None or dist > max_range:
        return False
    pa = player.avatar

    w = getattr(monster, "width", 1)
    h = getattr(monster, "height", 1)

    # Check if player shares a column with any tile in monster's width (float-aware)
    for dx in range(w):
        mx = monster.x + dx
        if abs(pa.x - mx) < 0.75:
            if check_los and not _has_los(mx, monster.y, int(round(pa.x)), int(round(pa.y)), room_id):
                continue
            return True

    # Check if player shares a row with any tile in monster's height (float-aware)
    for dy in range(h):
        my = monster.y + dy
        if abs(pa.y - my) < 0.75:
            if check_los and not _has_los(monster.x, my, int(round(pa.x)), int(round(pa.y)), room_id):
                continue
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
        pa = player.avatar
        dx = pa.x - monster.x
        dy = pa.y - monster.y
        if dx == 0 and dy == 0:
            return None
        if abs(dx) >= abs(dy):
            return (1 if dx > 0 else -1, 0)
        else:
            return (0, 1 if dy > 0 else -1)

    if direction == "away":
        if player is None:
            return None
        pa = player.avatar
        dx = monster.x - pa.x
        dy = monster.y - pa.y
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

def _can_move_to(monster, x, y, room_id):
    """Check if a monster (possibly multi-tile) can move to position (x, y)."""
    w = getattr(monster, "width", 1)
    h = getattr(monster, "height", 1)
    if w == 1 and h == 1:
        return _is_walkable(x, y, room_id)
    return _is_walkable_multi(x, y, w, h, room_id)


def _resolve_move(rule, monster, room_id):
    """Resolve a move action. Returns {"action": "move", "x", "y", "distance", "direction"} or None.

    Resolves 1 tile per call. The `distance` param (default 1) is passed through
    so the caller can chain multiple walks back-to-back.
    """
    direction = rule.get("direction", "random")

    if direction == "patrol":
        return _resolve_patrol_move(rule, monster, room_id)

    if direction == "random":
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = monster.x + dx, monster.y + dy
            if _can_move_to(monster, nx, ny, room_id):
                return {"action": "move", "x": nx, "y": ny}
        return None

    if direction == "player":
        target, _ = _nearest_player(monster, room_id)
        if target is None:
            return _resolve_move({"direction": "random"}, monster, room_id)
        ta = target.avatar
        best_dir = None
        best_dist = float("inf")
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = monster.x + dx, monster.y + dy
            if not _can_move_to(monster, nx, ny, room_id):
                continue
            dist = abs(ta.x - nx) + abs(ta.y - ny)
            if dist < best_dist:
                best_dist = dist
                best_dir = (dx, dy)
        if best_dir:
            return {"action": "move", "x": monster.x + best_dir[0], "y": monster.y + best_dir[1]}
        return None

    if direction == "away":
        target, _ = _nearest_player(monster, room_id)
        if target is None:
            return _resolve_move({"direction": "random"}, monster, room_id)
        ta = target.avatar
        best_dir = None
        best_dist = -1
        dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
        random.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = monster.x + dx, monster.y + dy
            if not _can_move_to(monster, nx, ny, room_id):
                continue
            dist = abs(ta.x - nx) + abs(ta.y - ny)
            if dist > best_dist:
                best_dist = dist
                best_dir = (dx, dy)
        if best_dir:
            return {"action": "move", "x": monster.x + best_dir[0], "y": monster.y + best_dir[1]}
        return None

    # Cardinal direction — 1 tile
    d = CARDINAL_DIRS.get(direction)
    if d:
        nx, ny = monster.x + d[0], monster.y + d[1]
        if _can_move_to(monster, nx, ny, room_id):
            return {"action": "move", "x": nx, "y": ny}
    return None


_PATROL_DIRS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}


def _resolve_patrol_move(rule, monster, room_id):
    """Move 1 step along a patrol route string (e.g. 'RRDDLLUU').

    Skips blocked steps within the same tick so the monster doesn't stall
    at walls.  Falls back to random wander if no route or all steps blocked.
    """
    route = rule.get("patrol_route", "")
    if not route:
        return _resolve_move({"direction": "random"}, monster, room_id)

    start_idx = getattr(monster, "_patrol_index", 0) % len(route)
    for i in range(len(route)):
        idx = (start_idx + i) % len(route)
        step = route[idx].upper()
        d = _PATROL_DIRS.get(step)
        if not d:
            continue
        nx, ny = monster.x + d[0], monster.y + d[1]
        if _can_move_to(monster, nx, ny, room_id):
            monster._patrol_index = (idx + 1) % len(route)
            return {"action": "move", "x": nx, "y": ny}
    # All steps blocked — advance index so we don't retry the same start next tick
    monster._patrol_index = (start_idx + 1) % len(route)
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

    # Determine center point (must be integer tile coords for tilemap lookups)
    if target_mode == "player":
        player, player_dist = _nearest_player(monster, room_id)
        if player is None:
            return None
        if player_dist > max_range:
            return None
        pa = player.avatar
        cx, cy = int(round(pa.x)), int(round(pa.y))
    elif target_mode == "away":
        player, _ = _nearest_player(monster, room_id)
        if player is None:
            cx, cy = monster.x, monster.y
        else:
            pa = player.avatar
            dx = monster.x - int(round(pa.x))
            dy = monster.y - int(round(pa.y))
            length = max(abs(dx), abs(dy), 1)
            cx = monster.x + int(dx / length * max_range)
            cy = monster.y + int(dy / length * max_range)
            cx = max(0, min(_ROOM_COLS - 1, cx))
            cy = max(0, min(_ROOM_ROWS - 1, cy))
    else:  # "random"
        cx = random.randint(0, _ROOM_COLS - 1)
        cy = random.randint(0, _ROOM_ROWS - 1)

    # Find a walkable position within drift of the center point
    candidates = []
    for ddx in range(-drift, drift + 1):
        for ddy in range(-drift, drift + 1):
            tx, ty = cx + ddx, cy + ddy
            dist_from_monster = abs(tx - monster.x) + abs(ty - monster.y)
            if dist_from_monster > max_range:
                continue
            if dist_from_monster == 0:
                continue  # don't teleport to self
            if _can_move_to(monster, tx, ty, room_id):
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
    # Center on middle of footprint for multi-tile monsters
    w = getattr(monster, "width", 1)
    h = getattr(monster, "height", 1)
    cx = monster.x + (w - 1) // 2
    cy = monster.y + (h - 1) // 2
    return {
        "action": "area",
        "x": cx,
        "y": cy,
        "range": rule.get("range", 2),
        "damage": rule.get("damage", monster.damage),
    }


def _resolve_move_with_distance(rule, monster, room_id):
    """Wrapper that attaches distance and direction to the resolved move."""
    result = _resolve_move(rule, monster, room_id)
    if result is not None:
        result["distance"] = max(1, int(rule.get("distance", 1)))
        result["direction"] = rule.get("direction", "random")
    return result


ACTION_RESOLVERS = {
    "move": _resolve_move_with_distance,
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
    """Evaluate behavior rules for a monster. Called only when state == "idle".

    Returns:
        {"action": ..., "warmup": int, "cooldown": int, ...params} — matched rule
        None — no matching rule
    """
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

        if cooldown > 0:
            monster._rule_cooldowns[i] = cooldown

        _decrement_cooldowns(monster)
        return {**action, "warmup": warmup, "cooldown": cooldown}

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
