"""
Generate a Legends of Amara trailer video with:
  - Animated title sequence
  - Rendered game scenes (clearing, dungeon, combat)
  - Overworld music overlay
Uses OpenCV + Pillow for rendering, imageio-ffmpeg for audio muxing.
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import math
import random
import json
import subprocess
import os
import shutil

# ── Video settings ──────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1280, 720
FPS = 30
SCALE = 3          # pixel scale for game rendering (16px tile * 3 = 48px)
TILE_PX = 16
TS = TILE_PX * SCALE  # 48 — tile size on screen
ROOM_COLS, ROOM_ROWS = 15, 11

# Game viewport (centered in the 1280x720 frame)
GAME_W = ROOM_COLS * TS   # 720
GAME_H = ROOM_ROWS * TS   # 528
GAME_X = (WIDTH - GAME_W) // 2
GAME_Y = (HEIGHT - GAME_H) // 2

# ── Colors ──────────────────────────────────────────────────────────────────
BLACK = (0, 0, 0)
GOLD = (218, 165, 32)
GOLD_BRIGHT = (255, 215, 0)
DARK_BLUE = (8, 12, 30)
DEEP_PURPLE = (15, 5, 25)
WHITE = (255, 255, 255)
TEAL = (0, 200, 180)
AMBER = (255, 191, 0)

# ── Game palette ────────────────────────────────────────────────────────────
PALETTE = {
    "SKIN": "#e8c898", "HAIR": "#4a3020", "PANTS": "#3a4a8a", "BOOTS": "#3a2a1a",
}
SHIRT_COLORS = ["#c8383c", "#3868c8", "#38a838", "#c8a838", "#a838c8", "#38c8c8"]

TILE_COLORS = {
    "GR": {"base": "#3a7a2a", "alt": "#2d6a1e"},
    "TR": {"base": "#1a5a1a", "alt": "#2a6a2a", "trunk": "#5a3a1a"},
    "FL": {"base": "#3a7a2a", "alt": "#2d6a1e", "flower1": "#ee4444", "flower2": "#eeee44"},
    "DW": {"base": "#3a3a4a", "alt": "#2a2a3a"},
    "DF": {"base": "#5a5a5a", "alt": "#4a4a4a"},
    "ST": {"base": "#9a9a9a", "alt": "#8a8a8a"},
    "WS": {"base": "#5a5a6a", "alt": "#4a4a5a"},
    "SD": {"base": "#8B6914", "alt": "#7a5a10"},
    "SU": {"base": "#8B6914", "alt": "#7a5a10"},
    "WA": {"base": "#2a6aaa", "alt": "#3a7abb"},
    "SH": {"base": "#5a9acc", "alt": "#6aaadd"},
    "MB": {"base": "#3a7a2a", "alt": "#2d6a1e"},  # monster barrier = looks like grass
    "CD": {"base": "#5a3a1a", "alt": "#3a2a10"},   # closed door
}

MONSTER_DATA = {
    "slime": {
        "colors": {"body": "#44cc44", "dark": "#228822", "eyes": "#222222", "highlight": "#88ee88"},
        "frame": [
            ["dark", 2, 9, 12, 6], ["body", 3, 8, 10, 6], ["body", 4, 7, 8, 1],
            ["eyes", 5, 9, 2, 2], ["eyes", 9, 9, 2, 2], ["highlight", 5, 8, 2, 1],
        ],
    },
    "skeleton": {
        "colors": {"bone": "#ddd8cc", "dark": "#aaa89a", "eyes": "#222222"},
        "frame": [
            ["bone", 5, 1, 6, 5], ["eyes", 6, 3, 2, 2], ["eyes", 9, 3, 2, 2],
            ["eyes", 7, 5, 2, 1], ["bone", 6, 6, 4, 5], ["dark", 7, 7, 2, 1],
            ["dark", 7, 9, 2, 1], ["bone", 4, 7, 2, 1], ["bone", 3, 8, 1, 3],
            ["bone", 10, 7, 2, 1], ["bone", 12, 8, 1, 3], ["bone", 6, 11, 2, 3],
            ["bone", 9, 11, 2, 3], ["dark", 5, 14, 3, 1], ["dark", 9, 14, 3, 1],
        ],
    },
    "bat": {
        "colors": {"body": "#3a2a4a", "wing": "#5a3a6a", "eyes": "#ff4444"},
        "frame": [
            ["body", 6, 6, 4, 4], ["wing", 1, 3, 5, 4], ["wing", 10, 3, 5, 4],
            ["wing", 2, 2, 3, 1], ["wing", 11, 2, 3, 1], ["eyes", 6, 7, 1, 1], ["eyes", 9, 7, 1, 1],
        ],
    },
}

# Player walk frames (down, frame 0)
PLAYER_DOWN_0 = [
    ["HAIR", 5, 0, 6, 2], ["SKIN", 5, 2, 6, 4], ["#222", 6, 3, 1, 1], ["#222", 9, 3, 1, 1],
    ["SHIRT", 4, 6, 8, 5], ["SHIRT", 3, 6, 1, 4], ["SHIRT", 12, 6, 1, 4],
    ["SKIN", 3, 10, 1, 1], ["SKIN", 12, 10, 1, 1],
    ["PANTS", 5, 11, 6, 2], ["BOOTS", 5, 13, 2, 2], ["BOOTS", 9, 13, 2, 2],
]
PLAYER_DOWN_1 = [
    ["HAIR", 5, 0, 6, 2], ["SKIN", 5, 2, 6, 4], ["#222", 6, 3, 1, 1], ["#222", 9, 3, 1, 1],
    ["SHIRT", 4, 6, 8, 5], ["SHIRT", 3, 6, 1, 4], ["SHIRT", 12, 6, 1, 4],
    ["SKIN", 3, 10, 1, 1], ["SKIN", 12, 10, 1, 1],
    ["PANTS", 5, 11, 6, 2], ["BOOTS", 4, 13, 2, 2], ["BOOTS", 10, 13, 2, 2],
]
PLAYER_RIGHT_0 = [
    ["HAIR", 6, 0, 6, 2], ["HAIR", 6, 2, 2, 4],
    ["SKIN", 8, 2, 4, 4], ["#222", 11, 3, 1, 1],
    ["SHIRT", 5, 6, 6, 5], ["SHIRT", 11, 7, 1, 3], ["SKIN", 11, 10, 1, 1],
    ["PANTS", 6, 11, 5, 2], ["BOOTS", 8, 13, 3, 2],
]
PLAYER_RIGHT_1 = [
    ["HAIR", 6, 0, 6, 2], ["HAIR", 6, 2, 2, 4],
    ["SKIN", 8, 2, 4, 4], ["#222", 11, 3, 1, 1],
    ["SHIRT", 5, 6, 6, 5], ["SHIRT", 11, 7, 1, 3], ["SKIN", 11, 10, 1, 1],
    ["PANTS", 6, 11, 5, 2], ["BOOTS", 9, 13, 3, 2],
]
PLAYER_LEFT_0 = [
    ["HAIR", 4, 0, 6, 2], ["HAIR", 8, 2, 2, 4],
    ["SKIN", 4, 2, 4, 4], ["#222", 4, 3, 1, 1],
    ["SHIRT", 5, 6, 6, 5], ["SHIRT", 4, 7, 1, 3], ["SKIN", 4, 10, 1, 1],
    ["PANTS", 5, 11, 5, 2], ["BOOTS", 5, 13, 3, 2],
]

# Sword sprite (simple horizontal slash to the right)
SWORD_LAYERS = [
    ["#cccccc", 12, 6, 5, 1],  # blade
    ["#aaaaaa", 12, 7, 5, 1],  # blade lower
    ["#8B6914", 11, 6, 1, 2],  # hilt
]

# ── Room definitions ────────────────────────────────────────────────────────
CLEARING_MAP = [
    "TR TR TR TR TR TR GR GR GR TR TR TR TR TR TR",
    "TR TR GR GR GR GR GR GR GR GR GR GR GR TR TR",
    "TR GR GR FL GR GR GR GR GR GR FL GR GR GR TR",
    "TR GR GR GR GR FL GR GR GR GR GR GR GR TR TR",
    "TR GR FL GR GR GR GR GR GR FL GR GR GR GR TR",
    "TR GR GR GR GR GR GR GR GR GR GR FL GR TR TR",
    "TR GR GR GR GR GR GR GR GR GR GR GR GR GR TR",
    "TR GR FL GR GR GR GR GR GR GR GR GR FL TR TR",
    "TR TR GR GR GR GR FL GR GR GR GR GR GR TR TR",
    "TR TR TR GR GR GR GR GR GR GR GR TR TR TR TR",
    "TR TR TR TR TR TR GR GR GR TR TR TR TR TR TR",
]

DUNGEON_MAP = [
    "DW DW DW DW DW DW DF DF DF DW DW DW DW DW DW",
    "DW DF DF DF DF DF DF DF DF DF DF DF DF DF DW",
    "DW DF DF DF DF DF DF DF DF DF DF DF DF DF DW",
    "DW DF DF DF DF DF DF DF DF DF DF DF DF DF DW",
    "DF DF DF DF DF DF DF DF DF DF DF DF DF DF DF",
    "DF DF DF DF DF DF DF DF DF DF DF DF DF DF DF",
    "DF DF DF DF DF DF DF DF DF DF DF DF DF DF DF",
    "DW DF DF DF DF DF DF DF DF DF DF DF DF DF DW",
    "DW DF DF DF DF DF DF DF DF DF DF DF DF DF DW",
    "DW DF DF DF DF DF DF DF DF DF DF DF DF DF DW",
    "DW DW DW DW DW DW DF DF DF DW DW DW DW DW DW",
]


# ── Utility functions ───────────────────────────────────────────────────────

def hex_to_rgb(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = h[0] * 2 + h[1] * 2 + h[2] * 2
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def ease_in_out(t):
    return t * t * (3 - 2 * t)


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


def lerp(a, b, t):
    return a + (b - a) * max(0, min(1, t))


def lerp_color(c1, c2, t):
    t = max(0, min(1, t))
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


class Star:
    def __init__(self):
        self.x = random.randint(0, WIDTH)
        self.y = random.randint(0, HEIGHT)
        self.brightness = random.random()
        self.speed = random.uniform(0.5, 2.0)
        self.phase = random.uniform(0, math.pi * 2)
        self.size = random.choice([1, 1, 1, 2])


class Particle:
    def __init__(self, x, y, t_born):
        self.x = x
        self.y = y
        self.vx = random.uniform(-1.5, 1.5)
        self.vy = random.uniform(-3, -0.5)
        self.life = random.uniform(0.5, 2.0)
        self.t_born = t_born
        self.color_shift = random.uniform(0, 1)
        self.size = random.randint(2, 5)


# ── Tile renderer ───────────────────────────────────────────────────────────

def render_tile(tile_code):
    """Render a single tile to a 48x48 PIL RGBA image."""
    img = Image.new('RGBA', (TS, TS), (0, 0, 0, 255))
    draw = ImageDraw.Draw(img)

    colors = TILE_COLORS.get(tile_code, {"base": "#ff00ff"})
    base = hex_to_rgb(colors["base"])
    draw.rectangle([0, 0, TS - 1, TS - 1], fill=(*base, 255))

    # Add some texture based on tile type
    if "alt" in colors:
        alt = hex_to_rgb(colors["alt"])
        rng = random.Random(hash(tile_code))
        for _ in range(8):
            rx, ry = rng.randint(0, TS - 6), rng.randint(0, TS - 6)
            rw, rh = rng.randint(3, 8), rng.randint(3, 6)
            draw.rectangle([rx, ry, rx + rw, ry + rh], fill=(*alt, 255))

    # Special: tree has a trunk + canopy
    if tile_code == "TR":
        trunk_c = hex_to_rgb(colors.get("trunk", "#5a3a1a"))
        canopy_dark = hex_to_rgb("#0a4a0a")
        # Trunk
        draw.rectangle([TS // 2 - 4, TS // 2, TS // 2 + 4, TS - 1], fill=(*trunk_c, 255))
        # Canopy circle
        cx, cy = TS // 2, TS // 3
        r = TS // 3
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*base, 255))
        draw.ellipse([cx - r + 3, cy - r + 3, cx + r - 3, cy + r - 3], fill=(*hex_to_rgb(colors["alt"]), 255))
        draw.ellipse([cx - r + 2, cy - r + 1, cx + r - 6, cy + r - 6], fill=(*canopy_dark, 255))

    # Special: flower dots on grass
    if tile_code == "FL":
        f1 = hex_to_rgb(colors.get("flower1", "#ee4444"))
        f2 = hex_to_rgb(colors.get("flower2", "#eeee44"))
        rng = random.Random(42)
        for _ in range(3):
            fx, fy = rng.randint(8, TS - 8), rng.randint(8, TS - 8)
            c = f1 if rng.random() > 0.5 else f2
            draw.ellipse([fx - 2, fy - 2, fx + 2, fy + 2], fill=(*c, 255))

    return img


# Pre-render tile cache
_tile_cache = {}


def get_tile(code):
    if code not in _tile_cache:
        _tile_cache[code] = render_tile(code)
    return _tile_cache[code]


# ── Sprite renderer ─────────────────────────────────────────────────────────

def resolve_color(key, local_colors, shirt_color="#c8383c"):
    """Resolve a color key to an RGB tuple."""
    if key == "SHIRT":
        return hex_to_rgb(shirt_color)
    if key in local_colors:
        return hex_to_rgb(local_colors[key])
    if key in PALETTE:
        return hex_to_rgb(PALETTE[key])
    if key.startswith("#"):
        return hex_to_rgb(key)
    return (255, 0, 255)  # fallback magenta


def draw_sprite(img, layers, local_colors, px, py, shirt_color="#c8383c", scale=SCALE):
    """Draw a sprite at pixel position (px, py) on the image."""
    draw = ImageDraw.Draw(img)
    for layer in layers:
        color_key, sx, sy, sw, sh = layer
        rgb = resolve_color(color_key, local_colors, shirt_color)
        x1 = px + sx * scale
        y1 = py + sy * scale
        x2 = x1 + sw * scale - 1
        y2 = y1 + sh * scale - 1
        draw.rectangle([x1, y1, x2, y2], fill=(*rgb, 255))


def draw_monster(img, kind, px, py):
    """Draw a monster sprite at pixel position."""
    data = MONSTER_DATA.get(kind)
    if not data:
        return
    draw_sprite(img, data["frame"], data["colors"], px, py)


# ── Room renderer ───────────────────────────────────────────────────────────

def render_room(tilemap_strs):
    """Render a full room tilemap to a PIL RGBA image (720x528)."""
    img = Image.new('RGBA', (GAME_W, GAME_H), (0, 0, 0, 255))
    for row_idx, row_str in enumerate(tilemap_strs):
        codes = row_str.split()
        for col_idx, code in enumerate(codes):
            tile = get_tile(code)
            img.paste(tile, (col_idx * TS, row_idx * TS))
    return img


# ── Scene compositors ──────────────────────────────────────────────────────

def compose_game_frame(room_img, overlays=None):
    """Place a game room image centered in a 1280x720 frame with black bars."""
    frame = Image.new('RGBA', (WIDTH, HEIGHT), (*BLACK, 255))
    frame.paste(room_img, (GAME_X, GAME_Y))

    # Dark border/vignette around game area
    draw = ImageDraw.Draw(frame)
    # Subtle border
    draw.rectangle([GAME_X - 2, GAME_Y - 2, GAME_X + GAME_W + 1, GAME_Y + GAME_H + 1],
                    outline=(40, 40, 60, 200), width=2)
    return frame


def apply_darkness(img, light_sources, radius_tiles=3.5):
    """Apply dark-room effect with light circles."""
    dark = Image.new('RGBA', img.size, (0, 0, 0, 220))
    mask = Image.new('L', img.size, 255)
    mask_draw = ImageDraw.Draw(mask)

    for lx, ly in light_sources:
        r = int(radius_tiles * TS)
        mask_draw.ellipse([lx - r, ly - r, lx + r, ly + r], fill=0)
        # Soft edge
        for ring in range(r, r + 30):
            alpha = int(255 * ((ring - r) / 30))
            mask_draw.ellipse([lx - ring, ly - ring, lx + ring, ly + ring],
                              outline=min(255, alpha))

    dark.putalpha(mask)
    return Image.alpha_composite(img, dark)


# ── Title sequence (0-12s) ──────────────────────────────────────────────────

def draw_glow_text(draw, text, center_x, center_y, font, color, glow_radius, glow_alpha):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = center_x - tw // 2
    y = center_y - th // 2
    for r in range(glow_radius, 0, -2):
        alpha = int(glow_alpha * (1 - r / glow_radius) * 0.3)
        gc = tuple(min(255, c + 60) for c in color)
        for dx in range(-r, r + 1, max(1, r // 2)):
            for dy in range(-r, r + 1, max(1, r // 2)):
                if dx * dx + dy * dy <= r * r:
                    draw.text((x + dx, y + dy), text, font=font, fill=(*gc, alpha))
    draw.text((x, y), text, font=font, fill=(*color, int(glow_alpha)))


def render_title_frame(t, stars, particles, title_font, subtitle_font, small_font):
    """Render one frame of the title sequence."""
    img = Image.new('RGBA', (WIDTH, HEIGHT), (*DARK_BLUE, 255))
    draw = ImageDraw.Draw(img)

    # Background gradient
    for y_line in range(HEIGHT):
        ratio = y_line / HEIGHT
        bg = lerp_color(DARK_BLUE, DEEP_PURPLE, ratio)
        draw.line([(0, y_line), (WIDTH, y_line)], fill=(*bg, 255))

    # Stars
    star_alpha = min(1.0, t / 2.0)
    for star in stars:
        twinkle = 0.5 + 0.5 * math.sin(t * star.speed * 2 + star.phase)
        brightness = int(255 * star.brightness * twinkle * star_alpha)
        if brightness > 10:
            c = (brightness, brightness, min(255, brightness + 30), brightness)
            if star.size == 1:
                draw.point((star.x, star.y), fill=c)
            else:
                draw.ellipse([star.x - 1, star.y - 1, star.x + 1, star.y + 1], fill=c)

    # Title
    if t > 1.5:
        p = min(1.0, (t - 1.5) / 2.0)
        a = ease_in_out(p)
        fy = math.sin(t * 0.8) * 5
        ty = int(HEIGHT * 0.32 + fy)
        gp = 0.7 + 0.3 * math.sin(t * 1.5)
        gr = int(15 * a * gp)
        draw_glow_text(draw, "LEGENDS  OF  AMARA", WIDTH // 2, ty,
                        title_font, GOLD_BRIGHT, gr, int(255 * a))

    # Decorative line
    if t > 3.0:
        lp = min(1.0, (t - 3.0) / 1.0)
        lw = int(400 * ease_out_cubic(lp))
        ly = int(HEIGHT * 0.44)
        la = int(180 * lp)
        cx = WIDTH // 2
        draw.line([(cx - lw, ly), (cx + lw, ly)], fill=(*GOLD, la), width=2)
        if lp > 0.5:
            da = int(255 * min(1, (lp - 0.5) * 2))
            for dx in [-lw, lw]:
                px = cx + dx
                s = 4
                draw.polygon([(px, ly - s), (px + s, ly), (px, ly + s), (px - s, ly)],
                              fill=(*GOLD_BRIGHT, da))

    # Subtitle
    if t > 4.0:
        sp = min(1.0, (t - 4.0) / 1.5)
        sa = int(255 * ease_in_out(sp))
        draw_glow_text(draw, "A Browser-Based Multiplayer Adventure",
                        WIDTH // 2, int(HEIGHT * 0.50), subtitle_font, TEAL,
                        int(6 * sp), sa)

    # Tagline
    if t > 6.0:
        tp = min(1.0, (t - 6.0) / 1.5)
        ta = int(200 * ease_in_out(tp))
        draw_glow_text(draw, "Explore  \u00b7  Battle  \u00b7  Discover",
                        WIDTH // 2, int(HEIGHT * 0.70), small_font, AMBER,
                        int(4 * tp), ta)

    # Sparkle particles
    if 2.5 < t < 10.0:
        px = WIDTH // 2 + random.randint(-300, 300)
        py = int(HEIGHT * 0.32) + random.randint(-40, 40)
        particles.append(Particle(px, py, t))

    alive = []
    for p in particles:
        age = t - p.t_born
        if age > p.life:
            continue
        alive.append(p)
        p.x += p.vx
        p.y += p.vy
        p.vy += 0.05
        fade = 1.0 - (age / p.life)
        sc = lerp_color(GOLD_BRIGHT, WHITE, p.color_shift)
        alpha = int(255 * fade * fade)
        size = max(1, int(p.size * fade))
        if alpha > 5:
            draw.ellipse([int(p.x) - size, int(p.y) - size,
                          int(p.x) + size, int(p.y) + size], fill=(*sc, alpha))
    particles.clear()
    particles.extend(alive)

    # Scanlines
    if t > 1.0:
        sa = int(15 * min(1, (t - 1.0) / 2.0))
        for yl in range(0, HEIGHT, 3):
            draw.line([(0, yl), (WIDTH, yl)], fill=(0, 0, 0, sa))

    # Vignette
    for ring in range(60):
        r = ring / 60.0
        alpha = int(80 * r * r)
        inset = int(ring * max(WIDTH, HEIGHT) / 140)
        if 0 < inset < WIDTH // 2 and inset < HEIGHT // 2:
            draw.rectangle([inset, inset, WIDTH - inset - 1, HEIGHT - inset - 1],
                            outline=(0, 0, 0, alpha))

    # Fade in/out
    if t < 1.0:
        overlay = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, int(255 * (1.0 - t))))
        img = Image.alpha_composite(img, overlay)
    elif t > 10.5:
        fa = int(255 * min(1.0, (t - 10.5) / 1.5))
        overlay = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, fa))
        img = Image.alpha_composite(img, overlay)

    return img


# ── Scene: Clearing (player walks, NPC guard, slime hops) ──────────────────

def render_clearing_scene(t, scene_t, room_base, subtitle_font, small_font):
    """t = global time, scene_t = time within this scene (0-based)."""
    img = room_base.copy()

    # NPC guard at tile (7, 2)
    guard_colors = {"helmet": "#8090a0", "armor": "#9aa8b8"}
    guard_layers = [
        ["helmet", 4, 0, 8, 2], ["SKIN", 5, 2, 6, 3], ["#222", 6, 3, 1, 1], ["#222", 9, 3, 1, 1],
        ["armor", 4, 5, 8, 6], ["PANTS", 5, 11, 6, 2], ["BOOTS", 5, 13, 2, 2], ["BOOTS", 9, 13, 2, 2],
    ]
    draw_sprite(img, guard_layers, guard_colors, 7 * TS, 2 * TS, "#c8383c")

    # Slime at tile (7, 8) — hopping
    hop_y = abs(math.sin(scene_t * 3)) * 8
    draw_monster(img, "slime", 7 * TS, int(8 * TS - hop_y))

    # Player walking from left to right across the clearing
    walk_speed = 1.8  # tiles per second
    player_tile_x = 2 + scene_t * walk_speed
    if player_tile_x > 12:
        player_tile_x = 12
    player_tile_y = 5
    anim_frame = int(scene_t * 4) % 2
    frame = PLAYER_RIGHT_0 if anim_frame == 0 else PLAYER_RIGHT_1
    draw_sprite(img, frame, {}, int(player_tile_x * TS), int(player_tile_y * TS), "#c8383c")

    # Speech bubble from guard
    if 1.0 < scene_t < 4.5:
        draw = ImageDraw.Draw(img)
        bx, by = 7 * TS + TS // 2, 2 * TS - 12
        bubble_w, bubble_h = 180, 28
        draw.rounded_rectangle([bx - bubble_w // 2, by - bubble_h,
                                 bx + bubble_w // 2, by],
                                radius=8, fill=(255, 255, 255, 230))
        # Tail
        draw.polygon([(bx - 5, by), (bx + 5, by), (bx, by + 8)],
                      fill=(255, 255, 255, 230))
        try:
            bf = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 14)
        except (OSError, IOError):
            bf = ImageFont.load_default()
        draw.text((bx - bubble_w // 2 + 8, by - bubble_h + 6),
                   "Watch out for slimes!", font=bf, fill=(40, 40, 40, 255))

    # Compose into full frame
    frame_img = compose_game_frame(img)

    # Scene label
    draw2 = ImageDraw.Draw(frame_img)
    if scene_t < 1.5:
        label_a = int(255 * min(1, scene_t / 0.5))
        draw_glow_text(draw2, "Sunlit Clearing", WIDTH // 2, GAME_Y - 30,
                        subtitle_font, WHITE, 4, label_a)

    return frame_img


# ── Scene: Dungeon (dark room, skeletons, player with lantern) ─────────────

def render_dungeon_scene(t, scene_t, room_base, subtitle_font, small_font):
    img = room_base.copy()

    # Skeletons
    sk_bob1 = math.sin(scene_t * 2) * 3
    sk_bob2 = math.sin(scene_t * 2 + 1) * 3
    draw_monster(img, "skeleton", 5 * TS, int(3 * TS + sk_bob1))
    draw_monster(img, "skeleton", 10 * TS, int(7 * TS + sk_bob2))

    # Bat flying in a circle
    bat_cx, bat_cy = 8 * TS, 5 * TS
    bat_r = 2.5 * TS
    bat_x = bat_cx + math.cos(scene_t * 1.5) * bat_r
    bat_y = bat_cy + math.sin(scene_t * 1.5) * bat_r * 0.6
    draw_monster(img, "bat", int(bat_x), int(bat_y))

    # Player with lantern light
    player_x = 3 + scene_t * 1.2
    if player_x > 11:
        player_x = 11
    player_y = 5
    px_px = int(player_x * TS)
    py_px = int(player_y * TS)
    anim_frame = int(scene_t * 4) % 2
    frame = PLAYER_RIGHT_0 if anim_frame == 0 else PLAYER_RIGHT_1
    draw_sprite(img, frame, {}, px_px, py_px, "#38a838")  # green shirt for variety

    # Lantern glow (yellowish light around player)
    glow_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    glow_cx = px_px + TS // 2
    glow_cy = py_px + TS // 2
    for r in range(int(3.5 * TS), 0, -3):
        alpha = int(30 * (r / (3.5 * TS)))
        glow_draw.ellipse([glow_cx - r, glow_cy - r, glow_cx + r, glow_cy + r],
                           fill=(255, 200, 80, alpha))
    img = Image.alpha_composite(img, glow_layer)

    # Dark overlay with light punch-through
    light_sources = [(glow_cx, glow_cy)]
    img = apply_darkness(img, light_sources, radius_tiles=3.5)

    # Compose
    frame_img = compose_game_frame(img)

    # Label
    draw2 = ImageDraw.Draw(frame_img)
    if scene_t < 1.5:
        la = int(255 * min(1, scene_t / 0.5))
        draw_glow_text(draw2, "The Dark Dungeon", WIDTH // 2, GAME_Y - 30,
                        subtitle_font, (200, 100, 100), 4, la)

    return frame_img


# ── Scene: Combat (player fighting slime, sword swing) ─────────────────────

def render_combat_scene(t, scene_t, room_base, subtitle_font, small_font):
    img = room_base.copy()

    # Slime (gets hit at scene_t ~2s)
    slime_alive = scene_t < 2.5
    slime_x, slime_y = 8, 5
    if slime_alive:
        hop_y = abs(math.sin(scene_t * 3)) * 8
        # Slime retreats slightly when player approaches
        if scene_t > 1.5:
            slime_x += (scene_t - 1.5) * 0.5
        draw_monster(img, "slime", int(slime_x * TS), int(slime_y * TS - hop_y))
    else:
        # Death splat - draw green goo
        draw = ImageDraw.Draw(img)
        goo_colors = [(0x44, 0xcc, 0x44), (0x22, 0x88, 0x22)]
        cx = int(slime_x * TS) + TS // 2
        cy = int(slime_y * TS) + TS // 2
        fade = max(0, 1.0 - (scene_t - 2.5) / 2.0)
        for i, gc in enumerate(goo_colors):
            a = int(200 * fade)
            r = 15 - i * 5
            draw.ellipse([cx - r - 10, cy - r + 5, cx + r + 10, cy + r + 5],
                          fill=(*gc, a))

    # Second slime for variety
    slime2_alive = scene_t < 3.5
    if slime2_alive:
        s2_hop = abs(math.sin(scene_t * 2.5 + 1)) * 8
        draw_monster(img, "slime", 10 * TS, int(7 * TS - s2_hop))

    # Player approaching and attacking
    player_x = 4 + min(scene_t * 1.5, 3.0)
    player_y = 5
    px_px = int(player_x * TS)
    py_px = int(player_y * TS)

    # Determine player frame & sword
    is_attacking = (1.8 < scene_t < 2.2) or (3.0 < scene_t < 3.4)
    anim_frame = int(scene_t * 4) % 2
    if scene_t < 1.8 or (2.5 < scene_t < 3.0):
        frame = PLAYER_RIGHT_0 if anim_frame == 0 else PLAYER_RIGHT_1
    else:
        frame = PLAYER_RIGHT_0

    draw_sprite(img, frame, {}, px_px, py_px, "#c8383c")

    # Sword slash effect
    if is_attacking:
        attack_progress = ((scene_t - 1.8) % 1.2) / 0.4
        # Sword arc
        draw = ImageDraw.Draw(img)
        sx = px_px + 12 * SCALE
        sy = py_px + 4 * SCALE
        slash_len = int(20 * SCALE * min(1, attack_progress * 2))
        # White slash line
        draw.line([(sx, sy), (sx + slash_len, sy + 2)],
                   fill=(255, 255, 255, 200), width=3)
        draw.line([(sx, sy + 4), (sx + slash_len - 4, sy + 6)],
                   fill=(200, 200, 220, 150), width=2)
        # Hit spark
        if attack_progress > 0.3:
            for _ in range(3):
                spark_x = sx + slash_len + random.randint(-5, 5)
                spark_y = sy + random.randint(-8, 8)
                draw.ellipse([spark_x - 2, spark_y - 2, spark_x + 2, spark_y + 2],
                              fill=(255, 255, 200, 200))

    # Damage number popup
    if 2.0 < scene_t < 2.8:
        draw = ImageDraw.Draw(img)
        pop_y = int(slime_y * TS - 20 - (scene_t - 2.0) * 30)
        pop_a = int(255 * max(0, 1.0 - (scene_t - 2.0) / 0.8))
        try:
            dmg_font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 18)
        except (OSError, IOError):
            dmg_font = ImageFont.load_default()
        draw.text((int(slime_x * TS) + 10, pop_y), "1", font=dmg_font, fill=(255, 60, 60, pop_a))

    # Compose
    frame_img = compose_game_frame(img)

    draw2 = ImageDraw.Draw(frame_img)
    if scene_t < 1.5:
        la = int(255 * min(1, scene_t / 0.5))
        draw_glow_text(draw2, "Battle!", WIDTH // 2, GAME_Y - 30,
                        subtitle_font, (255, 100, 100), 4, la)

    return frame_img


# ── Main video generation ──────────────────────────────────────────────────

def generate_video(output_path):
    random.seed(42)

    # Timeline:
    # 0-5:     Disclaimer card (no audio)
    # 5-17:    Title sequence
    # 17-24:   Clearing scene (7s)
    # 24-31:   Combat scene (7s)
    # 31-39:   Dungeon scene (8s)
    # 39-43:   End card + fade out
    DISC_DUR = 5       # disclaimer duration
    DURATION = 43
    TOTAL_FRAMES = FPS * DURATION

    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    out = cv2.VideoWriter(output_path, fourcc, FPS, (WIDTH, HEIGHT))
    if not out.isOpened():
        fourcc = cv2.VideoWriter_fourcc(*'MJPG')
        output_path = output_path.replace('.avi', '_mjpg.avi')
        out = cv2.VideoWriter(output_path, fourcc, FPS, (WIDTH, HEIGHT))

    # Fonts
    try:
        title_font = ImageFont.truetype("C:/Windows/Fonts/georgia.ttf", 72)
        subtitle_font = ImageFont.truetype("C:/Windows/Fonts/georgia.ttf", 28)
        small_font = ImageFont.truetype("C:/Windows/Fonts/georgia.ttf", 20)
    except (OSError, IOError):
        title_font = ImageFont.load_default()
        subtitle_font = title_font
        small_font = title_font

    # Pre-render room backgrounds
    print("Pre-rendering rooms...")
    clearing_base = render_room(CLEARING_MAP)
    dungeon_base = render_room(DUNGEON_MAP)

    # Title state
    stars = [Star() for _ in range(200)]
    particles = []

    print(f"Generating {TOTAL_FRAMES} frames ({DURATION}s) at {WIDTH}x{HEIGHT} @ {FPS}fps...")

    # Disclaimer font
    try:
        disc_font = ImageFont.truetype("C:/Windows/Fonts/georgia.ttf", 24)
        disc_font_sm = ImageFont.truetype("C:/Windows/Fonts/georgiaz.ttf", 20)
    except (OSError, IOError):
        disc_font = subtitle_font
        disc_font_sm = small_font

    for frame_num in range(TOTAL_FRAMES):
        t = frame_num / FPS

        # ── Disclaimer card (0 - DISC_DUR) ──
        if t < DISC_DUR:
            img = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 255))
            draw = ImageDraw.Draw(img)

            # Fade text in (0-1s), hold, fade out (last 0.8s)
            if t < 1.0:
                text_a = int(255 * (t / 1.0))
            elif t > DISC_DUR - 0.8:
                text_a = int(255 * ((DISC_DUR - t) / 0.8))
            else:
                text_a = 255

            line1 = "This trailer was entirely made by Claude"
            line2 = "with no human intervention."
            line3 = "It made up a lot of stuff."

            fill1 = (220, 220, 220, text_a)
            fill2 = (220, 220, 220, text_a)
            fill3 = (180, 180, 180, int(text_a * 0.8))

            for txt, font, fill, y_off in [
                (line1, disc_font, fill1, -30),
                (line2, disc_font, fill2, 5),
                (line3, disc_font_sm, fill3, 50),
            ]:
                bbox = draw.textbbox((0, 0), txt, font=font)
                tw = bbox[2] - bbox[0]
                draw.text(((WIDTH - tw) // 2, HEIGHT // 2 + y_off), txt, font=font, fill=fill)

        # ── Title sequence (DISC_DUR to DISC_DUR+12) ──
        elif t < DISC_DUR + 12.0:
            title_t = t - DISC_DUR
            img = render_title_frame(title_t, stars, particles, title_font, subtitle_font, small_font)

        # ── Clearing scene (17-24s) ──
        elif t < DISC_DUR + 19.0:
            scene_t = t - (DISC_DUR + 12.0)
            img = render_clearing_scene(t, scene_t, clearing_base, subtitle_font, small_font)
            # Crossfade from title
            if scene_t < 0.8:
                fade_a = int(255 * (1.0 - scene_t / 0.8))
                overlay = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, fade_a))
                img = Image.alpha_composite(img, overlay)

        # ── Combat scene (24-31s) ──
        elif t < DISC_DUR + 26.0:
            scene_t = t - (DISC_DUR + 19.0)
            img = render_combat_scene(t, scene_t, clearing_base, subtitle_font, small_font)
            # Crossfade
            if scene_t < 0.5:
                fade_a = int(200 * (1.0 - scene_t / 0.5))
                overlay = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, fade_a))
                img = Image.alpha_composite(img, overlay)

        # ── Dungeon scene (31-39s) ──
        elif t < DISC_DUR + 34.0:
            scene_t = t - (DISC_DUR + 26.0)
            img = render_dungeon_scene(t, scene_t, dungeon_base, subtitle_font, small_font)
            if scene_t < 0.8:
                fade_a = int(255 * (1.0 - scene_t / 0.8))
                overlay = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, fade_a))
                img = Image.alpha_composite(img, overlay)

        # ── End card (39-43s) ──
        else:
            end_t = t - (DISC_DUR + 34.0)
            img = Image.new('RGBA', (WIDTH, HEIGHT), (*DARK_BLUE, 255))
            draw = ImageDraw.Draw(img)
            # Gradient bg
            for yl in range(HEIGHT):
                bg = lerp_color(DARK_BLUE, DEEP_PURPLE, yl / HEIGHT)
                draw.line([(0, yl), (WIDTH, yl)], fill=(*bg, 255))

            # Stars (reuse)
            for star in stars:
                twinkle = 0.5 + 0.5 * math.sin(t * star.speed * 2 + star.phase)
                brightness = int(180 * star.brightness * twinkle)
                if brightness > 10:
                    draw.point((star.x, star.y), fill=(brightness, brightness, brightness + 20, brightness))

            text_a = int(255 * min(1, end_t / 1.0))
            draw_glow_text(draw, "LEGENDS  OF  AMARA", WIDTH // 2, int(HEIGHT * 0.35),
                            title_font, GOLD_BRIGHT, 10, text_a)
            draw_glow_text(draw, "Play Now at legendsofamara.com", WIDTH // 2, int(HEIGHT * 0.55),
                            subtitle_font, TEAL, 5, text_a)

            # Fade out at very end
            if end_t > 3.0:
                fo = int(255 * min(1, (end_t - 3.0) / 1.0))
                overlay = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, fo))
                img = Image.alpha_composite(img, overlay)

            # Fade in from dungeon
            if end_t < 0.8:
                fi = int(255 * (1.0 - end_t / 0.8))
                overlay = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, fi))
                img = Image.alpha_composite(img, overlay)

        # Convert to OpenCV frame
        rgb = img.convert('RGB')
        frame = np.array(rgb)
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        out.write(frame)

        if frame_num % (FPS * 2) == 0:
            print(f"  {int(t)}s / {DURATION}s")

    out.release()
    print(f"Video frames written to: {output_path}")
    return output_path


def mux_audio(video_path, audio_path, output_path):
    """Combine video and audio using ffmpeg from imageio-ffmpeg."""
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg_exe,
        "-y",                   # overwrite
        "-i", video_path,       # video input
        "-itsoffset", "5",      # delay audio by 5s (disclaimer is silent)
        "-i", audio_path,       # audio input
        "-c:v", "copy",         # copy video stream
        "-c:a", "aac",          # encode audio as AAC
        "-b:a", "192k",
        "-shortest",            # trim to shorter stream
        "-movflags", "+faststart",
        output_path
    ]
    print(f"Muxing audio: {audio_path}")
    print(f"  -> {output_path}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr[:500]}")
        # Try with re-encoding video for better container compat
        cmd2 = [
            ffmpeg_exe, "-y",
            "-i", video_path,
            "-itsoffset", "5",
            "-i", audio_path,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart",
            output_path
        ]
        print("Retrying with re-encode...")
        result2 = subprocess.run(cmd2, capture_output=True, text=True)
        if result2.returncode != 0:
            print(f"FFmpeg error (retry): {result2.stderr[:500]}")
            return None
    print("Audio muxed successfully!")
    return output_path


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    video_only = "tools/legends_of_amara_video.avi"
    generate_video(video_only)

    # Try to add music
    music_file = "music/overworld/overworld.mp3"
    if os.path.exists(music_file):
        final_output = "tools/legends_of_amara_trailer.mp4"
        result = mux_audio(video_only, music_file, final_output)
        if result:
            print(f"\n*** Final trailer: {final_output} ***")
            # Clean up intermediate
            # os.remove(video_only)  # keep for debugging
        else:
            print(f"\nAudio mux failed. Video-only at: {video_only}")
    else:
        print(f"\nNo music found at {music_file}. Video-only at: {video_only}")
