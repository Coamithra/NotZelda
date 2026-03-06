"""
Behavior Engine — data-driven monster AI.

Rules are evaluated top-to-bottom; first match wins.
All conditions and actions are pre-coded functions.
The AI (or hand-authored data) composes them as JSON.

Example behavior:
    {
        "rules": [
            {"if": "hp_below_pct", "value": 30, "do": "flee"},
            {"if": "player_within", "range": 2, "do": "chase"},
            {"if": "player_within", "range": 6, "do": "hold"},
            {"default": "wander"}
        ]
    }
"""

import random
import time

# These are injected by mud_server at import time to avoid circular imports
_players_in_room = None
_ROOM_COLS = None
_ROOM_ROWS = None
_WALKABLE_TILES = None
_GUARDS = None
_ROOMS = None


def init(players_in_room, ROOM_COLS, ROOM_ROWS, WALKABLE_TILES, GUARDS, ROOMS):
    """Called once by mud_server to inject shared state references."""
    global _players_in_room, _ROOM_COLS, _ROOM_ROWS, _WALKABLE_TILES, _GUARDS, _ROOMS
    _players_in_room = players_in_room
    _ROOM_COLS = ROOM_COLS
    _ROOM_ROWS = ROOM_ROWS
    _WALKABLE_TILES = WALKABLE_TILES
    _GUARDS = GUARDS
    _ROOMS = ROOMS


DEFAULT_BEHAVIOR = {"rules": [{"default": "wander"}]}


# ---------------------------------------------------------------------------
# Condition evaluators — return True/False
# ---------------------------------------------------------------------------

def _nearest_player(monster, room_id):
    """Find the nearest player in the room (Manhattan distance). Returns (player, dist) or (None, inf)."""
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


def cond_player_within(monster, room_id, rule):
    """True if nearest living player is within `range` tiles (Manhattan)."""
    _, dist = _nearest_player(monster, room_id)
    return dist <= rule.get("range", 3)


def cond_player_beyond(monster, room_id, rule):
    """True if nearest living player is farther than `range` tiles (Manhattan)."""
    _, dist = _nearest_player(monster, room_id)
    return dist > rule.get("range", 3)


def cond_hp_below_pct(monster, room_id, rule):
    """True if monster HP is below `value`% of max."""
    max_hp = monster.max_hp if hasattr(monster, "max_hp") else monster.hp
    if max_hp <= 0:
        return False
    pct = (monster.hp / max_hp) * 100
    return pct < rule.get("value", 30)


def cond_hp_above_pct(monster, room_id, rule):
    """True if monster HP is above `value`% of max."""
    max_hp = monster.max_hp if hasattr(monster, "max_hp") else monster.hp
    if max_hp <= 0:
        return False
    pct = (monster.hp / max_hp) * 100
    return pct > rule.get("value", 70)


def cond_random_chance(monster, room_id, rule):
    """True with `value`% probability per tick."""
    return random.random() * 100 < rule.get("value", 50)


def cond_always(monster, room_id, rule):
    return True


def cond_can_attack(monster, room_id, rule):
    """True if at least one attack is off cooldown and a player is in range."""
    behavior = getattr(monster, "behavior", None)
    if not behavior:
        return False
    attacks = behavior.get("attacks", [])
    if not attacks:
        return False
    cooldowns = getattr(monster, "_attack_cooldowns", {})
    now = time.monotonic()
    player, player_dist = _nearest_player(monster, room_id)
    if player is None:
        return False
    has_charge_prep = getattr(monster, "_charge_prep", None) is not None
    for i, atk in enumerate(attacks):
        last_used = cooldowns.get(i, 0)
        cd = atk.get("cooldown", 1.0)
        if now - last_used >= cd and player_dist <= atk.get("range", 1):
            if atk.get("type") == "charge":
                if has_charge_prep or (monster.x != player.x and monster.y != player.y):
                    continue
            return True
    return False


def cond_player_in_attack_range(monster, room_id, rule):
    """True if a player is within range of any defined attack."""
    behavior = getattr(monster, "behavior", None)
    if not behavior:
        return False
    attacks = behavior.get("attacks", [])
    if not attacks:
        return False
    player, player_dist = _nearest_player(monster, room_id)
    if player is None:
        return False
    return any(player_dist <= atk.get("range", 1) for atk in attacks)


CONDITION_MAP = {
    "player_within": cond_player_within,
    "player_beyond": cond_player_beyond,
    "hp_below_pct": cond_hp_below_pct,
    "hp_above_pct": cond_hp_above_pct,
    "random_chance": cond_random_chance,
    "always": cond_always,
    "default": cond_always,
    "can_attack": cond_can_attack,
    "player_in_attack_range": cond_player_in_attack_range,
}


# ---------------------------------------------------------------------------
# Action executors — return (new_x, new_y) or None (no move)
# ---------------------------------------------------------------------------

def _is_walkable(x, y, room_id, monster_list=None, exclude_monster=None):
    """Check if a tile is walkable (in bounds, walkable tile, no NPC)."""
    if x < 0 or x >= _ROOM_COLS or y < 0 or y >= _ROOM_ROWS:
        return False
    tilemap = _ROOMS[room_id]["tilemap"]
    if tilemap[y][x] not in _WALKABLE_TILES:
        return False
    guards = _GUARDS.get(room_id, [])
    if any(g["x"] == x and g["y"] == y for g in guards):
        return False
    return True


def do_wander(monster, room_id):
    """Move to a random adjacent walkable tile."""
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
    random.shuffle(directions)
    for dx, dy in directions:
        nx, ny = monster.x + dx, monster.y + dy
        if _is_walkable(nx, ny, room_id):
            return nx, ny
    return None


def do_chase(monster, room_id):
    """Move toward the nearest player (greedy: pick adjacent tile that minimizes Manhattan distance)."""
    target, _ = _nearest_player(monster, room_id)
    if target is None:
        return do_wander(monster, room_id)

    best = None
    best_dist = float("inf")
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
    random.shuffle(directions)  # break ties randomly
    for dx, dy in directions:
        nx, ny = monster.x + dx, monster.y + dy
        if not _is_walkable(nx, ny, room_id):
            continue
        dist = abs(target.x - nx) + abs(target.y - ny)
        if dist < best_dist:
            best_dist = dist
            best = (nx, ny)
    return best


def do_flee(monster, room_id):
    """Move away from the nearest player (maximize Manhattan distance)."""
    target, _ = _nearest_player(monster, room_id)
    if target is None:
        return do_wander(monster, room_id)

    best = None
    best_dist = -1
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
    random.shuffle(directions)
    for dx, dy in directions:
        nx, ny = monster.x + dx, monster.y + dy
        if not _is_walkable(nx, ny, room_id):
            continue
        dist = abs(target.x - nx) + abs(target.y - ny)
        if dist > best_dist:
            best_dist = dist
            best = (nx, ny)
    return best


def do_patrol(monster, room_id):
    """Cycle through relative waypoint offsets from spawn position.

    The monster stores its patrol state in `_patrol_index` and uses
    waypoints from its behavior data. Waypoints are relative to spawn.
    If no waypoints are defined, falls back to wander.
    """
    waypoints = getattr(monster, "_patrol_waypoints", None)
    if not waypoints:
        return do_wander(monster, room_id)

    idx = getattr(monster, "_patrol_index", 0)
    spawn_x = getattr(monster, "spawn_x", monster.x)
    spawn_y = getattr(monster, "spawn_y", monster.y)

    wx, wy = waypoints[idx]
    target_x = spawn_x + wx
    target_y = spawn_y + wy

    # If we're at the waypoint, advance to the next one
    if monster.x == target_x and monster.y == target_y:
        idx = (idx + 1) % len(waypoints)
        monster._patrol_index = idx
        wx, wy = waypoints[idx]
        target_x = spawn_x + wx
        target_y = spawn_y + wy

    # Move one step toward the current waypoint (greedy)
    best = None
    best_dist = float("inf")
    directions = [(0, -1), (0, 1), (-1, 0), (1, 0)]
    random.shuffle(directions)
    for dx, dy in directions:
        nx, ny = monster.x + dx, monster.y + dy
        if not _is_walkable(nx, ny, room_id):
            continue
        dist = abs(target_x - nx) + abs(target_y - ny)
        if dist < best_dist:
            best_dist = dist
            best = (nx, ny)
    return best


def do_hold(monster, room_id):
    """Stay still."""
    return None


def do_attack(monster, room_id):
    """Signal attack intent — actual execution handled by the server."""
    return None


ACTION_MAP = {
    "wander": do_wander,
    "chase": do_chase,
    "flee": do_flee,
    "patrol": do_patrol,
    "hold": do_hold,
    "attack": do_attack,
}


# ---------------------------------------------------------------------------
# Rule evaluator
# ---------------------------------------------------------------------------

def evaluate_rules(monster, room_id):
    """Evaluate behavior rules top-to-bottom, return the action name of the first match.

    Returns the action string (e.g. "chase", "wander") or "wander" as fallback.
    """
    behavior = getattr(monster, "behavior", None) or DEFAULT_BEHAVIOR
    rules = behavior.get("rules", [])

    for rule in rules:
        # Handle {"default": "wander"} shorthand
        if "default" in rule:
            return rule["default"]

        cond_name = rule.get("if")
        if not cond_name:
            continue

        cond_fn = CONDITION_MAP.get(cond_name)
        if cond_fn and cond_fn(monster, room_id, rule):
            action = rule.get("do", "wander")
            return action

    return "wander"


def execute_action(action_name, monster, room_id):
    """Execute a movement action. Returns (new_x, new_y) or None if no move."""
    action_fn = ACTION_MAP.get(action_name, do_wander)
    return action_fn(monster, room_id)
