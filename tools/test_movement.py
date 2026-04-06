"""Integration tests — character control and movement.

Tests player spawning, walking, wall collisions, room transitions,
half-tile alignment, and movement speed consistency.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from test_harness import (
    load_test_assets, reset_game_state, create_player, simulate_ticks,
    inject_input, walk_player_to, make_test_room, assert_player_at,
    find_msgs, find_sends, find_broadcasts, run_tests,
    FLOOR, WALL,
)
from server.state import game
from server.constants import (
    TICK_INTERVAL, PLAYER_SPEED, ROOM_COLS, ROOM_ROWS, STARTING_ROOM,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_spawn_default_position(clock):
    """Player spawns at default position (8, 5) in starting room."""
    player = create_player("Hero")
    assert player.room == STARTING_ROOM
    assert_player_at(player, 8.0, 5.0)


def test_walk_right_open_floor(clock):
    """Walk right across an open room — player reaches target position."""
    make_test_room("open_room")
    player = create_player("Walker", room_id="open_room", x=2.0, y=5.0)

    arrived, msgs, ticks = walk_player_to(player, 10.0, 5.0, clock)
    assert arrived, f"Player didn't arrive after {ticks} ticks, at ({player.avatar.x:.2f}, {player.avatar.y:.2f})"


def test_walk_blocked_by_wall(clock):
    """Walking into a wall stops the player — position doesn't cross into wall."""
    make_test_room("wall_room")
    # Place a wall column at x=6 (interior column)
    room = game.rooms["wall_room"]
    for r in range(ROOM_ROWS):
        room["tilemap"][r][6] = WALL

    player = create_player("Blocked", room_id="wall_room", x=4.0, y=5.0)

    # Walk right toward the wall for 60 ticks (~2 seconds)
    for _ in range(60):
        inject_input(player, "right", clock)
    simulate_ticks(60, clock)

    # Player should not have passed x=5 (wall at column 6, player hitbox needs clearance)
    assert player.avatar.x < 6.0, (
        f"Player passed through wall: x={player.avatar.x:.2f}"
    )


def test_walk_around_obstacle(clock):
    """Navigate around an L-shaped wall using multi-step movement."""
    make_test_room("obstacle_room")
    room = game.rooms["obstacle_room"]
    # Create L-shaped wall: horizontal bar at row 5 from col 4-8,
    # vertical bar at col 8 from row 5-8
    for c in range(4, 9):
        room["tilemap"][5][c] = WALL
    for r in range(5, 9):
        room["tilemap"][r][8] = WALL

    player = create_player("Navigator", room_id="obstacle_room", x=3.0, y=4.0)

    # Walk down past the vertical wall's bottom (row 8), stay left of col 4
    arrived, _, _ = walk_player_to(player, 3.0, 9.0, clock, max_ticks=150)
    assert arrived, f"Phase 1 failed: at ({player.avatar.x:.2f}, {player.avatar.y:.2f})"

    # Walk right past the vertical wall (col 8)
    arrived, _, _ = walk_player_to(player, 10.0, 9.0, clock, max_ticks=200)
    assert arrived, f"Phase 2 failed: at ({player.avatar.x:.2f}, {player.avatar.y:.2f})"


def test_room_exit_transition(clock):
    """Walking through a room exit triggers room transition."""
    # Create two connected rooms
    make_test_room("room_a", exits={"east": "room_b"})
    room_a = game.rooms["room_a"]
    # Open the east doorway (col 14, rows 4-6)
    for r in [4, 5, 6]:
        room_a["tilemap"][r][14] = FLOOR
    room_a["spawn_points"]["east"] = (14, 5)

    make_test_room("room_b", exits={"west": "room_a"})
    room_b = game.rooms["room_b"]
    for r in [4, 5, 6]:
        room_b["tilemap"][r][0] = FLOOR
    room_b["spawn_points"]["west"] = (0, 5)

    player = create_player("Traveler", room_id="room_a", x=12.0, y=5.0)

    # Walk right toward the east exit
    all_msgs = []
    for _ in range(100):
        if player.room != "room_a":
            break
        inject_input(player, "right", clock)
        msgs = simulate_ticks(1, clock)
        all_msgs.extend(msgs)

    assert player.room == "room_b", (
        f"Player didn't transition: still in {player.room}"
    )


def test_half_tile_alignment(clock):
    """Moving along one axis snaps the perpendicular axis to half-tile grid."""
    make_test_room("snap_room")
    # Start at a non-aligned position
    player = create_player("Snapper", room_id="snap_room", x=5.3, y=5.3)

    # Walk right — y should snap to nearest 0.5 (5.5)
    for _ in range(10):
        inject_input(player, "right", clock)
    simulate_ticks(10, clock)

    y = player.avatar.y
    snapped = round(y * 2) / 2  # nearest 0.5
    assert abs(y - snapped) < 0.05, (
        f"Y not half-tile aligned: y={y:.3f}, expected {snapped}"
    )


def test_speed_consistency(clock):
    """Player moves at PLAYER_SPEED tiles/sec — 4 tiles takes ~30 ticks."""
    make_test_room("speed_room")
    player = create_player("Speedy", room_id="speed_room", x=2.0, y=5.0)
    target_x = 6.0  # 4 tiles right

    arrived, msgs, ticks = walk_player_to(player, target_x, 5.0, clock, max_ticks=60)
    assert arrived, f"Didn't arrive: at ({player.avatar.x:.2f}, {player.avatar.y:.2f})"

    # At 4.0 tiles/sec with ~0.033s per tick: 4 tiles / (4.0 * 0.033) ≈ 30 ticks
    expected_ticks = 4.0 / (PLAYER_SPEED * TICK_INTERVAL)
    assert abs(ticks - expected_ticks) < 5, (
        f"Took {ticks} ticks, expected ~{expected_ticks:.0f} (±5)"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(run_tests(globals()))
