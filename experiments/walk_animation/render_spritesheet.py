"""Render player walk frames as a sprite sheet PNG for visual iteration."""
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image, ImageDraw, ImageFont

PALETTE = {
    "SKIN": "#e8c898", "HAIR": "#4a3020", "PANTS": "#3a4a8a",
    "BOOTS": "#3a2a1a", "SHIRT": "#c8383c",
}

def resolve_color(key):
    return PALETTE.get(key, key)

def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = h[0]*2 + h[1]*2 + h[2]*2
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

# v4 — based on video reference: dramatic arm swing, wide stride, prominent fist
V4_LEFT = [
    # F0 — Stride A: wide legs, arm forward with 2x2 fist, head lean
    [["HAIR",3,0,6,2],["HAIR",7,2,2,4],["SKIN",3,2,4,4],["#222",3,3,1,1],["SHIRT",5,6,6,5],["SHIRT",3,7,2,1],["SKIN",1,8,2,2],["PANTS",3,11,3,2],["PANTS",9,11,2,2],["BOOTS",2,13,3,2],["BOOTS",9,13,2,2]],
    # F1 — Closing A
    [["HAIR",4,0,6,2],["HAIR",8,2,2,4],["SKIN",4,2,4,4],["#222",4,3,1,1],["SHIRT",5,6,6,5],["SHIRT",4,7,1,2],["SKIN",3,9,1,1],["PANTS",4,11,3,2],["PANTS",7,11,3,2],["BOOTS",4,13,2,2],["BOOTS",7,13,2,2]],
    # F2 — Pass
    [["HAIR",4,-1,6,2],["HAIR",8,1,2,4],["SKIN",4,1,4,4],["#222",4,2,1,1],["SHIRT",5,5,6,5],["SHIRT",4,6,1,3],["SKIN",4,9,1,1],["PANTS",5,10,5,2],["BOOTS",5,12,3,2]],
    # F3 — Stride B: arm behind, back hand peeks
    [["HAIR",3,0,6,2],["HAIR",7,2,2,4],["SKIN",3,2,4,4],["#222",3,3,1,1],["SHIRT",5,6,6,5],["SHIRT",4,7,1,1],["SKIN",11,8,1,2],["PANTS",4,11,2,2],["PANTS",8,11,3,2],["BOOTS",3,13,2,2],["BOOTS",8,13,3,2]],
    # F4 — Closing B
    [["HAIR",4,0,6,2],["HAIR",8,2,2,4],["SKIN",4,2,4,4],["#222",4,3,1,1],["SHIRT",5,6,6,5],["SHIRT",3,7,1,2],["SKIN",3,9,1,1],["PANTS",5,11,2,2],["PANTS",7,11,2,2],["BOOTS",4,13,2,2],["BOOTS",7,13,2,2]],
    # F5 — Pass (same as F2)
    [["HAIR",4,-1,6,2],["HAIR",8,1,2,4],["SKIN",4,1,4,4],["#222",4,2,1,1],["SHIRT",5,5,6,5],["SHIRT",4,6,1,3],["SKIN",4,9,1,1],["PANTS",5,10,5,2],["BOOTS",5,12,3,2]],
]

V4_RIGHT = [
    [["HAIR",7,0,6,2],["HAIR",7,2,2,4],["SKIN",9,2,4,4],["#222",12,3,1,1],["SHIRT",5,6,6,5],["SHIRT",11,7,2,1],["SKIN",13,8,2,2],["PANTS",5,11,2,2],["PANTS",10,11,3,2],["BOOTS",5,13,2,2],["BOOTS",11,13,3,2]],
    [["HAIR",6,0,6,2],["HAIR",6,2,2,4],["SKIN",8,2,4,4],["#222",11,3,1,1],["SHIRT",5,6,6,5],["SHIRT",11,7,1,2],["SKIN",12,9,1,1],["PANTS",6,11,3,2],["PANTS",9,11,3,2],["BOOTS",7,13,2,2],["BOOTS",10,13,2,2]],
    [["HAIR",6,-1,6,2],["HAIR",6,1,2,4],["SKIN",8,1,4,4],["#222",11,2,1,1],["SHIRT",5,5,6,5],["SHIRT",11,6,1,3],["SKIN",11,9,1,1],["PANTS",6,10,5,2],["BOOTS",8,12,3,2]],
    [["HAIR",7,0,6,2],["HAIR",7,2,2,4],["SKIN",9,2,4,4],["#222",12,3,1,1],["SHIRT",5,6,6,5],["SHIRT",11,7,1,1],["SKIN",4,8,1,2],["PANTS",5,11,3,2],["PANTS",10,11,2,2],["BOOTS",5,13,3,2],["BOOTS",11,13,2,2]],
    [["HAIR",6,0,6,2],["HAIR",6,2,2,4],["SKIN",8,2,4,4],["#222",11,3,1,1],["SHIRT",5,6,6,5],["SHIRT",12,7,1,2],["SKIN",12,9,1,1],["PANTS",7,11,2,2],["PANTS",9,11,2,2],["BOOTS",7,13,2,2],["BOOTS",10,13,2,2]],
    [["HAIR",6,-1,6,2],["HAIR",6,1,2,4],["SKIN",8,1,4,4],["#222",11,2,1,1],["SHIRT",5,5,6,5],["SHIRT",11,6,1,3],["SKIN",11,9,1,1],["PANTS",6,10,5,2],["BOOTS",8,12,3,2]],
]


def render_rows(rows, output_path="spritesheet.png", scale=8):
    sprite_w, sprite_h = 16, 16
    padding = 2
    max_frames = max(len(r[0]) for r in rows)
    row_w = (sprite_w + padding) * max_frames + padding
    row_h = sprite_h + padding * 2 + 3
    total_h = row_h * len(rows) + 2 * (len(rows) - 1)
    img = Image.new("RGBA", (row_w * scale, (total_h + 2) * scale), (40, 40, 40, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial", scale * 2)
    except Exception:
        font = ImageFont.load_default()
    for row_idx, (frames, title) in enumerate(rows):
        base_y = row_idx * (row_h + 2) * scale
        for i, frame in enumerate(frames):
            ox = (padding + i * (sprite_w + padding)) * scale
            oy = base_y + (padding + 3) * scale
            draw.rectangle([ox - scale, oy - scale, ox + sprite_w * scale, oy + sprite_h * scale], fill=(60, 60, 60, 255))
            draw.text((ox, oy - 3 * scale), f"F{i}", fill=(200, 200, 200), font=font)
            for layer in frame:
                key, x, y, w, h = layer
                color = hex_to_rgb(resolve_color(key))
                draw.rectangle([ox + x * scale, oy + y * scale, ox + (x + w) * scale - 1, oy + (y + h) * scale - 1], fill=color + (255,))
        draw.text((padding * scale, base_y + (row_h - 1) * scale), title, fill=(180, 180, 180), font=font)
    img.save(output_path)
    print(f"Saved: {output_path} ({img.width}x{img.height})")


if __name__ == "__main__":
    out_dir = Path(__file__).parent
    render_rows([
        (V4_LEFT,  "v4 left (video ref: big fist, wide stride, head lean)"),
        (V4_RIGHT, "v4 right (mirrored)"),
    ], str(out_dir / "spritesheet_walk.png"))
