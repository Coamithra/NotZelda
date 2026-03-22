"""Extract drawrect layers from all video reference frames.

Downsamples each frame to pixel-art resolution, classifies colors to the
game palette, extracts minimal covering rectangles, and outputs both
.js drawrect files and _approximation.png previews.
"""
import sys, os
import numpy as np
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Game palette (RGB)
# ---------------------------------------------------------------------------
PALETTE = {
    "HAIR":  (74, 48, 32),
    "SKIN":  (232, 200, 152),
    "SHIRT": (200, 56, 60),
    "PANTS": (58, 74, 138),
    "BOOTS": (58, 42, 26),
    "EYE":   (34, 34, 34),
}

PALETTE_ARRAY = np.array(list(PALETTE.values()), dtype=np.float32)
PALETTE_NAMES = list(PALETTE.keys())

# Map "EYE" -> "#222" for the JS output (matches game convention)
JS_KEY = {k: k for k in PALETTE}
JS_KEY["EYE"] = '"#222"'


def classify_pixel(r, g, b):
    """Return the closest palette name for an RGB color."""
    px = np.array([r, g, b], dtype=np.float32)
    dists = np.sum((PALETTE_ARRAY - px) ** 2, axis=1)
    return PALETTE_NAMES[np.argmin(dists)]


def downsample_frame(img_path, grid=26):
    """Downsample a frame image to an art-pixel grid.

    Returns a 2D list of palette names (or None for transparent).
    """
    img = Image.open(img_path).convert("RGBA")
    arr = np.array(img)
    alpha = arr[:, :, 3]

    # Find content bounds
    rows_with = np.where(np.any(alpha > 128, axis=1))[0]
    cols_with = np.where(np.any(alpha > 128, axis=0))[0]
    if len(rows_with) == 0:
        return []
    y_min, y_max = rows_with[0], rows_with[-1]
    x_min, x_max = cols_with[0], cols_with[-1]
    content_w = x_max - x_min + 1
    content_h = y_max - y_min + 1
    art_w = round(content_w / grid)
    art_h = round(content_h / grid)

    grid_data = []
    for ay in range(art_h):
        row = []
        for ax in range(art_w):
            by = y_min + int(ay * content_h / art_h)
            bx = x_min + int(ax * content_w / art_w)
            ey = y_min + int((ay + 1) * content_h / art_h)
            ex = x_min + int((ax + 1) * content_w / art_w)
            block = arr[by:ey, bx:ex]
            opaque = block[:, :, 3] > 128
            if np.sum(opaque) > block.shape[0] * block.shape[1] * 0.3:
                rgb = block[:, :, :3][opaque]
                median = np.median(rgb, axis=0).astype(int)
                row.append(classify_pixel(*median))
            else:
                row.append(None)
        grid_data.append(row)
    return grid_data


def fit_to_16x16(grid_data):
    """Fit an art grid into a 16x16 sprite grid.

    Centers horizontally, aligns to top vertically (with bottom padding).
    Returns a 16x16 list of palette names (or None).
    """
    art_h = len(grid_data)
    art_w = len(grid_data[0]) if art_h > 0 else 0

    # Center horizontally
    x_off = (16 - art_w) // 2
    # Align top, pad bottom
    y_off = 0

    result = [[None] * 16 for _ in range(16)]
    for ay in range(min(art_h, 16)):
        for ax in range(min(art_w, 16)):
            gx = ax + x_off
            gy = ay + y_off
            if 0 <= gx < 16 and 0 <= gy < 16:
                result[gy][gx] = grid_data[ay][ax]
    return result


def extract_rects(grid_16):
    """Extract minimal covering rectangles from a 16x16 classified grid.

    Uses a greedy approach: for each color, scan top-to-bottom, left-to-right,
    and greedily extend rectangles as far as possible.
    """
    # Collect all colors present
    colors = set()
    for row in grid_16:
        for c in row:
            if c is not None:
                colors.add(c)

    # Process in a specific order for good layering
    color_order = ["HAIR", "SKIN", "EYE", "SHIRT", "PANTS", "BOOTS"]
    colors = [c for c in color_order if c in colors]

    visited = [[False] * 16 for _ in range(16)]
    rects = []

    for color in colors:
        for y in range(16):
            for x in range(16):
                if grid_16[y][x] == color and not visited[y][x]:
                    # Greedily expand rectangle right, then down
                    # First find max width
                    w = 0
                    for xx in range(x, 16):
                        if grid_16[y][xx] == color and not visited[y][xx]:
                            w += 1
                        else:
                            break
                    # Then find max height with that width
                    h = 1
                    for yy in range(y + 1, 16):
                        row_ok = True
                        for xx in range(x, x + w):
                            if grid_16[yy][xx] != color or visited[yy][xx]:
                                row_ok = False
                                break
                        if row_ok:
                            h += 1
                        else:
                            break
                    # Mark visited
                    for yy in range(y, y + h):
                        for xx in range(x, x + w):
                            visited[yy][xx] = True
                    rects.append((color, x, y, w, h))

    return rects


def render_approximation(rects, output_path, scale=26):
    """Render rects as a PNG approximation."""
    img = Image.new("RGBA", (16 * scale, 16 * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for color, x, y, w, h in rects:
        rgb = PALETTE[color]
        draw.rectangle(
            [x * scale, y * scale, (x + w) * scale - 1, (y + h) * scale - 1],
            fill=rgb + (255,),
        )
    img.save(output_path)


def write_drawrects_js(rects, output_path, frame_name):
    """Write rects as a JS drawrects file."""
    # Group by body part for comments
    part_order = {"HAIR": "Hair", "SKIN": "Face/Hand", "EYE": "Eye",
                  "SHIRT": "Shirt", "PANTS": "Pants", "BOOTS": "Boots"}
    current_part = None
    lines = [f"// {frame_name} — right-facing (from video reference)"]
    lines.append("// Format: [colorKey, x, y, w, h]")
    lines.append("[")
    for color, x, y, w, h in rects:
        part = part_order.get(color, color)
        if part != current_part:
            if current_part is not None:
                lines.append("")
            lines.append(f"  // {part}")
            current_part = part
        js_key = JS_KEY.get(color, f'"{color}"')
        # Use quotes for special keys, plain for palette keys
        if js_key.startswith('"'):
            lines.append(f'  [{js_key},{x:3d},{y:3d},{w:2d},{h:2d}],')
        else:
            lines.append(f'  ["{js_key}",{x:3d},{y:3d},{w:2d},{h:2d}],')

    lines.append("]")
    with open(output_path, "w") as f:
        f.write("\n".join(lines) + "\n")


def process_frame(frame_path, out_dir):
    """Process a single frame: downsample, extract rects, render, save JS."""
    name = Path(frame_path).stem  # e.g. "frame1"
    print(f"Processing {name}...")

    grid_data = downsample_frame(frame_path, grid=26)
    if not grid_data:
        print(f"  Skipping {name} — no content")
        return

    grid_16 = fit_to_16x16(grid_data)
    rects = extract_rects(grid_16)

    # Save approximation PNG
    png_path = os.path.join(out_dir, f"{name}_approximation.png")
    render_approximation(rects, png_path)

    # Save drawrects JS
    js_path = os.path.join(out_dir, f"{name}_drawrects.js")
    write_drawrects_js(rects, js_path, name)

    print(f"  {len(rects)} rects -> {Path(png_path).name}, {Path(js_path).name}")


def main():
    frames_dir = Path(__file__).parent / "video_frames"
    # Process frame1 through frame13
    for i in range(1, 14):
        frame_path = frames_dir / f"frame{i}.png"
        if frame_path.exists():
            process_frame(str(frame_path), str(frames_dir))
        else:
            print(f"Skipping frame{i}.png — not found")

    # Also render a combined spritesheet for easy comparison
    print("\nGenerating combined spritesheet...")
    scale = 8
    padding = 2
    sprite_w, sprite_h = 16, 16
    n = 13
    sheet_w = (sprite_w + padding) * n + padding
    sheet_h = sprite_h + padding * 2 + 3

    sheet = Image.new("RGBA", (sheet_w * scale, (sheet_h + 2) * scale), (40, 40, 40, 255))
    draw = ImageDraw.Draw(sheet)

    try:
        from PIL import ImageFont
        font = ImageFont.truetype("arial", scale * 2)
    except Exception:
        from PIL import ImageFont
        font = ImageFont.load_default()

    for i in range(1, 14):
        frame_path = frames_dir / f"frame{i}.png"
        if not frame_path.exists():
            continue
        grid_data = downsample_frame(str(frame_path), grid=26)
        grid_16 = fit_to_16x16(grid_data)
        rects = extract_rects(grid_16)

        idx = i - 1
        ox = (padding + idx * (sprite_w + padding)) * scale
        oy = (padding + 3) * scale

        draw.rectangle(
            [ox - scale, oy - scale, ox + sprite_w * scale, oy + sprite_h * scale],
            fill=(60, 60, 60, 255),
        )
        draw.text((ox, oy - 3 * scale), f"F{i}", fill=(200, 200, 200), font=font)

        for color, x, y, w, h in rects:
            rgb = PALETTE[color]
            draw.rectangle(
                [ox + x * scale, oy + y * scale,
                 ox + (x + w) * scale - 1, oy + (y + h) * scale - 1],
                fill=rgb + (255,),
            )

    draw.text((padding * scale, (sheet_h - 1) * scale),
              "All 13 frames (video reference, auto-extracted)",
              fill=(180, 180, 180), font=font)

    sheet_path = frames_dir / "all_frames_spritesheet.png"
    sheet.save(str(sheet_path))
    print(f"Saved: {sheet_path}")


if __name__ == "__main__":
    main()
