"""
tag_music.py — Update MP3 metadata for all game music tracks.

Sets artist, title, comment, and embeds a small pixel-art album cover
generated from actual game tile colors.

Usage:  python tools/tag_music.py
"""

import io, random, sys
from pathlib import Path
from PIL import Image, ImageDraw
from mutagen.id3 import ID3, TIT2, TPE1, COMM, APIC, ID3NoHeaderError

ROOT = Path(__file__).resolve().parent.parent
MUSIC = ROOT / "audio" / "music"

ARTIST = "Legends of Amara"
COMMENT = "Made with Suno"

# --- Tile colors from data/tiles.json ---
TILES = {
    "GR": ("#3a7a2a", "#2d6a1e"),   # grass
    "TR": ("#1a5a1a", "#2a6a2a"),   # tree
    "DW": ("#3a3a4a", "#2a2a3a"),   # dungeon wall
    "DF": ("#5a5a5a", "#4a4a4a"),   # dungeon floor
    "WA": ("#2a6aaa", "#3a7abb"),   # water
    "SH": ("#5a9acc", "#6aaadd"),   # shallow water
    "ST": ("#9a9a9a", "#8a8a8a"),   # stone
    "SA": ("#c8a85a", "#b89848"),   # sand
}

# --- 3x3 tile layouts for each theme ---
LAYOUTS = {
    "overworld": [
        ["TR", "GR", "TR"],
        ["GR", "ST", "GR"],
        ["TR", "GR", "TR"],
    ],
    "dungeon": [
        ["DW", "DW", "DW"],
        ["DW", "DF", "DW"],
        ["DW", "DF", "DW"],
    ],
    "boss": [
        ["DW", "DW", "DW"],
        ["DW", "DF", "DW"],
        ["DW", "DW", "DW"],
    ],
    "water": [
        ["WA", "SH", "WA"],
        ["SH", "WA", "SH"],
        ["WA", "SH", "WA"],
    ],
    "water_boss": [
        ["WA", "WA", "WA"],
        ["WA", "SH", "WA"],
        ["WA", "WA", "WA"],
    ],
    "cave": [
        ["DW", "ST", "DW"],
        ["ST", "DW", "ST"],
        ["DW", "ST", "DW"],
    ],
    "castle": [
        ["DW", "ST", "DW"],
        ["ST", "DF", "ST"],
        ["DW", "ST", "DW"],
    ],
    "desert": [
        ["SA", "SA", "ST"],
        ["SA", "ST", "SA"],
        ["ST", "SA", "SA"],
    ],
    "desert_boss": [
        ["SA", "SA", "SA"],
        ["SA", "ST", "SA"],
        ["SA", "SA", "SA"],
    ],
    "menu": [
        ["TR", "GR", "WA"],
        ["GR", "ST", "SH"],
        ["WA", "SH", "TR"],
    ],
}

CELL = 100       # pixels per tile cell
PX   = 7         # pixel-art block size (retro feel)
SIZE = CELL * 3  # 300x300 total


def _hex(c):
    """Parse #rrggbb to (r, g, b)."""
    return tuple(int(c[i:i+2], 16) for i in (1, 3, 5))


def _tint(rgb, tint_rgb, amount=0.35):
    """Blend rgb toward tint_rgb."""
    return tuple(int(a + (b - a) * amount) for a, b in zip(rgb, tint_rgb))


def _draw_tile(draw, ox, oy, tile_id, tint=None):
    """Draw one tile cell at pixel offset (ox, oy) with retro pixel blocks."""
    base_hex, alt_hex = TILES[tile_id]
    base = _hex(base_hex)
    alt  = _hex(alt_hex)
    if tint:
        base = _tint(base, tint)
        alt  = _tint(alt, tint)

    # Seed RNG per-cell for consistent pattern
    rng = random.Random(hash((ox, oy, tile_id)))

    for py in range(0, CELL, PX):
        for px in range(0, CELL, PX):
            color = alt if rng.random() < 0.3 else base
            draw.rectangle(
                [ox + px, oy + py, ox + px + PX - 1, oy + py + PX - 1],
                fill=color,
            )


def make_artwork(theme):
    """Generate a 300x300 pixel-art album cover for the given theme."""
    layout = LAYOUTS[theme]
    tint = None
    if theme == "boss":
        tint = (200, 40, 40)       # red tint for boss
    elif theme == "water_boss":
        tint = (180, 40, 60)       # reddish tint for water boss
    elif theme == "desert_boss":
        tint = (200, 60, 30)       # fiery orange tint for desert boss

    img = Image.new("RGB", (SIZE, SIZE))
    draw = ImageDraw.Draw(img)

    for row in range(3):
        for col in range(3):
            tile = layout[row][col]
            # Only tint the center tile for boss themes
            cell_tint = tint if (tint and row == 1 and col == 1) else None
            _draw_tile(draw, col * CELL, row * CELL, tile, cell_tint)

    # Draw subtle grid lines between tiles
    for i in range(1, 3):
        draw.line([(i * CELL, 0), (i * CELL, SIZE - 1)], fill=(0, 0, 0), width=1)
        draw.line([(0, i * CELL), (SIZE - 1, i * CELL)], fill=(0, 0, 0), width=1)

    return img


def img_to_bytes(img):
    """Convert PIL Image to PNG bytes."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --- Track definitions: (file_path, title, theme) ---
TRACKS = [
    # Overworld
    ("overworld/village.mp3",     "Village",               "overworld"),
    ("overworld/tavern.mp3",      "Tavern",                "overworld"),
    ("overworld/chapel.mp3",      "Chapel",                "overworld"),
    ("overworld/overworld.mp3",   "Overworld",             "overworld"),
    ("overworld/cave_marbles.mp3","Cave Marbles",            "cave"),
    ("overworld/castle_ruins.mp3","Castle Ruins",           "castle"),
    # Dark Dungeon — ambient
    ("dungeon1/dungeon_b.mp3",    "Dark Dungeon I",        "dungeon"),
    ("dungeon1/dungeon_d.mp3",    "Dark Dungeon II",       "dungeon"),
    ("dungeon1/dungeon_e.mp3",    "Dark Dungeon III",      "dungeon"),
    ("dungeon1/dungeon_f.mp3",    "Dark Dungeon IV",       "dungeon"),
    # Dark Dungeon — boss
    ("dungeon1/boss1.mp3",        "Boss Battle I",         "boss"),
    ("dungeon1/boss1_choir.mp3",  "Boss Battle I (Choir)", "boss"),
    ("dungeon1/boss2.mp3",        "Boss Battle II",        "boss"),
    ("dungeon1/boss2_choir.mp3",  "Boss Battle II (Choir)","boss"),
    ("dungeon1/boss3.mp3",        "Boss Battle III",       "boss"),
    ("dungeon1/boss3_choir.mp3",  "Boss Battle III (Choir)","boss"),
    # Water Temple — ambient
    ("dungeon2/watertemple_a.mp3",          "Water Temple I",              "water"),
    ("dungeon2/watertemple_b.mp3",          "Water Temple II",             "water"),
    ("dungeon2/watertemple_c.mp3",          "Water Temple III",            "water"),
    # Water Temple — boss
    ("dungeon2/watertemple_boss1.mp3",      "Water Temple Boss I",         "water_boss"),
    ("dungeon2/watertemple_boss1_choir.mp3","Water Temple Boss I (Choir)", "water_boss"),
    ("dungeon2/watertemple_boss2.mp3",      "Water Temple Boss II",        "water_boss"),
    ("dungeon2/watertemple_boss2_choir.mp3","Water Temple Boss II (Choir)","water_boss"),
    # Desert Tomb — ambient
    ("dungeon3/desert_a.mp3",     "Desert Tomb I",         "desert"),
    ("dungeon3/desert_b.mp3",     "Desert Tomb II",        "desert"),
    ("dungeon3/desert_c.mp3",     "Desert Tomb III",       "desert"),
    # Desert Tomb — boss
    ("dungeon3/desert_boss1.mp3",      "Desert Tomb Boss I",          "desert_boss"),
    ("dungeon3/desert_boss1_choir.mp3","Desert Tomb Boss I (Choir)",  "desert_boss"),
    ("dungeon3/desert_boss2.mp3",      "Desert Tomb Boss II",         "desert_boss"),
    ("dungeon3/desert_boss2_choir.mp3","Desert Tomb Boss II (Choir)", "desert_boss"),
    # Menu
    ("other/menu.mp3",            "Title Screen",          "menu"),
]


def tag_track(rel_path, title, theme, artwork_cache):
    """Set ID3 tags on a single MP3 file."""
    path = MUSIC / rel_path
    if not path.exists():
        print(f"  SKIP (missing): {rel_path}")
        return False

    # Get or create artwork for this theme
    if theme not in artwork_cache:
        artwork_cache[theme] = img_to_bytes(make_artwork(theme))
    art_data = artwork_cache[theme]

    # Load or create ID3 tags
    try:
        tags = ID3(str(path))
    except ID3NoHeaderError:
        tags = ID3()

    # Clear existing tags we're setting
    tags.delall("TIT2")
    tags.delall("TPE1")
    tags.delall("COMM")
    tags.delall("APIC")

    tags.add(TIT2(encoding=3, text=title))
    tags.add(TPE1(encoding=3, text=ARTIST))
    tags.add(COMM(encoding=3, lang="eng", desc="", text=COMMENT))
    tags.add(APIC(
        encoding=3,
        mime="image/png",
        type=3,  # Cover (front)
        desc="Cover",
        data=art_data,
    ))

    tags.save(str(path))
    return True


def main():
    # Optional: pass a filename fragment to tag just one track
    # Usage: python tools/tag_music.py desert_c
    filter_str = sys.argv[1] if len(sys.argv) > 1 else None
    to_tag = TRACKS
    if filter_str:
        to_tag = [(r, t, th) for r, t, th in TRACKS if filter_str in r]
        if not to_tag:
            print(f"No tracks matching '{filter_str}'")
            return

    print(f"Tagging {len(to_tag)} track(s)...\n")
    artwork_cache = {}
    ok = 0
    for rel_path, title, theme in to_tag:
        success = tag_track(rel_path, title, theme, artwork_cache)
        status = "OK" if success else "SKIP"
        print(f"  [{status}] {title:<30s}  ({rel_path})")
        if success:
            ok += 1

    print(f"\nDone: {ok}/{len(to_tag)} tracks tagged.")
    print(f"  Artist:  {ARTIST}")
    print(f"  Comment: {COMMENT}")
    print(f"  Artwork: {SIZE}x{SIZE}px pixel-art covers (6 themes)")

    # Save artwork previews so the user can see them
    preview_dir = ROOT / "tools" / "artwork_preview"
    preview_dir.mkdir(exist_ok=True)
    for theme in artwork_cache:
        img = make_artwork(theme)
        img.save(preview_dir / f"{theme}.png")
    print(f"\n  Artwork previews saved to tools/artwork_preview/")


if __name__ == "__main__":
    main()
