"""Generate a .ico file for the NotZelda desktop shortcut.

Renders the player character (facing down) as pixel art on a grass-green
background tile, producing a multi-size .ico (16x16, 32x32, 48x48, 256x256).

Run:  python tools/make_icon.py
Output: notzelda.ico (project root)
"""

from PIL import Image, ImageDraw

# -- Colors (from sprite_data.js PALETTE + player defaults) --
SKIN   = (0xe8, 0xc8, 0x98)
HAIR   = (0x4a, 0x30, 0x20)
PANTS  = (0x3a, 0x4a, 0x8a)
BOOTS  = (0x3a, 0x2a, 0x1a)
SHIRT  = (0x40, 0xb0, 0x40)   # green shirt (default player color)
EYES   = (0x22, 0x22, 0x22)

# Background: grass tile base color
GRASS_BASE  = (0x4a, 0x8c, 0x3a)
GRASS_LIGHT = (0x5a, 0x9c, 0x4a)
GRASS_DARK  = (0x3a, 0x7c, 0x2a)

# Player walk_down frame 0 sprite layers on a 16x16 grid
# Format: (color, x, y, w, h)
PLAYER_LAYERS = [
    (HAIR,  5, 0, 6, 2),
    (SKIN,  5, 2, 6, 4),
    (EYES,  6, 3, 1, 1),
    (EYES,  9, 3, 1, 1),
    (SHIRT, 4, 6, 8, 5),
    (SHIRT, 3, 6, 1, 4),
    (SHIRT,12, 6, 1, 4),
    (SKIN,  3,10, 1, 1),
    (SKIN, 12,10, 1, 1),
    (PANTS, 5,11, 6, 2),
    (BOOTS, 5,13, 2, 2),
    (BOOTS, 9,13, 2, 2),
]

# Simple sword (pointing down, like an attack pose icon)
SWORD_LAYERS = [
    ((0xc0, 0xc0, 0xc8), 7, 11, 2, 3),  # blade
    ((0x8a, 0x6a, 0x3a), 7, 14, 2, 1),   # hilt
]


def draw_grass_bg(img):
    """Draw a simple grass background with a few lighter/darker patches."""
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 15, 15], fill=GRASS_BASE)
    # A few grass tufts for texture
    for x, y, c in [
        (1, 2, GRASS_LIGHT), (3, 9, GRASS_LIGHT), (12, 3, GRASS_LIGHT),
        (14, 11, GRASS_LIGHT), (0, 7, GRASS_DARK), (8, 14, GRASS_DARK),
        (13, 1, GRASS_DARK), (2, 13, GRASS_DARK),
    ]:
        draw.point((x, y), fill=c)


def draw_player(img):
    """Draw the player sprite layers onto the image."""
    draw = ImageDraw.Draw(img)
    for color, x, y, w, h in PLAYER_LAYERS:
        draw.rectangle([x, y, x + w - 1, y + h - 1], fill=color)


def make_icon():
    # Create 16x16 base image
    base = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    draw_grass_bg(base)
    draw_player(base)

    # Scale up to multiple sizes using nearest-neighbor (pixel art)
    sizes = [16, 32, 48, 256]
    frames = []
    for s in sizes:
        frames.append(base.resize((s, s), Image.NEAREST))

    out_path = "notzelda.ico"
    # Save as ICO — Pillow re-scales from the largest image for each size
    largest = frames[-1]  # 256x256
    largest.save(
        out_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
    )
    print(f"Created {out_path} with sizes: {sizes}")


if __name__ == "__main__":
    make_icon()
