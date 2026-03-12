"""Room file loading — reads .room files from disk into game state."""

from pathlib import Path

from server.state import game
from server.constants import (
    TILE_CODES, GRASS, STAIRS_UP, STAIRS_DOWN, DUNGEON_FLOOR,
    EDGE_SPAWN_POINTS, DEFAULT_SPAWN,
)


def load_room_files(directory: str = "rooms"):
    """Load all .room files and merge into game.rooms, game.guards, game.monster_templates."""
    rooms_dir = Path(__file__).parent.parent / directory
    if not rooms_dir.exists():
        print(f"[ROOMS] No '{directory}/' directory found, skipping room file loading")
        return

    count = 0
    for room_file in sorted(rooms_dir.glob("*.room")):
        room_id = room_file.stem  # e.g. "ow_0_7" from "ow_0_7.room"
        try:
            text = room_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[ROOMS] Error reading {room_file.name}: {e}")
            continue

        parts = text.split("---")
        if len(parts) < 2:
            print(f"[ROOMS] Skipping {room_file.name}: missing --- separator")
            continue

        # Parse header
        header = {}
        for line in parts[0].strip().splitlines():
            line = line.strip()
            if ":" in line:
                key, val = line.split(":", 1)
                header[key.strip()] = val.strip()

        # Parse exits
        exits = {}
        if "exits" in header:
            for pair in header["exits"].split():
                if "=" in pair:
                    direction, target = pair.split("=", 1)
                    exits[direction] = target

        # Parse tilemap
        tilemap_text = parts[1].strip()
        tilemap = []
        for row_line in tilemap_text.splitlines():
            row_line = row_line.strip()
            if not row_line:
                continue
            codes = row_line.split()
            row = [TILE_CODES.get(code, GRASS) for code in codes]
            # Pad or trim to 15 columns
            while len(row) < 15:
                row.append(GRASS)
            row = row[:15]
            tilemap.append(row)
        # Pad or trim to 11 rows
        while len(tilemap) < 11:
            tilemap.append([GRASS] * 15)
        tilemap = tilemap[:11]

        # Build spawn points from exits
        spawn_points = {"default": DEFAULT_SPAWN}
        for direction, pos in EDGE_SPAWN_POINTS.items():
            if direction in exits:
                spawn_points[direction] = pos
        # Scan for stairs tiles
        su_pos = None
        sd_pos = None
        for ry, row in enumerate(tilemap):
            for rx, tile in enumerate(row):
                if tile == STAIRS_UP and su_pos is None:
                    su_pos = (rx, ry)
                elif tile == STAIRS_DOWN and sd_pos is None:
                    sd_pos = (rx, ry)
        if su_pos:
            spawn_points["down"] = su_pos   # entering from above -> land at stairs up
        if sd_pos:
            spawn_points["up"] = sd_pos     # entering from below -> land at stairs down

        room = {
            "name": header.get("name", room_id),
            "exits": exits,
            "tilemap": tilemap,
            "spawn_points": spawn_points,
            "biome": header.get("biome", "plains"),
            "music": header.get("music", "overworld"),
        }
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
                    # Split on | to separate static dialog from personality
                    if "|" in npc_rest:
                        npc_dialog, npc_personality = npc_rest.split("|", 1)
                        npc_dialog = npc_dialog.strip()
                        npc_personality = npc_personality.strip()
                    else:
                        npc_dialog = npc_rest
                        npc_personality = ""
                    if room_id not in game.guards:
                        game.guards[room_id] = []
                    game.guards[room_id].append({
                        "name": npc_name, "x": npc_x, "y": npc_y,
                        "sprite": npc_sprite, "dialog": npc_dialog,
                        "personality": npc_personality,
                    })
                elif tokens[0] == "monster" and len(tokens) >= 4:
                    kind = tokens[1]
                    mx = int(tokens[2])
                    my = int(tokens[3])
                    if room_id not in game.monster_templates:
                        game.monster_templates[room_id] = []
                    game.monster_templates[room_id].append({"kind": kind, "x": mx, "y": my})

        count += 1

    print(f"[ROOMS] Loaded {count} room files from {directory}/")
    print(f"[ROOMS] Total rooms: {len(game.rooms)}")


def load_dungeon_templates(directory: str = "rooms/dungeon1"):
    """Load dungeon room templates from .room files (no exits parsed)."""
    rooms_dir = Path(__file__).parent.parent / directory
    if not rooms_dir.exists():
        print(f"[DUNGEON] No '{directory}/' directory found, skipping")
        return

    count = 0
    for room_file in sorted(rooms_dir.glob("*.room")):
        template_id = room_file.stem
        try:
            text = room_file.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[DUNGEON] Error reading {room_file.name}: {e}")
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
            row = [TILE_CODES.get(code, DUNGEON_FLOOR) for code in codes]
            while len(row) < 15:
                row.append(DUNGEON_FLOOR)
            row = row[:15]
            tilemap.append(row)
        while len(tilemap) < 11:
            tilemap.append([DUNGEON_FLOOR] * 15)
        tilemap = tilemap[:11]

        guards = []
        monsters = []
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
                elif tokens[0] == "monster" and len(tokens) >= 4:
                    monsters.append({"kind": tokens[1], "x": int(tokens[2]), "y": int(tokens[3])})

        game.dungeon_templates[template_id] = {
            "name": header.get("name", template_id),
            "tilemap": tilemap,
            "guards": guards,
            "monsters": monsters,
        }
        count += 1

    print(f"[DUNGEON] Loaded {count} dungeon templates from {directory}/")
