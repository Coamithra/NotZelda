"""Deadlock-free key placement solver (multigraph, edge-traversal model).

Given a dungeon multigraph and a start room, finds all distributions of
keys such that:
  - Total keys == number of edges (one key per locked door)
  - No node holds more than `max_keys` keys
  - The player must unlock EVERY door (traverse every edge)
  - No matter what order the player unlocks doors, they never get stuck

Supports parallel edges (multiple locked doors between the same rooms).

Constraint: for every connected subset S containing start (S != V):
    sum(keys in S) >= edges_within(S) + 1

where edges_within(S) counts all edges (with multiplicity) that have
both endpoints in S. This is stricter than the old sum >= |S| because
it accounts for the player unlocking doors between already-visited rooms.

Usage:
    from key_solver import solve

    solutions = solve(
        graph={'A': ['B', 'B', 'C'], 'B': ['A', 'A'], 'C': ['A']},
        start='A',
        max_keys=2,
    )
"""

from collections import deque
from itertools import combinations


def solve(graph, start, max_keys=2):
    """Find all deadlock-free key distributions.

    Args:
        graph:    adjacency dict {node: [neighbors]}, undirected.
                  Duplicate entries = parallel edges (multigraph).
        start:    starting node
        max_keys: max keys any single node can hold (default 2)

    Returns:
        List of dicts {node: key_count} — every valid distribution.
        Empty list if no solution exists under the given max_keys cap.
    """
    nodes = set(graph.keys())
    n = len(nodes)
    num_edges = sum(1 for u in graph for v in graph[u] if u <= v)

    if n == 0:
        return []
    if n == 1:
        # Single node: all edges are self-loops, need all keys here
        return [{start: num_edges}] if num_edges <= max_keys else []

    node_list = _bfs_order(graph, start)
    node_to_idx = {node: i for i, node in enumerate(node_list)}

    # Build constraints: for every connected subset S containing start
    # where S != V, we need sum(keys in S) >= edges_within(S) + 1.
    constraints = []
    other_nodes = sorted(nodes - {start})
    for r in range(len(other_nodes)):
        for combo in combinations(other_nodes, r):
            subset = frozenset({start} | set(combo))
            if _is_connected(subset, graph):
                ew = _edges_within(subset, graph)
                indices = tuple(sorted(node_to_idx[nd] for nd in subset))
                constraints.append((indices, indices[-1], ew + 1))

    constraints.sort(key=lambda c: c[1])

    # Backtracking search
    cap = min(max_keys, num_edges)
    values = [0] * n
    solutions = []

    def backtrack(idx, remaining):
        if idx == n:
            if remaining == 0:
                solutions.append(
                    {node_list[i]: values[i] for i in range(n)})
            return

        for v in range(min(remaining, cap) + 1):
            values[idx] = v
            if _feasible(values, idx, remaining - v, constraints):
                backtrack(idx + 1, remaining - v)
        values[idx] = 0

    backtrack(0, num_edges)
    return solutions


def verify(graph, start, values):
    """Brute-force verify by checking all reachable edge subsets.

    Enumerates every subset of edges buildable from start and checks
    that budget >= 1 at each incomplete state.

    Returns (is_valid, failing_edges_or_None).
    """
    all_edges = []
    for u in sorted(graph.keys()):
        for v in graph[u]:
            if u <= v:
                all_edges.append((u, v))

    n_edges = len(all_edges)
    if n_edges == 0:
        return True, None

    for mask in range(1, 2**n_edges):
        if mask == 2**n_edges - 1:
            continue  # all edges done = success

        edges = [all_edges[i] for i in range(n_edges) if mask & (1 << i)]

        # Compute reachable nodes via these unlocked edges
        reachable = {start}
        changed = True
        while changed:
            changed = False
            for u, v in edges:
                if u in reachable and v not in reachable:
                    reachable.add(v)
                    changed = True
                elif v in reachable and u not in reachable:
                    reachable.add(u)
                    changed = True

        # Only valid if every edge has at least one reachable endpoint
        if not all(u in reachable or v in reachable for u, v in edges):
            continue

        budget = sum(values.get(nd, 0) for nd in reachable) - len(edges)
        if budget < 1:
            return False, edges

    return True, None


# --- internals ---

def _bfs_order(graph, start):
    order = [start]
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for nb in sorted(set(graph[node])):
            if nb not in seen:
                seen.add(nb)
                order.append(nb)
                queue.append(nb)
    return order


def _is_connected(subset, graph):
    if len(subset) <= 1:
        return True
    root = next(iter(subset))
    visited = {root}
    queue = deque([root])
    while queue:
        node = queue.popleft()
        for nb in graph[node]:
            if nb in subset and nb not in visited:
                visited.add(nb)
                queue.append(nb)
    return len(visited) == len(subset)


def _edges_within(subset, graph):
    """Count edges (with multiplicity) where both endpoints are in subset.

    Uses u<=v filtering instead of //2 so self-loops are counted correctly.
    """
    return sum(1 for u in subset for v in graph[u] if v in subset and u <= v)


def _feasible(values, idx, future_budget, constraints):
    for indices, max_idx, min_sum in constraints:
        if max_idx < idx:
            continue
        if max_idx == idx:
            if sum(values[i] for i in indices) < min_sum:
                return False
        else:
            assigned = sum(values[i] for i in indices if i <= idx)
            if assigned + future_budget < min_sum:
                return False
    return True
