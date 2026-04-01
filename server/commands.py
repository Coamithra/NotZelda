"""Command processing — drains player command queues during game_tick."""

import math
import random

from server.state import game
from server.constants import (
    DEBUG_MODE,
    DIRECTIONS, ROOM_COLS, ROOM_ROWS, DOORWAY_TILES,
    ATTACK_COOLDOWN, TICK_INTERVAL, HEART_DROP_CHANCE, HEART_RESTORE_HP,
    POSITION_UPDATE_RATE, MAX_MOVE_PER_UPDATE,
    COLLISION_GRACE_PERIOD, ITEM_PICKUP_FREEZE_DURATION,
    SEAL_FRAGMENT_HP_BONUS, SWORD_PERP_WIDTH, PLAYER_COLLISION_MARGIN,
)
from server import log
from server.lifecycle import (
    do_room_transition, get_room_monsters,
    broadcast_choir_start, broadcast_choir_stop,
    unlock_room, set_monster_idle,
)
from server.dungeons import get_dungeon_for_room, _run_content_deprecation, start_background_regen, broadcast_to_dungeon
from server.npc_chat import find_adjacent_npc


def process_player_commands(player, now, msgs):
    """Drain and process all queued commands for a player."""
    while player.command_queue:
        cmd_type, data = player.command_queue.popleft()
        if cmd_type == "position_update":
            _process_position_update(player, data, now, msgs)
        elif cmd_type == "face":
            _process_face(player, data, msgs)
        elif cmd_type == "attack":
            _process_attack(player, data, now, msgs)
        elif cmd_type == "chat":
            _process_chat(player, data, msgs)
        elif cmd_type == "unlock_door":
            _process_unlock_door(player, data, msgs)


# ---------------------------------------------------------------------------
# Reconcile helper
# ---------------------------------------------------------------------------

def _send_reconcile(player, msgs, reason=""):
    """Append a reconcile message for the player."""
    a = player.avatar
    if reason:
        log.server(f"[RECONCILE] {player.name}: {reason} -> snap to ({a.x}, {a.y})")
    msgs.append(("send", player, {
        "type": "reconcile",
        "x": a.x,
        "y": a.y,
        "direction": a.direction,
    }))


# ---------------------------------------------------------------------------
# Movement — continuous free movement
# ---------------------------------------------------------------------------

# Exit zone ranges derived from DOORWAY_TILES (± 0.5 for hitbox overlap margin).
# North/south share columns; west/east share rows (standard room layout).
_ns_cols = [c for _, c in DOORWAY_TILES["north"]]
_ew_rows = [r for r, _ in DOORWAY_TILES["west"]]
_EXIT_X_MIN, _EXIT_X_MAX = min(_ns_cols) - 0.5, max(_ns_cols) + 0.5
_EXIT_Y_MIN, _EXIT_Y_MAX = min(_ew_rows) - 0.5, max(_ew_rows) + 0.5


def _check_edge_exit_float(x, y, direction, room):
    """Check if a float position at room edge corresponds to an exit."""
    exits = room["exits"]
    if direction == "up" and y < 0 and "north" in exits and _EXIT_X_MIN <= x <= _EXIT_X_MAX:
        return "north"
    if direction == "down" and y > ROOM_ROWS - 1 and "south" in exits and _EXIT_X_MIN <= x <= _EXIT_X_MAX:
        return "south"
    if direction == "left" and x < 0 and "west" in exits and _EXIT_Y_MIN <= y <= _EXIT_Y_MAX:
        return "west"
    if direction == "right" and x > ROOM_COLS - 1 and "east" in exits and _EXIT_Y_MIN <= y <= _EXIT_Y_MAX:
        return "east"
    return None


def _is_position_walkable(x, y, room):
    """Check if a 1x1 hitbox at (x,y) is walkable.
    Only checks the bottom half (y+0.5 to y+1) so the sprite's top half
    can overlap walls — NES Zelda style, regardless of direction."""
    tilemap = room["tilemap"]
    check_y_start = y + 0.5

    min_tx = int(math.floor(x + 0.001))
    max_tx = int(math.floor(x + 1.0 - 0.001))
    min_ty = int(math.floor(check_y_start + 0.001))
    max_ty = int(math.floor(y + 1.0 - 0.001))

    for ty in range(min_ty, max_ty + 1):
        for tx in range(min_tx, max_tx + 1):
            if tx < 0 or tx >= ROOM_COLS or ty < 0 or ty >= ROOM_ROWS:
                continue  # off-grid handled by edge detection
            if not game.is_walkable_tile(tilemap[ty][tx]):
                return False
    return True


def _process_position_update(player, data, now, msgs):
    """Validate a client position update and relay to other players."""
    a = player.avatar
    new_x = data.get("x")
    new_y = data.get("y")
    direction = data.get("direction", a.direction)

    if player.hp <= 0:
        return
    if not isinstance(new_x, (int, float)) or not isinstance(new_y, (int, float)):
        return

    new_x = float(new_x)
    new_y = float(new_y)

    # Anti-cheat: rate limit
    dt = now - player.last_pos_update_time
    if dt < POSITION_UPDATE_RATE * 0.5:
        return  # silently drop (too fast)

    # Anti-cheat: distance check
    dist = abs(new_x - a.x) + abs(new_y - a.y)
    if dist > MAX_MOVE_PER_UPDATE:
        _send_reconcile(player, msgs, f"too far: dist={dist:.2f} from ({a.x},{a.y}) to ({new_x},{new_y})")
        return

    # Direction
    if direction in DIRECTIONS:
        a.direction = direction
    a.dancing = False

    # Edge detection (room transition)
    room = game.rooms[player.room]
    exit_dir = _check_edge_exit_float(new_x, new_y, direction, room)
    if exit_dir:
        do_room_transition(player, exit_dir, msgs)
        return

    # Stairs — skip if player just spawned on this stair tile
    center_tx, center_ty = int(round(new_x)), int(round(new_y))
    if 0 <= center_tx < ROOM_COLS and 0 <= center_ty < ROOM_ROWS:
        tile = room["tilemap"][center_ty][center_tx]
        on_stair = tile in ("SU", "SD")
        spawn_stair = getattr(a, "spawn_stair", None)
        if on_stair and spawn_stair == (center_tx, center_ty):
            pass  # still on the stair we spawned on — ignore
        else:
            if spawn_stair is not None:
                a.spawn_stair = None  # moved off spawn stair
            if tile == "SU" and "up" in room["exits"]:
                do_room_transition(player, "up", msgs)
                return
            if tile == "SD" and "down" in room["exits"]:
                do_room_transition(player, "down", msgs)
                return

    # Walkability — check all tiles the 1x1 hitbox overlaps
    if not _is_position_walkable(new_x, new_y, room):
        _send_reconcile(player, msgs, f"unwalkable at ({new_x}, {new_y})")
        return

    # Guard collision (AABB)
    for guard in game.guards.get(player.room, []):
        if (new_x < guard["x"] + 1 and new_x + 1 > guard["x"] and
            new_y < guard["y"] + 1 and new_y + 1 > guard["y"]):
            _send_reconcile(player, msgs, f"guard collision at ({new_x}, {new_y}) vs guard ({guard['x']}, {guard['y']})")
            return

    # Accept — update position
    prev_x, prev_y = a.x, a.y
    a.x = new_x
    a.y = new_y
    player.last_pos_update_time = now

    # Relay to other players
    if new_x != a.last_reported_x or new_y != a.last_reported_y:
        msgs.append(("broadcast", player.room, {
            "type": "player_walk_half",
            "name": player.name,
            "x": new_x, "y": new_y,
            "direction": a.direction,
        }, player.ws))
        a.last_reported_x = new_x
        a.last_reported_y = new_y

    # Collision checks (monster contact, hearts, dungeon items, guard proximity)
    _check_position_collisions(player, now, msgs, prev_x, prev_y)


def _get_monster_visual_pos(monster, now):
    """Get interpolated monster position during walks, actual position otherwise."""
    if monster.state == "walking":
        sd = monster.state_data
        elapsed = now - sd.start_time
        progress = min(elapsed / sd.walk_time, 1.0)
        fx = sd.from_x
        fy = sd.from_y
        return fx + (sd.to_x - fx) * progress, fy + (sd.to_y - fy) * progress
    return monster.x, monster.y


def _spawn_treasure_exit(dinst, room_id, msgs):
    """Spawn an exit stairwell in the treasure room when the Seal Fragment is picked up."""
    from server.dungeon_types import DUNGEON_TYPES
    room = game.rooms.get(room_id)
    if not room:
        return
    type_config = DUNGEON_TYPES.get(dinst.dungeon_id, {})
    exit_room = type_config.get("exit_room", "clearing")

    # Place stairs in a corner (top-left walkable area)
    stair_col, stair_row = 2, 2
    tilemap = room.get("tilemap", [])
    if stair_row < len(tilemap) and stair_col < len(tilemap[stair_row]):
        tilemap[stair_row][stair_col] = "SU"
    room.setdefault("exits", {})["up"] = exit_room
    room.setdefault("spawn_points", {})["down"] = (stair_col, stair_row)

    msgs.append(("broadcast", room_id, {
        "type": "tile_change",
        "changes": [[stair_row, stair_col, "SU"]],
    }, None))
    log.debug(f"[DUNGEON] Spawned exit stairwell in {room_id} at ({stair_col},{stair_row})")


def _check_position_collisions(player, now, msgs, prev_player_x=None, prev_player_y=None):
    """Check monster contact, heart pickup, dungeon items at player position."""
    a = player.avatar
    if prev_player_x is None:
        prev_player_x = a.x
    if prev_player_y is None:
        prev_player_y = a.y
    # Monster contact damage (AABB: player hitbox vs monster footprint)
    # Player hitbox is 20% smaller (PLAYER_COLLISION_MARGIN inset per side)
    # monster.x/y is continuously interpolated during walks, so no visual pos needed
    if player.hp > 0:
        m = PLAYER_COLLISION_MARGIN
        overlapping = set()
        for monster in get_room_monsters(player.room):
            if monster.alive and not monster.intangible:
                mx, my = monster.x, monster.y
                if (a.x + m < mx + monster.width and a.x + 1 - m > mx and
                    a.y + m < my + monster.height and a.y + 1 - m > my):
                    mid = id(monster)
                    overlapping.add(mid)
                    if mid not in a.pending_collisions:
                        a.pending_collisions[mid] = {
                            "monster": monster, "room_id": player.room, "time": now,
                            "prev_player_x": prev_player_x, "prev_player_y": prev_player_y,
                            "prev_source_x": mx, "prev_source_y": my,
                        }
        # Clear pending for monsters no longer overlapping
        for mid in list(a.pending_collisions):
            if mid not in overlapping:
                del a.pending_collisions[mid]

    # Heart pickup (proximity)
    if player.hp > 0:
        hearts = game.room_hearts.get(player.room, [])
        for heart in hearts:
            if (abs(a.x - heart["x"]) < 0.75 and
                abs(a.y - heart["y"]) < 0.75 and player.hp < player.max_hp):
                player.hp = min(player.max_hp, player.hp + HEART_RESTORE_HP)
                hearts.remove(heart)
                msgs.append(("send", player, {"type": "hp_update", "hp": player.hp, "max_hp": player.max_hp}))
                msgs.append(("broadcast", player.room, {"type": "heart_collected", "id": heart["id"]}, None))
                break

    # Dungeon item pickup (proximity) — hidden during trap room lockdown
    if player.hp > 0:
        dinst = get_dungeon_for_room(player.room)
        if dinst and player.room not in game.locked_rooms:
            items = dinst.dungeon_items.get(player.room, [])
            for item in list(items):
                if abs(a.x - item["x"]) < 0.75 and abs(a.y - item["y"]) < 0.75:
                    item_type = item["item_type"]
                    items.remove(item)
                    if item_type == "key":
                        # Keys go to the player, not to collected_items
                        player.keys += 1
                        item_name = "Small Key"
                    elif item_type == "spirit_jar":
                        # Spirit jar is per-player (like keys), not shared
                        player.grant_flag("has_spirit_jar")
                        item_name = "Spirit Jar"
                    else:
                        dinst.collected_items.add(item_type)
                        item_name = {"map": "Dungeon Map", "compass": "Compass"}.get(item_type, item_type)
                    msgs.append(("send", player, {
                        "type": "item_obtained",
                        "item_type": item_type,
                        "item_name": item_name,
                    }))
                    msgs.append(("broadcast", player.room, {
                        "type": "item_effect",
                        "item_type": item_type,
                        "item_name": item_name,
                        "name": player.name,
                    }, player.ws))
                    collect_msg = {
                        "type": "dungeon_item_collected",
                        "item_type": item_type,
                        "collected_by": player.name,
                    }
                    # Include position for keys (multiple can exist, need precise removal)
                    if item_type == "key":
                        collect_msg["x"] = item["x"]
                        collect_msg["y"] = item["y"]
                        collect_msg["room_id"] = player.room
                    broadcast_to_dungeon(dinst, collect_msg, msgs)
                    # Freeze monsters in the room during item pickup animation
                    freeze_end = now + ITEM_PICKUP_FREEZE_DURATION
                    existing = game.room_pickup_freeze.get(player.room)
                    if not existing:
                        game.room_pickup_freeze[player.room] = {
                            "start": now, "end": freeze_end,
                        }
                    elif freeze_end > existing["end"]:
                        existing["end"] = freeze_end  # extend without resetting start
                    # Clear pending contact collisions (grace periods go stale during freeze)
                    for p in game.players.values():
                        if p.room == player.room and p.avatar:
                            p.avatar.pending_collisions.clear()
                    msgs.append(("broadcast", player.room, {
                        "type": "room_freeze",
                        "duration": ITEM_PICKUP_FREEZE_DURATION,
                    }, None))
                    break

    # Per-player dungeon items (lantern, seal_fragment) — stay on ground for others
    if player.hp > 0:
        dinst = get_dungeon_for_room(player.room)
        if dinst and player.room not in game.locked_rooms:
            pp_items = dinst.per_player_items.get(player.room, [])
            for item in pp_items:
                if abs(a.x - item["x"]) < 0.75 and abs(a.y - item["y"]) < 0.75:
                    item_type = item["item_type"]
                    flag_name = f"has_{item_type}"
                    if player.has_flag(flag_name):
                        continue  # already collected by this player
                    player.grant_flag(flag_name)
                    if item_type == "lantern":
                        item_name = "Magic Lantern"
                    elif item_type == "seal_fragment":
                        item_name = "Seal Fragment"
                        # +1 heart container
                        player.max_hp += SEAL_FRAGMENT_HP_BONUS
                        player.hp = player.max_hp
                        msgs.append(("send", player, {
                            "type": "hp_update", "hp": player.hp, "max_hp": player.max_hp,
                        }))
                        # Spawn exit stairwell in treasure room
                        _spawn_treasure_exit(dinst, player.room, msgs)
                    else:
                        item_name = item_type.replace("_", " ").title()
                    msgs.append(("send", player, {
                        "type": "item_obtained",
                        "item_type": item_type,
                        "item_name": item_name,
                    }))
                    msgs.append(("broadcast", player.room, {
                        "type": "item_effect",
                        "item_type": item_type,
                        "item_name": item_name,
                        "name": player.name,
                    }, player.ws))
                    # Freeze monsters during pickup animation
                    freeze_end = now + ITEM_PICKUP_FREEZE_DURATION
                    existing = game.room_pickup_freeze.get(player.room)
                    if not existing:
                        game.room_pickup_freeze[player.room] = {
                            "start": now, "end": freeze_end,
                        }
                    elif freeze_end > existing["end"]:
                        existing["end"] = freeze_end
                    for p in game.players.values():
                        if p.room == player.room and p.avatar:
                            p.avatar.pending_collisions.clear()
                    msgs.append(("broadcast", player.room, {
                        "type": "room_freeze",
                        "duration": ITEM_PICKUP_FREEZE_DURATION,
                    }, None))
                    break

    # Guard proximity chat (float-aware)
    if player.hp > 0:
        _check_guard_proximity_sync(player, now, msgs)


def _check_guard_proximity_sync(player, now, msgs):
    """If near a guard and not yet greeted this visit, queue guard dialog."""
    from server.npc_chat import is_npc_thinking
    a = player.avatar
    for guard in game.guards.get(player.room, []):
        dx = abs(a.x - guard["x"])
        dy = abs(a.y - guard["y"])
        if dx + dy <= 1.5:
            # Skip proximity dialog if the NPC is still generating an LLM response
            if is_npc_thinking(player.name, guard["name"]):
                continue
            key = f"{player.room}:{guard['name']}:{guard['x']},{guard['y']}"
            if key not in player.guard_greeted:
                player.guard_greeted.add(key)
                player.guard_cooldowns[key] = now  # keep timestamp for LLM seeding
                msgs.append(("guard_chat", player, guard))


def _process_face(player, data, msgs):
    """Handle face direction change."""
    a = player.avatar
    direction = data.get("direction", "")
    if direction in DIRECTIONS:
        a.direction = direction
        a.dancing = False
        msgs.append(("broadcast", player.room, {
            "type": "player_faced",
            "name": player.name,
            "direction": direction,
        }, player.ws))


# ---------------------------------------------------------------------------
# Attack
# ---------------------------------------------------------------------------

def sword_hitbox(px, py, direction):
    """Compute sword AABB from player position + direction. Single source of truth."""
    dx, dy = DIRECTIONS.get(direction, (0, 0))
    # Forward: 0.25 back into player + 0.75 forward (1.0 total along attack axis)
    # Perpendicular: SWORD_PERP_WIDTH centered on player body
    perp_off = (1.0 - SWORD_PERP_WIDTH) / 2  # centering offset
    return (
        px + (0.75 if dx > 0 else -0.75 if dx < 0 else perp_off),
        py + (0.75 if dy > 0 else -0.75 if dy < 0 else perp_off),
        1.0 if dx != 0 else SWORD_PERP_WIDTH,
        SWORD_PERP_WIDTH if dx != 0 else 1.0,
    )


def sword_hit_scan(player, direction, room_id, hit_monsters, now, msgs, *, anchor_x=None, anchor_y=None):
    """Check sword AABB against all monsters in the room, damaging new targets.

    Called on the initial attack tick and on each subsequent tick while the
    sword is active.  ``hit_monsters`` is a *set* of monster object IDs already
    damaged by this swing — updated in-place so each monster is only hit once.

    If ``anchor_x``/``anchor_y`` are provided, the hitbox is computed from that
    position (client-supplied) instead of the server-side avatar position.
    """
    a = player.avatar
    if a is None:
        return
    px = anchor_x if anchor_x is not None else a.x
    py = anchor_y if anchor_y is not None else a.y
    dx, dy = DIRECTIONS.get(direction, (0, 0))
    sword_x, sword_y, sword_w, sword_h = sword_hitbox(px, py, direction)
    for i, monster in enumerate(get_room_monsters(room_id)):
        mid = id(monster)
        if mid in hit_monsters:
            continue
        if monster.alive and not monster.intangible and (
            sword_x < monster.x + monster.width and sword_x + sword_w > monster.x and
            sword_y < monster.y + monster.height and sword_y + sword_h > monster.y):
            hit_monsters.add(mid)
            monster.hp -= 1
            # Knockback: push surviving non-boss monster 1 tile in attack direction
            knock_x = None
            knock_y = None
            if monster.hp > 0 and monster.knockbackable:
                room = game.rooms.get(room_id)
                if room:
                    # Knockback 1 tile, snap to integer grid
                    kx = round(monster.x + dx)
                    ky = round(monster.y + dy)
                    can_knock = True
                    # Check all tiles covered by the knocked-back footprint
                    min_tx = math.floor(kx)
                    max_tx = math.ceil(kx + monster.width) - 1
                    min_ty = math.floor(ky)
                    max_ty = math.ceil(ky + monster.height) - 1
                    for cy in range(min_ty, max_ty + 1):
                        for cx in range(min_tx, max_tx + 1):
                            if cx < 0 or cx >= ROOM_COLS or cy < 0 or cy >= ROOM_ROWS:
                                can_knock = False
                            elif not _is_position_walkable(cx, cy, room):
                                can_knock = False
                    if can_knock:
                        monster.x = kx
                        monster.y = ky
                        knock_x = kx
                        knock_y = ky
                        monster.move_seq += 1
                    elif monster.state == "walking":
                        # Can't knock back but snap from fractional walk coords
                        monster.x = round(monster.x)
                        monster.y = round(monster.y)
                        monster.move_seq += 1
            # Interrupt current action on hit — but non-knockbackable monsters
            # (bosses, heavy monsters) continue their behavior uninterrupted
            if monster.hp > 0 and monster.knockbackable:
                if monster.state != "idle":
                    set_monster_idle(monster, room_id, i, msgs)
                else:
                    monster.last_action_time = now
            # Boss engagement — start choir overlay if boss survives this hit
            dinst = get_dungeon_for_room(room_id)
            is_boss = monster.is_boss and dinst is not None
            if (monster.hp > 0
                    and is_boss
                    and dinst
                    and not dinst.boss_engaged):
                dinst.boss_engaged = True
                broadcast_choir_start(room_id, msgs)
            if monster.hp <= 0:
                set_monster_idle(monster, room_id, i, msgs)
                monster.alive = False
                from server.quests import quest_event
                quest_event("monster_killed", player, msgs,
                            kind=monster.kind, room=room_id)
                msg_killed = {
                    "type": "monster_killed",
                    "id": i,
                    "x": monster.x,
                    "y": monster.y,
                }
                if knock_x is not None:
                    msg_killed["knock_x"] = knock_x
                    msg_killed["knock_y"] = knock_y
                msgs.append(("broadcast", room_id, msg_killed, None))
                # Kill message (chat log only, no popup)
                monster_name = monster.kind.replace("_", " ").title()
                msgs.append(("send", player, {
                    "type": "log", "text": f"You defeated the {monster_name}!",
                }))
                msgs.append(("broadcast", room_id, {
                    "type": "log", "text": f"{player.name} defeated the {monster_name}!",
                }, player.ws))
                # Heart drop (disabled in gauntlet for clean damage tracking)
                if not room_id.startswith("gauntlet_") and random.random() < HEART_DROP_CHANCE:
                    hid = game.next_heart_id
                    game.next_heart_id += 1
                    heart = {"x": monster.x, "y": monster.y, "id": hid}
                    game.room_hearts.setdefault(room_id, []).append(heart)
                    msgs.append(("broadcast", room_id, {
                        "type": "heart_spawned",
                        "id": hid,
                        "x": monster.x,
                        "y": monster.y,
                    }, None))
                # Unlock trap room doors if all monsters dead (dungeon or overworld)
                alive = [m for m in game.room_monsters[room_id] if m.alive]
                if not alive:
                    if room_id in game.locked_rooms:
                        unlock_room(room_id, msgs)
                    # Gauntlet: log results + create next room
                    if room_id.startswith("gauntlet_"):
                        from server.gauntlet import on_gauntlet_room_cleared
                        on_gauntlet_room_cleared(player, room_id, msgs)
                # Mark dungeon room as cleared if all monsters dead
                if dinst and not alive:
                    dinst.cleared_rooms.add(room_id)
                    # Boss defeated — silence music + stop choir
                    if is_boss:
                        log.debug(f"[BOSS] Boss defeated in {room_id}, silencing music")
                        dinst.boss_engaged = False
                        msgs.append(("broadcast", room_id, {
                            "type": "music_change", "music": None,
                        }, None))
                        broadcast_choir_stop(room_id, msgs)
                        # Spawn seal fragment in sanctum (center of room)
                        sanctum_room_id = f"{dinst.dungeon_id}_{dinst.sanctum_cell[0]}_{dinst.sanctum_cell[1]}"
                        # Ensure sanctum room is resolved (it's lazily loaded)
                        if sanctum_room_id not in game.rooms:
                            from server.dungeons import resolve_dungeon_room
                            resolve_dungeon_room(dinst, dinst.sanctum_cell)
                        dinst.per_player_items.setdefault(sanctum_room_id, []).append(
                            {"x": 7, "y": 5, "item_type": "seal_fragment"}
                        )
                        log.debug(f"[BOSS] Seal Fragment spawned in {sanctum_room_id} at (7,5)")
            else:
                msg_hit = {
                    "type": "monster_hit",
                    "id": i,
                    "x": monster.x,
                    "y": monster.y,
                    "hp": monster.hp,
                    "seq": monster.move_seq,
                }
                if knock_x is not None:
                    msg_hit["knock_x"] = knock_x
                    msg_hit["knock_y"] = knock_y
                msgs.append(("broadcast", room_id, msg_hit, None))


def _process_attack(player, data, now, msgs):
    """Handle a player's sword attack — initiate swing + first hit scan."""
    if player.hp <= 0:
        return
    if not player.has_flag("has_sword"):
        msgs.append(("send", player, {"type": "info", "text": "You don't have a weapon."}))
        return
    if now - player.last_attack_time < ATTACK_COOLDOWN - TICK_INTERVAL:
        return
    player.last_attack_time = now
    a = player.avatar
    a.dancing = False

    # Use client-supplied direction so quick turn+attack works without waiting
    # for the server to process the direction change first
    direction = data.get("direction")
    if direction in DIRECTIONS:
        a.direction = direction

    msgs.append(("broadcast", player.room, {
        "type": "attack",
        "name": player.name,
        "direction": a.direction,
    }, None))

    # Use client-supplied position for precise hitbox placement (the server
    # may not have the latest position yet)
    anchor_x = data.get("x")
    anchor_y = data.get("y")
    if anchor_x is not None and anchor_y is not None:
        anchor_x = float(anchor_x)
        anchor_y = float(anchor_y)
    else:
        anchor_x = a.x
        anchor_y = a.y

    # Set up active attack for multi-frame hit detection
    hit_monsters = set()
    player.active_attack = {
        "direction": a.direction,
        "start_time": now,
        "room": player.room,
        "hit_monsters": hit_monsters,
        "anchor_x": anchor_x,
        "anchor_y": anchor_y,
    }

    # First hit scan — instant hits still register with zero delay
    sword_hit_scan(player, a.direction, player.room, hit_monsters, now, msgs,
                   anchor_x=anchor_x, anchor_y=anchor_y)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

def _process_chat(player, data, msgs):
    """Handle chat message — slash commands and normal chat."""
    text = data.get("text", "").strip()
    if not text:
        return

    if text.startswith("/"):
        _process_slash_command(player, text, msgs)
        return

    # Normal chat — broadcast to room
    room_name = game.rooms[player.room]["name"]
    log.event("CHAT", f"{player.name} ({room_name}): {text}")
    msgs.append(("broadcast", player.room, {
        "type": "chat",
        "from": player.name,
        "text": text,
    }, None))

    # Check if player is adjacent to an NPC — trigger LLM conversation
    guard = find_adjacent_npc(player.room, player.avatar)
    if guard:
        msgs.append(("npc_chat", player, guard, text))


def _cmd_who(player, args, msgs):
    lines = ["Players online:"]
    for p in game.players.values():
        room_name = game.rooms[p.room]["name"]
        lines.append(f"  {p.name} — {p.description} (in {room_name})")
    msgs.append(("send", player, {"type": "info", "text": "\n".join(lines)}))


def _cmd_help(player, args, msgs):
    msgs.append(("send", player, {"type": "info", "text": (
        "Arrow keys / WASD — Move\n"
        "Space — Attack\n"
        "Enter — Open chat\n"
        "Escape — Close chat\n"
        "M — Toggle music\n"
        "/who — List online players\n"
        "/dance — Bust a move\n"
        "/help — Show this message"
    )}))


def _cmd_dance(player, args, msgs):
    player.avatar.dancing = True
    msgs.append(("broadcast", player.room, {
        "type": "dance", "name": player.name,
    }, None))


def _cmd_me(player, args, msgs):
    if args:
        msgs.append(("broadcast", player.room, {
            "type": "chat", "from": player.name, "text": f"*{args}*",
        }, None))


def _cmd_cheat(player, args, msgs):
    if player.has_flag("invulnerable"):
        player.flags.discard("invulnerable")
        msgs.append(("send", player, {"type": "info", "text": "Cheat mode off: vulnerable again"}))
    else:
        player.grant_flag("has_sword")
        player.grant_flag("has_lantern")
        player.grant_flag("invulnerable")
        player.hp = player.max_hp
        msgs.append(("send", player, {"type": "item_obtained", "item_type": "sword", "item_name": "Sword"}))
        msgs.append(("send", player, {"type": "item_obtained", "item_type": "lantern", "item_name": "Magic Lantern"}))
        msgs.append(("send", player, {"type": "hp_update", "hp": player.hp, "max_hp": player.max_hp}))
        msgs.append(("send", player, {"type": "info", "text": "Cheat mode: sword + lantern + invulnerability"}))


def _cmd_lantern(player, args, msgs):
    if player.has_flag("has_lantern"):
        player.flags.discard("has_lantern")
        msgs.append(("send", player, {"type": "info", "text": "Lantern removed"}))
    else:
        player.grant_flag("has_lantern")
        msgs.append(("send", player, {"type": "item_obtained", "item_type": "lantern", "item_name": "Magic Lantern"}))
        msgs.append(("send", player, {"type": "info", "text": "Lantern granted"}))


def _cmd_debug_spawn(player, args, msgs):
    msgs.append(("debug_spawn", player, args))


def _cmd_deprecate(player, args, msgs):
    for _tid in list(game.content_libraries.keys()):
        _run_content_deprecation(_tid)
    msgs.append(("send", player, {"type": "info", "text": "Forced deprecation pass — see ~ debug log"}))


def _cmd_regen(player, args, msgs):
    regen_inst = get_dungeon_for_room(player.room)
    regen_type = regen_inst.dungeon_id if regen_inst else "d1"
    regen_libs = game.content_libraries.get(regen_type, {})
    regen_room_lib = regen_libs.get("rooms")
    count = int(args) if args and args.isdigit() else (regen_room_lib.placeholder_count if regen_room_lib else 0)
    if count <= 0:
        msgs.append(("send", player, {"type": "info", "text": f"No {regen_type} room library slots to fill"}))
    else:
        start_background_regen(count, regen_type)
        msgs.append(("send", player, {"type": "info", "text": f"Regen started: {count} {regen_type} room(s) — see ~ debug log"}))


def _cmd_viewserver(player, args, msgs):
    enabled = not getattr(player, '_viewserver', False)
    player._viewserver = enabled
    msgs.append(("send", player, {"type": "viewserver_toggle", "enabled": enabled}))


def _cmd_choir(player, args, msgs):
    debug_on = getattr(player, '_debug_choir', False)
    choir_inst = get_dungeon_for_room(player.room)
    if debug_on:
        player._debug_choir = False
        if choir_inst:
            choir_inst.boss_engaged = False
        msgs.append(("send", player, {"type": "boss_choir_stop"}))
        msgs.append(("send", player, {"type": "info", "text": "Choir overlay OFF"}))
    else:
        dist = int(args) if args and args.isdigit() else 2
        player._debug_choir = True
        if choir_inst:
            choir_inst.boss_engaged = True
        msgs.append(("send", player, {"type": "boss_choir_start", "distance": dist}))
        msgs.append(("send", player, {"type": "info", "text": f"Choir overlay ON (distance={dist})"}))


def _cmd_key(player, args, msgs):
    player.keys += 1
    msgs.append(("send", player, {"type": "key_update", "keys": player.keys}))
    msgs.append(("send", player, {"type": "info", "text": f"Granted key (total: {player.keys})"}))


def _cmd_keylayout(player, args, msgs):
    from collections import Counter
    dinst = get_dungeon_for_room(player.room)
    if not dinst or not dinst.zone_cells:
        msgs.append(("send", player, {"type": "info", "text": "Not in a dungeon with locked doors"}))
    else:
        key_counts = Counter(dinst.key_cells)
        zone_data = []
        for zid, cells in dinst.zone_cells.items():
            keys_in_zone = sum(key_counts.get(c, 0) for c in cells)
            zone_data.append({
                "zone_id": zid,
                "cells": [[c[0], c[1]] for c in cells],
                "keys": keys_in_zone,
            })
        msgs.append(("send", player, {
            "type": "keylayout",
            "zones": zone_data,
        }))
        msgs.append(("send", player, {"type": "info",
            "text": f"Key layout: {len(dinst.zone_cells)} zones, "
                    f"{len(dinst.locked_doors)} doors, {len(dinst.key_cells)} keys"}))


# ---------------------------------------------------------------------------
# Command registry
# ---------------------------------------------------------------------------

SLASH_COMMANDS = {
    "who": _cmd_who,
    "help": _cmd_help,
    "dance": _cmd_dance,
    "me": _cmd_me,
}

DEBUG_COMMANDS = {
    "cheat": _cmd_cheat,
    "lantern": _cmd_lantern,
    "debug_spawn": _cmd_debug_spawn,
    "deprecate": _cmd_deprecate,
    "regen": _cmd_regen,
    "viewserver": _cmd_viewserver,
    "choir": _cmd_choir,
    "key": _cmd_key,
    "keylayout": _cmd_keylayout,
    "gauntlet": lambda p, a, m: __import__("server.gauntlet", fromlist=["cmd_gauntlet"]).cmd_gauntlet(p, a, m),
    "gt": lambda p, a, m: __import__("server.gauntlet", fromlist=["cmd_gt"]).cmd_gt(p, a, m),
}


def _process_slash_command(player, text, msgs):
    """Handle a slash command via registry lookup."""
    parts = text[1:].split(None, 1)
    cmd = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    handler = SLASH_COMMANDS.get(cmd)
    if not handler and DEBUG_MODE:
        handler = DEBUG_COMMANDS.get(cmd)
    if handler:
        handler(player, args, msgs)
    else:
        msgs.append(("send", player, {"type": "info", "text": "Unknown command. Try /help"}))


# ---------------------------------------------------------------------------
# Locked door unlock
# ---------------------------------------------------------------------------

_UNLOCK_DIR_OFFSETS = {"north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0)}
_OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}


def _process_unlock_door(player, data, msgs):
    """Handle player walking into a locked door — consume key and open it."""
    if player.keys <= 0 or player.hp <= 0:
        return
    direction = data.get("direction")
    if direction not in DOORWAY_TILES:
        return

    dinst = get_dungeon_for_room(player.room)
    if not dinst:
        return

    # Map room_id back to cell
    cell = _room_id_to_cell(player.room, dinst)
    if not cell:
        return

    # Check if there's a locked door in this direction
    dc, dr = _UNLOCK_DIR_OFFSETS[direction]
    neighbor = (cell[0] + dc, cell[1] + dr)
    edge = frozenset((cell, neighbor))
    if edge not in dinst.locked_doors or edge in dinst.unlocked_doors:
        return

    # Consume key and unlock
    player.keys -= 1
    dinst.unlocked_doors.add(edge)

    # Edge data for client minimap update
    unlocked_edge = [list(cell), list(neighbor)]

    # Restore tiles in this room
    _unlock_locked_door(player.room, direction, dinst, msgs, unlocked_edge)

    # Restore tiles in neighbor room (if resolved)
    neighbor_room_id = f"{dinst.dungeon_id}_{neighbor[0]}_{neighbor[1]}"
    opposite = _OPPOSITE[direction]
    if neighbor_room_id in game.rooms:
        _unlock_locked_door(neighbor_room_id, opposite, dinst, msgs, unlocked_edge)

    # Send key count update
    msgs.append(("send", player, {"type": "key_update", "keys": player.keys}))
    msgs.append(("send", player, {"type": "info", "text": "Used a Small Key!"}))

    log.debug(f"[DUNGEON] {player.name} unlocked door {direction} in {player.room} "
              f"(keys remaining: {player.keys})")


def _room_id_to_cell(room_id, dinst):
    """Convert a room_id like 'd1_3_2' back to a (col, row) cell tuple."""
    for cell, rid in dinst.room_map.items():
        if rid == room_id:
            return cell
    return None


def _unlock_locked_door(room_id, direction, dinst, msgs, unlocked_edge=None):
    """Restore original tiles for a locked doorway in one room."""
    room = game.rooms.get(room_id)
    if not room:
        return
    tilemap = room["tilemap"]
    originals = dinst.locked_door_originals.get(room_id, {})
    tile_changes = []
    for r, c in DOORWAY_TILES[direction]:
        original = originals.get((r, c), "DF")
        tilemap[r][c] = original
        tile_changes.append([r, c, original])
    if tile_changes:
        unlock_msg = {
            "type": "doors_unlocked",
            "tile_changes": tile_changes,
        }
        if unlocked_edge:
            unlock_msg["unlocked_edge"] = unlocked_edge
        msgs.append(("broadcast", room_id, unlock_msg, None))
