"""
Dungeon layout renderer — reads dungeon_layouts.py and renders dungeon_layouts.png.

Run:  python render_dungeons.py
Requires: pip install Pillow
"""

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).parent.parent))
from server.dungeon_layouts import DUNGEON_LAYOUTS

OUTPUT = Path(__file__).parent.parent / "docs" / "dungeon_layouts.png"

CELL = 32       # pixels per cell
PAD = 8         # padding between layouts
COLS = 4        # layouts per row
GRID = 8        # 8x8 grid per layout
LABEL_H = 24    # height for name label


def render():
    rows = (len(DUNGEON_LAYOUTS) + COLS - 1) // COLS
    layout_w = GRID * CELL
    layout_h = GRID * CELL

    total_w = COLS * layout_w + (COLS + 1) * PAD
    total_h = rows * (layout_h + LABEL_H) + (rows + 1) * PAD

    img = Image.new("RGB", (total_w, total_h), (20, 20, 30))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("arial.ttf", 14)
    except OSError:
        font = ImageFont.load_default()

    room_color = (80, 80, 200)
    entrance_color = (200, 60, 60)
    empty_color = (30, 30, 40)
    grid_line_color = (50, 50, 60)

    for idx, layout in enumerate(DUNGEON_LAYOUTS):
        col = idx % COLS
        row = idx // COLS
        ox = PAD + col * (layout_w + PAD)
        oy = PAD + row * (layout_h + LABEL_H + PAD)

        # Label
        name = layout["name"].replace("_", " ").title()
        cells = sum(r.count("X") for r in layout["grid"])
        draw.text((ox, oy), f"{name} ({cells})", fill=(200, 200, 200), font=font)
        oy += LABEL_H

        # Grid background
        draw.rectangle([ox, oy, ox + layout_w - 1, oy + layout_h - 1], fill=empty_color)

        # Grid lines
        for i in range(GRID + 1):
            draw.line([(ox + i * CELL, oy), (ox + i * CELL, oy + layout_h)], fill=grid_line_color)
            draw.line([(ox, oy + i * CELL), (ox + layout_w, oy + i * CELL)], fill=grid_line_color)

        # Rooms
        ec, er = layout["entrance"]
        for r, row_str in enumerate(layout["grid"]):
            for c, ch in enumerate(row_str):
                if ch == "X":
                    x1 = ox + c * CELL + 1
                    y1 = oy + r * CELL + 1
                    x2 = x1 + CELL - 2
                    y2 = y1 + CELL - 2
                    color = entrance_color if (c == ec and r == er) else room_color
                    draw.rectangle([x1, y1, x2, y2], fill=color)

    img.save(OUTPUT)
    print(f"Rendered {len(DUNGEON_LAYOUTS)} layouts to {OUTPUT}")
    print(f"Image size: {img.size[0]}x{img.size[1]} pixels")


if __name__ == "__main__":
    render()
