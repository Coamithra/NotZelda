"""CLI entry point for the deadlock-free key distribution solver."""

import sys
from solver import find_key_distributions
from visualizer import visualize_solutions


EXAMPLES = {
    'triangle': {
        'adjacency': {'A': ['B', 'C'], 'B': ['A', 'C'], 'C': ['A', 'B']},
        'start': 'A',
        'description': 'Simple triangle (3 nodes, 3 edges)',
    },
    'path': {
        'adjacency': {
            'A': ['B'], 'B': ['A', 'C'], 'C': ['B', 'D'], 'D': ['C'],
        },
        'start': 'A',
        'description': 'Linear path of 4 nodes',
    },
    'diamond': {
        'adjacency': {
            'A': ['B', 'C'],
            'B': ['A', 'D'],
            'C': ['A', 'D'],
            'D': ['B', 'C'],
        },
        'start': 'A',
        'description': 'Diamond shape (4 nodes, 4 edges)',
    },
    'star': {
        'adjacency': {
            'hub': ['a', 'b', 'c', 'd'],
            'a': ['hub'], 'b': ['hub'], 'c': ['hub'], 'd': ['hub'],
        },
        'start': 'hub',
        'description': 'Star with 4 leaves',
    },
    'dungeon': {
        'adjacency': {
            'entrance': ['hall'],
            'hall': ['entrance', 'left', 'right'],
            'left': ['hall', 'treasure'],
            'right': ['hall', 'boss'],
            'treasure': ['left'],
            'boss': ['right'],
        },
        'start': 'entrance',
        'description': 'Simple dungeon layout (6 rooms)',
    },
    'grid4': {
        'adjacency': {
            'A': ['B', 'C'],
            'B': ['A', 'D'],
            'C': ['A', 'D'],
            'D': ['B', 'C'],
        },
        'start': 'A',
        'description': '2x2 grid (same as diamond)',
    },
}


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else None

    if name is None or name == '--help' or name == '-h':
        print("Deadlock-Free Key Distribution Solver")
        print("=" * 40)
        print(f"\nUsage: python main.py <graph_name>")
        print(f"\nAvailable graphs:")
        for key, val in EXAMPLES.items():
            print(f"  {key:12s} -- {val['description']}")
        return

    if name not in EXAMPLES:
        print(f"Unknown graph '{name}'. Available: {', '.join(EXAMPLES.keys())}")
        return

    example = EXAMPLES[name]
    adj = example['adjacency']
    start = example['start']

    print(f"Graph: {name} -- {example['description']}")
    print(f"Nodes: {list(adj.keys())}")
    print(f"Edges: {sum(len(v) for v in adj.values()) // 2}")
    print(f"Start: {start}")
    print()

    num_edges = sum(len(v) for v in adj.values()) // 2
    solutions = find_key_distributions(adj, start, max_per_node=2)

    if not solutions:
        print("No valid distributions found!")
        return

    print(f"Total keys (= edges): {num_edges}")
    print(f"Found {len(solutions)} solutions (showing first 20):\n")

    for i, (sol, meta) in enumerate(solutions[:20]):
        values_str = ", ".join(f"{k}={v}" for k, v in sorted(sol.items()))
        print(f"  {i + 1:2d}. [{values_str}]")
        print(f"      spread={meta['spread']}  "
              f"entropy={meta['entropy']}  avg_dist={meta['avg_distance']}")
    if len(solutions) > 20:
        print(f"  ... and {len(solutions) - 20} more")

    print(f"\nLaunching visualizer...")
    visualize_solutions(adj, start, solutions)


if __name__ == '__main__':
    main()
