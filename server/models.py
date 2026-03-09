"""Data classes for game entities — Player, Monster, Projectile."""

import time

from server.state import game
from server.constants import PLAYER_MAX_HP, STARTING_ROOM


class Player:
    def __init__(self, ws, name: str, description: str, color_index: int):
        self.ws = ws
        self.name = name
        self.description = description
        self.room = STARTING_ROOM
        self.x = 7
        self.y = 5
        self.direction = "down"
        self.color_index = color_index
        self.hp = PLAYER_MAX_HP
        self.max_hp = PLAYER_MAX_HP
        self.last_damage_time = 0.0
        self.last_move_time = 0.0
        self.last_attack_time = 0.0
        self.dancing = False
        self.guard_cooldowns = {}  # guard_key -> last_trigger_time
        self.quests = {}   # quest_id (str) -> stage (int)
        self.flags = set() # string flags, e.g. {"has_sword"}

    def quest(self, qid: str) -> int:
        return self.quests.get(qid, 0)

    def set_quest(self, qid: str, stage: int):
        self.quests[qid] = stage

    def has_flag(self, flag: str) -> bool:
        return flag in self.flags

    def grant_flag(self, flag: str):
        self.flags.add(flag)


class Monster:
    def __init__(self, x, y, kind="slime"):
        self.x = x
        self.y = y
        self.spawn_x = x
        self.spawn_y = y
        self.kind = kind
        self.alive = True
        self.last_tick_time = time.monotonic()
        stats = game.monster_stats.get(kind, {"hp": 1, "tick_rate": 0.5, "damage": 1})
        self.hp = stats["hp"]
        self.max_hp = stats["hp"]
        self.tick_rate = stats["tick_rate"]  # ticks per second (higher = faster)
        self.damage = stats.get("damage", 1)
        # Behavior engine data (None = use default wander)
        self.behavior = game.monster_behaviors.get(kind)
        # Rule cooldown tracking: rule_index -> ticks remaining
        self._rule_cooldowns = {}
        # Pending warmup: {rule_index, ticks, action} or None
        self._pending_warmup = None
        # Patrol state (index into route string, shared across patrol rules)
        self._patrol_index = 0

    @property
    def tick_interval(self):
        """Seconds between ticks (1.0 / tick_rate)."""
        return 1.0 / self.tick_rate if self.tick_rate > 0 else 2.0

    @property
    def intangible(self):
        """True when monster can't be hit or deal contact damage (e.g. mid-teleport)."""
        pw = self._pending_warmup
        return pw is not None and pw["action"].get("action") == "teleport"


class Projectile:
    def __init__(self, x, y, dx, dy, damage, color, room_id, speed=1, piercing=False):
        self.x = x
        self.y = y
        self.dx = dx
        self.dy = dy
        self.damage = damage
        self.color = color
        self.room_id = room_id
        self.speed = speed        # tiles per move tick
        self.piercing = piercing  # pass through players (hit all in path)
