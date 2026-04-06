"""Dungeon instance system — procedurally generated dungeon layouts."""

import asyncio
import os
import random
import time
from collections import deque

from server.state import game
from server.constants import (EDGE_SPAWN_POINTS, DEFAULT_SPAWN, ROOM_COLS, ROOM_ROWS,
                              DOORWAY_TILES, bfs_reachable, DARK_ROOM_FRACTION,
                              DEFAULT_DARK_FRACTION)
from server.dungeon_topology import DungeonTopology
from server import log
from server.net import broadcast_debug
from server.ai_generator import patch_unreachable_doorways, patch_monster_placements


class DungeonInstance:
    def __init__(self, dungeon_id, layout, room_map, active_rooms, entrance_room_id, music_track, boss_track):
        self.dungeon_id = dungeon_id
        self.layout = layout
        self.room_map = room_map           # (col, row) -> template_id
        self.active_rooms = active_rooms   # set of room_id strings
        self.cleared_rooms = set()         # room_ids where all monsters killed
        self.entrance_room_id = entrance_room_id
        self.music_track = music_track
        self.boss_track = boss_track

        # Stage 7: Library-managed cell tracking
        # (col, row) -> {"source": "precreated"|"custom"|"special", "entry": LibraryEntry|None, "resolved": bool}
        self.cell_assignments = {}
        self.resolved_rooms = set()        # room_ids that have been materialized into game.rooms

        # Custom slot pool — shared pool of room content for custom cells.
        # Each slot: {"data": dict, "entry": LibraryEntry} or None (needs generation).
        # Custom cells pick a random slot at resolution time.
        self.custom_slots = []

        # Topology — lazy spatial oracle (all distance/path queries go here)
        self.topo = None               # DungeonTopology instance

        # Dungeon path — connectivity graph (set of frozensets of cell tuples)
        self.connections = set()
        self.boss_cell = None          # (col, row) — boss room
        self.sanctum_cell = None       # (col, row) — seal-shard room (past boss)
        self.treasure_cell = None      # (col, row) — treasure chest (lantern in d1)
        self.boss_engaged = False      # True once boss takes first non-lethal hit

        # Dungeon items (Map & Compass & Lantern)
        self.item_cells = {}           # "map" -> (col, row), "compass" -> (col, row), "lantern" -> (col, row)
        self.dungeon_items = {}        # room_id -> [{x, y, item_type}]
        self.collected_items = set()   # "map", "compass"
        self.per_player_items = {}     # room_id -> [{x, y, item_type}] — items that stay for all players

        # Darkness
        self.dark_cells = set()        # cells flagged as dark rooms

        # Difficulty tiers — decided at creation time (easy/challenging/hard)
        self.cell_difficulty = {}          # cell -> "easy"|"challenging"|"hard"

        # Trap rooms — decided at creation time so key placement can use it
        self.trap_cells = set()            # cells that will become trap rooms on resolution

        # Locked doors & keys
        self.locked_doors = set()          # frozensets of cell tuples (locked connections)
        self.unlocked_doors = set()        # frozensets (doors unlocked by players during this run)
        self.zone_of = {}                  # cell -> zone_id (for debug visualization)
        self.zone_cells = {}               # zone_id -> set of cells
        self.locked_door_originals = {}    # room_id -> {(r,c): original_tile_code}
        self.key_cells = []                # [(col, row), ...] — cells where keys spawn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_dungeon_for_room(room_id):
    """Get the DungeonInstance containing a given room, or None."""
    type_id = game.room_to_dungeon.get(room_id)
    if type_id:
        return game.active_dungeons.get(type_id)
    return None


def is_dungeon_room(room_id: str) -> bool:
    return room_id in game.room_to_dungeon


def broadcast_to_dungeon(instance, msg, msgs, exclude=None):
    """Append a send message for all players currently in the dungeon."""
    for p in list(game.players.values()):
        if p.room in instance.active_rooms and p.ws != exclude:
            msgs.append(("send", p, msg))


def _find_item_tile(room_id, exclude=None):
    """Find a random walkable interior tile reachable from a doorway,
    not occupied by NPCs (which block movement).
    exclude: set of (col, row) positions to avoid (e.g. already-placed items)."""
    room = game.rooms.get(room_id)
    if not room:
        return None
    tilemap = room["tilemap"]
    guards = game.guards.get(room_id, [])
    npc_tiles = {(g["x"], g["y"]) for g in guards}
    blocked = npc_tiles | (exclude or set())

    # Build seeds from active exits + stairs
    exits = room.get("exits", {})
    seeds = []
    for direction in exits:
        if direction in DOORWAY_TILES:
            seeds.extend(DOORWAY_TILES[direction])
    for ry, trow in enumerate(tilemap):
        for rx, tile in enumerate(trow):
            if tile == "SU":
                seeds.append((ry, rx))

    reachable = bfs_reachable(tilemap, game.is_walkable_tile, seeds) if seeds else set()

    # Filter to interior tiles (avoid exit doorways), skip NPC tiles
    # bfs_reachable returns (row, col); convert to (col, row) for output
    candidates = [(c, r) for (r, c) in reachable
                  if 1 <= r <= 9 and 1 <= c <= 13
                  and (c, r) not in blocked]

    # Fallback: if no reachable interior tiles (e.g. all exits locked), scan for any walkable interior tile
    if not candidates:
        for r in range(1, ROOM_ROWS - 1):
            for c in range(1, ROOM_COLS - 1):
                if game.is_walkable_tile(tilemap[r][c]) and (c, r) not in blocked:
                    candidates.append((c, r))

    if candidates:
        return random.choice(candidates)
    return None


def dungeon_player_count(instance) -> int:
    if instance is None:
        return 0
    return sum(1 for p in game.players.values() if p.room in instance.active_rooms)


# ---------------------------------------------------------------------------
# Dungeon graph generation
# ---------------------------------------------------------------------------

def _build_spanning_tree(active_cells, entrance):
    """Build a random spanning tree over the dungeon grid.

    Uses randomized DFS to create a single connected tree through all
    active cells.  Returns a set of frozenset edges.
    """
    cell_set = set(active_cells)

    if entrance not in cell_set:
        log.debug(f"[DUNGEON] BUG: entrance {entrance} not in active_cells — "
                  f"spanning tree will be incomplete")

    # Build adjacency list from grid neighbors
    adj = {c: [] for c in cell_set}
    for (col, row) in cell_set:
        for dc, dr in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            neighbor = (col + dc, row + dr)
            if neighbor in cell_set:
                adj[(col, row)].append(neighbor)

    # Randomized DFS spanning tree
    visited = {entrance}
    tree_edges = set()
    stack = [entrance]

    while stack:
        cell = stack[-1]
        neighbors = [n for n in adj.get(cell, []) if n not in visited]
        if neighbors:
            random.shuffle(neighbors)
            next_cell = neighbors[0]
            tree_edges.add(frozenset((cell, next_cell)))
            visited.add(next_cell)
            stack.append(next_cell)
        else:
            stack.pop()

    # Defense: connect any disconnected components via grid-adjacent bridges
    unvisited = cell_set - visited
    if unvisited:
        log.debug(f"[DUNGEON] BUG: {len(unvisited)} cells unreachable from "
                  f"entrance {entrance} — bridging disconnected components")
        while unvisited:
            # Only bridge grid-adjacent pairs (distance 1) so doors work
            adjacent_pairs = [
                (v, u) for v in visited for u in unvisited
                if abs(v[0] - u[0]) + abs(v[1] - u[1]) == 1
            ]
            if not adjacent_pairs:
                log.debug(f"[DUNGEON] BUG: {len(unvisited)} cells have no "
                          f"grid-adjacent bridge to visited cells — layout "
                          f"is structurally broken, skipping them")
                break
            bridge_v, bridge_u = random.choice(adjacent_pairs)
            tree_edges.add(frozenset((bridge_v, bridge_u)))
            # DFS through the newly connected component
            visited.add(bridge_u)
            stack = [bridge_u]
            while stack:
                cell = stack[-1]
                neighbors = [n for n in adj.get(cell, []) if n not in visited]
                if neighbors:
                    random.shuffle(neighbors)
                    next_cell = neighbors[0]
                    tree_edges.add(frozenset((cell, next_cell)))
                    visited.add(next_cell)
                    stack.append(next_cell)
                else:
                    stack.pop()
            unvisited = cell_set - visited

    return tree_edges


def _pick_extra_edges(active_cells, tree_edges, exclude=None):
    """Sample ~25% of non-tree grid-adjacent edges for non-linearity.

    Edges touching any cell in `exclude` are never added (keeps dead ends).
    Returns a set of frozenset edges.
    """
    exclude = exclude or set()
    cell_set = set(active_cells)

    # Build grid adjacency
    adj = {c: [] for c in cell_set}
    for (col, row) in cell_set:
        for dc, dr in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            neighbor = (col + dc, row + dr)
            if neighbor in cell_set:
                adj[(col, row)].append(neighbor)

    # Collect non-tree edges that don't touch excluded cells
    non_tree = set()
    for cell in cell_set:
        for n in adj[cell]:
            edge = frozenset((cell, n))
            if edge not in tree_edges and not (edge & exclude):
                non_tree.add(edge)

    if not non_tree:
        return set()

    non_tree = list(non_tree)
    extra_count = max(1, len(non_tree) // 4)
    return set(random.sample(non_tree, min(extra_count, len(non_tree))))


def _assign_difficulty_tiers(active_cells, entrance, boss, sanctum, treasure, type_config):
    """Assign easy/challenging/hard tier to each non-special dungeon cell.

    Distribution is configured per dungeon type in dungeon_types.py.
    Cells are shuffled randomly — difficulty is not distance-based.
    Special cells (entrance, boss, sanctum, treasure) are excluded.

    Returns dict of cell -> "easy"|"challenging"|"hard".
    """
    dist = type_config.get("difficulty_distribution",
                           {"easy": 0.50, "challenging": 0.30, "hard": 0.20})
    special = {entrance, boss, sanctum, treasure}
    regular = [c for c in active_cells if c not in special]
    random.shuffle(regular)

    n = len(regular)
    n_easy = round(n * dist["easy"])
    n_hard = round(n * dist["hard"])
    n_challenging = n - n_easy - n_hard  # remainder goes to challenging

    tiers = {}
    for i, cell in enumerate(regular):
        if i < n_easy:
            tiers[cell] = "easy"
        elif i < n_easy + n_challenging:
            tiers[cell] = "challenging"
        else:
            tiers[cell] = "hard"
    # Entrance gets easy tier so its template monsters still spawn
    tiers[entrance] = "easy"
    return tiers


def _identify_trap_rooms(cell_difficulty, boss, entrance, sanctum):
    """Identify which rooms become trap rooms (lock-in until cleared).

    Hard = always trapped. Challenging = 1/3 chance. Easy = never.
    Boss room is always a trap. Entrance and sanctum are never traps.

    Returns a set of cells.
    """
    trap_cells = {boss}
    for cell, tier in cell_difficulty.items():
        if cell in (entrance, boss, sanctum):
            continue
        if tier == "hard":
            trap_cells.add(cell)
        elif tier == "challenging" and random.random() < TRAP_ROOM_CHANCE:
            trap_cells.add(cell)
    return trap_cells



def _get_cell_exits(cell, connections, entrance_col, entrance_row, dungeon_id, exit_room):
    """Compute exits for a cell based on the dungeon connection graph."""
    col, row = cell
    exits = {}
    for direction, (dc, dr) in [("north", (0, -1)), ("south", (0, 1)),
                                 ("west", (-1, 0)), ("east", (1, 0))]:
        neighbor = (col + dc, row + dr)
        if frozenset((cell, neighbor)) in connections:
            exits[direction] = f"{dungeon_id}_{neighbor[0]}_{neighbor[1]}"
    if col == entrance_col and row == entrance_row:
        exits["up"] = exit_room
    return exits


# ---------------------------------------------------------------------------
# Locked doors & key placement
# ---------------------------------------------------------------------------

_DIR_OFFSETS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}


def _place_locked_doors(topo, min_locks, max_locks):
    """Choose which connections to lock and build the zone graph.

    Does NOT place keys — that happens in the main pipeline via topo queries.

    Returns (locked_doors, zone_of, zone_cells, zone_adj).
    locked_doors: set of frozenset edges that are locked.
    zone_of: cell -> zone_id (connected components without locked edges).
    zone_cells: zone_id -> set of cells.
    zone_adj: zone_id -> list of zone_ids (multigraph, for solver).
    """
    connections = topo.connections
    active_cells = topo.cells

    # Exclude sanctum's single connection (dead end, pointless to lock)
    candidates = [e for e in connections
                  if not any(topo.has_mark(c, "sanctum") for c in e)]
    effective_max = min(max_locks, len(candidates))
    num_locks = random.randint(min(min_locks, effective_max), effective_max)
    if num_locks == 0:
        zone_of = {c: 0 for c in active_cells}
        zone_cells = {0: set(active_cells)}
        return set(), zone_of, zone_cells, {}

    locked = set(random.sample(candidates, num_locks))
    log.debug(f"[LOCKS] Chose {num_locks} locks from {len(candidates)} candidates")

    # Build zone graph (connected components without locked edges)
    unlocked_connections = connections - locked
    cell_set = set(active_cells)

    zone_of = {}    # cell -> zone_id
    zone_cells = {} # zone_id -> set of cells
    zid = 0
    for cell in active_cells:
        if cell in zone_of:
            continue
        queue = deque([cell])
        zone_of[cell] = zid
        zone_cells[zid] = {cell}
        while queue:
            c = queue.popleft()
            for dc, dr in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
                nb = (c[0] + dc, c[1] + dr)
                if nb in cell_set and nb not in zone_of:
                    edge = frozenset((c, nb))
                    if edge in unlocked_connections:
                        zone_of[nb] = zid
                        zone_cells[zid].add(nb)
                        queue.append(nb)
        zid += 1

    # Build zone adjacency — full multigraph for solver.
    # Self-loops = redundant doors (player can walk around). Remove them.
    redundant = set()
    zone_adj = {}
    for edge in locked:
        cells = list(edge)
        za, zb = zone_of[cells[0]], zone_of[cells[1]]
        if za == zb:
            redundant.add(edge)
            continue
        zone_adj.setdefault(za, []).append(zb)
        zone_adj.setdefault(zb, []).append(za)
    if redundant:
        locked -= redundant
        num_locks = len(locked)
        log.debug(f"[LOCKS] Removed {len(redundant)} redundant self-loop doors (bypassable)")

    entrance_zone = zone_of[topo.entrance]
    if entrance_zone not in zone_adj:
        zone_adj[entrance_zone] = []

    solver_edges = sum(len(v) for v in zone_adj.values()) // 2
    log.debug(f"[LOCKS] Zone graph: {zone_adj}")
    log.debug(f"[LOCKS] Entrance zone: {entrance_zone}, solver edges: {solver_edges}, "
              f"total doors: {num_locks}")

    return locked, zone_of, zone_cells, zone_adj


def _solve_key_distribution(zone_adj, entrance_zone, num_locks):
    """Solve for which zones should contain keys.

    Returns {zone_id: num_keys}. Falls back to all keys in entrance zone
    if the solver finds no solutions.
    """
    from tools.key_math.key_solver import solve as solve_keys

    solutions = solve_keys(zone_adj, entrance_zone, max_keys=2)
    log.debug(f"[LOCKS] Solver returned {len(solutions)} solutions")

    if solutions:
        distribution = random.choice(solutions)
        log.debug(f"[LOCKS] Chosen distribution: {distribution}")
        return distribution

    # Fallback: all keys in entrance zone
    log.debug(f"[LOCKS] No solutions, falling back to entrance zone")
    return {entrance_zone: num_locks}



# ---------------------------------------------------------------------------
# Trap room (lock-in) support
# ---------------------------------------------------------------------------

# Inner ring doorway positions: (col, row) per direction
_INNER_RING = {
    "north": [(6, 1), (7, 1), (8, 1)],
    "south": [(6, 9), (7, 9), (8, 9)],
    "west":  [(1, 4), (1, 5), (1, 6)],
    "east":  [(13, 4), (13, 5), (13, 6)],
}

# Direction to "inward" offset (toward room center)
_INWARD_OFFSET = {
    "north": (0, 1),
    "south": (0, -1),
    "west":  (1, 0),
    "east":  (-1, 0),
}

# One tile inward from the center doorway — used when the doorway tile itself
# is blocked (locked/trapped) and we need to place a marker just inside the room.
_INWARD_FROM_DOORWAY = {
    "north": (1, 7),
    "south": (9, 7),
    "west":  (5, 1),
    "east":  (5, 13),
}

TRAP_ROOM_CHANCE = 1 / 3
TRAP_ROOM_MIN_MONSTERS = 3
_MONSTER_MIN_SPACING = 2  # minimum Manhattan distance between dynamically placed monsters


def _find_monster_positions(room_id, count, exits):
    """Find valid walkable positions for dynamically placed monsters.

    Uses BFS reachability from doorways, excludes doorway inner ring and
    edge tiles.  Tries to space monsters apart (Manhattan >= 2), relaxes
    if needed.  Returns list of (x, y) tuples.
    """
    room = game.rooms.get(room_id)
    if not room:
        return []
    tilemap = room["tilemap"]

    # BFS seeds from active exits + stairs
    seeds = []
    for direction in exits:
        if direction in DOORWAY_TILES:
            seeds.extend(DOORWAY_TILES[direction])
    for ry, trow in enumerate(tilemap):
        for rx, tile in enumerate(trow):
            if tile == "SU":
                seeds.append((ry, rx))

    reachable = bfs_reachable(tilemap, game.is_walkable_tile, seeds) if seeds else set()

    # Doorway exclusion zones (inner ring)
    exclusion = set()
    for direction in exits:
        if direction in _INNER_RING:
            exclusion.update((c, r) for c, r in _INNER_RING[direction])

    # bfs_reachable returns (row, col); convert to (col, row)
    candidates = [(c, r) for (r, c) in reachable
                  if 1 <= r <= 9 and 1 <= c <= 13
                  and (c, r) not in exclusion]
    random.shuffle(candidates)

    # Pick positions with spacing
    positions = []
    occupied = set()
    for cx, cy in candidates:
        if len(positions) >= count:
            break
        if any(abs(cx - ox) + abs(cy - oy) < _MONSTER_MIN_SPACING
               for ox, oy in occupied):
            continue
        positions.append((cx, cy))
        occupied.add((cx, cy))

    # Relax spacing if we couldn't place enough
    if len(positions) < count:
        for cx, cy in candidates:
            if len(positions) >= count:
                break
            if (cx, cy) not in occupied:
                positions.append((cx, cy))
                occupied.add((cx, cy))

    return positions


def _resolve_dynamic_monsters(room_id, monster_groups, difficulty_tier, type_config, exits):
    """Convert monster_groups to concrete placements based on difficulty tier.

    Each group has a pack fraction (0.0-1.0+) which is multiplied by the
    monster's pack size (pack_min..pack_max) to get the challenging-tier count,
    then scaled by the difficulty tier multiplier.

    Returns list of {"kind", "x", "y"} dicts (same format as monster_placements).
    """
    scaling = type_config.get("difficulty_scaling",
                              {"easy": 0.5, "challenging": 1.0, "hard": 1.5})
    multiplier = scaling.get(difficulty_tier, 1.0)

    # Default pack size for monsters without pack_min/pack_max
    DEFAULT_PACK_MIN, DEFAULT_PACK_MAX = 3, 5

    # Calculate total monsters needed across all groups
    groups_with_counts = []
    total_needed = 0
    for group in monster_groups:
        fraction = group["count"]
        kind = group["kind"]
        stats = game.monster_stats.get(kind, {})
        pack_min = stats.get("pack_min", DEFAULT_PACK_MIN)
        pack_max = stats.get("pack_max", DEFAULT_PACK_MAX)
        pack_size = random.randint(pack_min, pack_max)
        base_count = fraction * pack_size
        scaled = base_count * multiplier
        # Probabilistic rounding
        final = int(scaled) + (1 if random.random() < (scaled % 1) else 0)
        final = max(1, final)
        groups_with_counts.append((kind, final))
        total_needed += final

    # Find positions for all monsters at once (better spacing)
    positions = _find_monster_positions(room_id, total_needed, exits)

    placements = []
    pos_idx = 0
    for kind, count in groups_with_counts:
        for _ in range(count):
            if pos_idx < len(positions):
                x, y = positions[pos_idx]
                pos_idx += 1
            else:
                # Fallback: place at room center-ish
                x, y = 7, 5
            placements.append({"kind": kind, "x": x, "y": y})

    log.debug(f"[DUNGEON] {room_id} dynamic monsters ({difficulty_tier}, {multiplier}x): "
              f"{[(k, c) for k, c in groups_with_counts]} -> {len(placements)} placed")
    return placements


def _apply_trap_room(room_id, tilemap, exits):
    """Turn a resolved room into a trap room: force 2nd-ring clearance, relocate monsters."""
    # Collect all inner-ring exclusion tiles for active exits
    exclusion = set()
    for direction in exits:
        if direction not in _INNER_RING:
            continue
        exclusion.update(_INNER_RING[direction])

        # Force 2nd-ring tiles to match the outer-ring floor tile
        if direction == "north":
            floor_tile = tilemap[0][7]
            for c in (6, 7, 8):
                tilemap[1][c] = floor_tile
        elif direction == "south":
            floor_tile = tilemap[10][7]
            for c in (6, 7, 8):
                tilemap[9][c] = floor_tile
        elif direction == "west":
            floor_tile = tilemap[5][0]
            for r in (4, 5, 6):
                tilemap[r][1] = floor_tile
        elif direction == "east":
            floor_tile = tilemap[5][14]
            for r in (4, 5, 6):
                tilemap[r][13] = floor_tile

    # Relocate any monsters sitting on exclusion tiles (doorway spawn zones)
    templates = game.monster_templates.get(room_id, [])
    for t in templates:
        if (t["x"], t["y"]) not in exclusion:
            continue
        # Find which direction this exclusion tile belongs to
        for direction, tiles in _INNER_RING.items():
            if direction not in exits or (t["x"], t["y"]) not in tiles:
                continue
            # Try pushing 1 tile inward
            dx, dy = _INWARD_OFFSET[direction]
            nx, ny = t["x"] + dx, t["y"] + dy
            if (0 <= nx < ROOM_COLS and 0 <= ny < ROOM_ROWS
                    and game.is_walkable_tile(tilemap[ny][nx])
                    and (nx, ny) not in exclusion):
                t["x"], t["y"] = nx, ny
            else:
                # Random search for a nearby walkable tile
                for _ in range(10):
                    rx = t["x"] + random.randint(-3, 3)
                    ry = t["y"] + random.randint(-3, 3)
                    if (0 <= rx < ROOM_COLS and 0 <= ry < ROOM_ROWS
                            and game.is_walkable_tile(tilemap[ry][rx])
                            and (rx, ry) not in exclusion):
                        t["x"], t["y"] = rx, ry
                        break
            break

    # Re-check monster reachability after relocation — a random offset
    # could have pushed a monster into a walkable but disconnected pocket.
    _fix_post_wall_reachability(room_id, tilemap, exits)

    game.rooms[room_id]["locked"] = True
    log.debug(f"[DUNGEON] Room {room_id} is a trap room (locked)")


# ---------------------------------------------------------------------------
# Post-wall reachability fix
# ---------------------------------------------------------------------------

def _fix_post_wall_reachability(room_id, tilemap, exits):
    """After walling off unused exits, ensure open doorways are connected
    and relocate any monsters stranded in unreachable pockets.

    Reuses patch_unreachable_doorways (carve paths) and
    patch_monster_placements (relocate/remove monsters) from ai_generator.
    """
    walkable = {t for t, r in game.custom_tile_recipes.items()
                if r.get("walkable", False)}

    # Only check doorways that are still open
    open_doorways = []
    for direction in exits:
        if direction in DOORWAY_TILES:
            open_doorways.extend(DOORWAY_TILES[direction])
    if not open_doorways:
        return

    # Wrap tilemap for the patching functions' data-dict interface
    data = {"tilemap": tilemap}

    # 1. Carve paths to reconnect any open doorways cut off by walling
    patches = patch_unreachable_doorways(data, walkable, doorways=open_doorways)
    for p in patches:
        log.debug(f"[DUNGEON] {room_id}: {p}")

    # 2. Relocate monsters stranded in unreachable tiles
    templates = game.monster_templates.get(room_id)
    if templates:
        data["monster_placements"] = templates
        patches = patch_monster_placements(data, walkable)
        for p in patches:
            log.debug(f"[DUNGEON] {room_id}: {p}")
        # patch_monster_placements may filter out removed entries
        game.monster_templates[room_id] = data["monster_placements"]
        if not game.monster_templates[room_id]:
            game.monster_templates.pop(room_id, None)


# ---------------------------------------------------------------------------
# Room resolution
# ---------------------------------------------------------------------------

def _resolve_room_from_entry(room_id, entry_data, exits, cell, music_track, is_entrance, biome="dungeon", music_override=None, wall_tile="DW", is_trap=False, locked_directions=None, difficulty_tier=None, type_config=None):
    """Materialize a library entry's data into a live game.rooms[] entry.

    entry_data: dict with 'name', 'tilemap' (list[list[str]]), 'monster_placements'
    music_override: if set, use this music instead of the dungeon's track.
    wall_tile: tile code to use for walling off unused exits.
    locked_directions: set of direction strings whose doorways get LD/KD tiles.
    """
    if locked_directions is None:
        locked_directions = set()
    # Deep-copy tilemap (string tile codes)
    tilemap = [list(r) for r in entry_data["tilemap"]]
    if "north" not in exits:
        for c in (6, 7, 8):
            tilemap[0][c] = wall_tile
    if "south" not in exits:
        for c in (6, 7, 8):
            tilemap[10][c] = wall_tile
    if "west" not in exits:
        for r in (4, 5, 6):
            tilemap[r][0] = wall_tile
    if "east" not in exits:
        for r in (4, 5, 6):
            tilemap[r][14] = wall_tile

    # Entrance gets stairs up
    if is_entrance:
        tilemap[9][7] = "SU"

    # Build spawn points
    spawn_points = {"default": DEFAULT_SPAWN}
    for direction, pos in EDGE_SPAWN_POINTS.items():
        if direction in exits:
            spawn_points[direction] = pos
    # Scan for stairs (numeric or string)
    for ry, trow in enumerate(tilemap):
        for rx, tile in enumerate(trow):
            if tile == "SU":
                spawn_points["down"] = (rx, ry)

    raw_name = entry_data.get("name", "Dungeon Room")
    # Prettify snake_case names from older AI generations
    if "_" in raw_name and raw_name == raw_name.lower():
        raw_name = raw_name.replace("_", " ").title()
    game.rooms[room_id] = {
        "name": raw_name,
        "exits": exits,
        "tilemap": tilemap,
        "spawn_points": spawn_points,
        "biome": biome,
        "music": music_override or music_track,
    }

    # Register monster templates from fixed placements
    placements = entry_data.get("monster_placements", [])
    if placements:
        game.monster_templates[room_id] = [
            {"kind": p["kind"], "x": p["x"], "y": p["y"]}
            for p in placements
        ]

    # Dynamic monster groups — scale count by difficulty tier, place dynamically
    monster_groups = entry_data.get("monster_groups", [])
    if monster_groups and difficulty_tier and type_config:
        dynamic = _resolve_dynamic_monsters(
            room_id, monster_groups, difficulty_tier, type_config, exits)
        if dynamic:
            existing = game.monster_templates.get(room_id, [])
            game.monster_templates[room_id] = existing + dynamic

    # After walling off exits, fix room connectivity and monster reachability.
    # AI rooms assume all 4 exits open — walling unused ones can disconnect
    # doorways or strand monsters in unreachable pockets.
    _fix_post_wall_reachability(room_id, tilemap, exits)

    # Trap room setup — decided at dungeon creation time, applied here.
    # Must run BEFORE locked door tiles so _apply_trap_room reads real floor tiles.
    if is_trap:
        _apply_trap_room(room_id, tilemap, exits)

    # Place locked door tiles (LD KD LD) AFTER trap room setup
    # so _apply_trap_room doesn't copy LD/KD into the inner ring
    locked_originals = {}
    for direction in locked_directions:
        if direction not in DOORWAY_TILES:
            continue
        tiles = DOORWAY_TILES[direction]
        # tiles is 3 positions: [side, center, side]
        for i, (r, c) in enumerate(tiles):
            locked_originals[(r, c)] = tilemap[r][c]
            tilemap[r][c] = "KD" if i == 1 else "LD"

    return locked_originals


def create_dungeon(type_id) -> DungeonInstance | None:
    """Create a new dungeon instance for a given type.

    Picks a random layout, assigns library entries to each cell (~50% precreated,
    ~50% custom), but only resolves the entrance room immediately. Other rooms
    are resolved lazily when a player enters them.
    """
    from server.dungeon_types import DUNGEON_TYPES

    type_config = DUNGEON_TYPES.get(type_id)
    if not type_config:
        log.debug(f"[DUNGEON] Unknown dungeon type: {type_id}")
        return None

    layout = random.choice(type_config["layouts"])
    music_track = random.choice(type_config["music_tracks"])
    boss_track = random.choice(type_config["boss_tracks"])

    # Get libraries for this type
    libs = game.content_libraries.get(type_id, {})
    room_library = libs.get("rooms")

    if not room_library or room_library.real_count == 0:
        log.debug(f"[DUNGEON] No room library entries for type '{type_id}', cannot create dungeon")
        return None

    # Find all active cells in layout
    active_cells = []
    for row_idx, row_str in enumerate(layout["grid"]):
        for col_idx, ch in enumerate(row_str):
            if ch == "X":
                active_cells.append((col_idx, row_idx))

    entrance_col, entrance_row = layout["entrance"]
    entrance_room_id = f"{type_id}_{entrance_col}_{entrance_row}"
    active_rooms = set()
    room_map = {}
    cell_assignments = {}

    # Assign library entries to cells
    permanent_entries = [e for e in room_library.real_entries if e.permanent]
    custom_entries = [e for e in room_library.real_entries if not e.permanent]
    has_placeholders = room_library.placeholder_count > 0
    max_custom_slots = 15

    random.shuffle(permanent_entries)
    random.shuffle(custom_entries)

    # Shuffle cells so precreated/custom rooms are spatially distributed
    random.shuffle(active_cells)

    # Split: entrance always precreated, ~50% of rest are custom
    non_entrance = [c for c in active_cells if not (c[0] == entrance_col and c[1] == entrance_row)]
    if custom_entries or has_placeholders:
        num_custom = len(non_entrance) // 2
    else:
        num_custom = 0
    custom_cell_set = set(non_entrance[:num_custom])

    # Build custom slot pool: pre-fill with existing custom library entries, rest are placeholders
    if has_placeholders:
        num_slots = max_custom_slots
    else:
        num_slots = min(len(custom_entries), max_custom_slots)
    custom_slots = []
    for i in range(num_slots):
        if i < len(custom_entries):
            custom_slots.append({"data": custom_entries[i].data, "entry": custom_entries[i]})
        else:
            custom_slots.append(None)
    random.shuffle(custom_slots)

    # Assign rooms to cells — custom cells get a slot from the pool upfront.
    # If the slot is empty/placeholder, fall back to precreated immediately.
    perm_idx = 0
    for cell in active_cells:
        room_id = f"{type_id}_{cell[0]}_{cell[1]}"
        active_rooms.add(room_id)
        room_map[cell] = room_id

        if cell in custom_cell_set:
            slot = custom_slots.pop() if custom_slots else None
            if slot is not None and slot.get("data") is not None:
                cell_assignments[cell] = {
                    "source": "custom", "entry": slot.get("entry"),
                    "slot_data": slot["data"], "resolved": False,
                }
            else:
                # Empty slot or pool exhausted — fall back to precreated
                entry = permanent_entries[perm_idx % len(permanent_entries)]
                perm_idx += 1
                cell_assignments[cell] = {"source": "precreated", "entry": entry, "resolved": False}
        else:
            entry = permanent_entries[perm_idx % len(permanent_entries)]
            perm_idx += 1
            cell_assignments[cell] = {"source": "precreated", "entry": entry, "resolved": False}

    # ===================================================================
    # Placement pipeline — all spatial queries go through the topology
    # ===================================================================
    entrance = (entrance_col, entrance_row)

    # --- Generation: build spanning tree ---
    tree_edges = _build_spanning_tree(active_cells, entrance)
    topo = DungeonTopology(active_cells, tree_edges, entrance)

    # --- Sanctum: the seal-shard room at the dungeon's deepest point ---
    sanctum = max(topo.leaves, key=lambda c:
        topo.dist(c, "entrance")                # furthest tree-leaf from entrance
    )
    topo.mark(sanctum, "sanctum")

    # --- Generation: add extra edges (sanctum stays a dead end) ---
    extra_edges = _pick_extra_edges(active_cells, tree_edges, exclude={sanctum})
    topo.add_connections(extra_edges)

    # --- Boss: guards the sanctum, one room before it ---
    boss_cell = topo.parent_of(sanctum, "entrance")
    topo.mark(boss_cell, "boss")

    # --- Treasure chest: far from both boss and entrance ---
    # (contains lantern in d1, TBD for other dungeons)
    # Hard-exclude sanctum — only the seal shard belongs there
    treasure_candidates = [c for c in topo.cells if not topo.has_mark(c, "sanctum")]
    treasure_cell = max(treasure_candidates, key=lambda c: (
        topo.lacks_mark(c, "boss"),             # avoid the boss room
        c != topo.entrance,                     # avoid the entrance
        topo.dist(c, "boss") + topo.dist(c, "entrance"),  # maximize remoteness
    ))
    topo.mark(treasure_cell, "treasure")

    # --- Difficulty tiers: easy/challenging/hard ---
    cell_difficulty = _assign_difficulty_tiers(
        active_cells, entrance, boss_cell, sanctum, treasure_cell,
        type_config)

    # --- Trap rooms: lock-in until cleared (tier-based) ---
    trap_cells = _identify_trap_rooms(cell_difficulty, boss_cell, entrance, sanctum)
    for cell in trap_cells:
        topo.mark(cell, "trap")

    # --- Darkness ---
    if type_id == "d1":
        # Entrance→treasure path stays lit so players can find the chest
        immune = topo.path_between("entrance", "treasure")
        dark_cells = {n for n in topo.neighbors(boss_cell) if n not in immune}
        eligible = [c for c in topo.cells if c not in immune and c not in dark_cells]
        random.shuffle(eligible)
        dark_cells |= set(eligible[:round(len(eligible) * DARK_ROOM_FRACTION)])
    else:
        # Other dungeons: flat dark fraction, but never boss or sanctum
        eligible = [c for c in topo.cells
                    if c != entrance
                    and not topo.has_mark(c, "boss")
                    and not topo.has_mark(c, "sanctum")]
        random.shuffle(eligible)
        dark_cells = set(eligible[:round(len(eligible) * DEFAULT_DARK_FRACTION)])
    for c in dark_cells:
        topo.mark(c, "dark")
    # Note: D1 rooms with bright tiles (braziers/sconces) are auto-flagged dark
    # at room resolution time in resolve_dungeon_room, not here.

    # --- Locked doors (just doors + zones, no key placement) ---
    lock_min = type_config.get("min_locks", 0)
    lock_max = type_config.get("max_locks", 3)
    locked_doors, zone_of, zone_cells, zone_adj = _place_locked_doors(
        topo, lock_min, lock_max)
    # Deduplicate zone_adj for topology (solver gets the multigraph version)
    deduped_zone_adj = {z: set(neighbors) for z, neighbors in zone_adj.items()}
    topo.set_zones(zone_of, zone_cells, deduped_zone_adj)

    # --- Keys: one per locked door, placed in solver-assigned zones ---
    num_locks = len(locked_doors)
    entrance_zone = zone_of[entrance]
    key_distribution = _solve_key_distribution(zone_adj, entrance_zone, num_locks)

    # Precompute locked door counts per cell (for key scoring)
    locked_door_count = {}
    for edge in locked_doors:
        for c in edge:
            locked_door_count[c] = locked_door_count.get(c, 0) + 1

    key_cells = []
    for zone_id, num_keys in key_distribution.items():
        pool = list(topo.cells_in_zone(zone_id))
        for _ in range(num_keys):
            pick = max(pool, key=lambda c: (
                -topo.marks(c, "key"),              # spread keys across rooms
                topo.lacks_mark(c, "treasure"),      # avoid the treasure room
                not topo.is_on_path(c, "entrance", "sanctum"),  # prefer side rooms
                topo.has_mark(c, "trap"),            # prefer trap rooms (thematic)
                locked_door_count.get(c, 0) == 0,   # prefer rooms with no locked doors
                locked_door_count.get(c, 0) >= 2,   # then prefer 2+ locked doors
            ))
            topo.mark(pick, "key")
            key_cells.append(pick)

    if len(key_cells) != num_locks:
        log.debug(f"[LOCKS] WARNING: keys={len(key_cells)} != doors={num_locks}!")

    # --- Map & compass: zone-aware ---
    # Step 1: rank zones by remoteness from entrance and boss
    # Exclude sanctum/boss cells from availability — sanctum is seal-shard only
    zone_scores = {}
    for z in topo.zone_ids:
        remoteness = topo.zone_dist(z, "entrance") + topo.zone_dist(z, "boss")
        available = sum(1 for c in topo.cells_in_zone(z)
                        if topo.lacks_mark(c, "treasure")
                        and topo.lacks_mark(c, "key")
                        and topo.lacks_mark(c, "sanctum")
                        and topo.lacks_mark(c, "boss"))
        zone_scores[z] = (available > 0, remoteness, available)

    ranked_zones = sorted(topo.zone_ids, key=lambda z: zone_scores[z], reverse=True)

    # Step 2: pick best cell in a zone (sanctum/boss hard-excluded)
    def _pick_cell_in_zone(zone_id):
        candidates = [c for c in topo.cells_in_zone(zone_id)
                       if not topo.has_mark(c, "sanctum")
                       and not topo.has_mark(c, "boss")]
        if not candidates:
            candidates = list(topo.cells_in_zone(zone_id))
        return max(candidates, key=lambda c: (
            topo.lacks_mark(c, "treasure"),        # avoid the treasure room
            topo.lacks_mark(c, "key"),             # avoid rooms with keys
            topo.lacks_mark(c, "map"),             # avoid rooms with map (for compass)
            c != topo.entrance,                    # avoid the entrance
            not topo.is_on_path(c, "entrance", "sanctum"),  # prefer side rooms
            topo.dist(c, "entrance") + topo.dist(c, "boss"),  # maximize remoteness
        ))

    item_cells = {}

    # Treasure chest item (lantern for d1, tide_medallion for d2)
    treasure_item_type = {"d1": "lantern", "d2": "tide_medallion"}.get(type_id, "lantern")
    item_cells[treasure_item_type] = treasure_cell

    # Map
    if ranked_zones:
        map_cell = _pick_cell_in_zone(ranked_zones[0])
        topo.mark(map_cell, "map")
        item_cells["map"] = map_cell

    # Compass (second-best zone, or same zone if only one)
    if ranked_zones:
        compass_zone = ranked_zones[1] if len(ranked_zones) > 1 else ranked_zones[0]
        compass_cell = _pick_cell_in_zone(compass_zone)
        topo.mark(compass_cell, "compass")
        item_cells["compass"] = compass_cell

    log.debug(f"[DUNGEON] Item placement: {item_cells} "
              f"(zones: {len(zone_scores)}, zone_scores: {zone_scores})")
    log.debug(f"[LOCKS] Placed {len(key_cells)} keys for {num_locks} doors "
              f"({len(zone_adj)} zones)")

    # ===================================================================
    # Override cell assignments for special rooms (boss, sanctum templates)
    # ===================================================================
    from server.dungeon_content import _template_to_room_data
    from server.content_library import LibraryEntry

    type_templates = game.dungeon_templates.get(type_id, {})
    boss_template_id = type_config["boss_template"]
    sanctum_template_id = type_config["treasure_template"]  # TODO: rename in dungeon_types

    for special_id, special_cell in [(boss_template_id, boss_cell),
                                     (sanctum_template_id, sanctum)]:
        template = type_templates.get(special_id)
        if template:
            room_data = _template_to_room_data(template)
            entry = LibraryEntry(
                id=special_id, content_type="room",
                tags=["dungeon", "special"], created_at=time.time(),
                data=room_data, permanent=True,
            )
            cell_assignments[special_cell] = {
                "source": "special", "entry": entry, "resolved": False,
            }

    # ===================================================================
    # Populate DungeonInstance
    # ===================================================================
    instance = DungeonInstance(
        dungeon_id=type_id,
        layout=layout,
        room_map=room_map,
        active_rooms=active_rooms,
        entrance_room_id=entrance_room_id,
        music_track=music_track,
        boss_track=boss_track,
    )
    instance.cell_assignments = cell_assignments
    instance.cell_difficulty = cell_difficulty
    instance.custom_slots = custom_slots
    instance.topo = topo
    instance.connections = topo.connections
    instance.boss_cell = boss_cell
    instance.treasure_cell = treasure_cell
    instance.sanctum_cell = sanctum
    instance.item_cells = item_cells
    instance.trap_cells = trap_cells
    instance.locked_doors = locked_doors
    instance.key_cells = key_cells
    instance.zone_of = zone_of
    instance.zone_cells = zone_cells
    instance.dark_cells = dark_cells

    game.active_dungeons[type_id] = instance
    for room_id in active_rooms:
        game.room_to_dungeon[room_id] = type_id

    # Logging
    precreated_count = sum(1 for a in cell_assignments.values() if a["source"] == "precreated")
    custom_count = sum(1 for a in cell_assignments.values() if a["source"] == "custom")
    special_count = sum(1 for a in cell_assignments.values() if a["source"] == "special")
    filled_slots = sum(1 for s in custom_slots if s is not None)
    empty_slots = num_slots - filled_slots

    boss_id = f"{type_id}_{boss_cell[0]}_{boss_cell[1]}"
    sanctum_id = f"{type_id}_{sanctum[0]}_{sanctum[1]}"
    log.debug(f"[DUNGEON] Created {type_id}: layout={layout['name']}, "
              f"rooms={len(active_rooms)} ({precreated_count}p/{custom_count}c/{special_count}s), "
              f"slots={num_slots} ({filled_slots}filled/{empty_slots}empty), "
              f"entrance={entrance_room_id}, boss={boss_id}, sanctum={sanctum_id}, "
              f"music={music_track}, boss_music={boss_track}, connections={len(topo.connections)}, "
              f"locked_doors={len(locked_doors)}, keys={len(key_cells)}, "
              f"difficulty={sum(1 for t in cell_difficulty.values() if t=='easy')}e/"
              f"{sum(1 for t in cell_difficulty.values() if t=='challenging')}c/"
              f"{sum(1 for t in cell_difficulty.values() if t=='hard')}h")
    broadcast_debug(f"Dungeon {type_id} created: {layout['name']} ({len(active_rooms)} rooms, "
                    f"boss={boss_id}, sanctum={sanctum_id})")

    # Dump dungeon layout to file for debugging
    _dump_dungeon_debug(instance, active_cells, topo.connections, locked_doors,
                        key_cells, item_cells, entrance, boss_cell, sanctum,
                        dark_cells, treasure_cell)

    # Resolve the entrance room immediately (always precreated, so instant)
    resolve_dungeon_room(instance, (entrance_col, entrance_row))

    return instance


def _dump_dungeon_debug(instance, active_cells, connections, locked_doors,
                        key_cells, item_cells, entrance, boss_cell, sanctum_cell,
                        dark_cells=None, treasure_cell=None):
    """Write a human-readable dungeon layout to dungeon.txt for debugging."""
    dark_cells = dark_cells or set()
    lines = []
    lines.append(f"=== Dungeon: {instance.dungeon_id} ===")
    lines.append(f"Entrance: {entrance}  Boss: {boss_cell}  Sanctum: {sanctum_cell}  Treasure: {treasure_cell}")
    lines.append(f"Locked doors: {len(locked_doors)}  Keys: {len(key_cells)}  "
                 f"Dark rooms: {len(dark_cells)}")
    lines.append("")

    # Build cell labels
    labels = {}
    for c in active_cells:
        tag = []
        if c == entrance:
            tag.append("ENT")
        if c == boss_cell:
            tag.append("BOSS")
        if c == sanctum_cell:
            tag.append("SANC")
        if c == treasure_cell:
            tag.append("TRES")
        if c in dark_cells:
            tag.append("DARK")
        tier = instance.cell_difficulty.get(c)
        if tier:
            tag.append(tier[0].upper())  # E/C/H
        if c in instance.trap_cells:
            tag.append("TRAP")
        # Mark critical path cells (entrance→treasure shortest path)
        topo = instance.topo
        if topo:
            path = topo.path_between("entrance", "treasure")
            if c in path and c != entrance and c != treasure_cell:
                tag.append("PATH")
        for itype, icell in item_cells.items():
            if c == icell and itype != "lantern":  # lantern already tagged above
                tag.append(itype.upper())
        key_count = sum(1 for k in key_cells if k == c)
        if key_count:
            tag.append(f"KEY x{key_count}")
        labels[c] = ", ".join(tag) if tag else ""

    # Grid display
    cols = sorted(set(c[0] for c in active_cells))
    rows = sorted(set(c[1] for c in active_cells))
    cell_set = set(active_cells)

    lines.append("Grid (rooms marked with contents):")
    for r in rows:
        row_str = ""
        for c in cols:
            if (c, r) in cell_set:
                label = labels.get((c, r), "")
                row_str += f"[{c},{r} {label}]".ljust(22)
            else:
                row_str += " " * 22
        lines.append(row_str.rstrip())
    lines.append("")

    # Connections
    lines.append("Connections:")
    for edge in sorted(connections, key=lambda e: tuple(sorted(e))):
        cells = sorted(edge)
        locked_tag = " ** LOCKED **" if edge in locked_doors else ""
        lines.append(f"  {cells[0]} <-> {cells[1]}{locked_tag}")
    lines.append("")

    # Key placement summary
    lines.append("Key cells:")
    from collections import Counter
    for cell, count in Counter(key_cells).items():
        lines.append(f"  {cell} x{count}")
    lines.append("")

    try:
        with open("dungeon.txt", "w") as f:
            f.write("\n".join(lines))
        log.debug(f"[DUNGEON] Debug layout written to dungeon.txt")
    except Exception as e:
        log.debug(f"[DUNGEON] Failed to write dungeon.txt: {e}")


def resolve_dungeon_room(instance: DungeonInstance, cell: tuple) -> bool:
    """Materialize a library entry into a live game.rooms[] entry.

    For precreated entries, uses the pre-assigned library entry.
    For custom entries, picks from the shared pool; falls back to precreated
    if the pool is exhausted or the slot was a placeholder.
    Fully synchronous — no AI generation, no awaits.
    """
    from server.dungeon_types import DUNGEON_TYPES

    assignment = instance.cell_assignments.get(cell)
    if not assignment:
        return False  # no assignment for this cell

    col, row = cell
    room_id = f"{instance.dungeon_id}_{col}_{row}"

    if assignment["resolved"]:
        # Verify room data still exists — should always be true, but guard
        # against corrupted state so callers don't crash on a missing room.
        if room_id in game.rooms:
            return True
        log.debug(f"[DUNGEON] WARNING: {room_id} marked resolved but missing from game.rooms — re-resolving")
        assignment["resolved"] = False
        instance.resolved_rooms.discard(room_id)
    dungeon_id = instance.dungeon_id
    entrance_col, entrance_row = instance.layout["entrance"]
    is_entrance = (col == entrance_col and row == entrance_row)

    type_config = DUNGEON_TYPES.get(dungeon_id, {})
    exit_room = type_config.get("exit_room", "clearing")
    biome = type_config.get("biome", "dungeon")
    wall_tile = type_config.get("wall_tile", "DW")

    exits = _get_cell_exits(cell, instance.connections, entrance_col, entrance_row, dungeon_id, exit_room)

    if assignment["source"] == "custom":
        # Custom cell — slot pre-assigned at creation time
        entry_data = assignment.get("slot_data")
        entry = assignment.get("entry")
        entry_id = entry.id if entry else "unknown"
        source_label = f"custom:{entry_id}"
        if entry_data is None:
            return False
    else:
        # Precreated or special — entry always available
        entry_data = assignment["entry"].data
        source_label = f"{assignment['source']}:{assignment['entry'].id}"

    # Boss room uses boss music instead of the dungeon's random track
    music_override = None
    if cell == instance.boss_cell:
        music_override = instance.boss_track

    is_trap = cell in instance.trap_cells

    # Compute which directions have locked doors (still locked at resolution time)
    locked_directions = set()
    still_locked = instance.locked_doors - instance.unlocked_doors
    for direction, (dc, dr) in _DIR_OFFSETS.items():
        neighbor = (col + dc, row + dr)
        edge = frozenset((cell, neighbor))
        if edge in still_locked:
            locked_directions.add(direction)

    difficulty_tier = instance.cell_difficulty.get(cell)
    locked_originals = _resolve_room_from_entry(
        room_id, entry_data, exits, cell, instance.music_track, is_entrance,
        biome=biome, music_override=music_override, wall_tile=wall_tile,
        is_trap=is_trap, locked_directions=locked_directions,
        difficulty_tier=difficulty_tier, type_config=type_config)

    if locked_originals:
        instance.locked_door_originals[room_id] = locked_originals

    # Place boss doorway warning tile on the approach side (rooms looking toward the boss).
    # boss_cell/sanctum_cell are tuples or None; != against a tuple is always True for None.
    if (instance.boss_cell
            and cell != instance.boss_cell
            and cell != instance.sanctum_cell):
        bd_tilemap = game.rooms[room_id]["tilemap"]
        for direction, (dc, dr) in _DIR_OFFSETS.items():
            neighbor = (col + dc, row + dr)
            if neighbor != instance.boss_cell:
                continue
            if direction not in exits:
                continue
            # Place BD on all 3 doorway tiles
            tiles = DOORWAY_TILES[direction]
            placed_any = False
            for r, c in tiles:
                if game.is_walkable_tile(bd_tilemap[r][c]):
                    bd_tilemap[r][c] = "BD"
                    placed_any = True
                else:
                    # Tile is blocked (locked door) — set BD as the unlock restore tile
                    originals = instance.locked_door_originals.get(room_id, {})
                    if (r, c) in originals:
                        originals[(r, c)] = "BD"
                        placed_any = True
            if placed_any:
                log.debug(f"[DUNGEON] Placed boss doorway (BD) across doorway in {room_id}")
            else:
                # Doorway fully blocked — place one tile inward
                ir, ic = _INWARD_FROM_DOORWAY[direction]
                if game.is_walkable_tile(bd_tilemap[ir][ic]):
                    bd_tilemap[ir][ic] = "BD"
                    log.debug(f"[DUNGEON] Placed boss doorway (BD) in {room_id} at ({ir},{ic}) (inward)")

    assignment["resolved"] = True
    instance.resolved_rooms.add(room_id)

    # Darkness — scan tilemap for bright tiles (sconces, braziers, fireplaces)
    room_data = game.rooms.get(room_id, {})
    tilemap = room_data.get("tilemap", [])
    light_sources = []
    has_bright_tiles = False
    for r_idx, row in enumerate(tilemap):
        for c_idx, tile_code in enumerate(row):
            tile_props = game.custom_tile_recipes.get(tile_code, {})
            if tile_props.get("bright"):
                has_bright_tiles = True
                light_sources.append([c_idx, r_idx])

    # A room is dark if explicitly in dark_cells, OR (D1 only) has bright tiles (atmosphere).
    # Bright-tile rooms on the critical path are still dark — the sconces provide enough light.
    is_dark = cell in instance.dark_cells or (has_bright_tiles and instance.dungeon_id == "d1")
    if is_dark:
        room_data["dark"] = True
        room_data["light_sources"] = light_sources
    if has_bright_tiles or cell in instance.dark_cells:
        log.debug(f"[DUNGEON] Room {room_id} dark={is_dark} "
                  f"(in dark_cells={cell in instance.dark_cells}, bright_tiles={has_bright_tiles}, "
                  f"lights={len(light_sources)})")

    # Place dungeon items — track used positions to avoid overlap
    # Clear any prior items for this room (guards against duplicate placement on re-resolve)
    instance.dungeon_items.pop(room_id, None)
    instance.per_player_items.pop(room_id, None)
    used_positions = set()

    # Per-player items (lantern) — always placed, tracked separately
    per_player_types = {"lantern", "tide_medallion"}
    for item_type, item_cell in instance.item_cells.items():
        if item_type in per_player_types:
            if cell == item_cell:
                pos = _find_item_tile(room_id, exclude=used_positions)
                if pos:
                    used_positions.add(pos)
                    instance.per_player_items.setdefault(room_id, []).append(
                        {"x": pos[0], "y": pos[1], "item_type": item_type}
                    )
                    log.debug(f"[DUNGEON] Placed {item_type} (per-player) in {room_id} at ({pos[0]},{pos[1]})")
        elif cell == item_cell and item_type not in instance.collected_items:
            pos = _find_item_tile(room_id, exclude=used_positions)
            if pos:
                used_positions.add(pos)
                instance.dungeon_items.setdefault(room_id, []).append(
                    {"x": pos[0], "y": pos[1], "item_type": item_type}
                )
                log.debug(f"[DUNGEON] Placed {item_type} in {room_id} at ({pos[0]},{pos[1]})")

    for key_cell in instance.key_cells:
        if cell == key_cell:
            pos = _find_item_tile(room_id, exclude=used_positions)
            if pos:
                used_positions.add(pos)
                instance.dungeon_items.setdefault(room_id, []).append(
                    {"x": pos[0], "y": pos[1], "item_type": "key"}
                )
                log.debug(f"[DUNGEON] Placed key in {room_id} at ({pos[0]},{pos[1]})")

    log.debug(f"[DUNGEON] Resolved {room_id} ({source_label})")
    return True




# ---------------------------------------------------------------------------
# Library persistence
# ---------------------------------------------------------------------------

def _save_libraries(type_id=None):
    """Persist content libraries and deprecated sets to disk."""
    from pathlib import Path
    data_dir = Path(__file__).parent.parent / "data"

    types_to_save = [type_id] if type_id else list(game.content_libraries.keys())

    for tid in types_to_save:
        libs = game.content_libraries.get(tid, {})
        if libs.get("monsters"):
            libs["monsters"].save(data_dir / f"{tid}_monster_library.json")
        if libs.get("tiles"):
            libs["tiles"].save(data_dir / f"{tid}_tile_library.json")
        if libs.get("rooms"):
            libs["rooms"].save(data_dir / f"{tid}_room_library.json")

    _save_deprecated_sets()
    log.debug("[DUNGEON] Libraries saved to disk")


def _save_deprecation_timestamp():
    """Persist the last deprecation timestamp to disk."""
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "data" / "deprecation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last_deprecation_time": game.last_deprecation_time}), encoding="utf-8")


def load_deprecation_timestamp():
    """Load the last deprecation timestamp from disk (call at startup)."""
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "data" / "deprecation.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        game.last_deprecation_time = data.get("last_deprecation_time", 0.0)
        log.debug(f"[DEPRECATION] Last deprecation: {time.strftime('%Y-%m-%d %H:%M', time.localtime(game.last_deprecation_time))}")


def _save_deprecated_sets():
    """Persist deprecated monster/tile IDs to disk."""
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "data" / "deprecated.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    for type_id, dep in game.deprecated_content.items():
        data[type_id] = {
            "monsters": sorted(dep.get("monsters", set())),
            "tiles": sorted(dep.get("tiles", set())),
        }
    path.write_text(json.dumps(data), encoding="utf-8")


def load_deprecated_sets():
    """Load deprecated monster/tile IDs from disk (call at startup)."""
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "data" / "deprecated.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        # Handle both old format (flat) and new format (per-type)
        if "monsters" in data and isinstance(data["monsters"], list):
            # Old format — migrate to d1
            game.deprecated_content["d1"] = {
                "monsters": set(data.get("monsters", [])),
                "tiles": set(data.get("tiles", [])),
            }
        else:
            # New format — per type
            for type_id, dep in data.items():
                game.deprecated_content[type_id] = {
                    "monsters": set(dep.get("monsters", [])),
                    "tiles": set(dep.get("tiles", [])),
                }
        total_m = sum(len(d.get("monsters", set())) for d in game.deprecated_content.values())
        total_t = sum(len(d.get("tiles", set())) for d in game.deprecated_content.values())
        if total_m or total_t:
            log.debug(f"[DEPRECATION] Loaded deprecated: {total_m} monsters, {total_t} tiles")


# ---------------------------------------------------------------------------
# Content deprecation
# ---------------------------------------------------------------------------

def get_active_content_lists(type_id):
    """Build monster/tile lists for AI prompts, excluding deprecated entries."""
    libs = game.content_libraries.get(type_id, {})
    dep = game.deprecated_content.get(type_id, {})
    dep_monsters = dep.get("monsters", set())
    dep_tiles = dep.get("tiles", set())

    monsters = []
    monster_lib = libs.get("monsters")
    if monster_lib:
        for e in monster_lib.real_entries:
            if e.id not in dep_monsters:
                m = {"kind": e.id, "tags": e.tags}
                stats = game.monster_stats.get(e.id, {})
                if "pack_min" in stats:
                    m["pack_min"] = stats["pack_min"]
                if "pack_max" in stats:
                    m["pack_max"] = stats["pack_max"]
                monsters.append(m)

    tiles = []
    tile_lib = libs.get("tiles")
    if tile_lib:
        for e in tile_lib.real_entries:
            if e.id not in dep_tiles:
                tiles.append({"id": e.id, "walkable": e.data.get("walkable", False), "tags": e.tags})

    return monsters, tiles


def _get_referenced_ids(room_library):
    """Scan all rooms in the library for referenced monster kinds and tile IDs."""
    referenced_monsters = set()
    referenced_tiles = set()
    if not room_library:
        return referenced_monsters, referenced_tiles
    for entry in room_library.real_entries:
        data = entry.data
        for p in data.get("monster_placements", []):
            referenced_monsters.add(p["kind"])
        for g in data.get("monster_groups", []):
            referenced_monsters.add(g["kind"])
        for row in data.get("tilemap", []):
            for tid in row:
                if isinstance(tid, str):
                    referenced_tiles.add(tid)
    return referenced_monsters, referenced_tiles


def _cleanup_monster(mid, type_id=None):
    """Fully remove a monster from game registries."""
    game.monster_stats.pop(mid, None)
    game.custom_sprites.pop(mid, None)
    game.custom_death_sprites.pop(mid, None)
    game.monster_behaviors.pop(mid, None)
    if type_id:
        dep = game.deprecated_content.get(type_id, {})
        dep.get("monsters", set()).discard(mid)
    else:
        for dep in game.deprecated_content.values():
            dep.get("monsters", set()).discard(mid)


def _cleanup_tile(tid, type_id=None):
    """Fully remove a tile from game registries."""
    game.custom_tile_recipes.pop(tid, None)
    if type_id:
        dep = game.deprecated_content.get(type_id, {})
        dep.get("tiles", set()).discard(tid)
    else:
        for dep in game.deprecated_content.values():
            dep.get("tiles", set()).discard(tid)


def _sweep_orphaned_content():
    """Remove registry entries not tracked by any library or referenced by any room.

    Catches orphaned entries from background regen that couldn't fit in a
    full library. Built-in content (loaded at startup) is always preserved.
    """
    keep_monsters = set(game.builtin_monster_ids)
    keep_tiles = set(game.builtin_tile_ids)

    for type_id, libs in game.content_libraries.items():
        m_lib = libs.get("monsters")
        t_lib = libs.get("tiles")
        r_lib = libs.get("rooms")

        if m_lib:
            keep_monsters.update(e.id for e in m_lib.real_entries)
        if t_lib:
            keep_tiles.update(e.id for e in t_lib.real_entries)
        if r_lib:
            ref_m, ref_t = _get_referenced_ids(r_lib)
            keep_monsters.update(ref_m)
            keep_tiles.update(ref_t)

    orphan_m = [k for k in list(game.custom_sprites) if k not in keep_monsters]
    for mid in orphan_m:
        _cleanup_monster(mid)

    orphan_t = [k for k in list(game.custom_tile_recipes) if k not in keep_tiles]
    for tid in orphan_t:
        _cleanup_tile(tid)

    if orphan_m or orphan_t:
        log.debug(f"[SWEEP] Removed {len(orphan_m)} orphaned monster(s), {len(orphan_t)} orphaned tile(s)")
        broadcast_debug(f"Sweep: removed {len(orphan_m)}M {len(orphan_t)}T orphans")


# ---------------------------------------------------------------------------
# Dungeon teardown
# ---------------------------------------------------------------------------

def destroy_dungeon(instance):
    """Tear down a dungeon instance. Content deprecation is handled by the daily task."""
    type_id = instance.dungeon_id

    for room_id in instance.active_rooms:
        game.rooms.pop(room_id, None)
        game.guards.pop(room_id, None)
        game.monster_templates.pop(room_id, None)
        game.room_monsters.pop(room_id, None)
        game.room_cooldowns.pop(room_id, None)
        game.room_hearts.pop(room_id, None)
        game.room_projectiles.pop(room_id, None)
        game.room_to_dungeon.pop(room_id, None)
        game.locked_rooms.pop(room_id, None)
        game.room_pickup_freeze.pop(room_id, None)

    game.active_dungeons.pop(type_id, None)

    layout_name = instance.layout['name']
    log.debug(f"[DUNGEON] Destroyed {type_id}: layout={layout_name}")
    broadcast_debug(f"Dungeon {type_id} destroyed ({layout_name})")

    # Run daily content deprecation only when no dungeons are active
    if len(game.active_dungeons) == 0:
        _maybe_run_deprecation()

    # Fill empty placeholder slots via background regen
    is_debug = os.environ.get("DEBUG_MODE", "").lower() in ("1", "true")
    libs = game.content_libraries.get(type_id, {})
    room_library = libs.get("rooms")
    if not is_debug and room_library:
        num_empty = room_library.placeholder_count
        if num_empty > 0:
            log.debug(f"[REGEN] Filling {num_empty} empty {type_id} room slot(s)")
            broadcast_debug(f"Regen: filling {num_empty} empty {type_id} room slot(s)")
            start_background_regen(num_empty, type_id)


DEPRECATION_INTERVAL = 86400  # 24 hours between deprecation passes


def _maybe_run_deprecation():
    """Run content deprecation if at least 24 hours have passed since the last run."""
    now = time.time()
    if now - game.last_deprecation_time < DEPRECATION_INTERVAL:
        elapsed = now - game.last_deprecation_time
        remaining = DEPRECATION_INTERVAL - elapsed
        hours = int(remaining // 3600)
        mins = int((remaining % 3600) // 60)
        log.debug(f"[DEPRECATION] Skipped — next pass in {hours}h{mins}m")
        broadcast_debug(f"Deprecation: next pass in {hours}h{mins}m")
        return
    broadcast_debug("Deprecation: starting pass...")

    total_expired = 0
    for tid in list(game.content_libraries.keys()):
        total_expired += _run_content_deprecation(tid)

    game.last_deprecation_time = now
    _save_deprecation_timestamp()

    # Sweep orphaned entries from registries (not tracked by any library)
    _sweep_orphaned_content()

    # Start background regen for types with expired slots (skip in debug mode — use /regen)
    is_debug = os.environ.get("DEBUG_MODE", "").lower() in ("1", "true")
    for tid in list(game.content_libraries.keys()):
        libs = game.content_libraries.get(tid, {})
        room_library = libs.get("rooms")
        if room_library:
            num_empty = room_library.placeholder_count
            if num_empty > 0:
                if is_debug:
                    broadcast_debug(f"Regen: skipped {tid} (debug mode) — use /regen")
                else:
                    start_background_regen(num_empty, tid)


def _deprecate_oldest(library, deprecated_set):
    """Mark the oldest 10% of non-deprecated custom entries as deprecated.

    Entries stay in the library and game registries — they're just excluded
    from AI prompts via get_active_content_lists(). Returns newly deprecated IDs.
    """
    import math
    if not library:
        return []
    candidates = [
        (e.created_at, e.id) for e in library.real_entries
        if not e.permanent and e.id not in deprecated_set
    ]
    if not candidates:
        return []
    candidates.sort()
    count = max(1, math.ceil(len(candidates) * 0.10))
    count = min(count, len(candidates))
    newly = [cid for _, cid in candidates[:count]]
    deprecated_set.update(newly)
    return newly


def _run_content_deprecation(type_id):
    """Execute one round of content deprecation for a dungeon type. Returns count of expired rooms.

    Rooms: oldest 10% are expired (removed from library).
    Monsters/tiles: oldest 10% are deprecated (kept in library + registries,
      but excluded from AI prompts). They're only fully removed once no room
      in the library references them anymore.
    """
    libs = game.content_libraries.get(type_id, {})
    room_library = libs.get("rooms")
    monster_library = libs.get("monsters")
    tile_library = libs.get("tiles")

    dep = game.deprecated_content.setdefault(type_id, {"monsters": set(), "tiles": set()})
    dep_monsters = dep["monsters"]
    dep_tiles = dep["tiles"]

    # Step 1: Expire oldest 10% of custom rooms
    expired_rooms = []
    if room_library:
        expired_rooms = room_library.expire_oldest()
        if expired_rooms:
            log.debug(f"[DEPRECATION] [{type_id}] Expired rooms: {expired_rooms}")
            broadcast_debug(f"[{type_id}] Expired {len(expired_rooms)} room(s): {', '.join(expired_rooms)}")

    # Step 2: Deprecate oldest 10% of custom monsters/tiles
    #   Marked as deprecated (excluded from AI prompts) but kept in library
    #   and registries so existing rooms still work.
    newly_dep_m = _deprecate_oldest(monster_library, dep_monsters)
    newly_dep_t = _deprecate_oldest(tile_library, dep_tiles)
    for mid in newly_dep_m:
        log.debug(f"[DEPRECATION] [{type_id}] Deprecated monster '{mid}'")
        broadcast_debug(f"[{type_id}] Monster '{mid}' deprecated")
    for tid in newly_dep_t:
        log.debug(f"[DEPRECATION] [{type_id}] Deprecated tile '{tid}'")
        broadcast_debug(f"[{type_id}] Tile '{tid}' deprecated")

    # Step 3: Scan remaining rooms for referenced monster/tile IDs
    ref_monsters, ref_tiles = _get_referenced_ids(room_library)

    # Step 4: Fully remove unreferenced custom monsters/tiles
    #   (from both library and game registries)
    removed_monsters = []
    if monster_library:
        for entry in list(monster_library.real_entries):
            if not entry.permanent and entry.id not in ref_monsters:
                monster_library.remove(entry.id)
                _cleanup_monster(entry.id, type_id)
                removed_monsters.append(entry.id)
                log.debug(f"[DEPRECATION] [{type_id}] Removed monster '{entry.id}' (unreferenced)")
                broadcast_debug(f"[{type_id}] Monster '{entry.id}' removed")

    removed_tiles = []
    if tile_library:
        for entry in list(tile_library.real_entries):
            if not entry.permanent and entry.id not in ref_tiles:
                tile_library.remove(entry.id)
                _cleanup_tile(entry.id, type_id)
                removed_tiles.append(entry.id)
                log.debug(f"[DEPRECATION] [{type_id}] Removed tile '{entry.id}' (unreferenced)")
                broadcast_debug(f"[{type_id}] Tile '{entry.id}' removed")

    # Also clean up deprecated IDs that aren't in the library at all
    # (edge case: entry was in deprecated set but already removed from library)
    stale_m = {mid for mid in dep_monsters if mid not in ref_monsters}
    for mid in stale_m:
        _cleanup_monster(mid, type_id)
    stale_t = {tid for tid in dep_tiles if tid not in ref_tiles}
    for tid in stale_t:
        _cleanup_tile(tid, type_id)

    # Save libraries to disk
    _save_libraries(type_id)

    # Summary
    removed_count = len(removed_monsters) + len(removed_tiles) + len(stale_m) + len(stale_t)
    dep_count = len(newly_dep_m) + len(newly_dep_t)
    if expired_rooms or dep_count > 0 or removed_count > 0:
        log.debug(f"[DEPRECATION] [{type_id}] Complete: {len(expired_rooms)} rooms expired, "
                  f"{len(newly_dep_m)}M {len(newly_dep_t)}T deprecated, "
                  f"{removed_count} removed")
        broadcast_debug(f"[{type_id}] Deprecation done: {len(expired_rooms)}R expired, "
                        f"{len(newly_dep_m)}M {len(newly_dep_t)}T deprecated, "
                        f"{removed_count} removed")
    else:
        log.debug(f"[DEPRECATION] [{type_id}] Nothing to deprecate")
        broadcast_debug(f"[{type_id}] Deprecation: nothing to expire")

    return len(expired_rooms)


# ---------------------------------------------------------------------------
# Background content generation
# ---------------------------------------------------------------------------

def start_background_regen(num_rooms, type_id):
    """Start background content generation to refill libraries for a dungeon type.

    Takes a snapshot of library state synchronously (before any await),
    then hands it to the async task. The task never reads from game.* —
    it only writes at the very end via _apply_staged_content().
    """
    regen_task = game.regen_tasks.get(type_id)
    if regen_task is not None and not regen_task.done():
        log.debug(f"[REGEN] Already in progress for {type_id}, skipping")
        broadcast_debug(f"Regen: already in progress for {type_id}")
        return
    if num_rooms <= 0:
        return

    libs = game.content_libraries.get(type_id, {})
    room_library = libs.get("rooms")
    monster_library = libs.get("monsters")
    tile_library = libs.get("tiles")

    if not room_library:
        return

    # Snapshot everything synchronously before launching the task
    existing_monsters, existing_tiles = get_active_content_lists(type_id)
    existing_room_names = [
        e.data.get("name", e.id) for e in room_library.real_entries
    ]
    snapshot = {
        "existing_monsters": existing_monsters,
        "existing_tiles": existing_tiles,
        "existing_room_names": existing_room_names,
        "monster_count": monster_library.real_count if monster_library else 0,
        "monster_cap": monster_library.capacity if monster_library else 0,
        "tile_count": tile_library.real_count if tile_library else 0,
        "tile_cap": tile_library.capacity if tile_library else 0,
    }

    game.regen_tasks[type_id] = asyncio.create_task(_background_regen(num_rooms, snapshot, type_id))


async def _background_regen(num_rooms, snapshot, type_id):
    """Generate rooms in the background to refill libraries after deprecation.

    Uses only the provided snapshot — never reads from game.* directly.
    Applies all results at the end via _apply_staged_content().
    """
    from server import ai_generator
    from server.dungeon_types import DUNGEON_TYPES

    type_config = DUNGEON_TYPES.get(type_id, {})
    theme = type_config.get("theme", type_config.get("biome", "dungeon"))

    log.debug(f"[REGEN] Starting {type_id} background generation of {num_rooms} room(s)...")
    broadcast_debug(f"Regen [{type_id}]: generating {num_rooms} room(s)...")
    staged = []

    # Progress callback — sends each AI step to the debug panel
    async def on_progress(step, detail=""):
        broadcast_debug(f"  {detail}" if detail else f"  {step}")

    # Unpack snapshot into local working copies
    existing_monsters = snapshot["existing_monsters"]
    existing_tiles = snapshot["existing_tiles"]
    existing_room_names = snapshot["existing_room_names"]
    monster_count = snapshot["monster_count"]
    monster_cap = snapshot["monster_cap"]
    tile_count = snapshot["tile_count"]
    tile_cap = snapshot["tile_cap"]

    # Collect all registered names so generate_room can detect collisions.
    # This is a mutable set — generate_room adds new names as it renames,
    # so subsequent rooms in this batch also see them.
    taken_monster_kinds = set(game.monster_stats.keys())
    taken_tile_ids = set(game.custom_tile_recipes.keys())

    for i in range(num_rooms):
        broadcast_debug(f"Regen [{type_id}]: room {i+1}/{num_rooms}...")
        try:
            result = await ai_generator.generate_room(
                theme=theme,
                difficulty=random.randint(3, 7),
                existing_monsters=existing_monsters,
                existing_tiles=existing_tiles,
                monster_library_full=(monster_count >= monster_cap),
                tile_library_full=(tile_count >= tile_cap),
                existing_room_names=existing_room_names,
                monster_library_count=monster_count,
                monster_library_capacity=monster_cap,
                tile_library_count=tile_count,
                tile_library_capacity=tile_cap,
                progress=on_progress,
                taken_monster_kinds=taken_monster_kinds,
                taken_tile_ids=taken_tile_ids,
            )
        except Exception as e:
            log.debug(f"[REGEN] [{type_id}] Room {i+1}/{num_rooms} failed: {type(e).__name__}: {e}")
            broadcast_debug(f"Regen [{type_id}] {i+1}/{num_rooms}: FAILED ({type(e).__name__})")
            continue

        if result is None:
            log.debug(f"[REGEN] [{type_id}] Room {i+1}/{num_rooms} returned None, skipping")
            broadcast_debug(f"Regen [{type_id}] {i+1}/{num_rooms}: empty result, skipped")
            continue

        staged.append(result)

        # Update snapshot so next room sees what we've generated
        for m in result.get("new_monsters", []):
            existing_monsters.append({"kind": m["kind"], "tags": m.get("tags", [])})
            monster_count += 1
        for t in result.get("new_tiles", []):
            existing_tiles.append({
                "id": t["id"], "walkable": t.get("walkable", False),
                "tags": t.get("tags", []),
            })
            tile_count += 1
        existing_room_names.append(result.get("name", "Unknown"))

        # Summarize what this room produced
        new_m = [m["kind"] for m in result.get("new_monsters", [])]
        new_t = [t["id"] for t in result.get("new_tiles", [])]
        detail = result.get("name", "?")
        if new_m:
            detail += f" +{','.join(new_m)}"
        if new_t:
            detail += f" +{','.join(new_t)}"
        log.debug(f"[REGEN] [{type_id}] Room {i+1}/{num_rooms} generated: \"{result.get('name', '?')}\"")
        broadcast_debug(f"Regen [{type_id}] {i+1}/{num_rooms}: {detail}")

    if staged:
        _apply_staged_content(staged, type_id)
    else:
        log.debug(f"[REGEN] [{type_id}] No rooms generated successfully")
        broadcast_debug(f"Regen [{type_id}]: no rooms generated")

    game.regen_tasks.pop(type_id, None)


def _apply_staged_content(results, type_id):
    """Register staged content into game registries and libraries.

    Fully synchronous — no awaits — so no interleaving with other coroutines.
    """
    from server.validation import register_monster_type, register_tile_type
    from server.content_library import LibraryEntry

    libs = game.content_libraries.get(type_id, {})
    monster_library = libs.get("monsters")
    tile_library = libs.get("tiles")
    room_library = libs.get("rooms")

    total_monsters = 0
    total_tiles = 0
    total_rooms = 0

    for result in results:
        # Register new monsters
        for m in result.get("new_monsters", []):
            ok, errors = register_monster_type(m)
            if ok and monster_library:
                added = monster_library.add(LibraryEntry(
                    id=m["kind"], content_type="monster",
                    tags=m.get("tags", []), created_at=time.time(), data=m,
                ))
                if added:
                    total_monsters += 1
            elif not ok:
                log.debug(f"[REGEN] Monster registration failed for {m.get('kind')}: {errors}")

        # Register new tiles
        for t in result.get("new_tiles", []):
            ok, errors = register_tile_type(t)
            if ok and tile_library:
                added = tile_library.add(LibraryEntry(
                    id=t["id"], content_type="tile",
                    tags=t.get("tags", []), created_at=time.time(), data=t,
                ))
                if added:
                    total_tiles += 1
            elif not ok:
                log.debug(f"[REGEN] Tile registration failed for {t.get('id')}: {errors}")

        # Add room to library (deduplicate ID)
        room_name = result.get("name", "Unknown Room")
        lib_id = room_name.lower().replace(" ", "_")
        base_id = lib_id
        counter = 1
        while room_library and room_library.get_by_id(lib_id):
            counter += 1
            lib_id = f"{base_id}_{counter}"

        if room_library:
            added = room_library.add(LibraryEntry(
                id=lib_id, content_type="room",
                tags=[], created_at=time.time(), data=result,
            ))
            if added:
                total_rooms += 1

    _save_libraries(type_id)
    log.debug(f"[REGEN] [{type_id}] Applied staged content: {total_rooms} rooms, "
              f"{total_monsters} monsters, {total_tiles} tiles")
    broadcast_debug(f"Regen [{type_id}] done: {total_rooms}R {total_monsters}M {total_tiles}T added")


# ---------------------------------------------------------------------------
# Boss distance computation
# ---------------------------------------------------------------------------

def get_boss_distances(instance: DungeonInstance) -> dict:
    """BFS distance from boss cell to all other cells. Returns {room_id: int}.

    Uses the topology's cached BFS if available.
    """
    if not instance or not instance.boss_cell:
        return {}
    topo = instance.topo
    if topo:
        did = instance.dungeon_id
        return {f"{did}_{c[0]}_{c[1]}": topo.dist(c, "boss") for c in topo.cells}
    # Fallback for instances without topology (shouldn't happen)
    return {}
