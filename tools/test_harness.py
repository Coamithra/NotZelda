"""Integration test harness — headless game loop driver.

Provides MockWebSocket, GameClock, state management, and helpers for
driving the game tick loop without a browser or real websocket connections.
"""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from server.state import game
from server.constants import TICK_INTERVAL, ROOM_COLS, ROOM_ROWS


# ---------------------------------------------------------------------------
# MockWebSocket
# ---------------------------------------------------------------------------

class MockWebSocket:
    """Minimal websocket mock — unique identity for exclude checks, captures sends."""
    _counter = 0

    def __init__(self, name="mock"):
        MockWebSocket._counter += 1
        self.name = f"{name}_{MockWebSocket._counter}"
        self.sent = []
        self.open = True

    async def send(self, data):
        self.sent.append(data)

    def __repr__(self):
        return f"<MockWS({self.name})>"


# ---------------------------------------------------------------------------
# GameClock — deterministic time
# ---------------------------------------------------------------------------

class GameClock:
    """Controllable clock that replaces time.monotonic for deterministic tests."""

    def __init__(self, start=1000.0):
        self._now = start

    def __call__(self):
        return self._now

    def advance(self, dt):
        self._now += dt

    @property
    def now(self):
        return self._now


# ---------------------------------------------------------------------------
# Asset loading (once per process)
# ---------------------------------------------------------------------------

_assets_loaded = False
_dungeon_assets_loaded = False


def load_test_assets():
    """Load tiles, monsters, NPC sprites, rooms — called once per process."""
    global _assets_loaded
    if _assets_loaded:
        return
    game.load_tiles()
    game.load_monsters()
    game.load_npc_sprites()

    from server.rooms import load_room_files
    load_room_files()

    from server.combat import _apply_damage
    from server import behavior_engine
    if behavior_engine.engine is None:
        behavior_engine.init(_apply_damage)

    _assets_loaded = True


def load_dungeon_assets():
    """Load dungeon templates and content libraries — needed for dungeon generation tests."""
    global _dungeon_assets_loaded
    load_test_assets()
    if _dungeon_assets_loaded:
        return

    from server.rooms import load_dungeon_templates
    from server.dungeon_types import DUNGEON_TYPES
    from server.dungeon_content import register_precreated_types, load_precreated_content
    from server.content_library import (
        ContentLibrary, MONSTER_LIBRARY_CAPACITY,
        TILE_LIBRARY_CAPACITY, ROOM_LIBRARY_CAPACITY,
    )
    from pathlib import Path

    register_precreated_types()

    data_dir = Path(__file__).parent.parent / "data"

    for type_id, type_config in DUNGEON_TYPES.items():
        load_dungeon_templates(type_config["template_dir"], type_id)

        m_cap = type_config.get("monster_capacity", MONSTER_LIBRARY_CAPACITY)
        t_cap = type_config.get("tile_capacity", TILE_LIBRARY_CAPACITY)
        r_cap = type_config.get("room_capacity", ROOM_LIBRARY_CAPACITY)
        monster_lib = ContentLibrary("monster", m_cap)
        tile_lib = ContentLibrary("tile", t_cap)
        room_lib = ContentLibrary("room", r_cap)

        templates = game.dungeon_templates.get(type_id, {})
        special_rooms = {type_config["boss_template"], type_config["treasure_template"]}
        load_precreated_content(monster_lib, tile_lib, room_lib, templates,
                                special_rooms=special_rooms, type_id=type_id)

        # Load custom entries if they exist
        for lib_name, lib, old_name in [
            ("monster", monster_lib, "monster_library.json"),
            ("tile", tile_lib, "tile_library.json"),
            ("room", room_lib, "room_library.json"),
        ]:
            new_path = data_dir / f"{type_id}_{old_name}"
            old_path = data_dir / old_name
            if new_path.exists():
                lib.load_custom(new_path)
            elif old_path.exists() and type_id == "d1":
                lib.load_custom(old_path)

        game.content_libraries[type_id] = {
            "rooms": room_lib,
            "monsters": monster_lib,
            "tiles": tile_lib,
        }
        game.deprecated_content.setdefault(type_id, {"monsters": set(), "tiles": set()})

    _dungeon_assets_loaded = True


# ---------------------------------------------------------------------------
# State reset (between tests)
# ---------------------------------------------------------------------------

def reset_game_state():
    """Clear mutable live-game state, preserving loaded assets."""
    game.players.clear()
    game.room_monsters.clear()
    game.room_cooldowns.clear()
    game.room_hearts.clear()
    game.room_projectiles.clear()
    game.locked_rooms.clear()
    game.room_pickup_freeze.clear()
    game.tombstones.clear()
    game.active_dungeons.clear()
    game.room_to_dungeon.clear()
    game.next_heart_id = 0
    game.next_color_index = 0
    game.next_projectile_id = 0
    game.last_deprecation_time = 0.0
    game.regen_tasks.clear()
    # Reset overworld items from room files (tests may have mutated them)
    game.overworld_items.clear()


# ---------------------------------------------------------------------------
# Player helpers
# ---------------------------------------------------------------------------

def create_player(name, room_id=None, x=8.0, y=5.0, direction="down", flags=None):
    """Create a Player with MockWebSocket, registered in game.players.

    Returns the Player object. The mock websocket is at player.ws.
    """
    from server.models import Player
    from server.constants import STARTING_ROOM

    ws = MockWebSocket(name)
    player = Player(ws, name, f"Test player {name}", game.next_color_index)
    game.next_color_index += 1
    player.room = room_id or STARTING_ROOM
    player.avatar.x = float(x)
    player.avatar.y = float(y)
    player.avatar.direction = direction
    if flags:
        for f in flags:
            player.grant_flag(f)
    game.players[ws] = player
    return player


# ---------------------------------------------------------------------------
# Tick simulation
# ---------------------------------------------------------------------------

def simulate_ticks(n, clock):
    """Run n game ticks synchronously. Returns accumulated msgs list.

    Advances the clock by TICK_INTERVAL per tick, calls all tick functions
    in the same order as game_tick() in combat.py.
    """
    from server.commands import process_player_commands
    from server.combat import (
        _tick_players, _tick_revivals, _tick_active_attacks,
        _tick_all_monsters, _resolve_pending_collisions, _tick_projectiles,
    )

    all_msgs = []
    for _ in range(n):
        clock.advance(TICK_INTERVAL)
        now = clock.now
        msgs = []

        for player in list(game.players.values()):
            if player.dead:
                while player.command_queue:
                    cmd_type, _ = player.command_queue.popleft()
                    if cmd_type == "respawn_request":
                        player.chose_respawn = True
                continue
            if player.avatar is None:
                continue
            process_player_commands(player, now, msgs)

        _tick_players(now, msgs)
        _tick_revivals(now, msgs)
        _tick_active_attacks(now, msgs)
        _tick_all_monsters(now, msgs)
        _resolve_pending_collisions(now, msgs)
        _tick_projectiles(msgs)

        # Handle "death" entries the same way flush_messages does
        # (sets player.dead, destroys avatar) so subsequent ticks see correct state
        for entry in msgs:
            if entry[0] == "death":
                _, player, old_room_id, dx, dy = entry
                player.dead = True
                player.death_time = now
                player.death_room = old_room_id
                player.death_x = dx
                player.death_y = dy
                player.avatar = None

        all_msgs.extend(msgs)
    return all_msgs


# ---------------------------------------------------------------------------
# Movement helpers
# ---------------------------------------------------------------------------

def inject_input(player, direction, clock, seq=None, dt=None, atk=False):
    """Queue a single movement input for the player."""
    if seq is None:
        seq = player.avatar.last_acked_seq + 1
    if dt is None:
        dt = TICK_INTERVAL
    player.command_queue.append(("player_input", {
        "inputs": [{"seq": seq, "dir": direction, "dt": dt}],
        "rtt": 0,
        "atk": atk,
    }))


def walk_player_to(player, target_x, target_y, clock, max_ticks=300):
    """Walk player toward target position by injecting directional inputs.

    Returns (arrived: bool, msgs: list, ticks_taken: int).
    """
    all_msgs = []
    for tick in range(max_ticks):
        a = player.avatar
        if a is None:
            return False, all_msgs, tick
        dx = target_x - a.x
        dy = target_y - a.y
        if abs(dx) < 0.15 and abs(dy) < 0.15:
            return True, all_msgs, tick
        # Pick primary axis
        if abs(dx) >= abs(dy):
            direction = "right" if dx > 0 else "left"
        else:
            direction = "down" if dy > 0 else "up"
        inject_input(player, direction, clock)
        msgs = simulate_ticks(1, clock)
        all_msgs.extend(msgs)
    return False, all_msgs, max_ticks


# ---------------------------------------------------------------------------
# Room helpers
# ---------------------------------------------------------------------------

FLOOR = "GR"
WALL = "DW"


def make_test_room(room_id, tilemap=None, exits=None):
    """Create a synthetic room in game.rooms. Returns the room dict.

    Default: all-floor interior, walls on border, no exits.
    """
    if tilemap is None:
        tilemap = []
        for r in range(ROOM_ROWS):
            row = []
            for c in range(ROOM_COLS):
                if r == 0 or r == ROOM_ROWS - 1 or c == 0 or c == ROOM_COLS - 1:
                    row.append(WALL)
                else:
                    row.append(FLOOR)
            tilemap.append(row)

    room = {
        "name": f"Test Room {room_id}",
        "tilemap": tilemap,
        "exits": exits or {},
        "spawn_points": {"default": (8, 5)},
    }
    game.rooms[room_id] = room

    # Ensure tile recipes exist
    if FLOOR not in game.custom_tile_recipes:
        game.custom_tile_recipes[FLOOR] = {"walkable": True}
    if WALL not in game.custom_tile_recipes:
        game.custom_tile_recipes[WALL] = {"walkable": False}

    return room


def spawn_room_monsters(room_id):
    """Trigger monster spawning for a room (requires templates loaded)."""
    from server.lifecycle import on_player_enter_room
    on_player_enter_room(room_id)
    return game.room_monsters.get(room_id, [])


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

def find_msgs(msgs, msg_type):
    """Find all message tuples with a given type in the msg dict."""
    results = []
    for entry in msgs:
        kind = entry[0]
        if kind == "broadcast":
            _, room_id, msg, exclude = entry
            if msg.get("type") == msg_type:
                results.append(entry)
        elif kind == "send":
            _, player, msg = entry
            if msg.get("type") == msg_type:
                results.append(entry)
        elif kind == "death" and msg_type == "death":
            results.append(entry)
    return results


def find_broadcasts(msgs, msg_type):
    """Find all broadcast tuples with a given type."""
    return [e for e in msgs
            if e[0] == "broadcast" and e[2].get("type") == msg_type]


def find_sends(msgs, msg_type, player=None):
    """Find all direct-send tuples with a given type, optionally filtered by player."""
    results = []
    for e in msgs:
        if e[0] == "send" and e[2].get("type") == msg_type:
            if player is None or e[1] is player:
                results.append(e)
    return results


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

def assert_player_at(player, x, y, tolerance=0.2):
    """Assert player avatar is at (x, y) within tolerance."""
    a = player.avatar
    assert a is not None, f"{player.name} has no avatar"
    assert abs(a.x - x) < tolerance and abs(a.y - y) < tolerance, (
        f"{player.name} at ({a.x:.2f}, {a.y:.2f}), expected ({x}, {y}) ±{tolerance}"
    )


# ---------------------------------------------------------------------------
# Test runner utility
# ---------------------------------------------------------------------------

def run_tests(test_module_globals, clock_start=1000.0):
    """Discover and run test_* functions with clock patching and state reset.

    Each test function receives (clock,) as argument.
    """
    test_funcs = [(k, v) for k, v in sorted(test_module_globals.items())
                  if k.startswith("test_") and callable(v)]

    load_test_assets()

    passed = 0
    failed = 0
    for name, fn in test_funcs:
        clock = GameClock(clock_start)
        reset_game_state()
        with patch("time.monotonic", clock):
            try:
                fn(clock)
                passed += 1
                print(f"  PASS  {name}")
            except Exception as ex:
                failed += 1
                import traceback
                print(f"  FAIL  {name}: {ex}")
                traceback.print_exc()

    print(f"\n{passed} passed, {failed} failed out of {len(test_funcs)} tests")
    return failed
