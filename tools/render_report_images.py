"""Render pixel-art NPC scene images for the prompt tuning report.

Reads sprite data from data/npc_sprites.json and the town_guard sprite from
server/npc_chat.py, renders scaled-up pixel art with speech bubbles.

Usage:
    python tools/render_report_images.py

Output: docs/images/report_*.png
"""

import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).parent.parent
SPRITES_FILE = REPO_ROOT / "data" / "npc_sprites.json"
OUTPUT_DIR = REPO_ROOT / "docs" / "images"

# Default skin/clothing colors (used when sprites reference SKIN, PANTS, BOOTS)
DEFAULTS = {
    "SKIN": "#e8c898",
    "PANTS": "#3a4a8a",
    "BOOTS": "#3a2a1a",
}

SCALE = 10  # each pixel unit = 10 screen pixels
GRID = 16   # sprite grid size

# Town guard sprite (from npc_chat.py TOWN_GUARD_MONSTER)
GUARD_SPRITE = {
    "colors": {
        "helmet": "#8090a0", "helmet_dark": "#606e7a", "armor": "#9aa8b8",
        "skin": "#e8c898", "eyes": "#222222", "pants": "#3a4a8a", "boots": "#3a2a1a",
    },
    "layers": [
        ["helmet",      4, 0, 8, 2],
        ["helmet_dark", 4, 2, 8, 1],
        ["skin",        5, 3, 6, 3],
        ["eyes",        6, 3, 1, 1],
        ["eyes",        9, 3, 1, 1],
        ["armor",       4, 6, 8, 5],
        ["armor",       3, 6, 1, 4],
        ["armor",      12, 6, 1, 4],
        ["skin",        3,10, 1, 1],
        ["skin",       12,10, 1, 1],
        ["pants",       5,11, 6, 2],
        ["boots",       5,13, 2, 2],
        ["boots",       9,13, 2, 2],
    ],
}

# Player sprite (simple adventurer)
PLAYER_SPRITE = {
    "colors": {
        "hair": "#5a3a1a", "tunic": "#2a6a2a", "belt": "#6a4a1a",
    },
    "layers": [
        ["hair",   5, 0, 6, 2],
        ["SKIN",   5, 2, 6, 4],
        ["#222",   6, 3, 1, 1],
        ["#222",   9, 3, 1, 1],
        ["tunic",  4, 6, 8, 5],
        ["tunic",  3, 7, 1, 3],
        ["tunic", 12, 7, 1, 3],
        ["belt",   4, 9, 8, 1],
        ["SKIN",   3,10, 1, 1],
        ["SKIN",  12,10, 1, 1],
        ["PANTS",  5,11, 6, 2],
        ["BOOTS",  5,13, 2, 2],
        ["BOOTS",  9,13, 2, 2],
    ],
}


def load_npc_sprites():
    with open(SPRITES_FILE, encoding="utf-8") as f:
        return json.load(f)


def resolve_color(color_key: str, colors: dict) -> str:
    """Resolve a color key to a hex color."""
    if color_key.startswith("#"):
        # Expand 3-char hex (#222 -> #222222)
        if len(color_key) == 4:
            return f"#{color_key[1]*2}{color_key[2]*2}{color_key[3]*2}"
        return color_key
    if color_key in colors:
        return colors[color_key]
    if color_key in DEFAULTS:
        return DEFAULTS[color_key]
    return "#ff00ff"  # magenta = missing color


def render_sprite(sprite_data: dict, scale: int = SCALE) -> Image.Image:
    """Render a sprite to a PIL Image with transparency."""
    img = Image.new("RGBA", (GRID * scale, GRID * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    colors = sprite_data.get("colors", {})

    for layer in sprite_data["layers"]:
        color_key, x, y, w, h = layer[0], layer[1], layer[2], layer[3], layer[4]
        hex_color = resolve_color(color_key, colors)
        # Parse hex
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        draw.rectangle(
            [x * scale, y * scale, (x + w) * scale - 1, (y + h) * scale - 1],
            fill=(r, g, b, 255)
        )
    return img


def try_load_font(size):
    """Try to load a nice font, fall back to default."""
    font_paths = [
        "C:/Windows/Fonts/consola.ttf",   # Consolas
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def draw_speech_bubble(draw: ImageDraw.Draw, text: str, x: int, y: int,
                       font, tag: str = None, tag_color: str = None,
                       max_width: int = 280):
    """Draw a rounded speech bubble with optional colored tag prefix."""
    # Measure text
    lines = []
    for line in text.split("\n"):
        lines.append(line)

    # Calculate bubble size
    padding = 12
    line_height = font.size + 4
    text_height = len(lines) * line_height
    text_width = max(draw.textlength(line, font=font) for line in lines)
    bubble_w = int(text_width + padding * 2)
    bubble_h = int(text_height + padding * 2)

    # Bubble background
    draw.rounded_rectangle(
        [x, y, x + bubble_w, y + bubble_h],
        radius=10, fill=(255, 255, 255, 240), outline=(80, 80, 80, 255), width=2
    )

    # Tail (little triangle pointing down)
    tail_x = x + bubble_w // 3
    tail_y = y + bubble_h
    draw.polygon([
        (tail_x, tail_y - 2),
        (tail_x + 12, tail_y - 2),
        (tail_x + 4, tail_y + 12),
    ], fill=(255, 255, 255, 240), outline=(80, 80, 80, 255))
    # Cover the outline on the bubble edge
    draw.line([(tail_x + 1, tail_y - 1), (tail_x + 11, tail_y - 1)],
              fill=(255, 255, 255, 240), width=2)

    # Draw text
    ty = y + padding
    for line in lines:
        # Check if line starts with a tag
        if tag and line.startswith(tag):
            # Draw tag in color
            tc = tag_color or "#cc4444"
            r, g, b = int(tc[1:3], 16), int(tc[3:5], 16), int(tc[5:7], 16)
            draw.text((x + padding, ty), tag, fill=(r, g, b, 255), font=font)
            tag_w = draw.textlength(tag, font=font)
            rest = line[len(tag):]
            draw.text((x + padding + tag_w, ty), rest, fill=(40, 40, 40, 255), font=font)
        else:
            draw.text((x + padding, ty), line, fill=(40, 40, 40, 255), font=font)
        ty += line_height

    return bubble_w, bubble_h + 14  # include tail


def create_scene(width: int, height: int, bg_color=(60, 75, 55)) -> tuple[Image.Image, ImageDraw.Draw]:
    """Create a scene canvas with a background."""
    img = Image.new("RGBA", (width, height), (*bg_color, 255))
    draw = ImageDraw.Draw(img)
    return img, draw


def draw_floor(draw, width, height, color=(75, 90, 65)):
    """Draw a simple floor area."""
    floor_y = height // 2
    draw.rectangle([0, floor_y, width, height], fill=(*color, 255))


def paste_sprite(scene: Image.Image, sprite: Image.Image, x: int, y: int):
    """Paste a sprite onto the scene with transparency."""
    scene.paste(sprite, (x, y), sprite)


# ---------------------------------------------------------------------------
# Scene generators
# ---------------------------------------------------------------------------

def scene_before(npc_sprites):
    """Scene 1: Before — Smith calls guards on 'hello'."""
    W, H = 750, 420
    scene, draw = create_scene(W, H, bg_color=(70, 60, 50))
    draw_floor(draw, W, H, color=(85, 72, 58))
    font = try_load_font(16)
    title_font = try_load_font(13)

    # Render sprites
    player = render_sprite(PLAYER_SPRITE)
    smith = render_sprite(npc_sprites["smith"])
    guard1 = render_sprite(GUARD_SPRITE)
    guard2 = render_sprite(GUARD_SPRITE)

    # Player speech bubble
    draw_speech_bubble(draw, "Hello there!", 40, 30, font)

    # Smith speech bubble
    draw_speech_bubble(draw, "[CALL_GUARDS] GUARDS!\nThis ruffian threatens me!", 340, 20, font,
                       tag="[CALL_GUARDS]", tag_color="#cc2222")

    # Place sprites
    paste_sprite(scene, player, 80, 200)
    paste_sprite(scene, smith, 450, 200)
    paste_sprite(scene, guard1, 560, 220)
    paste_sprite(scene, guard2, 620, 190)

    # "?!" over player
    draw.text((120, 185), "?!", fill=(255, 220, 50, 255), font=try_load_font(24))

    # Labels
    draw.text((90, 370), "Hero", fill=(200, 200, 200, 200), font=title_font)
    draw.text((455, 370), "Smith", fill=(200, 200, 200, 200), font=title_font)
    draw.text((565, 370), "Guard", fill=(200, 200, 200, 200), font=title_font)
    draw.text((625, 370), "Guard", fill=(200, 200, 200, 200), font=title_font)

    # Caption
    draw.text((W // 2 - 150, H - 25), 'You said "hello." Three guards showed up.',
              fill=(200, 180, 150, 220), font=title_font)

    return scene


def scene_after(npc_sprites):
    """Scene 2: After — friendly conversation, no guards."""
    W, H = 600, 380
    scene, draw = create_scene(W, H, bg_color=(55, 70, 50))
    draw_floor(draw, W, H, color=(68, 82, 60))
    font = try_load_font(16)
    title_font = try_load_font(13)

    player = render_sprite(PLAYER_SPRITE)
    smith = render_sprite(npc_sprites["smith"])

    draw_speech_bubble(draw, "Hello there!", 40, 30, font)
    draw_speech_bubble(draw, "[FRIENDLY] Well met,\ntraveler!", 310, 30, font,
                       tag="[FRIENDLY]", tag_color="#22aa44")

    paste_sprite(scene, player, 80, 180)
    paste_sprite(scene, smith, 400, 180)

    draw.text((90, 345), "Hero", fill=(200, 200, 200, 200), font=title_font)
    draw.text((405, 345), "Smith", fill=(200, 200, 200, 200), font=title_font)

    draw.text((W // 2 - 80, H - 25), "No guards. As it should be.",
              fill=(180, 220, 180, 220), font=title_font)

    return scene


def scene_angry_streak(npc_sprites):
    """Scene 3: Consecutive angry filter in action — two panels."""
    W, H = 750, 500
    scene, draw = create_scene(W, H, bg_color=(65, 58, 48))
    font = try_load_font(15)
    title_font = try_load_font(13)
    small_font = try_load_font(12)

    smith = render_sprite(npc_sprites["smith"])
    player = render_sprite(PLAYER_SPRITE)
    guard = render_sprite(GUARD_SPRITE)

    # --- Panel 1: first rude message, no guards ---
    # Divider
    draw.line([(0, 240), (W, 240)], fill=(100, 90, 75, 255), width=2)
    draw_floor(draw, W, 240, color=(80, 70, 58))

    draw_speech_bubble(draw, "You're useless.", 30, 10, font)
    draw_speech_bubble(draw, "[ANGRY] I'd like to see YOU\nwork the anvil all day!", 320, 5, font,
                       tag="[ANGRY]", tag_color="#dd6622")

    paste_sprite(scene, player, 70, 100)
    paste_sprite(scene, smith, 430, 100)

    draw.text((30, 215), "Streak: 1/2 — no guards yet",
              fill=(220, 180, 100, 220), font=small_font)

    # --- Panel 2: second rude message, GUARDS! ---
    y_off = 248
    draw.rectangle([0, y_off, W, H], fill=(65, 58, 48, 255))
    draw_floor(draw, W, H, color=(80, 70, 58))

    draw_speech_bubble(draw, "Your forge is garbage!", 30, y_off + 8, font)
    draw_speech_bubble(draw, "[ANGRY] GUARDS! Remove this\nfool from my shop!", 300, y_off + 3, font,
                       tag="[ANGRY]", tag_color="#cc2222")

    paste_sprite(scene, player, 70, y_off + 95)
    paste_sprite(scene, smith, 420, y_off + 95)
    paste_sprite(scene, guard, 560, y_off + 105)

    draw.text((30, H - 30), "Streak: 2/2 — HERE THEY COME!",
              fill=(255, 120, 80, 240), font=small_font)

    return scene


def scene_barmaid_gift(npc_sprites):
    """Scene 4: Barmaid giving a gift after charming conversation."""
    W, H = 650, 400
    scene, draw = create_scene(W, H, bg_color=(50, 45, 35))
    draw_floor(draw, W, H, color=(65, 58, 45))
    font = try_load_font(15)
    title_font = try_load_font(13)

    player = render_sprite(PLAYER_SPRITE)
    barmaid = render_sprite(npc_sprites["barmaid"])

    draw_speech_bubble(draw, "You're the heart of Corneria.\nI'd fight a dragon to\nsee you smile.", 20, 10, font)
    draw_speech_bubble(draw, "[GIVE_ITEM] Oh you! Here,\ntake this. You've earned it.", 340, 15, font,
                       tag="[GIVE_ITEM]", tag_color="#d4a840")

    paste_sprite(scene, player, 80, 200)
    paste_sprite(scene, barmaid, 440, 200)

    # Little heart
    draw.text((350, 180), "<3", fill=(255, 100, 100, 255), font=try_load_font(20))

    draw.text((90, 365), "Hero", fill=(200, 200, 200, 200), font=title_font)
    draw.text((440, 365), "Barmaid", fill=(200, 200, 200, 200), font=title_font)

    draw.text((W // 2 - 130, H - 25), "88.9% gift TP — she knows when you mean it.",
              fill=(220, 200, 160, 220), font=title_font)

    return scene


def scene_priest_minimal(npc_sprites):
    """Scene 5: Priest going berserk on minimal prompt."""
    W, H = 650, 400
    scene, draw = create_scene(W, H, bg_color=(55, 50, 60))
    draw_floor(draw, W, H, color=(68, 62, 72))
    font = try_load_font(16)
    title_font = try_load_font(13)

    player = render_sprite(PLAYER_SPRITE)
    priest = render_sprite(npc_sprites["priest"])
    guard1 = render_sprite(GUARD_SPRITE)
    guard2 = render_sprite(GUARD_SPRITE)

    draw_speech_bubble(draw, "Peace be with you,\nFather.", 30, 25, font)
    draw_speech_bubble(draw, "[CALL_GUARDS] HERESY!\nGUARDS!!", 350, 20, font,
                       tag="[CALL_GUARDS]", tag_color="#cc2222")

    paste_sprite(scene, player, 80, 195)
    paste_sprite(scene, priest, 420, 195)
    paste_sprite(scene, guard1, 540, 200)
    paste_sprite(scene, guard2, 590, 215)

    draw.text((90, 360), "Hero", fill=(200, 200, 200, 200), font=title_font)
    draw.text((420, 360), "Priest", fill=(200, 200, 200, 200), font=title_font)

    draw.text((W // 2 - 160, H - 25), 'Minimal prompt: 65% FP. The Priest was having a bad day.',
              fill=(200, 180, 200, 220), font=title_font)

    return scene


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    npc_sprites = load_npc_sprites()

    scenes = {
        "report_01_before": scene_before,
        "report_02_after": scene_after,
        "report_03_streak": scene_angry_streak,
        "report_04_gift": scene_barmaid_gift,
        "report_05_priest": scene_priest_minimal,
    }

    for name, builder in scenes.items():
        img = builder(npc_sprites)
        path = OUTPUT_DIR / f"{name}.png"
        img.save(path)
        print(f"  Saved {path}")

    print(f"\nDone! {len(scenes)} images in {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
