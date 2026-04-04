"""Room file loading — reads .room files from disk into game state."""

from pathlib import Path

from server import log
from server.state import game
from server.constants import EDGE_SPAWN_POINTS, DEFAULT_SPAWN, DEBUG_MODE


def load_room_files(directory: str = "rooms"):
    """Load all .room files and merge into game.rooms, game.guards, game.monster_templates."""
    rooms_dir = Path(__file__).parent.parent / directory
    if not rooms_dir.exists():
        log.debug(f"[ROOMS] No '{directory}/' directory found, skipping room file loading")
        return

    count = 0
    for room_file in sorted(rooms_dir.glob("*.room")):
        room_id = room_file.stem  # e.g. "ow_0_7" from "ow_0_7.room"
        try:
            text = room_file.read_text(encoding="utf-8")
        except Exception as e:
            log.debug(f"[ROOMS] Error reading {room_file.name}: {e}")
            continue

        parts = text.split("---")
        if len(parts) < 2:
            log.debug(f"[ROOMS] Skipping {room_file.name}: missing --- separator")
            continue

        # Parse header
        header = {}
        for line in parts[0].strip().splitlines():
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                header[key.strip()] = val.strip()

        # Parse exits (supports :debug[:replacement_tile] suffix)
        exits = {}
        debug_stair_replacements = {}  # direction -> tile to replace SD/SU with
        if "exits" in header:
            for pair in header["exits"].split():
                if "=" in pair:
                    direction, target = pair.split("=", 1)
                    # Check for :debug suffix — e.g. down=d1_entrance:debug:GR
                    if ":debug" in target:
                        parts_exit = target.split(":")
                        target = parts_exit[0]
                        if not DEBUG_MODE:
                            # Skip this exit in release mode
                            replacement = parts_exit[2] if len(parts_exit) > 2 else "GR"
                            debug_stair_replacements[direction] = replacement
                            continue
                    exits[direction] = target

        # Parse tilemap
        tilemap_text = parts[1].strip()
        tilemap = []
        for row_line in tilemap_text.splitlines():
            row_line = row_line.strip()
            if not row_line:
                continue
            codes = row_line.split()
            row = list(codes)
            # Pad or trim to 15 columns
            while len(row) < 15:
                row.append("GR")
            row = row[:15]
            tilemap.append(row)
        # Pad or trim to 11 rows
        while len(tilemap) < 11:
            tilemap.append(["GR"] * 15)
        tilemap = tilemap[:11]

        # Build spawn points from exits
        spawn_points = {"default": DEFAULT_SPAWN}
        for direction, pos in EDGE_SPAWN_POINTS.items():
            if direction in exits:
                spawn_points[direction] = pos
        # Replace debug-only stair tiles in release mode
        if "down" in debug_stair_replacements:
            repl = debug_stair_replacements["down"]
            for ry, row in enumerate(tilemap):
                for rx, tile in enumerate(row):
                    if tile == "SD":
                        tilemap[ry][rx] = repl
        if "up" in debug_stair_replacements:
            repl = debug_stair_replacements["up"]
            for ry, row in enumerate(tilemap):
                for rx, tile in enumerate(row):
                    if tile == "SU":
                        tilemap[ry][rx] = repl

        # Scan for stairs and portal tiles
        su_pos = None
        sd_pos = None
        po_pos = None
        for ry, row in enumerate(tilemap):
            for rx, tile in enumerate(row):
                if tile == "SU" and su_pos is None:
                    su_pos = (rx, ry)
                elif tile == "SD" and sd_pos is None:
                    sd_pos = (rx, ry)
                elif tile == "PO" and po_pos is None:
                    po_pos = (rx, ry)
        if su_pos:
            spawn_points["down"] = su_pos   # entering from above -> land at stairs up
        if sd_pos:
            spawn_points["up"] = sd_pos     # entering from below -> land at stairs down
        if po_pos:
            spawn_points["portal"] = po_pos  # entering via portal -> land on portal tile

        room = {
            "name": header.get("name", room_id),
            "exits": exits,
            "tilemap": tilemap,
            "spawn_points": spawn_points,
            "biome": header.get("biome", "plains"),
            "music": header.get("music", "overworld"),
        }
        if header.get("locked", "").lower() == "true":
            room["locked"] = True

        # Dark room support — float opacity (e.g. "0.5") or boolean ("true" = 1.0)
        dark_val = header.get("dark", "")
        if dark_val:
            try:
                room["dark"] = float(dark_val)
            except ValueError:
                if dark_val.lower() == "true":
                    room["dark"] = True

        # Scan for bright tiles → light sources (only if room is dark)
        if room.get("dark"):
            light_sources = []
            for r_idx, row in enumerate(tilemap):
                for c_idx, tile_code in enumerate(row):
                    tile_props = game.custom_tile_recipes.get(tile_code, {})
                    if tile_props.get("bright"):
                        light_sources.append([c_idx, r_idx])
            if light_sources:
                room["light_sources"] = light_sources

        # Parse optional 4th section — reveal tilemap (hidden terrain under water)
        if len(parts) >= 4:
            reveal_text = parts[3].strip()
            reveal_tilemap = []
            for row_line in reveal_text.splitlines():
                row_line = row_line.strip()
                if not row_line:
                    continue
                codes = row_line.split()
                row = list(codes)
                while len(row) < 15:
                    row.append("GR")
                row = row[:15]
                reveal_tilemap.append(row)
            while len(reveal_tilemap) < 11:
                reveal_tilemap.append(["GR"] * 15)
            reveal_tilemap = reveal_tilemap[:11]
            room["reveal_tilemap"] = reveal_tilemap

            # Scan reveal tilemap for stair/portal spawn points (hidden stairs/portals)
            for ry, r in enumerate(reveal_tilemap):
                for rx, tile in enumerate(r):
                    if tile == "SU" and su_pos is None:
                        su_pos = (rx, ry)
                        spawn_points["down"] = su_pos
                    elif tile == "SD" and sd_pos is None:
                        sd_pos = (rx, ry)
                        spawn_points["up"] = sd_pos
                    elif tile == "PO" and po_pos is None:
                        po_pos = (rx, ry)
                        spawn_points["portal"] = po_pos

        game.rooms[room_id] = room

        # Parse entity section (after second ---)
        if len(parts) >= 3:
            entity_text = parts[2].strip()
            for line in entity_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                tokens = line.split()
                if tokens[0] == "npc" and len(tokens) >= 5:
                    npc_name = tokens[1].replace("_", " ")
                    npc_x = int(tokens[2])
                    npc_y = int(tokens[3])
                    npc_sprite = tokens[4]
                    npc_rest = " ".join(tokens[5:]) if len(tokens) > 5 else ""
                    # Split on | to separate: dialog | personality | gift
                    pipe_parts = npc_rest.split("|")
                    npc_dialog = pipe_parts[0].strip() if len(pipe_parts) > 0 else ""
                    npc_personality = pipe_parts[1].strip() if len(pipe_parts) > 1 else ""
                    npc_gift = None
                    if len(pipe_parts) > 2:
                        gift_str = pipe_parts[2].strip()
                        # Format: Display Name:condition text
                        gift_parts = gift_str.split(":", 1)
                        if len(gift_parts) == 2:
                            display_name = gift_parts[0].strip()
                            # Auto-generate flag: gift_{room}_{npc}_{item}
                            norm = lambda s: s.lower().replace(" ", "_")
                            flag = f"gift_{norm(room_id)}_{norm(npc_name)}_{norm(display_name)}"
                            npc_gift = {
                                "flag": flag,
                                "display_name": display_name,
                                "condition": gift_parts[1].strip(),
                            }
                    if room_id not in game.guards:
                        game.guards[room_id] = []
                    guard_data = {
                        "name": npc_name, "x": npc_x, "y": npc_y,
                        "sprite": npc_sprite, "dialog": npc_dialog,
                        "personality": npc_personality,
                    }
                    if npc_gift:
                        guard_data["gift"] = npc_gift
                    game.guards[room_id].append(guard_data)
                elif tokens[0] == "monster" and len(tokens) >= 4:
                    kind = tokens[1]
                    mx = int(tokens[2])
                    my = int(tokens[3])
                    # Optional "debug" flag — monster only spawns in DEBUG_MODE
                    if len(tokens) >= 5 and tokens[4] == "debug":
                        if not DEBUG_MODE:
                            continue
                    if room_id not in game.monster_templates:
                        game.monster_templates[room_id] = []
                    game.monster_templates[room_id].append({"kind": kind, "x": mx, "y": my})

        count += 1

    log.debug(f"[ROOMS] Loaded {count} room files from {directory}/")
    log.debug(f"[ROOMS] Total rooms: {len(game.rooms)}")


def load_dungeon_templates(directory: str = "rooms/dungeon1", type_id: str = "d1"):
    """Load dungeon room templates from .room files for a dungeon type (no exits parsed)."""
    rooms_dir = Path(__file__).parent.parent / directory
    if not rooms_dir.exists():
        log.debug(f"[DUNGEON] No '{directory}/' directory found, skipping")
        return

    if type_id not in game.dungeon_templates:
        game.dungeon_templates[type_id] = {}

    count = 0
    for room_file in sorted(rooms_dir.glob("*.room")):
        template_id = room_file.stem
        try:
            text = room_file.read_text(encoding="utf-8")
        except Exception as e:
            log.debug(f"[DUNGEON] Error reading {room_file.name}: {e}")
            continue

        parts = text.split("---")
        if len(parts) < 2:
            continue

        header = {}
        for line in parts[0].strip().splitlines():
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                header[key.strip()] = val.strip()

        tilemap_text = parts[1].strip()
        tilemap = []
        for row_line in tilemap_text.splitlines():
            row_line = row_line.strip()
            if not row_line:
                continue
            codes = row_line.split()
            row = list(codes)
            while len(row) < 15:
                row.append("DF")
            row = row[:15]
            tilemap.append(row)
        while len(tilemap) < 11:
            tilemap.append(["DF"] * 15)
        tilemap = tilemap[:11]

        guards = []
        monsters = []
        monster_groups = []
        if len(parts) >= 3:
            for line in parts[2].strip().splitlines():
                line = line.strip()
                if not line:
                    continue
                tokens = line.split()
                if tokens[0] == "npc" and len(tokens) >= 5:
                    rest = " ".join(tokens[5:]) if len(tokens) > 5 else ""
                    if "|" in rest:
                        dlg, pers = rest.split("|", 1)
                        dlg, pers = dlg.strip(), pers.strip()
                    else:
                        dlg, pers = rest, ""
                    guards.append({
                        "name": tokens[1].replace("_", " "),
                        "x": int(tokens[2]), "y": int(tokens[3]),
                        "sprite": tokens[4],
                        "dialog": dlg, "personality": pers,
                    })
                elif tokens[0] == "monsters" and len(tokens) >= 3:
                    # Dynamic group: monsters <kind> <pack_fraction>
                    monster_groups.append({"kind": tokens[1], "count": float(tokens[2])})
                elif tokens[0] == "monster" and len(tokens) >= 4:
                    monsters.append({"kind": tokens[1], "x": int(tokens[2]), "y": int(tokens[3])})

        template_data = {
            "name": header.get("name", template_id),
            "tilemap": tilemap,
            "guards": guards,
            "monsters": monsters,
        }
        if monster_groups:
            template_data["monster_groups"] = monster_groups
        game.dungeon_templates[type_id][template_id] = template_data
        count += 1

    log.debug(f"[DUNGEON] Loaded {count} dungeon templates from {directory}/ for type '{type_id}'")
