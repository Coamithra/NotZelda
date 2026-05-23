"""Generate PWA icons for the OST site (client/icon-*.png, client/apple-touch-icon.png).

Ports the canvas `drawAlbumArt()` from client/ost.html so the installed-app icon
matches the album art shown in the player. Draws the pixel art at 64x64, then
scales up with nearest-neighbor to keep crisp pixels.

Run: python tools/gen_ost_icons.py
"""
from pathlib import Path
from PIL import Image

W = H = 64
CLIENT = Path(__file__).resolve().parent.parent / "client"


def _hex(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def draw_album_art() -> Image.Image:
    img = Image.new("RGB", (W, H), _hex("#0e1526"))
    px = img.load()

    def rect(x, y, w, h, color):
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                if 0 <= xx < W and 0 <= yy < H:
                    px[xx, yy] = color

    # Starfield
    stars = [(5, 4), (12, 8), (50, 6), (58, 12), (8, 20), (45, 18), (30, 5),
             (22, 10), (55, 25), (3, 35), (60, 40), (15, 50), (48, 55),
             (35, 58), (7, 58), (52, 48), (28, 42)]
    for i, (x, y) in enumerate(stars):
        rect(x, y, 1, 1, _hex("#666688") if i % 3 == 0 else _hex("#444455"))

    sx, sy = 20, 14

    def half_for(row):
        half = 12
        if row < 3:
            half = 8 + row
        if row > 22:
            half = 12 - (row - 22) * 2
        if row > 25:
            half = 12 - (row - 22) * 3
        return max(half, 1)

    # Shield body
    body = _hex("#1a3a5c")
    for row in range(28):
        half = half_for(row)
        cx = sx + 12
        for dx in range(-half, half + 1):
            rect(cx + dx, sy + row, 1, 1, body)

    # Shield border
    border = _hex("#3a7abd")
    for row in range(28):
        half = half_for(row)
        cx = sx + 12
        rect(cx - half, sy + row, 1, 1, border)
        rect(cx + half, sy + row, 1, 1, border)
        if row == 0 or row == 27 or (row > 22 and half <= 2):
            for dx in range(-half, half + 1):
                rect(cx + dx, sy + row, 1, 1, border)

    # Seal crystal emblem
    dcx, dcy = 32, 25
    for color, span in ((_hex("#d4a843"), 6), (_hex("#f0d060"), 4), (_hex("#fff8d0"), 2)):
        for row in range(-span, span + 1):
            half = span - abs(row)
            for dx in range(-half, half + 1):
                rect(dcx + dx, dcy + row, 1, 1, color)
    # Radiating sparkles
    spark = _hex("#d4a843")
    rect(dcx, dcy - 9, 1, 2, spark)
    rect(dcx, dcy + 8, 1, 2, spark)
    rect(dcx - 9, dcy, 2, 1, spark)
    rect(dcx + 8, dcy, 2, 1, spark)

    # Sword across
    blade = _hex("#c0c8d8")
    for i in range(20):
        rect(22 + i, 36 - int(i * 0.3), 1, 1, blade)
    hilt = _hex("#8b5e3c")
    rect(30, 34, 1, 4, hilt)
    rect(31, 34, 1, 4, hilt)
    rect(29, 35, 4, 1, hilt)

    # "AMARA" 3x5 pixel font
    green = _hex("#6bc47a")
    text = "AMARA"
    charW, charH, spacing = 3, 5, 1
    total_w = len(text) * (charW + spacing) - spacing
    tx = (W - total_w) // 2
    ty = 52
    font = {
        "A": [0, 1, 0, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1],
        "M": [1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 0, 1],
        "R": [1, 1, 0, 1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 1],
    }
    for ci, ch in enumerate(text):
        glyph = font.get(ch)
        if not glyph:
            continue
        ox = tx + ci * (charW + spacing)
        for py in range(charH):
            for pxx in range(charW):
                if glyph[py * charW + pxx]:
                    rect(ox + pxx, ty + py, 1, 1, green)

    return img


def main():
    base = draw_album_art()
    for size, name in ((512, "icon-512.png"), (192, "icon-192.png"),
                       (180, "apple-touch-icon.png")):
        out = base.resize((size, size), Image.NEAREST)
        out.save(CLIENT / name)
        print(f"wrote {CLIENT / name} ({size}x{size})")


if __name__ == "__main__":
    main()
