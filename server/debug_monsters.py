"""Debug monster definitions and /debug_spawn command handler."""

import time

from server.state import game
from server.constants import ROOM_COLS, ROOM_ROWS
from server.models import Monster
from server.net import send_to, broadcast_to_room
from server.validation import register_monster_type

# A few built-in test monster definitions for /debug_spawn
DEBUG_MONSTERS = {
    "fire_slime": {
        "kind": "fire_slime",
        "stats": {"hp": 2, "tick_rate": 0.7, "damage": 2},
        "behavior": {
            "rules": [
                {"if": "hp_below", "value": 2, "do": "move", "direction": "away"},
                {"if": "player_within", "range": 5, "do": "move", "direction": "player"},
                {"if": "always", "do": "move", "direction": "random"},
            ],
        },
        "sprite": {
            "colors": {"body": "#ff6600", "dark": "#cc3300", "eyes": "#222222", "highlight": "#ffaa00"},
            "frames": [
                [
                    ["dark",      2, 9,12, 6],
                    ["body",      3, 8,10, 6],
                    ["body",      4, 7, 8, 1],
                    ["eyes",      5, 9, 2, 2],
                    ["eyes",      9, 9, 2, 2],
                    ["highlight", 5, 8, 2, 1],
                ],
                [
                    ["dark",      4,12, 8, 2],
                    ["body",      4, 4, 8, 9],
                    ["body",      5, 3, 6, 1],
                    ["body",      5,13, 6, 1],
                    ["dark",      4,11, 8, 2],
                    ["eyes",      5, 6, 2, 2],
                    ["eyes",      9, 6, 2, 2],
                    ["highlight", 5, 4, 2, 1],
                ],
            ],
        },
    },
    "ice_bat": {
        "kind": "ice_bat",
        "stats": {"hp": 1, "tick_rate": 1.25, "damage": 1},
        "behavior": {
            "rules": [
                {"if": "player_within", "range": 3, "do": "move", "direction": "away"},
                {"if": "player_within", "range": 7, "do": "hold"},
                {"if": "always", "do": "move", "direction": "random"},
            ],
        },
        "sprite": {
            "colors": {"body": "#4a6a8a", "wing": "#7ab0dd", "eyes": "#00ffff"},
            "frames": [
                [
                    ["body",  6, 6, 4, 4],
                    ["wing",  1, 3, 5, 4],
                    ["wing", 10, 3, 5, 4],
                    ["wing",  2, 2, 3, 1],
                    ["wing", 11, 2, 3, 1],
                    ["eyes",  6, 7, 1, 1],
                    ["eyes",  9, 7, 1, 1],
                ],
                [
                    ["body",  6, 5, 4, 4],
                    ["wing",  1, 7, 5, 4],
                    ["wing", 10, 7, 5, 4],
                    ["wing",  2,11, 3, 1],
                    ["wing", 11,11, 3, 1],
                    ["eyes",  6, 6, 1, 1],
                    ["eyes",  9, 6, 1, 1],
                ],
            ],
        },
    },
    "shadow_skull": {
        "kind": "shadow_skull",
        "stats": {"hp": 3, "tick_rate": 0.5, "damage": 3},
        "behavior": {
            "rules": [
                {"if": "hp_below", "value": 2, "do": "move", "direction": "away"},
                {"if": "player_within", "range": 4, "do": "move", "direction": "player"},
                {"if": "random_chance", "value": 30, "do": "move", "direction": "random"},
                {"if": "always", "do": "hold"},
            ],
        },
        "sprite": {
            "colors": {"bone": "#e0d8c0", "dark": "#2a1a2a", "eyes": "#ff0044", "shadow": "#4a2a4a"},
            "frames": [
                [
                    ["shadow",  4, 9, 8, 5],
                    ["bone",    5, 3, 6, 6],
                    ["bone",    4, 4, 8, 4],
                    ["dark",    6, 5, 2, 2],
                    ["dark",    8, 5, 2, 2],
                    ["eyes",    6, 5, 1, 1],
                    ["eyes",    9, 5, 1, 1],
                    ["dark",    7, 7, 2, 1],
                ],
                [
                    ["shadow",  4, 8, 8, 5],
                    ["bone",    5, 2, 6, 6],
                    ["bone",    4, 3, 8, 4],
                    ["dark",    6, 4, 2, 2],
                    ["dark",    8, 4, 2, 2],
                    ["eyes",    6, 4, 1, 1],
                    ["eyes",    9, 4, 1, 1],
                    ["dark",    7, 6, 2, 1],
                ],
            ],
        },
    },
    "skeleton_archer": {
        "kind": "skeleton_archer",
        "stats": {"hp": 2, "tick_rate": 0.5, "damage": 1},
        "behavior": {
            "rules": [
                {"if": "hp_below", "value": 2, "do": "move", "direction": "away"},
                {"if": "player_in_range_line", "range": 6, "los": True,
                 "do": "projectile", "direction": "player", "damage": 1,
                 "sprite_color": "#ccbb88", "cooldown": 3},
                {"if": "player_within", "range": 3, "do": "move", "direction": "away"},
                {"if": "player_within", "range": 8, "do": "hold"},
                {"if": "always", "do": "move", "direction": "random"},
            ],
        },
        "sprite": {
            "colors": {"bone": "#d8d0b8", "dark": "#5a4a3a", "eyes": "#cc2200", "bow": "#8b6914"},
            "frames": [
                [
                    ["dark",  5,10, 6, 4],
                    ["bone",  6, 3, 4, 8],
                    ["bone",  5, 4, 6, 5],
                    ["dark",  7, 5, 2, 2],
                    ["eyes",  7, 5, 1, 1],
                    ["eyes",  9, 5, 1, 1],
                    ["bone",  6, 9, 1, 3],
                    ["bone",  9, 9, 1, 3],
                    ["bow",   3, 4, 2, 6],
                ],
                [
                    ["dark",  5, 9, 6, 4],
                    ["bone",  6, 2, 4, 8],
                    ["bone",  5, 3, 6, 5],
                    ["dark",  7, 4, 2, 2],
                    ["eyes",  7, 4, 1, 1],
                    ["eyes",  9, 4, 1, 1],
                    ["bone",  6, 8, 1, 3],
                    ["bone",  9, 8, 1, 3],
                    ["bow",   3, 3, 2, 6],
                ],
            ],
        },
    },
    "ghost_teleporter": {
        "kind": "ghost_teleporter",
        "stats": {"hp": 2, "tick_rate": 0.4, "damage": 2},
        "behavior": {
            "rules": [
                {"if": "player_within", "range": 8,
                 "do": "teleport", "target": "player", "drift": 1, "range": 8,
                 "damage": 2, "damage_radius": 1, "warmup": 1, "cooldown": 4},
                {"if": "player_within", "range": 3, "do": "move", "direction": "away"},
                {"if": "always", "do": "move", "direction": "random"},
            ],
        },
        "sprite": {
            "colors": {"body": "#6a7a9a", "glow": "#aabbdd", "eyes": "#ffffff", "dark": "#3a4a6a"},
            "frames": [
                [
                    ["dark",  5, 9, 6, 5],
                    ["body",  5, 4, 6, 7],
                    ["body",  6, 3, 4, 1],
                    ["glow",  6, 5, 1, 1],
                    ["glow",  9, 5, 1, 1],
                    ["eyes",  6, 5, 1, 1],
                    ["eyes",  9, 5, 1, 1],
                ],
                [
                    ["dark",  5, 8, 6, 5],
                    ["body",  5, 3, 6, 7],
                    ["body",  6, 2, 4, 1],
                    ["glow",  6, 4, 1, 1],
                    ["glow",  9, 4, 1, 1],
                    ["eyes",  6, 4, 1, 1],
                    ["eyes",  9, 4, 1, 1],
                ],
            ],
        },
    },
    "war_boar": {
        "kind": "war_boar",
        "stats": {"hp": 4, "tick_rate": 0.7, "damage": 2},
        "behavior": {
            "rules": [
                {"if": "player_in_range_line", "range": 4, "los": True,
                 "do": "charge", "direction": "player", "range": 4, "damage": 3,
                 "warmup": 1, "cooldown": 4},
                {"if": "player_within", "range": 6, "do": "move", "direction": "player"},
                {"if": "always", "do": "move", "direction": "random"},
            ],
        },
        "sprite": {
            "colors": {"body": "#8b5e3c", "dark": "#5a3a1e", "snout": "#dda488", "eyes": "#220000", "tusk": "#f0e8d0"},
            "frames": [
                [
                    ["dark",   3,10, 10, 4],
                    ["body",   3, 5, 10, 7],
                    ["body",   4, 4,  8, 1],
                    ["dark",   4, 9, 8,  2],
                    ["snout",  5, 6,  3, 3],
                    ["eyes",   5, 5,  1, 1],
                    ["eyes",   8, 5,  1, 1],
                    ["tusk",   5, 9,  1, 2],
                    ["tusk",   7, 9,  1, 2],
                ],
                [
                    ["dark",   3, 9, 10, 4],
                    ["body",   3, 4, 10, 7],
                    ["body",   4, 3,  8, 1],
                    ["dark",   4, 8, 8,  2],
                    ["snout",  5, 5,  3, 3],
                    ["eyes",   5, 4,  1, 1],
                    ["eyes",   8, 4,  1, 1],
                    ["tusk",   5, 8,  1, 2],
                    ["tusk",   7, 8,  1, 2],
                ],
            ],
        },
    },
    "flame_mage": {
        "kind": "flame_mage",
        "stats": {"hp": 3, "tick_rate": 0.4, "damage": 2},
        "behavior": {
            "rules": [
                {"if": "hp_below", "value": 2, "do": "move", "direction": "away"},
                {"if": "player_within", "range": 2,
                 "do": "area", "range": 2, "damage": 2,
                 "warmup": 2, "cooldown": 5},
                {"if": "player_in_range_line", "range": 5, "los": True,
                 "do": "projectile", "direction": "player", "damage": 1,
                 "sprite_color": "#ff6600", "cooldown": 3},
                {"if": "player_within", "range": 3, "do": "move", "direction": "away"},
                {"if": "player_within", "range": 7, "do": "hold"},
                {"if": "always", "do": "move", "direction": "random"},
            ],
        },
        "sprite": {
            "colors": {"robe": "#8b2500", "dark": "#4a1200", "skin": "#dda488", "fire": "#ff6600", "glow": "#ffaa00"},
            "frames": [
                [
                    ["dark",  4,10, 8, 4],
                    ["robe",  4, 5, 8, 8],
                    ["robe",  5, 4, 6, 1],
                    ["skin",  6, 3, 4, 2],
                    ["dark",  7, 4, 1, 1],
                    ["dark",  9, 4, 1, 1],
                    ["fire",  5, 2, 2, 2],
                    ["glow",  5, 1, 1, 1],
                ],
                [
                    ["dark",  4, 9, 8, 4],
                    ["robe",  4, 4, 8, 8],
                    ["robe",  5, 3, 6, 1],
                    ["skin",  6, 2, 4, 2],
                    ["dark",  7, 3, 1, 1],
                    ["dark",  9, 3, 1, 1],
                    ["fire",  5, 1, 2, 2],
                    ["glow",  6, 0, 1, 1],
                ],
            ],
        },
    },
    # --- Coverage gap monsters ---
    "sentinel_golem": {
        "kind": "sentinel_golem",
        "stats": {"hp": 5, "tick_rate": 0.5, "damage": 2},
        "behavior": {
            "rules": [
                {"if": "player_within", "range": 2,
                 "do": "area", "range": 2, "damage": 3,
                 "warmup": 2, "cooldown": 5},
                {"if": "player_within", "range": 5, "do": "move", "direction": "player"},
                {"if": "player_beyond", "range": 5, "do": "move", "direction": "patrol", "patrol_route": "RRRDDDLLLUU"},
                {"if": "always", "do": "move", "direction": "patrol", "patrol_route": "RRRDDDLLLUUU"},
            ],
        },
        "sprite": {
            "colors": {"body": "#7a7a7a", "dark": "#4a4a4a", "eyes": "#44ff44", "highlight": "#9a9a9a"},
            "frames": [
                [
                    ["dark",      3,10,10, 4],
                    ["body",      3, 4,10, 9],
                    ["body",      4, 3, 8, 1],
                    ["dark",      4, 9, 8, 2],
                    ["highlight", 5, 4, 6, 2],
                    ["eyes",      5, 5, 2, 2],
                    ["eyes",      9, 5, 2, 2],
                ],
                [
                    ["dark",      3, 9,10, 4],
                    ["body",      3, 3,10, 9],
                    ["body",      4, 2, 8, 1],
                    ["dark",      4, 8, 8, 2],
                    ["highlight", 5, 3, 6, 2],
                    ["eyes",      5, 4, 2, 2],
                    ["eyes",      9, 4, 2, 2],
                ],
            ],
        },
    },
    "storm_archer": {
        "kind": "storm_archer",
        "stats": {"hp": 2, "tick_rate": 0.7, "damage": 1},
        "behavior": {
            "rules": [
                {"if": "player_in_range_line", "range": 8, "los": False,
                 "do": "projectile", "direction": "player", "damage": 1,
                 "sprite_color": "#00ccff", "speed": 2, "piercing": True,
                 "cooldown": 2},
                {"if": "hp_below", "value": 2, "do": "move", "direction": "away"},
                {"if": "hp_above", "value": 1, "do": "hold"},
                {"if": "always", "do": "move", "direction": "random"},
            ],
        },
        "sprite": {
            "colors": {"body": "#2a4a6a", "bolt": "#00ccff", "eyes": "#00eeff", "dark": "#1a2a3a"},
            "frames": [
                [
                    ["dark",  5,10, 6, 4],
                    ["body",  5, 4, 6, 8],
                    ["body",  6, 3, 4, 1],
                    ["bolt",  3, 5, 2, 5],
                    ["bolt",  2, 6, 1, 3],
                    ["eyes",  6, 5, 1, 1],
                    ["eyes",  9, 5, 1, 1],
                    ["dark",  6, 7, 4, 1],
                ],
                [
                    ["dark",  5, 9, 6, 4],
                    ["body",  5, 3, 6, 8],
                    ["body",  6, 2, 4, 1],
                    ["bolt",  3, 4, 2, 5],
                    ["bolt",  2, 5, 1, 3],
                    ["eyes",  6, 4, 1, 1],
                    ["eyes",  9, 4, 1, 1],
                    ["dark",  6, 6, 4, 1],
                ],
            ],
        },
    },
    "phase_fox": {
        "kind": "phase_fox",
        "stats": {"hp": 3, "tick_rate": 0.5, "damage": 1},
        "behavior": {
            "rules": [
                {"if": "hp_below", "value": 2,
                 "do": "teleport", "target": "away", "drift": 3, "range": 10,
                 "damage": 1, "damage_radius": 0, "warmup": 1, "cooldown": 3},
                {"if": "player_within", "range": 3,
                 "do": "teleport", "target": "player", "drift": 0, "range": 8,
                 "damage": 2, "damage_radius": 0, "warmup": 1, "cooldown": 4},
                {"if": "random_chance", "value": 15,
                 "do": "teleport", "target": "random", "drift": 2, "range": 12,
                 "damage": 1, "damage_radius": 0, "warmup": 1, "cooldown": 3},
                {"if": "player_within", "range": 6, "do": "move", "direction": "player"},
                {"if": "always", "do": "move", "direction": "random"},
            ],
        },
        "sprite": {
            "colors": {"body": "#8844aa", "light": "#bb77dd", "eyes": "#ffcc00", "dark": "#553377"},
            "frames": [
                [
                    ["dark",   6,11, 4, 3],
                    ["body",   5, 5, 6, 7],
                    ["body",   6, 4, 4, 1],
                    ["light",  6, 5, 4, 3],
                    ["body",   3, 3, 3, 4],
                    ["body",  10, 3, 3, 4],
                    ["eyes",   6, 6, 1, 1],
                    ["eyes",   9, 6, 1, 1],
                    ["dark",   7, 8, 2, 1],
                ],
                [
                    ["dark",   6,10, 4, 3],
                    ["body",   5, 4, 6, 7],
                    ["body",   6, 3, 4, 1],
                    ["light",  6, 4, 4, 3],
                    ["body",   3, 2, 3, 4],
                    ["body",  10, 2, 3, 4],
                    ["eyes",   6, 5, 1, 1],
                    ["eyes",   9, 5, 1, 1],
                    ["dark",   7, 7, 2, 1],
                ],
            ],
        },
    },
    "magma_wyrm": {
        "kind": "magma_wyrm",
        "stats": {"hp": 6, "tick_rate": 0.8, "damage": 3},
        "behavior": {
            "rules": [
                {"if": "player_in_range_line", "range": 5, "los": True,
                 "do": "charge", "direction": "player", "range": 5, "damage": 4,
                 "warmup": 1, "cooldown": 4},
                {"if": "random_chance", "value": 25,
                 "do": "charge", "direction": "random", "range": 3, "damage": 3,
                 "warmup": 1, "cooldown": 3},
                {"if": "player_within", "range": 4, "do": "move", "direction": "player"},
                {"if": "always", "do": "move", "direction": "random"},
            ],
        },
        "sprite": {
            "colors": {"body": "#cc3300", "dark": "#881100", "belly": "#ff6600", "eyes": "#ffff00", "glow": "#ffaa00"},
            "frames": [
                [
                    ["dark",   3,10,10, 4],
                    ["body",   3, 4,10, 8],
                    ["body",   4, 3, 8, 1],
                    ["belly",  5, 8, 6, 3],
                    ["dark",   4, 7, 8, 1],
                    ["eyes",   5, 5, 2, 1],
                    ["eyes",   9, 5, 2, 1],
                    ["glow",   6, 6, 4, 1],
                ],
                [
                    ["dark",   3, 9,10, 4],
                    ["body",   3, 3,10, 8],
                    ["body",   4, 2, 8, 1],
                    ["belly",  5, 7, 6, 3],
                    ["dark",   4, 6, 8, 1],
                    ["eyes",   5, 4, 2, 1],
                    ["eyes",   9, 4, 2, 1],
                    ["glow",   6, 5, 4, 1],
                ],
            ],
        },
    },
}


async def handle_debug_spawn(player, args: str):
    """Handle /debug_spawn <kind> — register and spawn a test monster near the player."""
    args = args.strip()
    if not args:
        available = list(DEBUG_MONSTERS.keys()) + [k for k in game.custom_sprites if k not in DEBUG_MONSTERS]
        existing_custom = [k for k in game.monster_stats if k not in ("slime", "bat", "scorpion", "skeleton", "swamp_blob")]
        msg = "Usage: /debug_spawn <kind>\n"
        msg += f"Built-in test monsters: {', '.join(DEBUG_MONSTERS.keys())}\n"
        if existing_custom:
            msg += f"Registered custom: {', '.join(existing_custom)}\n"
        msg += "Also works with any built-in kind: slime, bat, scorpion, skeleton, swamp_blob"
        await send_to(player, {"type": "info", "text": msg})
        return

    kind = args.split()[0].lower()

    # If it's a debug monster that isn't registered yet, register it
    if kind in DEBUG_MONSTERS and kind not in game.monster_stats:
        ok, errors = register_monster_type(DEBUG_MONSTERS[kind])
        if not ok:
            await send_to(player, {"type": "info", "text": f"Registration failed: {'; '.join(errors)}"})
            return

    # Check the kind exists (built-in or custom)
    if kind not in game.monster_stats:
        await send_to(player, {"type": "info", "text": f"Unknown monster kind: {kind}"})
        return

    # Find a walkable tile near the player
    room = game.rooms[player.room]
    tilemap = room["tilemap"]
    guards = game.guards.get(player.room, [])
    spawn_x, spawn_y = None, None
    for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1), (2, 0), (-2, 0), (0, 2), (0, -2)]:
        nx, ny = player.x + dx, player.y + dy
        if 0 <= nx < ROOM_COLS and 0 <= ny < ROOM_ROWS:
            if game.is_walkable_tile(tilemap[ny][nx]):
                if not any(g["x"] == nx and g["y"] == ny for g in guards):
                    spawn_x, spawn_y = nx, ny
                    break

    if spawn_x is None:
        await send_to(player, {"type": "info", "text": "No walkable tile nearby to spawn monster."})
        return

    # Create and add the monster
    monster = Monster(spawn_x, spawn_y, kind)
    monster.last_tick_time = time.monotonic()
    if player.room not in game.room_monsters:
        game.room_monsters[player.room] = []
    monster_list = game.room_monsters[player.room]
    monster_id = len(monster_list)
    monster_list.append(monster)

    # Build the spawn message with custom sprite data if needed
    spawn_msg = {
        "type": "monster_spawned",
        "id": monster_id,
        "kind": kind,
        "x": spawn_x,
        "y": spawn_y,
    }
    if kind in game.custom_sprites:
        spawn_msg["custom_sprites"] = {kind: game.custom_sprites[kind]}
    if kind in game.custom_death_sprites:
        spawn_msg["custom_death_sprites"] = {kind: game.custom_death_sprites[kind]}

    await broadcast_to_room(player.room, spawn_msg)
    await send_to(player, {"type": "info", "text": f"Spawned {kind} at ({spawn_x}, {spawn_y})"})


def auto_register_debug_monsters():
    """Register any DEBUG_MONSTERS that appear in room templates."""
    needed = set()
    for room_id, templates in game.monster_templates.items():
        for t in templates:
            kind = t["kind"]
            if kind in DEBUG_MONSTERS and kind not in game.monster_stats:
                needed.add(kind)
    for kind in sorted(needed):
        register_monster_type(DEBUG_MONSTERS[kind])
