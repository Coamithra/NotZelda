"""Render the heart container sprite to a PNG for preview.

Draws a hand-crafted 18x13 pixel heart (bigger than the HUD 12x11 heart)
with a 1px gold container border via dilation.
"""
from PIL import Image, ImageDraw

S = 8  # render scale factor

# Big heart shape rects: (x, y, w, h) at S=1 — 18 wide x 13 tall
HEART_RECTS = [
    # Left half
    (2, 0, 5, 1), (1, 1, 7, 1), (0, 2, 9, 3),
    (1, 5, 8, 1), (2, 6, 7, 1), (3, 7, 6, 1),
    (4, 8, 5, 1), (5, 9, 4, 1), (6, 10, 3, 1),
    (7, 11, 2, 1), (8, 12, 1, 1),
    # Right half
    (11, 0, 5, 1), (10, 1, 7, 1), (9, 2, 9, 3),
    (9, 5, 8, 1), (9, 6, 7, 1), (9, 7, 6, 1),
    (9, 8, 5, 1), (9, 9, 4, 1), (9, 10, 3, 1),
    (9, 11, 2, 1), (9, 12, 1, 1),
]

# Build pixel set
heart_pixels = set()
for x, y, w, h in HEART_RECTS:
    for dx in range(w):
        for dy in range(h):
            heart_pixels.add((x + dx, y + dy))

# Dilate by 1px for gold border
gold_pixels = set()
for x, y in heart_pixels:
    for dx in range(-1, 2):
        for dy in range(-1, 2):
            gold_pixels.add((x + dx, y + dy))
gold_border = gold_pixels - heart_pixels

# Image sizing
all_pixels = gold_pixels
min_x = min(x for x, y in all_pixels)
min_y = min(y for x, y in all_pixels)
max_x = max(x for x, y in all_pixels)
max_y = max(y for x, y in all_pixels)

MARGIN = 4
ox, oy = -min_x + MARGIN, -min_y + MARGIN
W = (max_x - min_x + 1 + 2 * MARGIN) * S
H = (max_y - min_y + 1 + 2 * MARGIN) * S

img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

def px(x, y, color):
    rx, ry = (x + ox) * S, (y + oy) * S
    draw.rectangle([rx, ry, rx + S - 1, ry + S - 1], fill=color)

# --- Gold container border ---
GOLD = "#DAA520"
DARK_GOLD = "#8B6914"
for x, y in gold_border:
    below_outside = (x, y + 1) not in gold_pixels
    right_outside = (x + 1, y) not in gold_pixels
    px(x, y, DARK_GOLD if (below_outside or right_outside) else GOLD)

# --- Red heart fill ---
RED = "#e03030"
DARK_RED = "#a02020"
HIGHLIGHT = "#ff6060"
HIGHLIGHT2 = "#f04848"
for x, y in heart_pixels:
    px(x, y, RED)

# Highlight (top-left lobe shine)
for hx, hy in [(2, 1), (3, 1), (4, 1), (1, 2), (2, 2)]:
    px(hx, hy, HIGHLIGHT)
# Subtle mid-highlight on right lobe
for hx, hy in [(12, 1), (13, 1)]:
    px(hx, hy, HIGHLIGHT2)

# Shadows (bottom-left and bottom-right edges)
for sx, sy in [(0, 4), (1, 5), (2, 6), (3, 7), (17, 4), (16, 5), (15, 6), (14, 7)]:
    if (sx, sy) in heart_pixels:
        px(sx, sy, DARK_RED)

out = "tools/heart_container_preview.png"
img.save(out)
print(f"Saved to {out} ({img.size[0]}x{img.size[1]})")
