"""THE GAUNTLET — Monster balancing test arena (debug-only).

Linear dungeon of endless trap rooms for difficulty tuning via binary search.
Player fights through each room, HP resets between rooms, infinite spirit jars.
Results logged to gauntlet_results.txt after every room clear (append-only).

Commands:
    /gauntlet [kind] [count]  — Start a gauntlet (default: bat 25)
    /gauntlet stop            — Exit and return to overworld
    /gauntlet status          — Show current config
    /gt <param> <value>       — Tune a parameter for the next wave
    /gt halve <param|all>     — Halve a parameter toward its default
    /gt hard [kind] [count]   — Reset to max-hard starting config
"""

import copy
import random
import time
from datetime import datetime

from server.state import game
from server.constants import (
    EDGE_SPAWN_POINTS, DEFAULT_SPAWN,
    ROOM_COLS, ROOM_ROWS,
)

RESULTS_FILE = "gauntlet_results.txt"

# Tuneable stat keys (float values)
FLOAT_PARAMS = {
    "walk_time", "decision_time", "distance",
    "warmup", "cooldown", "range", "drift", "damage_radius",
}
INT_PARAMS = {"hp", "count", "damage"}
# Rule-level params that override behavior rule fields
RULE_PARAMS = {"warmup", "cooldown", "range", "drift", "distance", "damage_radius"}

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

_sessions = {}  # player_name → GauntletSession


# Params eligible for auto-adjustment and whether "harder" means higher or lower
# True = higher is harder, False = lower is harder
HARDER_IS_HIGHER = {
    "count": True,
    "damage": True,
    "hp": True,
    "walk_time": False,      # lower = faster = harder
    "decision_time": False,  # lower = more frequent = harder
}


class GauntletSession:
    def __init__(self, player_name, return_room):
        self.player_name = player_name
        self.return_room = return_room
        self.wave = 0
        self.config = {}         # current wave config (overrides)
        self.hard_config = {}    # max-hard values (ceiling for doubling)
        self.easy_config = {}    # default values (floor for halving)
        self.entry_hp = 0
        self.entry_time = 0.0
        self.deaths = 0          # spirit jar revives this wave
        self.consecutive_good = 0  # reset to max-hard after 2 in a row
        self.started = datetime.now()
        self.header_written = False


def get_session(player_name):
    return _sessions.get(player_name)


def is_gauntlet_room(room_id):
    return room_id.startswith("gauntlet_")


# ---------------------------------------------------------------------------
# Arena room generation
# ---------------------------------------------------------------------------

def _make_arena_tilemap():
    """15×11 dungeon arena — walls on edges, doorways on east/west at rows 4-6."""
    tm = []
    for r in range(ROOM_ROWS):
        row = []
        for c in range(ROOM_COLS):
            if r == 0 or r == ROOM_ROWS - 1:
                row.append("DW")
            elif c == 0 or c == ROOM_COLS - 1:
                # Doorway rows: open floor for east/west entry
                if r in (4, 5, 6):
                    row.append("DF")
                else:
                    row.append("DW")
            else:
                row.append("DF")
        tm.append(row)
    return tm


def _create_gauntlet_room(session):
    """Register a bare gauntlet room in game.rooms (monsters set at entry)."""
    room_id = f"gauntlet_{session.player_name}_{session.wave}"
    next_id = f"gauntlet_{session.player_name}_{session.wave + 1}"

    game.rooms[room_id] = {
        "name": f"The Gauntlet — Wave {session.wave + 1}",
        "exits": {
            "east": next_id,
            "west": session.return_room,
        },
        "tilemap": _make_arena_tilemap(),
        "spawn_points": {
            "default": DEFAULT_SPAWN,
            "west": EDGE_SPAWN_POINTS["west"],
            "east": EDGE_SPAWN_POINTS["east"],
        },
        "biome": "dungeon",
        "music": "dungeon1_b",
        "locked": True,
    }
    return room_id


# ---------------------------------------------------------------------------
# Monster placement & stat overrides
# ---------------------------------------------------------------------------

def _monster_positions(count):
    """Random positions inside the arena, away from west spawn."""
    candidates = []
    for r in range(1, 10):
        for c in range(2, 14):
            # Keep a buffer around the west entry so player isn't swarmed on spawn
            if c <= 4 and 3 <= r <= 7:
                continue
            candidates.append((c, r))
    random.shuffle(candidates)
    return candidates[:count]


def prepare_gauntlet_room(room_id):
    """Set monster templates from session config.  Called before spawning."""
    parts = room_id.split("_")
    player_name = "_".join(parts[1:-1])
    session = _sessions.get(player_name)
    if not session:
        return

    config = session.config
    kind = config.get("kind", "bat")
    count = config.get("count", 2)
    positions = _monster_positions(count)

    game.monster_templates[room_id] = [
        {"kind": kind, "x": x, "y": y} for x, y in positions
    ]


def apply_gauntlet_overrides(room_id, monsters):
    """Patch spawned Monster instances with session config overrides."""
    parts = room_id.split("_")
    player_name = "_".join(parts[1:-1])
    session = _sessions.get(player_name)
    if not session:
        return

    config = session.config
    for m in monsters:
        # Direct stat overrides
        if "hp" in config:
            m.hp = config["hp"]
            m.max_hp = config["hp"]
        if "walk_time" in config:
            m.walk_time = config["walk_time"]
        if "decision_time" in config:
            m.decision_time = config["decision_time"]
        if "damage" in config:
            m.damage = config["damage"]

        # Rule-level overrides — deep-copy behavior so we don't mutate globals
        rule_keys = RULE_PARAMS & set(config.keys())
        if rule_keys and m.behavior:
            m.behavior = copy.deepcopy(m.behavior)
            for rule in m.behavior.get("rules", []):
                for key in rule_keys:
                    if key in rule:
                        rule[key] = config[key]


# ---------------------------------------------------------------------------
# Lifecycle hooks (called from lifecycle.py / combat.py / commands.py)
# ---------------------------------------------------------------------------

def on_gauntlet_enter(player):
    """Player entered a gauntlet room — reset HP, grant spirit jar, track state."""
    session = _sessions.get(player.name)
    if not session:
        return
    player.flags.discard("invulnerable")  # no cheating in the gauntlet!
    player.hp = min(6, player.max_hp)  # 3 hearts
    player.flags.add("has_spirit_jar")
    session.entry_hp = player.hp
    session.entry_time = time.monotonic()
    session.deaths = 0



def on_gauntlet_death(player, now, msgs):
    """Player died in gauntlet — log as TOO HARD, advance to next wave."""
    from server.lifecycle import on_player_enter_room, send_room_enter
    from server.models import Avatar

    session = _sessions.get(player.name)
    if not session:
        return

    session.deaths += 1
    elapsed = time.monotonic() - session.entry_time
    hp_lost = session.entry_hp  # lost all HP (dead)

    _log_result(session, hp_lost, elapsed, "TOO HARD")

    # Auto-adjust one random param
    adjustment = _auto_adjust(session, "TOO HARD", msgs)

    config = session.config
    adj_str = f" | Next: {adjustment}" if adjustment else ""
    result_text = (
        f"Wave {session.wave + 1}: DIED | "
        f"{config.get('kind', '?')} x{config.get('count', '?')} | "
        f"Deaths: {session.deaths} | "
        f"Time: {elapsed:.1f}s | "
        f"[TOO HARD]{adj_str}"
    )

    # Clean up old room (monsters still ticking if not cleaned)
    old_room = player.death_room
    from server.lifecycle import on_player_leave_room
    on_player_leave_room(old_room, msgs)

    # Advance wave
    session.wave += 1
    next_room = _create_gauntlet_room(session)

    # Revive player into the next room
    player.dead = False
    player.death_time = 0.0
    player.death_room = None
    player.death_x = 0.0
    player.death_y = 0.0
    player.chose_respawn = False
    player.room = next_room
    player.hp = min(6, player.max_hp)
    player.flags.discard("invulnerable")
    player.flags.add("has_spirit_jar")
    player.avatar = Avatar(1.0, 5.0, "right")
    player.command_queue.clear()
    player.active_attack = None
    player.last_damage_time = now  # brief invincibility

    on_player_enter_room(next_room)

    session.entry_hp = player.hp
    session.entry_time = time.monotonic()
    session.deaths = 0

    send_room_enter(player, msgs)
    msgs.append(("send", player, {"type": "info", "text": result_text}))


def on_gauntlet_room_cleared(player, room_id, msgs):
    """All monsters dead — log result, create next room, show summary."""
    session = _sessions.get(player.name)
    if not session:
        return

    elapsed = time.monotonic() - session.entry_time
    hp_lost = session.entry_hp - player.hp

    # Classify outcome
    if session.deaths > 0:
        outcome = "TOO HARD"
    elif hp_lost >= 4:
        outcome = "HARD"
    elif hp_lost >= 1:
        outcome = "GOOD"
    else:
        outcome = "EASY"

    _log_result(session, hp_lost, elapsed, outcome)

    # Auto-adjust one random param
    adjustment = _auto_adjust(session, outcome, msgs)

    config = session.config
    adj_str = f" | Next: {adjustment}" if adjustment else ""
    result_text = (
        f"Wave {session.wave + 1}: "
        f"{config.get('kind', '?')} x{config.get('count', '?')} | "
        f"HP lost: {hp_lost} ({hp_lost / 2:.1f} hearts) | "
        f"Deaths: {session.deaths} | "
        f"Time: {elapsed:.1f}s | "
        f"[{outcome}]{adj_str}"
    )
    msgs.append(("send", player, {"type": "info", "text": result_text}))

    # Advance to next wave and prepare room
    session.wave += 1
    _create_gauntlet_room(session)

    # Reset HP for next room
    player.hp = min(6, player.max_hp)
    player.flags.add("has_spirit_jar")


def on_gauntlet_exit(player_name):
    """Clean up all gauntlet rooms when a player leaves the gauntlet."""
    session = _sessions.pop(player_name, None)
    if not session:
        return
    for i in range(session.wave + 2):
        rid = f"gauntlet_{player_name}_{i}"
        game.rooms.pop(rid, None)
        game.monster_templates.pop(rid, None)
        game.room_monsters.pop(rid, None)
        game.locked_rooms.pop(rid, None)
        game.room_cooldowns.pop(rid, None)
        game.room_hearts.pop(rid, None)
        game.room_projectiles.pop(rid, None)
        game.room_pickup_freeze.pop(rid, None)


# ---------------------------------------------------------------------------
# Results logging (append-only, flushed after every wave)
# ---------------------------------------------------------------------------

def _log_result(session, hp_lost, elapsed, outcome):
    config = session.config

    stat_parts = []
    for key in ("hp", "walk_time", "decision_time", "damage", "distance",
                "warmup", "cooldown", "range", "drift", "damage_radius"):
        if key in config:
            val = config[key]
            stat_parts.append(f"{key}={val:.2f}" if isinstance(val, float) else f"{key}={val}")
    stats_str = " ".join(stat_parts) if stat_parts else "(defaults)"

    with open(RESULTS_FILE, "a", encoding="utf-8") as f:
        if not session.header_written:
            f.write(f"{'=' * 50}\n")
            f.write(f"GAUNTLET SESSION — {session.player_name}\n")
            f.write(f"Started: {session.started.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'=' * 50}\n\n")
            session.header_written = True

        f.write(f"--- Wave {session.wave + 1} ---\n")
        f.write(f"Monster: {config.get('kind', 'bat')} x{config.get('count', '?')}\n")
        f.write(f"Stats: {stats_str}\n")
        deaths_str = f" ({session.deaths} deaths)" if session.deaths else ""
        f.write(
            f"Result: {'DIED' if session.deaths else 'SURVIVED'}{deaths_str}"
            f" | HP lost: {hp_lost} ({hp_lost / 2:.1f} hearts)"
            f" | Time: {elapsed:.1f}s\n"
        )
        f.write(f"Outcome: {outcome}\n\n")
        f.flush()


# ---------------------------------------------------------------------------
# Chat commands
# ---------------------------------------------------------------------------

def cmd_gauntlet(player, args, msgs):
    """/gauntlet [stop|status|<kind> <count>]"""
    args = args.strip().lower()

    if args == "stop":
        return _cmd_stop(player, msgs)
    if args == "status":
        return _cmd_status(player, msgs)

    if player.name in _sessions:
        msgs.append(("send", player, {
            "type": "info",
            "text": "Already in gauntlet! /gauntlet stop to exit, /gt to tune.",
        }))
        return

    # Parse optional kind and count
    parts = args.split() if args else []
    kind = parts[0] if len(parts) >= 1 else "bat"
    try:
        count = int(parts[1]) if len(parts) >= 2 else 25
    except ValueError:
        count = 25

    if kind not in game.monster_stats:
        kinds = ", ".join(sorted(game.monster_stats.keys()))
        msgs.append(("send", player, {
            "type": "info", "text": f"Unknown monster: {kind}. Available: {kinds}",
        }))
        return

    # Build max-hard starting config + binary search bounds
    defaults = game.monster_stats[kind]
    session = GauntletSession(player.name, player.room)
    session.config = _max_hard_config(kind, count, defaults)
    _init_bounds(session, defaults)
    _sessions[player.name] = session

    # Create first room
    room_id = _create_gauntlet_room(session)

    # Teleport player into the gauntlet
    from server.lifecycle import on_player_leave_room, on_player_enter_room, send_room_enter
    from server.models import Avatar

    on_player_leave_room(player.room, msgs)
    player.room = room_id
    # Spawn 1 tile inside the west doorway so we're not stuck in the door
    player.avatar = Avatar(1.0, 5.0, "right")
    player.flags.discard("invulnerable")  # no cheating in the gauntlet!
    player.hp = min(6, player.max_hp)
    player.flags.add("has_spirit_jar")

    on_player_enter_room(room_id)

    session.entry_hp = player.hp
    session.entry_time = time.monotonic()

    send_room_enter(player, msgs)

    c = session.config
    msgs.append(("send", player, {
        "type": "info",
        "text": (
            f"THE GAUNTLET BEGINS! {kind} x{count} | "
            f"walk={c['walk_time']:.2f} dec={c['decision_time']:.2f} "
            f"dmg={c['damage']} hp={c['hp']} | "
            f"/gt to tune, /gauntlet stop to exit"
        ),
    }))


def _max_hard_config(kind, count, defaults):
    """Starting config: everything cranked to maximum difficulty."""
    walk = round(max(0.08, defaults.get("walk_time", 0.25) * 0.4), 3)
    return {
        "kind": kind,
        "count": count,
        "walk_time": walk,
        "decision_time": walk,  # no idle gap — continuous movement
        "damage": 2,  # 1 heart — card says max 1 heart
        "hp": defaults.get("hp", 1),
    }


def _init_bounds(session, defaults):
    """Set hard ceiling and easy floor for each tuneable param."""
    session.hard_config = {k: v for k, v in session.config.items() if k != "kind"}
    session.easy_config = {
        "count": 1,
        "walk_time": max(0.5, defaults.get("walk_time", 0.25) * 2),
        "decision_time": max(2.0, defaults.get("decision_time", 1.0) * 2),
        "damage": 1,
        "hp": max(1, defaults.get("hp", 1)),
    }


def _auto_adjust(session, outcome, msgs_out):
    """Auto binary-search: adjust ONE random param based on the outcome.

    TOO HARD / HARD: pick a random param, halve toward easy.
    EASY:            pick a random param, double toward hard.
    GOOD:            sweet spot — count consecutive. After 2, reset to max hard.
    """
    config = session.config
    kind = config.get("kind", "bat")
    adjustable = [k for k in HARDER_IS_HIGHER if k in config]

    if outcome == "GOOD":
        session.consecutive_good += 1
        if session.consecutive_good >= 2:
            # Found a sweet spot twice — reset to max hard for a fresh search
            defaults = game.monster_stats.get(kind, {})
            hard = _max_hard_config(kind, session.hard_config.get("count", 25), defaults)
            config.update({k: v for k, v in hard.items() if k != "kind"})
            _init_bounds(session, defaults)
            session.consecutive_good = 0
            return "RESET TO MAX HARD — searching for a new balance"
        return None  # stay at current settings, try again

    session.consecutive_good = 0

    # Filter out params that are already at their bound (can't move further)
    if outcome in ("TOO HARD", "HARD"):
        adjustable = [k for k in adjustable
                      if config[k] != session.easy_config.get(k, config[k])]
    else:
        adjustable = [k for k in adjustable
                      if config[k] != session.hard_config.get(k, config[k])]
    if not adjustable:
        return "all params at bounds — use /gt to adjust manually"

    param = random.choice(adjustable)
    old_val = config[param]
    hard_val = session.hard_config.get(param, old_val)
    easy_val = session.easy_config.get(param, old_val)

    is_int = param in INT_PARAMS
    higher_is_harder = HARDER_IS_HIGHER[param]

    if outcome in ("TOO HARD", "HARD"):
        # Narrow: current value was too hard, so it becomes the new hard bound
        session.hard_config[param] = old_val
        # Make easier: bisect toward easy bound
        if is_int:
            new_val = max(1, (old_val + int(easy_val)) // 2)
            if new_val == old_val and old_val > 1:
                new_val = old_val - 1 if higher_is_harder else old_val + 1
        else:
            new_val = round((old_val + easy_val) / 2, 3)
    else:
        # EASY: current value was too easy, so it becomes the new easy bound
        session.easy_config[param] = old_val
        # Make harder: bisect toward hard bound
        if is_int:
            new_val = (old_val + int(hard_val) + 1) // 2
            if new_val == old_val:
                new_val = old_val + 1 if higher_is_harder else old_val - 1
        else:
            new_val = round((old_val + hard_val) / 2, 3)

    config[param] = new_val
    # Enforce: decision_time >= walk_time (can't decide faster than you walk)
    if "decision_time" in config and "walk_time" in config:
        if config["decision_time"] < config["walk_time"]:
            config["decision_time"] = config["walk_time"]
    direction = "easier" if outcome in ("TOO HARD", "HARD") else "harder"
    return f"{param}: {old_val}→{new_val} ({direction})"


def _cmd_stop(player, msgs):
    session = _sessions.get(player.name)
    if not session:
        msgs.append(("send", player, {"type": "info", "text": "Not in a gauntlet."}))
        return

    waves = session.wave + 1
    return_room = session.return_room

    # Leave current room BEFORE cleaning up gauntlet rooms
    from server.lifecycle import on_player_leave_room, on_player_enter_room, send_room_enter
    from server.models import Avatar

    if is_gauntlet_room(player.room):
        on_player_leave_room(player.room, msgs)

    on_gauntlet_exit(player.name)
    player.room = return_room
    spawn = game.rooms[return_room]["spawn_points"]["default"]
    player.avatar = Avatar(float(spawn[0]), float(spawn[1]), "down")
    on_player_enter_room(return_room)
    send_room_enter(player, msgs)

    msgs.append(("send", player, {
        "type": "info", "text": f"Gauntlet ended after {waves} waves. Results in {RESULTS_FILE}",
    }))


def _cmd_status(player, msgs):
    session = _sessions.get(player.name)
    if not session:
        msgs.append(("send", player, {"type": "info", "text": "Not in a gauntlet."}))
        return
    c = session.config
    parts = [f"{k}={v}" for k, v in sorted(c.items())]
    msgs.append(("send", player, {
        "type": "info",
        "text": f"Wave {session.wave + 1} | {' | '.join(parts)}",
    }))


def cmd_gt(player, args, msgs):
    """/gt <param> <value> | /gt halve <param|all> | /gt hard [kind] [count]"""
    session = _sessions.get(player.name)
    if not session:
        msgs.append(("send", player, {
            "type": "info", "text": "Not in a gauntlet. Use /gauntlet to start.",
        }))
        return

    args = args.strip()
    if not args:
        return _cmd_status(player, msgs)

    parts = args.split()
    subcmd = parts[0].lower()

    # /gt halve <param|all>
    if subcmd == "halve":
        return _cmd_halve(player, session, parts[1:], msgs)

    # /gt hard [kind] [count]
    if subcmd == "hard":
        return _cmd_hard(player, session, parts[1:], msgs)

    # /gt <param> <value>
    if len(parts) < 2:
        msgs.append(("send", player, {
            "type": "info",
            "text": (
                "Usage: /gt <param> <value> | /gt halve <param|all> | /gt hard [kind] [count]\n"
                "Params: kind count hp walk_time decision_time damage distance "
                "warmup cooldown range drift damage_radius"
            ),
        }))
        return

    key, val_str = parts[0].lower(), parts[1]

    if key == "kind":
        if val_str not in game.monster_stats:
            kinds = ", ".join(sorted(game.monster_stats.keys()))
            msgs.append(("send", player, {
                "type": "info", "text": f"Unknown: {val_str}. Available: {kinds}",
            }))
            return
        session.config["kind"] = val_str
    elif key in INT_PARAMS:
        session.config[key] = max(1, int(val_str))
    elif key in FLOAT_PARAMS:
        session.config[key] = round(float(val_str), 3)
    else:
        msgs.append(("send", player, {"type": "info", "text": f"Unknown param: {key}"}))
        return

    # Enforce: decision_time >= walk_time
    if "decision_time" in session.config and "walk_time" in session.config:
        if session.config["decision_time"] < session.config["walk_time"]:
            session.config["decision_time"] = session.config["walk_time"]

    msgs.append(("send", player, {
        "type": "info",
        "text": f"Next wave: {key}={session.config[key]}",
    }))


def _cmd_halve(player, session, parts, msgs):
    """Halve a parameter toward its default, or halve all."""
    if not parts:
        msgs.append(("send", player, {
            "type": "info", "text": "Usage: /gt halve <param|all>",
        }))
        return

    target = parts[0].lower()
    kind = session.config.get("kind", "bat")
    defaults = game.monster_stats.get(kind, {})
    config = session.config

    if target == "all":
        keys = [k for k in config if k not in ("kind",)]
    else:
        keys = [target]

    changed = []
    for key in keys:
        if key == "count":
            old = config.get("count", 2)
            new = max(1, old // 2)
            config["count"] = new
            changed.append(f"count: {old}→{new}")
        elif key in FLOAT_PARAMS:
            old = config.get(key)
            if old is None:
                continue
            default = defaults.get(key, old)
            new = round((old + default) / 2, 3)
            config[key] = new
            changed.append(f"{key}: {old}→{new}")
        elif key in INT_PARAMS:
            old = config.get(key)
            if old is None:
                continue
            default = defaults.get(key, old)
            new = max(1, (old + default) // 2)
            config[key] = new
            changed.append(f"{key}: {old}→{new}")

    if changed:
        msgs.append(("send", player, {
            "type": "info", "text": "Halved: " + ", ".join(changed),
        }))
    else:
        msgs.append(("send", player, {"type": "info", "text": "Nothing to halve."}))


def _cmd_hard(player, session, parts, msgs):
    """Reset to max-hard config, optionally switching monster type."""
    kind = parts[0] if parts else session.config.get("kind", "bat")
    try:
        count = int(parts[1]) if len(parts) >= 2 else session.config.get("count", 25)
    except ValueError:
        count = session.config.get("count", 25)

    if kind not in game.monster_stats:
        kinds = ", ".join(sorted(game.monster_stats.keys()))
        msgs.append(("send", player, {
            "type": "info", "text": f"Unknown: {kind}. Available: {kinds}",
        }))
        return

    defaults = game.monster_stats[kind]
    session.config = _max_hard_config(kind, count, defaults)
    _init_bounds(session, defaults)
    session.consecutive_good = 0
    c = session.config
    msgs.append(("send", player, {
        "type": "info",
        "text": (
            f"HARD RESET: {kind} x{count} | "
            f"walk={c['walk_time']:.2f} dec={c['decision_time']:.2f} "
            f"dmg={c['damage']} hp={c['hp']}"
        ),
    }))
