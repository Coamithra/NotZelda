"""Integration tests — multiplayer and networking.

Tests multi-player interactions: presence in same room, enter/leave broadcasts,
broadcast exclusion, chat, combat visibility, and revival.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from test_harness import (
    create_player, simulate_ticks, inject_input, make_test_room,
    find_broadcasts, find_sends, run_tests, FLOOR,
)
from server.state import game
from server.models import Monster, Tombstone
from server.constants import (
    TICK_INTERVAL, PLAYER_RESPAWN_DELAY, REVIVAL_DURATION,
    PLAYER_MAX_HP,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_two_players_in_room(clock):
    """Two players in the same room — both returned by players_in_room."""
    make_test_room("shared_room")
    p1 = create_player("Alice", room_id="shared_room", x=3.0, y=5.0)
    p2 = create_player("Bob", room_id="shared_room", x=10.0, y=5.0)

    from server.net import players_in_room, avatars_in_room
    players = players_in_room("shared_room")
    assert len(players) == 2, f"Expected 2 players in room, got {len(players)}"

    avatars = avatars_in_room("shared_room")
    assert len(avatars) == 2, f"Expected 2 avatars in room, got {len(avatars)}"


def test_player_enter_broadcast(clock):
    """When player A enters B's room, B gets player_entered broadcast."""
    # Room A connects east to Room B
    make_test_room("enter_a", exits={"east": "enter_b"})
    room_a = game.rooms["enter_a"]
    for r in [4, 5, 6]:
        room_a["tilemap"][r][14] = FLOOR
    room_a["spawn_points"]["east"] = (14, 5)

    make_test_room("enter_b", exits={"west": "enter_a"})
    room_b = game.rooms["enter_b"]
    for r in [4, 5, 6]:
        room_b["tilemap"][r][0] = FLOOR
    room_b["spawn_points"]["west"] = (0, 5)

    # Bob is already in room B
    bob = create_player("Bob", room_id="enter_b", x=7.0, y=5.0)
    # Alice starts in room A near the east exit
    alice = create_player("Alice", room_id="enter_a", x=12.0, y=5.0)

    # Walk Alice east until she transitions
    all_msgs = []
    for _ in range(100):
        if alice.room != "enter_a":
            break
        inject_input(alice, "right", clock)
        msgs = simulate_ticks(1, clock)
        all_msgs.extend(msgs)

    assert alice.room == "enter_b", f"Alice should be in enter_b, got {alice.room}"

    # Check for player_entered broadcast (sent to room_b, excluding alice)
    entered_msgs = find_broadcasts(all_msgs, "player_entered")
    alice_entered = [m for m in entered_msgs
                     if m[1] == "enter_b" and m[2].get("name") == "Alice"]
    assert len(alice_entered) >= 1, (
        f"Bob should see Alice's player_entered, got {[m[2] for m in entered_msgs]}"
    )
    # Verify exclusion — Alice's ws should be excluded
    assert alice_entered[0][3] == alice.ws, "Alice should be excluded from her own entry broadcast"


def test_player_leave_broadcast(clock):
    """When player A leaves B's room, B gets player_left broadcast."""
    make_test_room("leave_a", exits={"east": "leave_b"})
    room_a = game.rooms["leave_a"]
    for r in [4, 5, 6]:
        room_a["tilemap"][r][14] = FLOOR
    room_a["spawn_points"]["east"] = (14, 5)

    make_test_room("leave_b", exits={"west": "leave_a"})
    room_b = game.rooms["leave_b"]
    for r in [4, 5, 6]:
        room_b["tilemap"][r][0] = FLOOR
    room_b["spawn_points"]["west"] = (0, 5)

    bob = create_player("Bob", room_id="leave_a", x=3.0, y=5.0)
    alice = create_player("Alice", room_id="leave_a", x=12.0, y=5.0)

    # Walk Alice east until she transitions
    all_msgs = []
    for _ in range(100):
        if alice.room != "leave_a":
            break
        inject_input(alice, "right", clock)
        msgs = simulate_ticks(1, clock)
        all_msgs.extend(msgs)

    assert alice.room == "leave_b"

    left_msgs = find_broadcasts(all_msgs, "player_left")
    alice_left = [m for m in left_msgs
                  if m[1] == "leave_a" and m[2].get("name") == "Alice"]
    assert len(alice_left) >= 1, "Bob should see Alice's player_left"
    # Alice's ws should be excluded from the departure broadcast
    assert alice_left[0][3] == alice.ws, "Alice excluded from her own leave broadcast"


def test_broadcast_exclusion(clock):
    """Broadcast tuple correctly marks the acting player's ws as excluded."""
    make_test_room("excl_room")
    alice = create_player("Alice", room_id="excl_room", x=5.0, y=5.0, flags=["has_sword"])
    bob = create_player("Bob", room_id="excl_room", x=10.0, y=5.0)

    # Alice attacks — check that log broadcast excludes alice
    monster = Monster(6.0, 5.0, "slime")
    monster.hp = 1
    monster.max_hp = 1
    game.room_monsters["excl_room"] = [monster]

    from server.commands import sword_hit_scan
    msgs = []
    hit_monsters = set()
    sword_hit_scan(alice, "right", "excl_room", hit_monsters, clock.now, msgs)

    # The log message "Alice defeated the Slime!" should exclude alice's ws
    log_msgs = [m for m in msgs if m[0] == "broadcast" and m[2].get("type") == "log"]
    excluded_msgs = [m for m in log_msgs if m[3] == alice.ws]
    assert len(excluded_msgs) >= 1, (
        "Kill log broadcast should exclude the killer's ws"
    )


def test_chat_broadcast(clock):
    """Chat message broadcasts to the room."""
    make_test_room("chat_room")
    alice = create_player("Alice", room_id="chat_room", x=5.0, y=5.0)
    bob = create_player("Bob", room_id="chat_room", x=10.0, y=5.0)

    # Alice sends a chat message
    alice.command_queue.append(("chat", {"text": "Hello Bob!"}))
    msgs = simulate_ticks(1, clock)

    chat_msgs = find_broadcasts(msgs, "chat")
    assert len(chat_msgs) >= 1, "Chat should broadcast"
    assert chat_msgs[0][2]["from"] == "Alice"
    assert chat_msgs[0][2]["text"] == "Hello Bob!"
    # Chat has exclude=None (everyone sees it, including sender)
    assert chat_msgs[0][3] is None, "Chat broadcasts to everyone (no exclusion)"


def test_combat_visibility(clock):
    """When Alice kills a monster, Bob sees the monster_killed broadcast."""
    make_test_room("vis_room")
    alice = create_player("Alice", room_id="vis_room", x=4.0, y=5.0, flags=["has_sword"])
    bob = create_player("Bob", room_id="vis_room", x=10.0, y=5.0)

    monster = Monster(5.0, 5.0, "slime")
    monster.hp = 1
    monster.max_hp = 1
    game.room_monsters["vis_room"] = [monster]

    from server.commands import sword_hit_scan
    msgs = []
    hit_monsters = set()
    sword_hit_scan(alice, "right", "vis_room", hit_monsters, clock.now, msgs)

    # monster_killed broadcasts with exclude=None — both players see it
    killed_msgs = find_broadcasts(msgs, "monster_killed")
    assert len(killed_msgs) >= 1, "Both players should see monster_killed"
    assert killed_msgs[0][3] is None, "monster_killed should broadcast to everyone"
    assert killed_msgs[0][1] == "vis_room"


def test_revival_flow(clock):
    """Player A dies, B walks near tombstone, revival completes."""
    make_test_room("revive_room")
    alice = create_player("Alice", room_id="revive_room", x=5.0, y=5.0)
    bob = create_player("Bob", room_id="revive_room", x=5.0, y=5.5)

    # Kill Alice via direct damage
    from server.combat import _apply_damage
    alice.hp = 1
    msgs = []
    _apply_damage(alice, 1, "revive_room", msgs, source_x=4.0, source_y=5.0)

    # Process death entry (simulate what flush_messages does)
    for entry in msgs:
        if entry[0] == "death":
            _, player, old_room_id, dx, dy = entry
            player.dead = True
            player.death_time = clock.now
            player.death_room = old_room_id
            player.death_x = dx
            player.death_y = dy
            player.avatar = None

    assert alice.dead, "Alice should be dead"

    # Advance past respawn delay so tombstone placement triggers
    respawn_ticks = int((PLAYER_RESPAWN_DELAY + 0.5) / TICK_INTERVAL)
    msgs2 = simulate_ticks(respawn_ticks, clock)

    assert alice.name in game.tombstones, (
        f"Tombstone should be placed for Alice, tombstones={list(game.tombstones.keys())}"
    )

    # Bob is adjacent — revival should auto-start
    ts = game.tombstones[alice.name]
    revival_msgs = find_broadcasts(msgs2, "revival_started")
    assert len(revival_msgs) >= 1, "Revival should start (Bob is near tombstone)"

    # Advance past revival duration
    revival_ticks = int((REVIVAL_DURATION + 0.5) / TICK_INTERVAL)
    msgs3 = simulate_ticks(revival_ticks, clock)

    # Alice should be revived
    assert not alice.dead, "Alice should be revived"
    assert alice.avatar is not None, "Alice should have an avatar after revival"
    complete_msgs = find_broadcasts(msgs3, "revival_complete")
    assert len(complete_msgs) >= 1, "revival_complete should broadcast"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(run_tests(globals()))
