"""
Dungeon room template renderer — reads rooms/dungeon1/*.room and renders dungeon_rooms.png.

Run:  python render_dungeon_rooms.py
Requires: pip install Pillow

Renders all 64 dungeon room templates in an 8x8 grid, each room shown
as a 15x11 tilemap with 4px per tile.
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

ROOMS_DIR = Path(__file__).parent.parent / "rooms" / "dungeon1"
OUTPUT = Path(__file__).parent.parent / "docs" / "dungeon_rooms.png"

TPIX = 4        # pixels per tile
ROOM_COLS = 15
ROOM_ROWS = 11
ROOM_W = ROOM_COLS * TPIX  # 60
ROOM_H = ROOM_ROWS * TPIX  # 44
GAP = 4         # pixels between rooms
LABEL_H = 14    # height for room name
GRID_COLS = 8   # rooms per row
GRID_ROWS = 8   # rows of rooms

TILE_CODES = {
    "GR": 0, "ST": 1, "WD": 2, "WS": 3, "WW": 4,
    "WA": 5, "TR": 6, "FL": 7, "DT": 8, "SU": 9,
    "SD": 10, "AN": 11, "FP": 12, "TB": 13, "PW": 14,
    "DR": 15, "SA": 16, "CC": 17, "MT": 18, "CV": 19,
    "SM": 20, "DK": 21, "BR": 22, "GS": 23, "IF": 24,
    "RW": 25, "RF": 26, "TG": 27, "RD": 28, "CL": 29,
    "SH": 30, "BO": 31, "DW": 32, "DF": 33, "PL": 34, "SC": 35,
}

TILE_COLORS = {
    0:  "#3a7a2a",  # grass
    1:  "#9a9a9a",  # stone
    2:  "#8B6914",  # wood
    3:  "#5a5a6a",  # wall_stone
    4:  "#5a3a1a",  # wall_wood
    5:  "#2a6aaa",  # water
    6:  "#1a5a1a",  # tree
    7:  "#4a8a3a",  # flowers
    8:  "#8a7040",  # dirt
    9:  "#8B6914",  # stairs_up
    10: "#8B6914",  # stairs_down
    11: "#3a3a3a",  # anvil
    12: "#ee6633",  # fireplace
    13: "#6a4a1a",  # table
    14: "#6a4a1a",  # pew
    15: "#9a9a9a",  # door
    16: "#d4b870",  # sand
    17: "#2a8a2a",  # cactus
    18: "#7a7a8a",  # mountain
    19: "#5a5050",  # cave_floor
    20: "#4a6a30",  # swamp
    21: "#5a4a3a",  # dead_tree
    22: "#8B6914",  # bridge
    23: "#8a8a9a",  # gravestone
    24: "#4a4a5a",  # iron_fence
    25: "#6a6a7a",  # ruins_wall
    26: "#8a8a7a",  # ruins_floor
    27: "#5a9a4a",  # tall_grass
    28: "#9a8a6a",  # road
    29: "#6a5a4a",  # cliff
    30: "#5a9acc",  # shallow_water
    31: "#7a7a7a",  # boulder
    32: "#3a3a4a",  # dungeon_wall
    33: "#5a5a5a",  # dungeon_floor
    34: "#6a6a6a",  # pillar
    35: "#fc9933",  # sconce_wall (orange glow)
}


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def load_room(path):
    text = path.read_text(encoding="utf-8")
    parts = text.split("---")
    if len(parts) < 2:
        return None

    header = {}
    for line in parts[0].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            header[k.strip()] = v.strip()

    tilemap = []
    for line in parts[1].strip().splitlines():
        line = line.strip()
        if not line:
            continue
        codes = line.split()
        row = [TILE_CODES.get(c, 33) for c in codes]
        while len(row) < ROOM_COLS:
            row.append(33)
        tilemap.append(row[:ROOM_COLS])
    while len(tilemap) < ROOM_ROWS:
        tilemap.append([33] * ROOM_COLS)
    tilemap = tilemap[:ROOM_ROWS]

    monsters = []
    if len(parts) >= 3:
        for line in parts[2].strip().splitlines():
            tokens = line.strip().split()
            if tokens and tokens[0] == "monster" and len(tokens) >= 4:
                monsters.append({"kind": tokens[1], "x": int(tokens[2]), "y": int(tokens[3])})

    return {"name": header.get("name", path.stem), "tilemap": tilemap, "monsters": monsters}


def render():
    room_files = sorted(ROOMS_DIR.glob("*.room"))
    if not room_files:
        print(f"No .room files found in {ROOMS_DIR}")
        sys.exit(1)

    total_w = GRID_COLS * (ROOM_W + GAP) + GAP
    total_h = GRID_ROWS * (ROOM_H + LABEL_H + GAP) + GAP

    img = Image.new("RGB", (total_w, total_h), (13, 17, 23))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 10)
    except OSError:
        font = ImageFont.load_default()

    monster_colors = {
        "skeleton": (220, 220, 200),
        "bat":      (160, 80, 160),
    }

    for idx, room_file in enumerate(room_files):
        data = load_room(room_file)
        if not data:
            continue

        col = idx % GRID_COLS
        row = idx // GRID_COLS
        ox = GAP + col * (ROOM_W + GAP)
        oy = GAP + row * (ROOM_H + LABEL_H + GAP)

        # Label
        label = data["name"]
        if len(label) > 12:
            label = label[:11] + ".."
        draw.text((ox, oy), label, fill=(160, 160, 170), font=font)
        oy += LABEL_H

        # Tilemap
        for r in range(ROOM_ROWS):
            for c in range(ROOM_COLS):
                tile_id = data["tilemap"][r][c]
                color_hex = TILE_COLORS.get(tile_id, "#333333")
                color = hex_to_rgb(color_hex)
                x = ox + c * TPIX
                y = oy + r * TPIX
                draw.rectangle([x, y, x + TPIX - 1, y + TPIX - 1], fill=color)

        # Monster markers
        for m in data["monsters"]:
            mx = ox + m["x"] * TPIX
            my = oy + m["y"] * TPIX
            color = monster_colors.get(m["kind"], (255, 100, 100))
            draw.rectangle([mx, my, mx + TPIX - 1, my + TPIX - 1], fill=color)

    img.save(OUTPUT)
    print(f"Rendered {len(room_files)} dungeon rooms to {OUTPUT}")
    print(f"Image size: {img.size[0]}x{img.size[1]} pixels")


if __name__ == "__main__":
    render()
