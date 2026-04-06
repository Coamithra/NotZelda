"""Integration tests — monster behavior scripts.

Tests that monster AI behaviors execute correctly: wandering, decision timing,
projectiles, charges, patrol routes, and a sweep of all registered behaviors
to verify none crash or get stuck.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from test_harness import (
    create_player, simulate_ticks, make_test_room, spawn_room_monsters,
    find_broadcasts, run_tests,
)
from server.state import game
from server.models import Monster
from server.constants import TICK_INTERVAL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_monster_room(kind="slime", behavior=None, monster_x=7.0, monster_y=5.0,
                        decision_time=None):
    """Create a test room with one monster and a player (needed for monster ticking).

    Returns (player, monster).
    """
    make_test_room("monster_room")
    player = create_player("Observer", room_id="monster_room", x=3.0, y=5.0)
    monster = Monster(monster_x, monster_y, kind)
    if behavior is not None:
        monster.behavior = behavior
    if decision_time is not None:
        monster.decision_time = decision_time
    # Set last_action_time to clock start so the decision timer is fresh
    monster.last_action_time = 1000.0
    game.room_monsters["monster_room"] = [monster]
    return player, monster


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_slime_wander(clock):
    """Slime with default wander behavior moves from spawn after enough ticks."""
    player, monster = _setup_monster_room("slime", decision_time=0.5)
    start_x, start_y = monster.x, monster.y

    # Run enough ticks for a decision + walk (0.5s decision + 0.25s walk ≈ 23 ticks)
    simulate_ticks(60, clock)

    moved = (abs(monster.x - start_x) > 0.1 or abs(monster.y - start_y) > 0.1)
    assert moved, (
        f"Monster should have moved from ({start_x}, {start_y}), "
        f"still at ({monster.x:.2f}, {monster.y:.2f}), state={monster.state}"
    )


def test_decision_timing(clock):
    """Monster waits decision_time before evaluating its first action."""
    player, monster = _setup_monster_room("slime", decision_time=2.0)

    # Run ticks for 1.5 seconds (less than decision_time)
    simulate_ticks(int(1.5 / TICK_INTERVAL), clock)
    assert monster.state == "idle", (
        f"Monster should still be idle at 1.5s, state={monster.state}"
    )

    # Run past decision_time
    simulate_ticks(int(1.0 / TICK_INTERVAL), clock)
    # Monster should have evaluated and potentially started walking
    # (or stayed idle if random direction was blocked — both are valid,
    # but the decision should have been evaluated)
    # Check that last_action_time advanced past the initial value
    assert monster.last_action_time > 1000.0, (
        "Monster should have evaluated a decision by now"
    )


def test_projectile_monster(clock):
    """Monster with projectile behavior spawns a projectile."""
    behavior = {"rules": [
        {"if": "always", "do": "projectile", "direction": "left",
         "damage": 1, "sprite_color": "#ff0000"},
    ]}
    player, monster = _setup_monster_room(behavior=behavior, decision_time=0.5)

    # Run well past decision time (2 seconds = multiple decisions)
    simulate_ticks(int(2.0 / TICK_INTERVAL), clock)

    # Check that a projectile was spawned
    projs = game.room_projectiles.get("monster_room", {})
    # Also check if any projectile_spawned broadcasts were sent
    assert len(projs) > 0 or game.next_projectile_id > 0, (
        f"Monster should have fired a projectile, "
        f"room_projectiles={dict(game.room_projectiles)}, "
        f"next_proj_id={game.next_projectile_id}, "
        f"monster.state={monster.state}, last_action={monster.last_action_time}"
    )


def test_charge_monster(clock):
    """Monster with charge behavior enters charging state, then executes."""
    behavior = {"rules": [
        {"if": "always", "do": "charge", "direction": "left",
         "damage": 1, "warmup": 1},
    ]}
    player, monster = _setup_monster_room(behavior=behavior, decision_time=0.5)

    # Run enough ticks to trigger decision + warmup + execution (3 seconds total)
    all_msgs = []
    saw_charging = False
    for _ in range(int(3.0 / TICK_INTERVAL)):
        msgs = simulate_ticks(1, clock)
        all_msgs.extend(msgs)
        if monster.state == "charging":
            saw_charging = True

    assert saw_charging, "Monster should have entered 'charging' state at some point"
    # After 3 seconds, charge should have completed
    assert monster.state in ("idle", "walking", "charging"), (
        f"Monster in unexpected state: {monster.state}"
    )


def test_patrol_route(clock):
    """Monster with patrol behavior follows its route sequentially."""
    behavior = {"rules": [
        {"if": "always", "do": "move", "direction": "patrol",
         "patrol_route": "RRDD"},
    ]}
    # Place monster in the center of the room so all directions are walkable
    player, monster = _setup_monster_room(behavior=behavior, monster_x=5.0,
                                          monster_y=5.0, decision_time=0.3)
    start_x = monster.x

    # Run enough ticks for 2+ walk decisions (decision + walk for each)
    # decision_time=0.3 + walk_time≈0.25 = 0.55s per step, need 2 steps
    simulate_ticks(int(2.0 / TICK_INTERVAL), clock)

    # After patrol "RR", monster should have moved right at least once
    assert monster.x > start_x, (
        f"Monster should have moved right on patrol, x={monster.x:.2f} (started at {start_x})"
    )


def test_all_behaviors_no_crash(clock):
    """Every registered monster behavior runs 300 ticks without crashing."""
    failures = []
    for kind, behavior in game.monster_behaviors.items():
        make_test_room(f"sweep_{kind}")
        player = create_player(f"p_{kind}", room_id=f"sweep_{kind}", x=3.0, y=5.0)
        monster = Monster(7.0, 5.0, kind)
        monster.last_action_time = clock.now
        game.room_monsters[f"sweep_{kind}"] = [monster]

        try:
            simulate_ticks(300, clock)
        except Exception as ex:
            failures.append(f"{kind}: {ex}")
        finally:
            # Clean up for next iteration
            game.players = {k: v for k, v in game.players.items() if v is not player}
            game.room_monsters.pop(f"sweep_{kind}", None)
            game.rooms.pop(f"sweep_{kind}", None)

    assert not failures, (
        f"{len(failures)} behavior(s) crashed:\n" + "\n".join(failures)
    )


def test_all_behaviors_not_stuck(clock):
    """Every registered monster behavior either moves or returns to idle within 300 ticks."""
    stuck = []
    for kind, behavior in game.monster_behaviors.items():
        make_test_room(f"stuck_{kind}")
        player = create_player(f"p_{kind}", room_id=f"stuck_{kind}", x=3.0, y=5.0)
        monster = Monster(7.0, 5.0, kind)
        monster.last_action_time = clock.now
        game.room_monsters[f"stuck_{kind}"] = [monster]

        try:
            simulate_ticks(300, clock)
        except Exception:
            pass  # crash failures caught by test_all_behaviors_no_crash

        if monster.alive and monster.state not in ("idle", "walking"):
            stuck.append(f"{kind}: state={monster.state}")

        # Clean up
        game.players = {k: v for k, v in game.players.items() if v is not player}
        game.room_monsters.pop(f"stuck_{kind}", None)
        game.rooms.pop(f"stuck_{kind}", None)

    assert not stuck, (
        f"{len(stuck)} behavior(s) stuck in non-idle state:\n" + "\n".join(stuck)
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(run_tests(globals()))
