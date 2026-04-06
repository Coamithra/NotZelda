"""Aggregate runner for all integration test suites.

Usage:
    python tools/run_integration_tests.py                  # run all
    python tools/run_integration_tests.py --category movement  # run one category
    python tools/run_integration_tests.py --list           # list categories
"""

import sys
import importlib
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from test_harness import load_test_assets, load_dungeon_assets, reset_game_state, GameClock


CATEGORIES = {
    "movement":  "test_movement",
    "combat":    "test_combat",
    "monsters":  "test_monster_scripts",
    "multiplayer": "test_multiplayer",
    "reachability": "test_reachability",
}


def _collect_tests(module):
    """Collect all test_* functions from a module."""
    return [(name, fn) for name, fn in sorted(vars(module).items())
            if name.startswith("test_") and callable(fn)]


def main():
    args = sys.argv[1:]

    if "--list" in args:
        print("Available categories:")
        for cat in CATEGORIES:
            print(f"  {cat}")
        return 0

    # Filter categories
    if "--category" in args:
        idx = args.index("--category")
        if idx + 1 >= len(args):
            print("Error: --category requires a value")
            return 1
        selected = args[idx + 1]
        if selected not in CATEGORIES:
            print(f"Unknown category: {selected}")
            print(f"Available: {', '.join(CATEGORIES)}")
            return 1
        categories = {selected: CATEGORIES[selected]}
    else:
        categories = CATEGORIES

    # Load assets
    print("Loading game assets...")
    load_test_assets()
    # Load dungeon assets if reachability tests are included
    if "reachability" in categories:
        load_dungeon_assets()

    total_passed = 0
    total_failed = 0
    failed_tests = []

    for cat_name, module_name in categories.items():
        print(f"\n{'='*60}")
        print(f"  {cat_name.upper()}")
        print(f"{'='*60}")

        module = importlib.import_module(module_name)
        tests = _collect_tests(module)

        for name, fn in tests:
            clock = GameClock(1000.0)
            reset_game_state()
            with patch("time.monotonic", clock):
                try:
                    fn(clock)
                    total_passed += 1
                    print(f"  PASS  {name}")
                except Exception as ex:
                    total_failed += 1
                    failed_tests.append(f"{cat_name}/{name}: {ex}")
                    print(f"  FAIL  {name}: {ex}")

    print(f"\n{'='*60}")
    print(f"  TOTAL: {total_passed} passed, {total_failed} failed "
          f"out of {total_passed + total_failed} tests")
    print(f"{'='*60}")

    if failed_tests:
        print("\nFailed tests:")
        for ft in failed_tests:
            print(f"  - {ft}")

    return 1 if total_failed else 0


if __name__ == "__main__":
    sys.exit(main())
