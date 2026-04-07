"""Data classes for game entities — Player, Monster, Projectile."""

import time
from collections import deque
from dataclasses import dataclass

from server.state import game
from server.constants import PLAYER_MAX_HP, STARTING_ROOM


@dataclass
class WalkState:
    """State data for a monster mid-walk. Assigned to monster.state_data when state == 'walking'."""
    from_x: float
    from_y: float
    to_x: float
    to_y: float
    start_time: float
    walk_time: float        # actual duration for this step (scaled by step distance)
    room_id: str
    monster_idx: int
    remaining_distance: int
    direction: str
    seq: int


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
        self.last_reported_dir = direction
        self.last_reported_dancing = False
        self.last_reported_attacking = False
        self.pending_collisions = {}   # id(monster) -> {monster, room_id, time, knockback data}
        self.spawn_stair = None        # (tx, ty) if spawned on a stair tile — cleared on move-off
        self.last_acked_seq = 0        # last input sequence number processed (for client reconciliation)


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
        self.guard_cooldowns: dict[str, float] = {}  # guard_key -> last_trigger_time
        self.guard_greeted: set[str] = set()         # NPC keys greeted this room visit
        self.quests: dict[str, int] = {}              # quest_id -> stage
        self.flags: set[str] = set()                  # e.g. {"has_sword"}
        self.command_queue = deque()  # (msg_type, data) tuples — drained by game_tick
        self.dead = False             # True while waiting for respawn
        self.death_time = 0.0         # time.monotonic() when death occurred
        self.death_room = None        # room_id where the player died
        self.keys = 0                 # dungeon keys held (persists across dungeon exits)
        self.spirit_jar_count = 0     # stackable spirit jars (consumed on death)
        self.active_attack = None     # dict {direction, start_time, room, hit_monsters} or None
        self.rtt = 0.0                # round-trip time in seconds (from client ping/pong)
        self.death_x = 0.0            # x position where player died (tombstone location)
        self.death_y = 0.0            # y position where player died
        self.chose_respawn = False    # True if dead player clicked Respawn button
        self.spectating = None        # name of player being spectated (death camera), or None
        self.spectate_room = None     # room_id of the room being spectated, or None
        self.avatar = Avatar(8.0, 5.0, "down")

    def quest(self, qid: str) -> int:
        return self.quests.get(qid, 0)

    def set_quest(self, qid: str, stage: int):
        self.quests[qid] = stage

    def has_flag(self, flag: str) -> bool:
        return flag in self.flags

    def grant_flag(self, flag: str):
        self.flags.add(flag)


class Tombstone:
    """Standalone game object spawned when a player dies with allies nearby.

    All revival state lives here, not on Player. The dead player's avatar is
    destroyed as normal — this object tracks position and revival progress.
    """
    def __init__(self, player, room_id: str, x: float, y: float):
        self.player = player          # dead Player reference (for reviving)
        self.name = player.name       # display name
        self.room_id = room_id        # room where tombstone sits
        self.x = x
        self.y = y
        self.color_index = player.color_index
        self.reviver = None           # Player currently channeling, or None
        self.revival_start_time = 0.0 # when channel started
        self.created_time = 0.0       # time.monotonic() when tombstone appeared


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
        self.knockbackable = stats.get("knockback", not self.is_boss)
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
        # Monotonic counter incremented on every state change (walk, charge, knockback,
        # teleport, etc.).  Sent to clients so they can discard stale messages.
        self.move_seq = 0
        self.position_history = deque(maxlen=10)  # [(time, x, y)] — last ~200ms for lag compensation

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
