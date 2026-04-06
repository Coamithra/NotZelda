"""Integration tests — combat system.

Tests sword attacks, hit scanning, cooldowns, monster kills, contact damage,
knockback, and projectiles.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from test_harness import (
    create_player, simulate_ticks, inject_input, make_test_room,
    assert_player_at, find_broadcasts, find_sends, spawn_room_monsters,
    run_tests, FLOOR, WALL,
)
from server.state import game
from server.models import Monster, Projectile
from server.constants import (
    TICK_INTERVAL, ATTACK_COOLDOWN, SWORD_ACTIVE_DURATION,
    INVINCIBILITY_DURATION, PLAYER_MAX_HP,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_combat_room(monster_x=6.0, monster_y=5.0, monster_kind="slime",
                       player_x=4.0, player_y=5.0):
    """Create a test room with a player and a monster. Returns (player, monster)."""
    make_test_room("combat_room")
    player = create_player("Fighter", room_id="combat_room", x=player_x, y=player_y,
                           flags=["has_sword"])
    monster = Monster(monster_x, monster_y, monster_kind)
    game.room_monsters["combat_room"] = [monster]
    return player, monster


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sword_hit_basic(clock):
    """Sword swing hits adjacent monster — monster takes 1 damage."""
    player, monster = _setup_combat_room(monster_x=5.0, monster_y=5.0,
                                          player_x=4.0, player_y=5.0)
    initial_hp = monster.hp

    # Attack right (toward monster at x=5)
    from server.commands import sword_hit_scan
    msgs = []
    hit_monsters = set()
    sword_hit_scan(player, "right", "combat_room", hit_monsters, clock.now, msgs)

    assert monster.hp == initial_hp - 1, (
        f"Monster HP should be {initial_hp - 1}, got {monster.hp}"
    )
    assert len(hit_monsters) == 1, "Monster should be in hit set"


def test_sword_miss(clock):
    """Sword swing in wrong direction misses — monster takes no damage."""
    player, monster = _setup_combat_room(monster_x=6.0, monster_y=5.0,
                                          player_x=4.0, player_y=5.0)
    initial_hp = monster.hp

    from server.commands import sword_hit_scan
    msgs = []
    hit_monsters = set()
    # Attack left (away from monster)
    sword_hit_scan(player, "left", "combat_room", hit_monsters, clock.now, msgs)

    assert monster.hp == initial_hp, f"Monster should not be hit, HP={monster.hp}"
    assert len(hit_monsters) == 0


def test_attack_cooldown(clock):
    """Attack during cooldown is rejected; attack after cooldown succeeds."""
    player, monster = _setup_combat_room()
    player.avatar.direction = "right"

    # First attack
    inject_input(player, "right", clock, atk=True)
    simulate_ticks(1, clock)
    assert player.active_attack is not None, "First attack should initiate"

    # Manually clear active_attack (simulating sword expiry) so we can test
    # the cooldown window in isolation
    player.active_attack = None
    player.avatar.last_reported_attacking = False

    # Still within cooldown (only ~1 tick elapsed since last_attack_time,
    # cooldown is ~0.24s). Try to attack:
    inject_input(player, "right", clock, atk=True)
    simulate_ticks(1, clock)
    assert player.active_attack is None, "Attack during cooldown should be rejected"

    # Advance well past cooldown
    cooldown_ticks = int(ATTACK_COOLDOWN / TICK_INTERVAL) + 3
    simulate_ticks(cooldown_ticks, clock)

    # Attack should work now
    player.avatar.last_reported_attacking = False
    inject_input(player, "right", clock, atk=True)
    simulate_ticks(1, clock)
    assert player.active_attack is not None, "Attack after cooldown should succeed"


def test_monster_killed(clock):
    """Killing a monster broadcasts monster_killed and sets alive=False."""
    make_test_room("kill_room")
    player = create_player("Slayer", room_id="kill_room", x=4.0, y=5.0,
                           flags=["has_sword"])
    # 1-HP monster right next to player
    monster = Monster(5.0, 5.0, "slime")
    monster.hp = 1
    monster.max_hp = 1
    game.room_monsters["kill_room"] = [monster]

    from server.commands import sword_hit_scan
    msgs = []
    hit_monsters = set()
    sword_hit_scan(player, "right", "kill_room", hit_monsters, clock.now, msgs)

    assert not monster.alive, "Monster should be dead"
    assert monster.hp == 0
    killed_msgs = find_broadcasts(msgs, "monster_killed")
    assert len(killed_msgs) >= 1, f"Expected monster_killed broadcast, got {[m[2]['type'] for m in msgs]}"


def test_contact_damage(clock):
    """Monster overlapping player causes contact damage via pending collisions."""
    make_test_room("contact_room")
    player = create_player("Victim", room_id="contact_room", x=5.0, y=5.0)
    initial_hp = player.hp

    # Place monster directly on player
    monster = Monster(5.0, 5.0, "slime")
    game.room_monsters["contact_room"] = [monster]

    # Monster must be walking to trigger contact checks in _tick_all_monsters
    # Instead, we can manually set up pending collision and tick
    from server.constants import PLAYER_COLLISION_MARGIN
    m = PLAYER_COLLISION_MARGIN
    # Verify AABB overlap
    assert (player.avatar.x + m < monster.x + monster.width and
            player.avatar.x + 1 - m > monster.x), "AABB should overlap"

    # Give monster a walk state so _tick_all_monsters processes it
    from server.models import WalkState
    monster.state = "walking"
    monster.state_data = WalkState(
        from_x=5.0, from_y=5.0, to_x=5.0, to_y=5.0,
        start_time=clock.now, walk_time=0.25,
        room_id="contact_room", monster_idx=0,
        remaining_distance=0, direction="right", seq=0,
    )

    msgs = simulate_ticks(2, clock)

    # Player should have a pending collision that resolves
    hurt_msgs = find_broadcasts(msgs, "player_hurt")
    assert len(hurt_msgs) >= 1, f"Expected player_hurt, got msg types: {[m[2].get('type') for m in msgs if m[0] == 'broadcast']}"
    assert player.hp < initial_hp, f"Player HP should decrease from {initial_hp}, got {player.hp}"


def test_knockback_direction(clock):
    """Player knocked back away from damage source."""
    make_test_room("knock_room")
    player = create_player("Pushed", room_id="knock_room", x=5.0, y=5.0)

    # Simulate damage from a source at (4, 5) — should knock player to the right
    from server.combat import _apply_damage
    msgs = []
    _apply_damage(player, 1, "knock_room", msgs, source_x=4.0, source_y=5.0)

    assert player.avatar.x > 5.0, (
        f"Player should be knocked right from source at (4,5), x={player.avatar.x}"
    )
    hurt_msgs = find_broadcasts(msgs, "player_hurt")
    assert len(hurt_msgs) == 1
    assert hurt_msgs[0][2]["knockback"] is True


def test_projectile_hits_player(clock):
    """Projectile moving toward player deals damage."""
    make_test_room("proj_room")
    player = create_player("Target", room_id="proj_room", x=8.0, y=5.0)
    initial_hp = player.hp

    # Create a projectile heading right toward player
    proj = Projectile(x=6, y=5, dx=1, dy=0, damage=1,
                      color="#ff0000", room_id="proj_room")
    pid = game.next_projectile_id
    game.next_projectile_id += 1
    game.room_projectiles["proj_room"] = {pid: proj}

    # Tick until projectile reaches player (2 tiles away, 1 tile per tick)
    msgs = simulate_ticks(5, clock)

    hit_msgs = find_broadcasts(msgs, "projectile_hit")
    assert len(hit_msgs) >= 1, "Projectile should hit player"
    assert player.hp < initial_hp, f"Player HP should decrease, got {player.hp}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(run_tests(globals()))
