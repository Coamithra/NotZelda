"""
World map renderer — reads rooms/*.room files and renders world_map.png.

Run:  python render_map.py
Requires: pip install Pillow

Each tile = 4x4 pixels, each room = 60x44px.
Grid rooms laid out in 16x8 grid with gaps. Village rooms above.
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

ROOMS_DIR = Path(__file__).parent.parent / "rooms"
OUTPUT = Path(__file__).parent.parent / "docs" / "world_map.png"

# Tile pixel size
TPIX = 4
ROOM_COLS = 15
ROOM_ROWS = 11
ROOM_W = ROOM_COLS * TPIX  # 60
ROOM_H = ROOM_ROWS * TPIX  # 44
GAP = 4  # pixels between rooms

# Tile colors for the map (simplified)
TILE_MAP_COLORS = {
    0:  "#3a7a2a",  # grass
    1:  "#9a9a9a",  # stone
    2:  "#8B6914",  # wood
    3:  "#5a5a6a",  # wall_stone
    4:  "#5a3a1a",  # wall_wood
    5:  "#2a6aaa",  # water
    6:  "#1a5a1a",  # tree
    7:  "#4a8a3a",  # flowers (greenish)
    8:  "#8a7040",  # dirt
    9:  "#8B6914",  # stairs_up
    10: "#8B6914",  # stairs_down
    11: "#3a3a3a",  # anvil
    12: "#e63",     # fireplace
    13: "#6a4a1a",  # table
    14: "#6a4a1a",  # pew
    15: "#9a9a9a",  # door
    16: "#d4b870",  # sand
    17: "#2a8a2a",  # cactus (green on sand)
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
}

# Tile code -> numeric ID
TILE_CODES = {
    "GR": 0, "ST": 1, "WD": 2, "WS": 3, "WW": 4,
    "WA": 5, "TR": 6, "FL": 7, "DT": 8, "SU": 9,
    "SD": 10, "AN": 11, "FP": 12, "TB": 13, "PW": 14,
    "DR": 15, "SA": 16, "CC": 17, "MT": 18, "CV": 19,
    "SM": 20, "DK": 21, "BR": 22, "GS": 23, "IF": 24,
    "RW": 25, "RF": 26, "TG": 27, "RD": 28, "CL": 29,
    "SH": 30, "BO": 31,
}


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def load_room_file(path):
    """Parse a .room file and return tilemap as list of list of int."""
    text = path.read_text(encoding="utf-8")
    parts = text.split("---")
    if len(parts) < 2:
        return None

    tilemap_text = parts[1].strip()
    tilemap = []
    for line in tilemap_text.splitlines():
        line = line.strip()
        if not line:
            continue
        codes = line.split()
        row = [TILE_CODES.get(code, 0) for code in codes]
        while len(row) < ROOM_COLS:
            row.append(0)
        row = row[:ROOM_COLS]
        tilemap.append(row)
    while len(tilemap) < ROOM_ROWS:
        tilemap.append([0] * ROOM_COLS)
    tilemap = tilemap[:ROOM_ROWS]

    # Parse header for grid position
    header = {}
    for line in parts[0].strip().splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            header[key.strip()] = val.strip()

    return {"tilemap": tilemap, "header": header}


def render():
    # Grid layout: 16 cols x 8 rows, plus village above
    GRID_COLS = 16
    GRID_ROWS = 8
    VILLAGE_HEIGHT = 3  # room-height units above grid for village

    total_w = GRID_COLS * (ROOM_W + GAP) + GAP
    total_h = (GRID_ROWS + VILLAGE_HEIGHT) * (ROOM_H + GAP) + GAP

    img = Image.new("RGB", (total_w, total_h), (13, 17, 23))  # dark background
    draw = ImageDraw.Draw(img)

    def draw_room_at(tilemap, px, py):
        for r in range(ROOM_ROWS):
            for c in range(ROOM_COLS):
                tile_id = tilemap[r][c]
                color_hex = TILE_MAP_COLORS.get(tile_id, "#333333")
                color = hex_to_rgb(color_hex)
                x = px + c * TPIX
                y = py + r * TPIX
                draw.rectangle([x, y, x + TPIX - 1, y + TPIX - 1], fill=color)

    # Load and render grid rooms
    rooms_loaded = 0
    for room_file in sorted(ROOMS_DIR.glob("ow_*.room")):
        stem = room_file.stem  # e.g. "ow_0_7"
        parts = stem.split("_")
        if len(parts) != 3:
            continue
        try:
            row = int(parts[1])
            col = int(parts[2])
        except ValueError:
            continue

        data = load_room_file(room_file)
        if not data:
            continue

        px = GAP + col * (ROOM_W + GAP)
        py = GAP + (row + VILLAGE_HEIGHT) * (ROOM_H + GAP)
        draw_room_at(data["tilemap"], px, py)
        rooms_loaded += 1

    # Render interior rooms in a row below the grid
    interior_files = [f for f in ROOMS_DIR.glob("*.room") if not f.stem.startswith("ow_")]
    for i, room_file in enumerate(sorted(interior_files)):
        data = load_room_file(room_file)
        if not data:
            continue
        px = GAP + i * (ROOM_W + GAP)
        py = GAP + (GRID_ROWS + VILLAGE_HEIGHT) * (ROOM_H + GAP)
        draw_room_at(data["tilemap"], px, py)
        rooms_loaded += 1

    # Render village rooms (hardcoded tilemaps from mud_server.py)
    # These are rendered above the grid in approximate positions
    village_positions = {
        "town_square": (7, 1),   # center, row 1
        "blacksmith":  (7, 0),   # center, row 0
        "forest_path": (7, 2),   # center, row 2
        "tavern":      (9, 1),   # east of town square
        "tavern_upstairs": (10, 0), # above tavern
        "old_chapel":  (5, 1),   # west of town square
        "clearing":    (7, 2),   # same as forest_path (skip, it connects to grid)
    }

    # Just draw a label for village area
    # (Village rooms use Python tilemap format, not .room files, so we skip them in the map)

    # Draw connection lines between rooms
    for room_file in sorted(ROOMS_DIR.glob("ow_*.room")):
        stem = room_file.stem
        parts_s = stem.split("_")
        if len(parts_s) != 3:
            continue
        try:
            row = int(parts_s[1])
            col = int(parts_s[2])
        except ValueError:
            continue

        data = load_room_file(room_file)
        if not data or "exits" not in data["header"]:
            continue

        cx = GAP + col * (ROOM_W + GAP) + ROOM_W // 2
        cy = GAP + (row + VILLAGE_HEIGHT) * (ROOM_H + GAP) + ROOM_H // 2

        for pair in data["header"]["exits"].split():
            if "=" not in pair:
                continue
            direction, target = pair.split("=", 1)
            if not target.startswith("ow_"):
                continue
            tp = target.split("_")
            if len(tp) != 3:
                continue
            try:
                tr, tc = int(tp[1]), int(tp[2])
            except ValueError:
                continue

            tx = GAP + tc * (ROOM_W + GAP) + ROOM_W // 2
            ty = GAP + (tr + VILLAGE_HEIGHT) * (ROOM_H + GAP) + ROOM_H // 2

            # Draw a small line in the gap between rooms
            if direction == "east":
                draw.line([(cx + ROOM_W//2, cy), (tx - ROOM_W//2, ty)], fill=(100, 100, 100), width=1)
            elif direction == "south":
                draw.line([(cx, cy + ROOM_H//2), (tx, ty - ROOM_H//2)], fill=(100, 100, 100), width=1)

    img.save(OUTPUT)
    print(f"Rendered {rooms_loaded} rooms to {OUTPUT}")
    print(f"Image size: {img.size[0]}x{img.size[1]} pixels")


if __name__ == "__main__":
    render()
