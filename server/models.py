"""Data classes for game entities — Player, Monster, Projectile."""

import time
from collections import deque

from server.state import game
from server.constants import PLAYER_MAX_HP, STARTING_ROOM


class Avatar:
    """Physical presence of a character in the game world.

    Holds position, direction, appearance, and transient collision state.
    When a player has no avatar (avatar is None), they have no physical
    presence — monsters can't target them and they don't appear to others.
    """
    def __init__(self, x: float, y: float, direction: str = "down"):
        self.x = x
        self.y = y
        self.direction = direction
        self.dancing = False
        self.last_reported_x = x       # last position relayed to other clients
        self.last_reported_y = y
        self.pending_collisions = {}   # id(monster) -> {monster, room_id, time, knockback data}


class Player:
    def __init__(self, ws, name: str, description: str, color_index: int):
        self.ws = ws
        self.name = name
        self.description = description
        self.room = STARTING_ROOM
        self.color_index = color_index
        self.hp = PLAYER_MAX_HP
        self.max_hp = PLAYER_MAX_HP
        self.last_damage_time = 0.0
        self.last_attack_time = 0.0
        self.last_pos_update_time = 0.0   # anti-cheat: last accepted position_update timestamp
        self.guard_cooldowns = {}  # guard_key -> last_trigger_time
        self.quests = {}   # quest_id (str) -> stage (int)
        self.flags = set() # string flags, e.g. {"has_sword"}
        self.command_queue = deque()  # (msg_type, data) tuples — drained by game_tick
        self.dead = False             # True while waiting for respawn
        self.death_time = 0.0         # time.monotonic() when death occurred
        self.death_room = None        # room_id where the player died
        self.avatar = Avatar(8.0, 5.0, "down")

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
        stats = game.monster_stats.get(kind, {"hp": 1, "walk_time": 0.25, "decision_time": 2.0, "damage": 1})
        self.hp = stats["hp"]
        self.max_hp = stats["hp"]
        self.walk_time = stats.get("walk_time", 0.25)    # seconds — walk animation duration
        self.decision_time = stats.get("decision_time", 2.0)  # seconds — behavior eval interval
        self.damage = stats.get("damage", 1)
        # Size in tiles (default 1x1). Boss monsters can be 2x2.
        # Position (x, y) is the top-left tile of the footprint.
        self.width = stats.get("width", 1)
        self.height = stats.get("height", 1)
        self.is_boss = stats.get("boss", False)
        # Behavior engine data (None = use default wander)
        self.behavior = game.monster_behaviors.get(kind)
        # Rule cooldown tracking: rule_index -> ticks remaining
        self._rule_cooldowns = {}
        # Patrol state (index into route string, shared across patrol rules)
        self._patrol_index = 0
        # State machine: mirrors player's G.state pattern
        self.state = "idle"       # "idle" | "walking" | "charging" | "teleporting" | "area"
        self.state_data = {}      # state-scoped variables, replaced on state transition
        self.last_action_time = time.monotonic()  # when the last action completed (for idle timing)

    @property
    def tick_interval(self):
        """Seconds between behavior evaluations (= decision_time)."""
        return self.decision_time

    @property
    def intangible(self):
        """True when monster can't be hit or deal contact damage (e.g. mid-teleport)."""
        return self.state == "teleporting"

    def occupies(self, tx, ty):
        """True if tile (tx, ty) is within this monster's footprint."""
        return self.x <= tx < self.x + self.width and self.y <= ty < self.y + self.height


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
        self.hit_entities = set()  # track already-hit entity ids to prevent double damage
