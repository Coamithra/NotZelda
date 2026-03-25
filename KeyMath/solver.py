"""Deadlock-free key distribution solver (multigraph, edge-traversal model).

The player must unlock every edge (door). Each unlock costs 1 key.
Total keys = total edges. Supports parallel edges.

Constraint: for every connected subset S containing start (S != V):
    sum(keys in S) >= edges_within(S) + 1
"""

from collections import deque
from itertools import combinations
import math


def find_key_distributions(adjacency, start, max_per_node=None):
    """Find all deadlock-free key distributions where total keys == edge count.

    Args:
        adjacency: {node: [neighbors]} — undirected graph
        start: starting node
        max_per_node: cap on keys per node (None = no cap). Filters out
                      degenerate solutions that pile keys on one node.

    Returns:
        List of (values_dict, metadata_dict) tuples, sorted by diversity.
    """
    nodes = set(adjacency.keys())
    n = len(nodes)
    num_edges = sum(1 for u in adjacency for v in adjacency[u] if u <= v)

    if n == 0:
        return []
    if n == 1:
        meta = {'total': num_edges, 'spread': 1 if num_edges else 0,
                'entropy': 0.0, 'avg_distance': 0.0}
        return [({start: num_edges}, meta)]

    # Order: start first, then BFS order for better constraint pruning
    node_list = _bfs_order(adjacency, start)

    # Enumerate all constraints (connected subsets containing start, excl. V)
    constraints = _enumerate_connected_subsets(adjacency, start, nodes)

    # Precompute constraint index info for backtracking
    node_to_idx = {node: i for i, node in enumerate(node_list)}
    constraint_info = []
    for subset in constraints:
        ew = _edges_within(subset, adjacency)
        indices = tuple(sorted(node_to_idx[node] for node in subset))
        max_idx = indices[-1]
        constraint_info.append((indices, max_idx, ew + 1))

    # Sort by max_idx so we can skip already-checked constraints
    constraint_info.sort(key=lambda x: x[2])

    # Enumerate ALL solutions with total == num_edges
    all_solutions = _enumerate_solutions(node_list, constraint_info, num_edges,
                                         max_collect=10000,
                                         max_per_node=max_per_node)
    # Rank by diversity
    ranked = _rank_solutions(all_solutions, adjacency, start)
    return ranked


def verify_distribution(adjacency, start, values):
    """Verify that a distribution is deadlock-free (edge-traversal model).

    Checks all reachable edge subsets via bitmask enumeration.
    Returns (is_valid, failing_edge_set_or_None).
    """
    all_edges = []
    for u in sorted(adjacency.keys()):
        for v in adjacency[u]:
            if u <= v:
                all_edges.append((u, v))

    n_edges = len(all_edges)
    if n_edges == 0:
        return True, None

    for mask in range(1, 2**n_edges):
        if mask == 2**n_edges - 1:
            continue  # all edges done = success

        edges = [all_edges[i] for i in range(n_edges) if mask & (1 << i)]

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

        if not all(u in reachable or v in reachable for u, v in edges):
            continue

        budget = sum(values.get(nd, 0) for nd in reachable) - len(edges)
        if budget < 1:
            return False, edges

    return True, None


def simulate_all_paths(adjacency, start, values):
    """Brute-force: try every edge-unlock order.

    Returns (success, orders_tested, deadlock_sequence_or_None).
    """
    all_edges = []
    for u in sorted(adjacency.keys()):
        for v in adjacency[u]:
            if u <= v:
                all_edges.append((u, v))

    counter = [0]
    deadlock = [None]

    def explore(reachable, budget, remaining, history):
        if deadlock[0] is not None:
            return

        if not remaining:
            counter[0] += 1
            return

        # Find unlockable edges (at least one endpoint reachable)
        frontier = [i for i, (u, v) in enumerate(remaining)
                    if u in reachable or v in reachable]

        if budget < 1 or not frontier:
            deadlock[0] = list(history)
            return

        for i in frontier:
            u, v = remaining[i]
            new_remaining = remaining[:i] + remaining[i+1:]
            new_reachable = reachable | {u, v}
            gained = sum(values[nd] for nd in {u, v} - reachable)
            explore(new_reachable, budget - 1 + gained,
                    new_remaining, history + [f"{u}-{v}"])

    explore(frozenset({start}), values[start], all_edges, [start])
    return deadlock[0] is None, counter[0], deadlock[0]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _bfs_order(adjacency, start):
    """Return nodes in BFS order from start."""
    visited = [start]
    seen = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in sorted(adjacency[node]):
            if neighbor not in seen:
                seen.add(neighbor)
                visited.append(neighbor)
                queue.append(neighbor)
    return visited


def _is_connected_subset(subset, adjacency):
    """Check if a set of nodes forms a connected subgraph."""
    if len(subset) <= 1:
        return True
    start = next(iter(subset))
    visited = {start}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in adjacency[node]:
            if neighbor in subset and neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return len(visited) == len(subset)


def _edges_within(subset, adjacency):
    """Count edges (with multiplicity) where both endpoints are in subset.

    Uses u<=v filtering instead of //2 so self-loops are counted correctly.
    """
    return sum(1 for u in subset for v in adjacency[u] if v in subset and u <= v)


def _enumerate_connected_subsets(adjacency, start, all_nodes):
    """Enumerate all connected subsets containing start, excluding V itself."""
    other_nodes = sorted(all_nodes - {start})
    constraints = []

    # r = number of non-start nodes to include (0 gives singleton {start})
    for r in range(len(other_nodes)):
        for combo in combinations(other_nodes, r):
            subset = frozenset({start} | set(combo))
            if _is_connected_subset(subset, adjacency):
                constraints.append(subset)

    return constraints



def _enumerate_solutions(node_list, constraint_info, target_sum, max_collect,
                         max_per_node=None):
    """Find all valid distributions with a specific total sum."""
    n = len(node_list)
    values = [0] * n
    solutions = []
    cap = max_per_node if max_per_node is not None else target_sum

    def backtrack(idx, remaining):
        if len(solutions) >= max_collect:
            return
        if idx == n:
            if remaining == 0:
                sol = {node_list[i]: values[i] for i in range(n)}
                solutions.append(sol)
            return

        for v in range(min(remaining, cap) + 1):
            if len(solutions) >= max_collect:
                return
            values[idx] = v

            if not _check_constraints(values, idx, remaining - v, constraint_info):
                continue

            backtrack(idx + 1, remaining - v)

        values[idx] = 0

    backtrack(0, target_sum)
    return solutions


def _check_constraints(values, idx, future_budget, constraint_info):
    """Check constraints at backtracking index idx.

    Each constraint stores min_sum = edges_within(S) + 1.
    - Fully assigned (max_idx == idx): sum must reach min_sum.
    - Partially assigned (max_idx > idx): prune if unreachable.
    - Already checked (max_idx < idx): skip.
    """
    for indices, max_idx, min_sum in constraint_info:
        if max_idx < idx:
            continue
        if max_idx == idx:
            if sum(values[i] for i in indices) < min_sum:
                return False
        else:
            assigned_sum = sum(values[i] for i in indices if i <= idx)
            if assigned_sum + future_budget < min_sum:
                return False
    return True


def _bfs_distances(adjacency, start):
    """BFS distances from start to all nodes."""
    distances = {start: 0}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in adjacency[node]:
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)
    return distances


def _rank_solutions(solutions, adjacency, start):
    """Rank solutions by diversity metrics."""
    if not solutions:
        return []

    distances = _bfs_distances(adjacency, start)
    scored = []

    for sol in solutions:
        total = sum(sol.values())
        spread = sum(1 for v in sol.values() if v > 0)

        # Shannon entropy of key distribution
        if total > 0:
            probs = [v / total for v in sol.values() if v > 0]
            entropy = -sum(p * math.log2(p) for p in probs if p > 0)
        else:
            entropy = 0.0

        # Average distance of keys from start (weighted by key count)
        if total > 0:
            avg_dist = sum(distances.get(node, 0) * val
                           for node, val in sol.items()) / total
        else:
            avg_dist = 0.0

        meta = {
            'total': total,
            'spread': spread,
            'entropy': round(entropy, 3) if entropy != 0 else 0.0,
            'avg_distance': round(avg_dist, 3),
        }

        # Diversity score: prefer high spread and entropy
        score = spread * 10 + entropy * 5 + avg_dist * 2
        scored.append((sol, meta, score))

    # Sort by diversity score descending (total is fixed)
    scored.sort(key=lambda x: -x[2])

    return [(sol, meta) for sol, meta, _ in scored]
