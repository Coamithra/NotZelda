"""Interactive graph visualizer for key distributions.

Draws the graph with nodes colored by key count. Start node has a thick
blue border. Right arrow shows a random solution, left goes back through
history. Press 'r' to randomize the graph (10 edges) and re-solve.
"""

import random
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.widgets import Button
import networkx as nx

from solver import find_key_distributions, simulate_all_paths


def _generate_random_graph(num_edges=10):
    """Generate a random connected undirected graph with exactly num_edges edges.

    Returns (adjacency, start_node).
    """
    # Need at least 2 nodes for 1 edge; max nodes = num_edges + 1 (a tree)
    min_nodes = max(2, num_edges // 3 + 1)
    max_nodes = num_edges + 1
    n = random.randint(min_nodes, max_nodes)

    # Build a random spanning tree first (guarantees connectivity)
    nodes = list(range(n))
    random.shuffle(nodes)
    adj = {i: [] for i in range(n)}
    edges = set()

    for i in range(1, n):
        j = nodes[random.randint(0, i - 1)]
        u, v = nodes[i], j
        edge = (min(u, v), max(u, v))
        edges.add(edge)
        adj[u].append(v)
        adj[v].append(u)

    # Add random edges until we reach num_edges
    all_possible = [(i, j) for i in range(n) for j in range(i + 1, n)
                    if (i, j) not in edges]
    random.shuffle(all_possible)

    remaining = num_edges - len(edges)
    for edge in all_possible[:remaining]:
        u, v = edge
        edges.add(edge)
        adj[u].append(v)
        adj[v].append(u)

    # Convert to string labels
    labels = [chr(ord('A') + i) if i < 26 else f'N{i}' for i in range(n)]
    str_adj = {}
    for node, neighbors in adj.items():
        str_adj[labels[node]] = [labels[nb] for nb in neighbors]

    start = labels[0]
    return str_adj, start


def visualize_solutions(adjacency, start, solutions):
    """Interactive matplotlib window.

    - Right arrow: show a random solution
    - Left arrow: go back through previously viewed solutions
    - 'r' key or Randomize button: generate new random graph and re-solve
    """
    fig, ax = plt.subplots(figsize=(10, 8))
    plt.subplots_adjust(bottom=0.12)

    btn_rand_ax = fig.add_axes((0.7, 0.02, 0.2, 0.05))
    btn_rand = Button(btn_rand_ax, 'Randomize (r)')


    state = {
        'adj': adjacency,
        'start': start,
        'solutions': solutions,
        'history': [0] if solutions else [],  # indices into solutions
        'hist_pos': 0,  # current position in history
        'test_result': '',
        'G': None,
        'pos': None,
    }

    def rebuild_graph():
        G = nx.Graph()
        for node, neighbors in state['adj'].items():
            for neighbor in neighbors:
                G.add_edge(node, neighbor)
        state['G'] = G
        state['pos'] = nx.spring_layout(G, seed=random.randint(1, 9999))

    def draw_current():
        ax.clear()
        solutions = state['solutions']
        G = state['G']
        pos = state['pos']
        cur_start = state['start']

        if not solutions or not state['history']:
            num_edges = sum(len(v) for v in state['adj'].values()) // 2
            ax.set_title(f"No valid solutions for this graph "
                         f"({len(state['adj'])} nodes, {num_edges} edges)\n"
                         f"Press 'r' to randomize", fontsize=13)
            nx.draw(G, pos, ax=ax, with_labels=True, node_color='#ffcccc',
                    node_size=700, edge_color='#aaaaaa', width=2)
            fig.canvas.draw_idle()
            return

        sol_idx = state['history'][state['hist_pos']]
        sol, meta = solutions[sol_idx]
        node_list = list(G.nodes())
        max_val = max(max(sol.values()), 1)

        node_colors = []
        edge_colors = []
        linewidths = []

        for node in node_list:
            v = sol[node]
            if v == 0:
                node_colors.append('#e0e0e0')
            else:
                t = v / max_val
                r = 1.0
                g = 1.0 - 0.7 * t
                b = 0.2 * (1 - t)
                node_colors.append((r, g, b))

            if node == cur_start:
                edge_colors.append('#2266cc')
                linewidths.append(4.0)
            else:
                edge_colors.append('#444444')
                linewidths.append(1.5)

        nx.draw_networkx_edges(G, pos, ax=ax, edge_color='#aaaaaa', width=2)
        nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=node_list,
                               node_color=node_colors, node_size=900,
                               edgecolors=edge_colors, linewidths=linewidths)

        labels = {node: f"{node}\n[{sol[node]}]" for node in node_list}
        nx.draw_networkx_labels(G, pos, labels, ax=ax, font_size=11,
                                font_weight='bold')

        num_edges = sum(len(v) for v in state['adj'].values()) // 2
        n_nodes = len(state['adj'])
        total = len(solutions)
        hist_len = len(state['history'])
        hist_pos = state['hist_pos']
        test_str = state['test_result']
        ax.set_title(
            f"Graph: {n_nodes} nodes, {num_edges} edges  |  "
            f"{total} solutions  |  "
            f"spread={meta['spread']}, entropy={meta['entropy']}\n"
            f"{test_str}  |  "
            f"[right: random]  [left: back ({hist_pos}/{hist_len})]  "
            f"[r: new graph]",
            fontsize=12,
        )

        legend_elements = [
            mpatches.Patch(facecolor='#e0e0e0', edgecolor='#444444',
                           label='0 keys'),
            mpatches.Patch(facecolor='#ffe066', edgecolor='#444444',
                           label='Some keys'),
            mpatches.Patch(facecolor='#ff4400', edgecolor='#444444',
                           label='Max keys'),
            mpatches.Patch(facecolor='white', edgecolor='#2266cc',
                           linewidth=3, label='Start node'),
        ]
        ax.legend(handles=legend_elements, loc='lower left', fontsize=10)

        ax.margins(0.15)
        fig.canvas.draw_idle()

    def do_randomize():
        new_adj, new_start = _generate_random_graph(num_edges=10)
        num_edges = sum(len(v) for v in new_adj.values()) // 2
        n_nodes = len(new_adj)
        print(f"\nRandomized: {n_nodes} nodes, {num_edges} edges, start={new_start}")
        print(f"Adjacency: {new_adj}")

        state['adj'] = new_adj
        state['start'] = new_start
        rebuild_graph()

        new_solutions = find_key_distributions(new_adj, new_start, max_per_node=2)
        state['solutions'] = new_solutions
        state['history'] = [0] if new_solutions else []
        state['hist_pos'] = 0

        print(f"Found {len(new_solutions)} solutions")
        draw_current()

    def auto_test():
        """Run brute-force path simulation on current solution, show in title."""
        solutions = state['solutions']
        if not solutions or not state['history']:
            return

        sol_idx = state['history'][state['hist_pos']]
        sol, _meta = solutions[sol_idx]

        success, paths_tested, deadlock_path = simulate_all_paths(
            state['adj'], state['start'], sol)

        if success:
            state['test_result'] = f"PASS ({paths_tested} paths)"
        else:
            state['test_result'] = (
                f"DEADLOCK: {' -> '.join(deadlock_path)}")
            print(f"  FAIL — {state['test_result']}")

    def on_key(event):
        solutions = state['solutions']
        if event.key == 'right' and solutions:
            idx = random.randint(0, len(solutions) - 1)
            state['history'] = state['history'][:state['hist_pos'] + 1]
            state['history'].append(idx)
            state['hist_pos'] = len(state['history']) - 1
            draw_current()
            auto_test()
            draw_current()
        elif event.key == 'left' and state['hist_pos'] > 0:
            state['hist_pos'] -= 1
            draw_current()
            auto_test()
            draw_current()
        elif event.key == 'r':
            do_randomize()

    fig.canvas.mpl_connect('key_press_event', on_key)
    btn_rand.on_clicked(lambda _: do_randomize())

    rebuild_graph()
    auto_test()
    draw_current()
    plt.tight_layout()
    plt.show()
