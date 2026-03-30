"""Lazy spatial oracle for dungeon connection graphs.

DungeonTopology accepts cells and edges, then answers any spatial question
on demand (distances, paths, zone membership) with lazy caching.  It never
generates graph structure — it only queries what it's given.
"""

from collections import deque


# ---------------------------------------------------------------------------
# Graph helpers (moved from dungeons.py)
# ---------------------------------------------------------------------------

def _bfs_distances(adj, origin):
    """BFS from origin on adjacency dict. Returns (dist, parent) dicts."""
    dist = {origin: 0}
    parent = {origin: None}
    queue = deque([origin])
    while queue:
        cell = queue.popleft()
        for n in adj[cell]:
            if n not in dist:
                dist[n] = dist[cell] + 1
                parent[n] = cell
                queue.append(n)
    return dist, parent


def _trace_path(parents, target):
    """Backtrack from target to origin using a parent dict. Returns frozenset of cells."""
    path = set()
    cur = target
    while cur is not None:
        path.add(cur)
        cur = parents.get(cur)
    return frozenset(path)


def _connection_adj(connections, cells):
    """Build adjacency dict from a set of frozenset connection edges."""
    adj = {c: [] for c in cells}
    for edge in connections:
        a, b = tuple(edge)
        if a in adj:
            adj[a].append(b)
        if b in adj:
            adj[b].append(a)
    return adj


# ---------------------------------------------------------------------------
# DungeonTopology
# ---------------------------------------------------------------------------

class DungeonTopology:
    """Lazy spatial oracle for a dungeon's connection graph.

    All distance/path queries are computed on first access and cached.
    The graph is immutable after construction except via add_connections(),
    which clears all caches.  Marks (per-cell counters) are the only
    mutable state that placement code writes to.
    """

    def __init__(self, active_cells, connections, entrance):
        self._cells = frozenset(active_cells)
        self._connections = set(connections)
        self.entrance = entrance

        self._adj = _connection_adj(self._connections, self._cells)

        # Mark system: cell -> {name -> count}
        self._marks = {}

        # Lazy BFS caches: mark_name -> {cell: int} / {cell: cell|None}
        self._dist_cache = {}
        self._parent_cache = {}

        # Lazy path cache: (mark_a, mark_b) -> frozenset of cells
        self._path_cache = {}

        # Zone data (set via set_zones after lock placement)
        self._zone_of = None      # cell -> zone_id
        self._zone_cells = None   # zone_id -> set of cells
        self._zone_adj = None     # zone_id -> set of zone_ids
        self._zone_dist_cache = {}  # mark_name -> {zone_id: int}

    # --- Properties ---

    @property
    def cells(self):
        """All active cells as a frozenset."""
        return self._cells

    @property
    def connections(self):
        """Current set of frozenset edges."""
        return self._connections

    @property
    def leaves(self):
        """Cells with exactly one connection (excluding entrance)."""
        return [c for c in self._cells
                if len(self._adj.get(c, [])) == 1 and c != self.entrance]

    # --- Graph mutation ---

    def add_connections(self, new_edges):
        """Add edges to the graph. Clears all distance/path caches."""
        self._connections.update(new_edges)
        self._adj = _connection_adj(self._connections, self._cells)
        self._dist_cache.clear()
        self._parent_cache.clear()
        self._path_cache.clear()

    # --- Mark system ---

    def mark(self, cell, name):
        """Increment the mark counter for (cell, name)."""
        cell_marks = self._marks.setdefault(cell, {})
        cell_marks[name] = cell_marks.get(name, 0) + 1

    def marks(self, cell, name):
        """Return the mark count for (cell, name). 0 if absent."""
        return self._marks.get(cell, {}).get(name, 0)

    def has_mark(self, cell, name):
        """True if cell has at least one mark of the given name."""
        return self.marks(cell, name) > 0

    def lacks_mark(self, cell, name):
        """True if cell has no marks of the given name.

        Designed for high-to-low scoring: lacks_mark = True = preferred.
        """
        return self.marks(cell, name) == 0

    def cells_with_mark(self, name):
        """All cells that have at least one mark of the given name."""
        return [c for c, m in self._marks.items() if m.get(name, 0) > 0]

    # --- Lazy BFS ---

    def _resolve_origin(self, mark_name):
        """Find the BFS origin cell for a mark name."""
        if mark_name == "entrance":
            return self.entrance
        cells = self.cells_with_mark(mark_name)
        if len(cells) == 1:
            return cells[0]
        if not cells:
            raise ValueError(f"No cell marked '{mark_name}'")
        raise ValueError(f"Multiple cells marked '{mark_name}': {cells}")

    def _ensure_bfs(self, mark_name):
        """Run BFS from the mark's cell if not already cached."""
        if mark_name not in self._dist_cache:
            origin = self._resolve_origin(mark_name)
            self._dist_cache[mark_name], self._parent_cache[mark_name] = \
                _bfs_distances(self._adj, origin)

    def dist(self, cell, mark_name="entrance"):
        """BFS distance from the cell marked with mark_name. Lazily cached."""
        self._ensure_bfs(mark_name)
        return self._dist_cache[mark_name].get(cell, 0)

    def max_dist(self, mark_name="entrance"):
        """Maximum BFS distance from the mark's cell."""
        self._ensure_bfs(mark_name)
        d = self._dist_cache[mark_name]
        return max(d.values()) if d else 0

    def parent_of(self, cell, mark_name="entrance"):
        """The cell one step closer to the mark's cell on the shortest path."""
        self._ensure_bfs(mark_name)
        return self._parent_cache[mark_name].get(cell)

    def neighbors(self, cell):
        """Direct neighbors in the connection graph."""
        return self._adj.get(cell, [])

    # --- Path queries ---

    def path_between(self, mark_a, mark_b):
        """Shortest path between two marked cells as a frozenset. Lazily cached."""
        key = (mark_a, mark_b)
        if key not in self._path_cache:
            self._ensure_bfs(mark_a)
            target = self._resolve_origin(mark_b)
            self._path_cache[key] = _trace_path(
                self._parent_cache[mark_a], target)
        return self._path_cache[key]

    def is_on_path(self, cell, mark_a, mark_b):
        """True if cell lies on the shortest path between two marks."""
        return cell in self.path_between(mark_a, mark_b)

    # --- Zone queries ---

    def set_zones(self, zone_of, zone_cells, zone_adj):
        """Store zone data from lock placement. Clears zone distance cache."""
        self._zone_of = zone_of
        self._zone_cells = zone_cells
        self._zone_adj = zone_adj
        self._zone_dist_cache.clear()

    @property
    def zone_ids(self):
        """All zone IDs."""
        if self._zone_cells is None:
            return []
        return list(self._zone_cells.keys())

    def zone_of_cell(self, cell):
        """Zone ID for a cell, or None if zones not set."""
        if self._zone_of is None:
            return None
        return self._zone_of.get(cell)

    def cells_in_zone(self, zone_id):
        """Set of cells in a zone."""
        if self._zone_cells is None:
            return set()
        return self._zone_cells.get(zone_id, set())

    def _ensure_zone_bfs(self, mark_name):
        """BFS on the zone graph from the zone containing the mark's cell."""
        if mark_name not in self._zone_dist_cache:
            if self._zone_of is None or self._zone_adj is None:
                self._zone_dist_cache[mark_name] = {}
                return
            origin_cell = self._resolve_origin(mark_name)
            start_zone = self._zone_of[origin_cell]
            zd = {start_zone: 0}
            q = deque([start_zone])
            while q:
                z = q.popleft()
                for nz in self._zone_adj.get(z, set()):
                    if nz not in zd:
                        zd[nz] = zd[z] + 1
                        q.append(nz)
            self._zone_dist_cache[mark_name] = zd

    def zone_dist(self, zone_id, mark_name="entrance"):
        """BFS distance on the zone graph from the mark's zone. Lazily cached."""
        self._ensure_zone_bfs(mark_name)
        return self._zone_dist_cache[mark_name].get(zone_id, 0)
