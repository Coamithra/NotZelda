"""
Behavior Engine — consolidated monster AI state machine.

Contains both rule evaluation ("brain") and action execution ("body") for all
monster behaviors.  Adding a new action type requires changes only in this
file: add a resolver, an execution handler, and optionally a warmup handler.

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

import math

from server.state import game
from server.constants import ROOM_COLS, ROOM_ROWS, MOVE_STEP
from server.models import WalkState, Projectile
from server.net import avatars_in_room
from server.lifecycle import set_monster_idle


DEFAULT_BEHAVIOR = {"rules": [{"if": "always", "do": "move", "direction": "random"}]}

CARDINAL_DIRS = {
    "up":    (0, -1),
    "down":  (0,  1),
    "left":  (-1, 0),
    "right": (1,  0),
}

_PATROL_DIRS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}

# Module-level engine instance — set by mud_server at startup via init()
engine = None


def init(apply_damage):
    """Create the module-level engine instance.  Called once by mud_server."""
    global engine
    engine = BehaviorEngine(apply_damage)


class BehaviorEngine:
    """Consolidated monster AI: conditions, resolvers, execution, state machine."""

    def __init__(self, apply_damage):
        self._apply_damage = apply_damage

        self._condition_map = {
            "player_within": self._cond_player_within,
            "player_beyond": self._cond_player_beyond,
            "player_in_range_line": self._cond_player_in_range_line,
            "hp_below": self._cond_hp_below,
            "hp_above": self._cond_hp_above,
            "random_chance": self._cond_random_chance,
            "always": self._cond_always,
        }

        self._action_resolvers = {
            "move": self._resolve_move_with_distance,
            "hold": lambda rule, monster, room_id: {"action": "hold"},
            "projectile": self._resolve_projectile,
            "charge": self._resolve_charge,
            "teleport": self._resolve_teleport,
            "area": self._resolve_area,
        }

        self._warmup_handlers = {
            "charge": self._warmup_charge,
            "teleport": self._warmup_teleport,
            "area": self._warmup_area,
        }

        self._exec_handlers = {
            "projectile": self._exec_projectile,
            "charge": self._exec_charge,
            "teleport": self._exec_teleport,
            "area": self._exec_area,
        }

    # -------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------

    def _nearest_player(self, monster, room_id):
        """Find the nearest living player (Manhattan distance from closest tile).

        For multi-tile monsters, distance is measured from the closest occupied tile.
        Returns (player, dist) or (None, inf).
        """
        if monster.x is None or monster.y is None:
            return None, float("inf")
        best = None
        best_dist = float("inf")
        w = getattr(monster, "width", 1)
        h = getattr(monster, "height", 1)
        for p, a in avatars_in_room(room_id):
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

    def _is_walkable(self, x, y, room_id):
        """Check if a tile is in bounds, walkable, and not occupied by an NPC."""
        if x < 0 or x >= ROOM_COLS or y < 0 or y >= ROOM_ROWS:
            return False
        tilemap = game.rooms[room_id]["tilemap"]
        if not game.is_monster_walkable_tile(tilemap[y][x]):
            return False
        guards = game.guards.get(room_id, [])
        if any(g["x"] == x and g["y"] == y for g in guards):
            return False
        return True


    def _has_los(self, x1, y1, x2, y2, room_id):
        """Check line of sight between two points on the same row or column."""
        if x1 == x2:
            step = 1 if y2 > y1 else -1
            for y in range(y1 + step, y2, step):
                if not self._is_walkable(x1, y, room_id):
                    return False
        elif y1 == y2:
            step = 1 if x2 > x1 else -1
            for x in range(x1 + step, x2, step):
                if not self._is_walkable(x, y1, room_id):
                    return False
        return True

    def _is_walkable_at(self, x, y, w, h, room_id):
        """Check if a w x h footprint at float position (x, y) is fully walkable."""
        room = game.rooms.get(room_id)
        if not room:
            return False
        tilemap = room["tilemap"]
        min_tx = math.floor(x)
        max_tx = math.ceil(x + w) - 1
        min_ty = math.floor(y)
        max_ty = math.ceil(y + h) - 1
        for ty in range(min_ty, max_ty + 1):
            for tx in range(min_tx, max_tx + 1):
                if tx < 0 or tx >= ROOM_COLS or ty < 0 or ty >= ROOM_ROWS:
                    return False
                if not game.is_monster_walkable_tile(tilemap[ty][tx]):
                    return False
        # Guard (NPC) overlap — AABB since entity may be at fractional position
        for g in game.guards.get(room_id, []):
            if (x < g["x"] + 1 and x + w > g["x"] and
                y < g["y"] + 1 and y + h > g["y"]):
                return False
        return True

    def can_move_to(self, monster, x, y, room_id):
        """Check if a monster (possibly multi-tile) can move to float position (x, y)."""
        w = getattr(monster, "width", 1)
        h = getattr(monster, "height", 1)
        return self._is_walkable_at(x, y, w, h, room_id)

    # -------------------------------------------------------------------
    # Condition evaluators — return True/False
    # -------------------------------------------------------------------

    def _cond_player_within(self, monster, room_id, rule):
        """True if nearest living player is within `range` tiles (Manhattan)."""
        _, dist = self._nearest_player(monster, room_id)
        return dist <= rule.get("range", 3)

    def _cond_player_beyond(self, monster, room_id, rule):
        """True if nearest living player is farther than `range` tiles (Manhattan)."""
        _, dist = self._nearest_player(monster, room_id)
        return dist > rule.get("range", 3)

    def _cond_player_in_range_line(self, monster, room_id, rule):
        """True if a player is on the same row or column within `range` tiles.

        For multi-tile monsters, checks if the player shares a row/column with
        any tile of the monster's footprint. If `los` is true, obstacles between
        monster and player block the check.
        """
        max_range = rule.get("range", 3)
        check_los = rule.get("los", False)
        player, dist = self._nearest_player(monster, room_id)
        if player is None or dist > max_range:
            return False
        pa = player.avatar
        if pa is None:
            return False

        w = getattr(monster, "width", 1)
        h = getattr(monster, "height", 1)

        # Check if player shares a column with any tile in monster's width (float-aware)
        for dx in range(w):
            mx = monster.x + dx
            if abs(pa.x - mx) < 0.75:
                if check_los and not self._has_los(int(round(mx)), int(round(monster.y)), int(round(pa.x)), int(round(pa.y)), room_id):
                    continue
                return True

        # Check if player shares a row with any tile in monster's height (float-aware)
        for dy in range(h):
            my = monster.y + dy
            if abs(pa.y - my) < 0.75:
                if check_los and not self._has_los(int(round(monster.x)), int(round(my)), int(round(pa.x)), int(round(pa.y)), room_id):
                    continue
                return True

        return False

    def _cond_hp_below(self, monster, room_id, rule):
        """True if monster HP is below `value` hit points."""
        return monster.hp < rule.get("value", 2)

    def _cond_hp_above(self, monster, room_id, rule):
        """True if monster HP is above `value` hit points."""
        return monster.hp > rule.get("value", 1)

    def _cond_random_chance(self, monster, room_id, rule):
        """True with `value`% probability per tick."""
        return random.random() * 100 < rule.get("value", 50)

    def _cond_always(self, monster, room_id, rule):
        return True

    # -------------------------------------------------------------------
    # Direction resolution
    # -------------------------------------------------------------------

    def _resolve_direction(self, direction, monster, room_id):
        """Resolve a direction string to (dx, dy).

        Returns (dx, dy) or None if no valid direction.
        """
        if direction in CARDINAL_DIRS:
            return CARDINAL_DIRS[direction]

        player, _ = self._nearest_player(monster, room_id)

        if direction == "player":
            if player is None or player.avatar is None:
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
            if player is None or player.avatar is None:
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

    # -------------------------------------------------------------------
    # Action resolvers — build action dicts with locked-in parameters
    # -------------------------------------------------------------------

    def resolve_move(self, rule, monster, room_id):
        """Resolve a move action. Returns {"action": "move", "x", "y"} or None.

        Resolves MOVE_STEP tiles per call (1.0 tile).
        """
        direction = rule.get("direction", "random")
        s = MOVE_STEP

        if direction == "patrol":
            return self._resolve_patrol_move(rule, monster, room_id)

        if direction == "random":
            dirs = [(0, -s), (0, s), (-s, 0), (s, 0)]
            random.shuffle(dirs)
            for dx, dy in dirs:
                nx, ny = monster.x + dx, monster.y + dy
                if self.can_move_to(monster, nx, ny, room_id):
                    return {"action": "move", "x": nx, "y": ny, "distance": 1}
            return None

        if direction == "player":
            target, _ = self._nearest_player(monster, room_id)
            if target is None or target.avatar is None:
                return self.resolve_move({"direction": "random"}, monster, room_id)
            ta = target.avatar
            best_dir = None
            best_dist = float("inf")
            dirs = [(0, -s), (0, s), (-s, 0), (s, 0)]
            random.shuffle(dirs)
            for dx, dy in dirs:
                nx, ny = monster.x + dx, monster.y + dy
                if not self.can_move_to(monster, nx, ny, room_id):
                    continue
                dist = abs(ta.x - nx) + abs(ta.y - ny)
                if dist < best_dist:
                    best_dist = dist
                    best_dir = (dx, dy)
            if best_dir:
                return {"action": "move", "x": monster.x + best_dir[0], "y": monster.y + best_dir[1], "distance": 1}
            return None

        if direction == "away":
            target, _ = self._nearest_player(monster, room_id)
            if target is None or target.avatar is None:
                return self.resolve_move({"direction": "random"}, monster, room_id)
            ta = target.avatar
            best_dir = None
            best_dist = -1
            dirs = [(0, -s), (0, s), (-s, 0), (s, 0)]
            random.shuffle(dirs)
            for dx, dy in dirs:
                nx, ny = monster.x + dx, monster.y + dy
                if not self.can_move_to(monster, nx, ny, room_id):
                    continue
                dist = abs(ta.x - nx) + abs(ta.y - ny)
                if dist > best_dist:
                    best_dist = dist
                    best_dir = (dx, dy)
            if best_dir:
                return {"action": "move", "x": monster.x + best_dir[0], "y": monster.y + best_dir[1], "distance": 1}
            return None

        # Cardinal direction — full tile step
        d = CARDINAL_DIRS.get(direction)
        if d:
            nx, ny = monster.x + d[0] * s, monster.y + d[1] * s
            if self.can_move_to(monster, nx, ny, room_id):
                return {"action": "move", "x": nx, "y": ny, "distance": 1}
        return None

    def _resolve_patrol_move(self, rule, monster, room_id):
        """Move 1 step along a patrol route string (e.g. 'RRDDLLUU').

        Each route letter produces a full-tile step.
        Skips blocked steps within the same tick so the monster doesn't stall
        at walls.  Falls back to random wander if no route or all steps blocked.
        """
        route = rule.get("patrol_route", "")
        if not route:
            return self.resolve_move({"direction": "random"}, monster, room_id)

        start_idx = getattr(monster, "_patrol_index", 0) % len(route)
        for i in range(len(route)):
            idx = (start_idx + i) % len(route)
            step = route[idx].upper()
            d = _PATROL_DIRS.get(step)
            if not d:
                continue
            nx, ny = monster.x + d[0] * MOVE_STEP, monster.y + d[1] * MOVE_STEP
            if self.can_move_to(monster, nx, ny, room_id):
                monster._patrol_index = (idx + 1) % len(route)
                return {"action": "move", "x": nx, "y": ny, "distance": 1}
        # All steps blocked — advance index so we don't retry the same start next tick
        monster._patrol_index = (start_idx + 1) % len(route)
        return None

    def _resolve_projectile(self, rule, monster, room_id):
        """Resolve projectile action. Returns action dict or None."""
        direction = rule.get("direction", "player")
        d = self._resolve_direction(direction, monster, room_id)
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

    def _resolve_charge(self, rule, monster, room_id):
        """Resolve charge action. Returns action dict or None."""
        direction = rule.get("direction", "player")
        d = self._resolve_direction(direction, monster, room_id)
        if d is None:
            return None
        return {
            "action": "charge",
            "dx": d[0], "dy": d[1],
            "range": rule.get("range", 3),
            "damage": rule.get("damage", monster.damage),
        }

    def _resolve_teleport(self, rule, monster, room_id):
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
            player, player_dist = self._nearest_player(monster, room_id)
            if player is None or player.avatar is None:
                return None
            if player_dist > max_range:
                return None
            pa = player.avatar
            cx, cy = int(round(pa.x)), int(round(pa.y))
        elif target_mode == "away":
            player, _ = self._nearest_player(monster, room_id)
            if player is None or player.avatar is None:
                cx, cy = monster.x, monster.y
            else:
                pa = player.avatar
                dx = monster.x - int(round(pa.x))
                dy = monster.y - int(round(pa.y))
                length = max(abs(dx), abs(dy), 1)
                cx = monster.x + int(dx / length * max_range)
                cy = monster.y + int(dy / length * max_range)
                cx = max(0, min(ROOM_COLS - 1, cx))
                cy = max(0, min(ROOM_ROWS - 1, cy))
        else:  # "random"
            cx = random.randint(0, ROOM_COLS - 1)
            cy = random.randint(0, ROOM_ROWS - 1)

        # Find a walkable position within drift of the center point
        candidates = []
        mx_r, my_r = round(monster.x), round(monster.y)
        for ddx in range(-drift, drift + 1):
            for ddy in range(-drift, drift + 1):
                tx, ty = cx + ddx, cy + ddy
                dist_from_monster = abs(tx - mx_r) + abs(ty - my_r)
                if dist_from_monster > max_range:
                    continue
                if dist_from_monster == 0:
                    continue  # don't teleport to self
                if self.can_move_to(monster, tx, ty, room_id):
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

    def _resolve_area(self, rule, monster, room_id):
        """Resolve area attack action. Returns action dict."""
        return {
            "action": "area",
            "x": monster.x,
            "y": monster.y,
            "width": getattr(monster, "width", 1),
            "height": getattr(monster, "height", 1),
            "range": rule.get("range", 2),
            "damage": rule.get("damage", monster.damage),
        }

    def _resolve_move_with_distance(self, rule, monster, room_id):
        """Wrapper that attaches distance and direction to the resolved move."""
        result = self.resolve_move(rule, monster, room_id)
        if result is not None:
            tile_dist = max(1, int(rule.get("distance", 1)))
            result["distance"] = tile_dist
            result["direction"] = rule.get("direction", "random")
        return result

    # -------------------------------------------------------------------
    # Action execution (moved from combat.py)
    # -------------------------------------------------------------------

    def start_walk(self, monster, room_id, monster_idx, action, msgs, now):
        """Start a smooth walk — set monster state and broadcast walk_started."""
        nx, ny = action["x"], action["y"]
        remaining = action.get("distance", 1) - 1  # distance includes this step
        # Scale walk_time by step distance (0.5-tile step = half the time)
        step_dist = abs(nx - monster.x) + abs(ny - monster.y)
        walk_time = monster.walk_time * step_dist
        monster.state = "walking"
        monster.move_seq += 1
        monster.state_data = WalkState(
            from_x=monster.x, from_y=monster.y,
            to_x=nx, to_y=ny,
            start_time=now,
            walk_time=walk_time,
            room_id=room_id,
            monster_idx=monster_idx,
            remaining_distance=remaining,
            direction=action.get("direction", "random"),
            seq=monster.move_seq,
        )
        msgs.append(("broadcast", room_id, {
            "type": "monster_walk_started",
            "id": monster_idx,
            "from_x": monster.x, "from_y": monster.y,
            "to_x": nx, "to_y": ny,
            "walk_time": walk_time,
            "seq": monster.move_seq,
        }, None))

    def _exec_projectile(self, monster, room_id, monster_idx, action, msgs):
        """Spawn a projectile from the monster in the resolved direction."""
        dx, dy = action["dx"], action["dy"]
        damage = action.get("damage", 1)
        color = action.get("sprite_color", "#ff0000")
        speed = action.get("speed", 1)
        piercing = action.get("piercing", False)

        # For multi-tile monsters, spawn from the edge tile closest to the direction
        w, h = monster.width, monster.height
        if dx > 0:
            spawn_col = monster.x + w - 1  # rightmost column
        elif dx < 0:
            spawn_col = monster.x           # leftmost column
        else:
            spawn_col = monster.x + w // 2  # center
        if dy > 0:
            spawn_row = monster.y + h - 1   # bottom row
        elif dy < 0:
            spawn_row = monster.y            # top row
        else:
            spawn_row = monster.y + h // 2   # center
        start_x = round(spawn_col + dx)
        start_y = round(spawn_row + dy)
        if start_x < 0 or start_x >= ROOM_COLS or start_y < 0 or start_y >= ROOM_ROWS:
            return
        room = game.rooms.get(room_id)
        if not room:
            return
        if not game.is_walkable_tile(room["tilemap"][start_y][start_x]):
            return

        proj_id = game.next_projectile_id
        game.next_projectile_id += 1
        proj = Projectile(start_x, start_y, dx, dy, damage, color, room_id, speed, piercing)

        if room_id not in game.room_projectiles:
            game.room_projectiles[room_id] = {}
        game.room_projectiles[room_id][proj_id] = proj

        msgs.append(("broadcast", room_id, {
            "type": "projectile_spawned",
            "id": proj_id,
            "x": start_x,
            "y": start_y,
            "dx": dx,
            "dy": dy,
            "color": color,
        }, None))

        # Check if a player is already at the spawn tile (AABB overlap)
        for p, a in avatars_in_room(room_id):
            if p.hp > 0 and a.x < start_x + 1 and a.x + 1 > start_x and a.y < start_y + 1 and a.y + 1 > start_y:
                msgs.append(("broadcast", room_id, {
                    "type": "projectile_hit", "id": proj_id,
                    "x": start_x, "y": start_y,
                }, None))
                self._apply_damage(p, damage, room_id, msgs, start_x, start_y)
                proj.hit_entities.add(id(p))
                if not piercing:
                    game.room_projectiles.get(room_id, {}).pop(proj_id, None)
                    return

    def _warmup_charge(self, monster, room_id, monster_idx, action, msgs):
        """Send charge prep visuals when warmup starts.

        Does NOT increment move_seq — charge_prep is visual-only (no position
        change).  The seq sent here lets the client detect staleness without
        advancing the counter past the preceding walk/idle state."""
        dx, dy = action["dx"], action["dy"]
        max_range = action.get("range", 3)

        lane = []
        seen = set()
        # Snap to nearest integer for charge path (charges move in whole tiles)
        nx, ny = round(monster.x), round(monster.y)
        for _ in range(max_range):
            nx += dx
            ny += dy
            if not self.can_move_to(monster, nx, ny, room_id):
                break
            # Expand to full footprint for multi-tile monsters
            for ox in range(monster.width):
                for oy in range(monster.height):
                    tile = (nx + ox, ny + oy)
                    if tile not in seen:
                        seen.add(tile)
                        lane.append([nx + ox, ny + oy])

        msgs.append(("broadcast", room_id, {
            "type": "charge_prep",
            "id": monster_idx,
            "dx": dx,
            "dy": dy,
            "lane": lane,
            "seq": monster.move_seq,
            "duration": monster.state_data["duration"],
        }, None))

    def _exec_charge(self, monster, room_id, monster_idx, action, msgs):
        """Execute the charge dash with locked-in direction."""
        dx, dy = action["dx"], action["dy"]
        max_range = action.get("range", 3)
        damage = action.get("damage", monster.damage)
        path = []

        # Snap to nearest integer for charge path (charges move in whole tiles)
        nx, ny = round(monster.x), round(monster.y)
        for _ in range(max_range):
            nx += dx
            ny += dy
            if not self.can_move_to(monster, nx, ny, room_id):
                break
            path.append([nx, ny])

        if not path:
            return

        end_x, end_y = path[-1]
        monster.x = end_x
        monster.y = end_y
        monster.move_seq += 1

        # Expand path to full footprint for the visual charge trail
        w, h = monster.width, monster.height
        trail = []
        if w == 1 and h == 1:
            trail = path
        else:
            seen = set()
            for px, py in path:
                for ox in range(w):
                    for oy in range(h):
                        tile = (px + ox, py + oy)
                        if tile not in seen:
                            seen.add(tile)
                            trail.append([px + ox, py + oy])

        msgs.append(("broadcast", room_id, {
            "type": "monster_charged",
            "id": monster_idx,
            "path": trail,
            "x": end_x,
            "y": end_y,
            "seq": monster.move_seq,
        }, None))

        # Check if player was hit — AABB overlap with charge path
        for p, a in avatars_in_room(room_id):
            if p.hp > 0 and any(
                a.x < px + w and a.x + 1 > px and a.y < py + h and a.y + 1 > py
                for px, py in path
            ):
                self._apply_damage(p, damage, room_id, msgs, monster.x, monster.y)

    def _warmup_teleport(self, monster, room_id, monster_idx, action, msgs):
        """Send teleport start visuals when warmup starts (monster fades out)."""
        msgs.append(("broadcast", room_id, {
            "type": "teleport_start",
            "id": monster_idx,
            "target_x": action["target_x"],
            "target_y": action["target_y"],
            "delay": action.get("ticks", 1) * monster.decision_time,
            "damage_radius": action.get("damage_radius", 1),
        }, None))

    def _exec_teleport(self, monster, room_id, monster_idx, action, msgs):
        """Execute teleport — move monster to target and deal damage."""
        target_x = action["target_x"]
        target_y = action["target_y"]
        damage = action.get("damage", monster.damage)

        monster.x = target_x
        monster.y = target_y
        monster.move_seq += 1

        msgs.append(("broadcast", room_id, {
            "type": "teleport_end",
            "id": monster_idx,
            "x": target_x,
            "y": target_y,
            "seq": monster.move_seq,
        }, None))

        # Damage players within damage_radius of landing position
        damage_radius = action.get("damage_radius", 1)
        if damage > 0 and damage_radius >= 0:
            w, h = monster.width, monster.height
            for p, a in avatars_in_room(room_id):
                if p.hp > 0:
                    nearest_x = max(monster.x, min(a.x, monster.x + w - 1))
                    nearest_y = max(monster.y, min(a.y, monster.y + h - 1))
                    if abs(a.x - nearest_x) + abs(a.y - nearest_y) <= damage_radius:
                        self._apply_damage(p, damage, room_id, msgs, monster.x, monster.y)

    def _warmup_area(self, monster, room_id, monster_idx, action, msgs):
        """Send area warning visuals when warmup starts."""
        msg = {
            "type": "area_warning",
            "id": monster_idx,
            "x": action["x"],
            "y": action["y"],
            "range": action["range"],
            "duration": action.get("ticks", 1) * monster.decision_time,
        }
        if action.get("width", 1) > 1:
            msg["width"] = action["width"]
        if action.get("height", 1) > 1:
            msg["height"] = action["height"]
        msgs.append(("broadcast", room_id, msg, None))

    def _exec_area(self, monster, room_id, monster_idx, action, msgs):
        """Execute area attack — damage all players within range."""
        damage = action.get("damage", monster.damage)
        range_val = action.get("range", 2)
        # Use locked-in position from warmup
        ax = action.get("x", monster.x)
        ay = action.get("y", monster.y)
        aw = action.get("width", 1)
        ah = action.get("height", 1)

        atk_msg = {
            "type": "area_attack",
            "id": monster_idx,
            "x": ax,
            "y": ay,
            "range": range_val,
        }
        if aw > 1:
            atk_msg["width"] = aw
        if ah > 1:
            atk_msg["height"] = ah
        msgs.append(("broadcast", room_id, atk_msg, None))

        for p, a in avatars_in_room(room_id):
            if p.hp > 0:
                # Manhattan distance from nearest tile in the boss footprint
                nearest_x = max(ax, min(a.x, ax + aw - 1))
                nearest_y = max(ay, min(a.y, ay + ah - 1))
                dist = abs(a.x - nearest_x) + abs(a.y - nearest_y)
                if dist <= range_val:
                    self._apply_damage(p, damage, room_id, msgs, ax, ay)

    # -------------------------------------------------------------------
    # Rule evaluation
    # -------------------------------------------------------------------

    def _evaluate_rules(self, monster, room_id):
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
            cond_fn = self._condition_map.get(cond_name)
            if not cond_fn:
                continue
            if not cond_fn(monster, room_id, rule):
                continue

            # Condition matched — resolve action parameters
            action_name = rule.get("do", "hold")
            resolver = self._action_resolvers.get(action_name)
            if not resolver:
                continue
            action = resolver(rule, monster, room_id)
            if action is None:
                continue  # resolution failed (e.g. no walkable tile), try next rule

            warmup = rule.get("warmup", 0)
            cooldown = rule.get("cooldown", 0)

            if cooldown > 0:
                monster._rule_cooldowns[i] = cooldown

            self._decrement_cooldowns(monster)
            return {**action, "warmup": warmup, "cooldown": cooldown}

        self._decrement_cooldowns(monster)
        return None  # no matching rule

    def _decrement_cooldowns(self, monster):
        """Decrement all rule cooldowns by 1, removing expired ones."""
        expired = []
        for k in monster._rule_cooldowns:
            monster._rule_cooldowns[k] -= 1
            if monster._rule_cooldowns[k] <= 0:
                expired.append(k)
        for k in expired:
            del monster._rule_cooldowns[k]

    # -------------------------------------------------------------------
    # State machine tick (moved from combat.py)
    # -------------------------------------------------------------------

    def tick_monster_state(self, monster, room_id, i, now, msgs):
        """Process one monster's state machine tick (called from 33ms loop)."""
        state = monster.state

        if state == "walking":
            # Walk progression handled by _tick_all_monsters in combat.py
            return

        if state == "knockback":
            # Knockback progression handled by _tick_all_monsters in combat.py
            return

        if state in ("charging", "teleporting", "area"):
            # Warmup — time-based end
            sd = monster.state_data
            if now >= sd["end_time"]:
                action_name = sd["action_name"]
                action = sd["action"]
                handler = self._exec_handlers.get(action_name)
                if handler:
                    handler(monster, room_id, i, action, msgs)
                set_monster_idle(monster, room_id, i, msgs)
            return

        # state == "idle" — decision timer runs continuously (even during other states)
        # so if walk/warmup took longer than decision_time, we evaluate immediately
        if now - monster.last_action_time < monster.decision_time:
            return  # not time to decide yet

        # Decision point — reset timer regardless of outcome
        monster.last_action_time = now

        result = self._evaluate_rules(monster, room_id)
        if result is None:
            return

        action_name = result.get("action")
        warmup = result.get("warmup", 0)

        if action_name == "move":
            self.start_walk(monster, room_id, i, result, msgs, now)
            return

        if action_name == "hold":
            return

        # Projectile — instant, no state change
        if action_name == "projectile":
            handler = self._exec_handlers.get("projectile")
            if handler:
                handler(monster, room_id, i, result, msgs)
            return

        # Warmup actions: charge, teleport, area
        if warmup > 0 and action_name in self._warmup_handlers:
            state_name = {"charge": "charging", "teleport": "teleporting", "area": "area"}
            monster.state = state_name.get(action_name, "idle")
            warmup_duration = warmup * monster.decision_time
            monster.state_data = {
                "end_time": now + warmup_duration,
                "action_name": action_name,
                "action": result,
                "duration": warmup_duration,
            }
            handler = self._warmup_handlers.get(action_name)
            if handler:
                handler(monster, room_id, i, result, msgs)
            return

        # No warmup — execute immediately
        handler = self._exec_handlers.get(action_name)
        if handler:
            handler(monster, room_id, i, result, msgs)
