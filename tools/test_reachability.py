"""Integration tests — dungeon reachability.

Tests BFS reachability, dungeon generation validity, boss/item accessibility,
and key placement correctness.
"""

import sys
import random
from pathlib import Path
from collections import deque

sys.path.insert(0, str(Path(__file__).parent.parent))

from test_harness import (
    load_dungeon_assets, reset_game_state, run_tests,
)
from server.state import game
from server.constants import bfs_reachable, ROOM_COLS, ROOM_ROWS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bfs_cells(connections, start, blocked_edges=None):
    """BFS over dungeon cell graph. Returns set of reachable cells.

    blocked_edges: set of frozensets to skip (e.g. locked doors).
    """
    if blocked_edges is None:
        blocked_edges = set()
    visited = {start}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        for edge in connections:
            if cell not in edge:
                continue
            if edge in blocked_edges:
                continue
            other = next(c for c in edge if c != cell)
            if other not in visited:
                visited.add(other)
                queue.append(other)
    return visited


def _clean_dungeon_state():
    """Clean up dungeon state between tests."""
    game.active_dungeons.clear()
    game.room_to_dungeon.clear()
    # Remove dungeon rooms from game.rooms (keep overworld)
    dungeon_rooms = [rid for rid in game.rooms if rid.startswith("d1_") or rid.startswith("d2_")]
    for rid in dungeon_rooms:
        del game.rooms[rid]
    game.room_monsters = {k: v for k, v in game.room_monsters.items()
                          if not k.startswith("d1_") and not k.startswith("d2_")}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_bfs_reachable_basic(clock):
    """BFS reachability on a known tilemap identifies all connected walkable tiles."""
    tilemap = [["GR"] * 15 for _ in range(11)]
    # Put a wall column at x=7, splitting the room in half
    for r in range(11):
        tilemap[r][7] = "DW"
    # Open a gap at row 5
    tilemap[5][7] = "GR"

    reachable = bfs_reachable(tilemap, game.is_walkable_tile)
    # All walkable tiles should be reachable through the gap
    for r in range(11):
        for c in range(15):
            if tilemap[r][c] == "GR":
                assert (r, c) in reachable, f"({r},{c}) should be reachable"


def test_bfs_unreachable_island(clock):
    """BFS correctly identifies unreachable islands."""
    tilemap = [["GR"] * 15 for _ in range(11)]
    # Wall off a 3x3 island in the center (completely enclosed)
    for r in range(4, 7):
        for c in range(6, 9):
            tilemap[r][c] = "DW"
    # Put a walkable tile inside the wall box
    tilemap[5][7] = "GR"

    reachable = bfs_reachable(tilemap, game.is_walkable_tile)
    # The interior tile (5, 7) should NOT be reachable — it's enclosed by walls
    assert (5, 7) not in reachable, "(5,7) should be unreachable (enclosed by walls)"


def test_dungeon_generation_no_crash(clock):
    """All dungeon types: 50 random seeds each, none should crash."""
    load_dungeon_assets()
    from server.dungeons import create_dungeon
    from server.dungeon_types import DUNGEON_TYPES

    failures = []
    for type_id in sorted(DUNGEON_TYPES):
        for seed in range(50):
            _clean_dungeon_state()
            random.seed(seed)
            try:
                instance = create_dungeon(type_id)
                assert instance is not None, f"create_dungeon returned None"
            except Exception as ex:
                import traceback
                tb = traceback.format_exc().strip().split("\n")[-3:]
                failures.append(f"{type_id} seed {seed}: {ex}\n  " + "\n  ".join(tb))

    _clean_dungeon_state()
    assert not failures, f"{len(failures)} dungeon(s) crashed:\n" + "\n".join(failures)


def test_boss_reachable_from_entrance(clock):
    """All dungeon types: boss cell reachable from entrance (ignoring locks)."""
    load_dungeon_assets()
    from server.dungeons import create_dungeon
    from server.dungeon_types import DUNGEON_TYPES

    failures = []
    for type_id in sorted(DUNGEON_TYPES):
        for seed in range(20):
            _clean_dungeon_state()
            random.seed(seed)
            try:
                instance = create_dungeon(type_id)
            except Exception:
                continue
            if instance is None:
                continue

            entrance = tuple(instance.layout["entrance"])
            boss = instance.boss_cell
            if boss is None:
                failures.append(f"{type_id} seed {seed}: no boss cell")
                continue

            reachable = _bfs_cells(instance.connections, entrance)
            if boss not in reachable:
                failures.append(
                    f"{type_id} seed {seed}: boss {boss} unreachable from {entrance}"
                )

    _clean_dungeon_state()
    assert not failures, f"{len(failures)} seed(s) have unreachable boss:\n" + "\n".join(failures)


class ExploreResult:
    """Full result of a dungeon exploration simulation."""
    def __init__(self, instance):
        self.instance = instance
        self.visited = set()
        self.opened_doors = set()
        self.keys_held = 0
        self.all_cells = set()
        self.locked_doors = set()
        # Trace: ordered log of exploration events
        self.trace = []

    @property
    def unvisited(self):
        return self.all_cells - self.visited

    @property
    def unopened(self):
        return self.locked_doors - self.opened_doors

    @property
    def ok(self):
        return not self.unvisited and not self.unopened

    def dump(self):
        """Produce a human-readable debug report for a failed exploration."""
        inst = self.instance
        lines = []
        entrance = tuple(inst.layout["entrance"])
        lines.append(f"=== {inst.dungeon_id} | layout={inst.layout.get('name', '?')} ===")
        lines.append(f"Entrance: {entrance}  Boss: {inst.boss_cell}  "
                      f"Sanctum: {inst.sanctum_cell}  Treasure: {inst.treasure_cell}")
        lines.append(f"Locked doors: {len(inst.locked_doors)}  "
                      f"Keys placed: {len(inst.key_cells)}  "
                      f"Keys held at end: {self.keys_held}")
        lines.append("")

        # Grid display with cell annotations
        active_cells = list(self.all_cells)
        cols = sorted(set(c[0] for c in active_cells))
        rows = sorted(set(c[1] for c in active_cells))
        cell_set = set(active_cells)
        key_counts = {}
        for k in inst.key_cells:
            key_counts[k] = key_counts.get(k, 0) + 1

        lines.append("Grid:")
        for r in rows:
            row_str = ""
            for c in cols:
                cell = (c, r)
                if cell not in cell_set:
                    row_str += " " * 24
                    continue
                tags = []
                if cell == entrance:
                    tags.append("ENT")
                if cell == inst.boss_cell:
                    tags.append("BOSS")
                if cell == inst.sanctum_cell:
                    tags.append("SANC")
                if cell == inst.treasure_cell:
                    tags.append("TRES")
                tier = inst.cell_difficulty.get(cell)
                if tier:
                    tags.append(tier[0].upper())
                if cell in inst.trap_cells:
                    tags.append("TRAP")
                for itype, icell in inst.item_cells.items():
                    if cell == icell:
                        tags.append(itype[:3].upper())
                if cell in key_counts:
                    tags.append(f"K{key_counts[cell]}")
                if cell not in self.visited:
                    tags.append("UNVISITED")
                label = ",".join(tags)
                row_str += f"[{c},{r} {label}]".ljust(24)
            lines.append(row_str.rstrip())
        lines.append("")

        # Connections with lock status
        lines.append("Connections:")
        for edge in sorted(inst.connections, key=lambda e: tuple(sorted(e))):
            cells = sorted(edge)
            tag = ""
            if edge in inst.locked_doors:
                if edge in self.opened_doors:
                    tag = " [LOCKED -> OPENED]"
                else:
                    tag = " [LOCKED - STUCK]"
            lines.append(f"  {cells[0]} <-> {cells[1]}{tag}")
        lines.append("")

        # Zone info
        if inst.zone_of:
            zone_keys = {}
            for i, k in enumerate(inst.key_cells):
                z = inst.zone_of.get(k, "?")
                zone_keys.setdefault(z, []).append(k)
            lines.append("Zones:")
            for z in sorted(set(inst.zone_of.values())):
                cells_in_z = [c for c, zz in inst.zone_of.items() if zz == z]
                is_entrance_zone = entrance in cells_in_z
                keys_in_z = zone_keys.get(z, [])
                lines.append(f"  Zone {z}: {len(cells_in_z)} cells, "
                             f"{len(keys_in_z)} keys"
                             f"{' (entrance)' if is_entrance_zone else ''}")
            lines.append("")

        # Exploration trace
        if self.trace:
            lines.append("Exploration trace:")
            for event in self.trace:
                lines.append(f"  {event}")
            lines.append("")

        return "\n".join(lines)


def _explore_dungeon(instance):
    """Simulate exploring a dungeon: BFS collecting keys, open doors, repeat.

    Returns an ExploreResult with full trace for debugging.
    """
    result = ExploreResult(instance)
    entrance = tuple(instance.layout["entrance"])
    locked_doors = set(instance.locked_doors)
    key_set = set(instance.key_cells)

    result.locked_doors = set(locked_doors)
    for edge in instance.connections:
        result.all_cells.update(edge)

    visited = result.visited
    opened_doors = result.opened_doors
    keys_held = 0
    round_num = 0

    # Build adjacency: cell -> list of (edge, neighbor)
    adj = {}
    for edge in instance.connections:
        a, b = tuple(edge)
        adj.setdefault(a, []).append((edge, b))
        adj.setdefault(b, []).append((edge, a))

    # Outer loop: keep going as long as we make progress
    made_progress = True
    while made_progress:
        made_progress = False
        round_num += 1

        # BFS from all visited cells (first time: just entrance)
        frontier = deque(visited if visited else [entrance])
        if not visited:
            visited.add(entrance)
        reachable_locked = set()
        new_cells = []

        while frontier:
            cell = frontier.popleft()
            # Pick up key if present
            if cell in key_set:
                keys_held += 1
                key_set.discard(cell)
                made_progress = True
                result.trace.append(f"Round {round_num}: picked up key at {cell} (held={keys_held})")
            # Expand neighbors
            for edge, neighbor in adj.get(cell, []):
                if edge in locked_doors and edge not in opened_doors:
                    reachable_locked.add(edge)
                    continue
                if neighbor not in visited:
                    visited.add(neighbor)
                    frontier.append(neighbor)
                    new_cells.append(neighbor)
                    made_progress = True

        if new_cells:
            result.trace.append(f"Round {round_num}: explored {len(new_cells)} new cells")

        # Open as many reachable locked doors as we have keys for
        while keys_held > 0 and reachable_locked:
            door = reachable_locked.pop()
            opened_doors.add(door)
            keys_held -= 1
            made_progress = True
            cells = sorted(door)
            result.trace.append(
                f"Round {round_num}: opened door {cells[0]}<->{cells[1]} (keys_left={keys_held})")

        if not made_progress and reachable_locked:
            result.trace.append(
                f"Round {round_num}: STUCK — {len(reachable_locked)} locked doors visible, "
                f"0 keys held, {len(key_set)} keys remaining behind doors")

    result.keys_held = keys_held
    return result


def test_dungeon_fully_explorable(clock):
    """All dungeon types: every cell reachable and every door openable.

    Generates 50 dungeons per type and verifies that all are fully solvable by
    collecting keys and opening doors. On failure, dumps full dungeon layout +
    exploration trace for debugging.
    """
    load_dungeon_assets()
    from server.dungeons import create_dungeon
    from server.dungeon_types import DUNGEON_TYPES

    total = 0
    reports = []
    for type_id in sorted(DUNGEON_TYPES):
        for seed in range(50):
            _clean_dungeon_state()
            random.seed(seed)
            try:
                instance = create_dungeon(type_id)
            except Exception as ex:
                reports.append(f"--- {type_id} seed {seed} ---\nCRASH: {ex}")
                continue
            if instance is None:
                continue
            total += 1

            result = _explore_dungeon(instance)
            if not result.ok:
                reports.append(f"--- {type_id} seed {seed} ---\n{result.dump()}")

    _clean_dungeon_state()
    assert not reports, (
        f"{len(reports)}/{total} dungeons not fully explorable:\n\n"
        + "\n".join(reports)
    )


def test_dungeon_no_disconnected_rooms(clock):
    """All dungeon types: no structurally disconnected rooms (ignoring locks)."""
    load_dungeon_assets()
    from server.dungeons import create_dungeon
    from server.dungeon_types import DUNGEON_TYPES

    failures = []
    for type_id in sorted(DUNGEON_TYPES):
        for seed in range(50):
            _clean_dungeon_state()
            random.seed(seed)
            try:
                instance = create_dungeon(type_id)
            except Exception as ex:
                failures.append(f"{type_id} seed {seed}: crash: {ex}")
                continue
            if instance is None:
                continue

            entrance = tuple(instance.layout["entrance"])
            all_cells = set()
            for edge in instance.connections:
                all_cells.update(edge)
            reachable = _bfs_cells(instance.connections, entrance)
            disconnected = all_cells - reachable
            if disconnected:
                failures.append(
                    f"{type_id} seed {seed}: {len(disconnected)} disconnected cells: "
                    f"{disconnected}"
                )

    _clean_dungeon_state()
    assert not failures, (
        f"{len(failures)} dungeon(s) have disconnected rooms:\n"
        + "\n".join(failures)
    )


def test_items_in_reachable_cells(clock):
    """All dungeon types: items placed in cells reachable from entrance (ignoring locks)."""
    load_dungeon_assets()
    from server.dungeons import create_dungeon
    from server.dungeon_types import DUNGEON_TYPES

    failures = []
    for type_id in sorted(DUNGEON_TYPES):
        for seed in range(20):
            _clean_dungeon_state()
            random.seed(seed)
            try:
                instance = create_dungeon(type_id)
            except Exception:
                continue
            if instance is None:
                continue

            entrance = tuple(instance.layout["entrance"])
            reachable = _bfs_cells(instance.connections, entrance)

            for item_name, item_cell in instance.item_cells.items():
                if item_cell not in reachable:
                    failures.append(
                        f"{type_id} seed {seed}: {item_name} at {item_cell} "
                        f"unreachable from {entrance}"
                    )

    _clean_dungeon_state()
    assert not failures, (
        f"{len(failures)} item(s) unreachable:\n" + "\n".join(failures)
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(run_tests(globals()))
