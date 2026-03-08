"""Generate TILE_SPRITE_DATA for tiles.js from the original tile algorithms.

Converts noise, bricks, grid lines, stripes, wave, and ripple patterns
into arrays of [colorKey, x, y, w, h] rect layers.
"""
import ctypes
import json


def seeded_rand(x, y, tile_id):
    h = ctypes.c_int32(x * 374761393 + y * 668265263 + tile_id * 1274126177).value
    h = ctypes.c_int32((h ^ (h >> 13)) * 1274126177).value
    return (h & 0x7fffffff) / 0x7fffffff


def merge_pixels_to_rects(color_key, pixels):
    """Merge 1x1 pixels into wider rects by scanning left-to-right per row."""
    if not pixels:
        return []
    pset = set(pixels)
    used = set()
    rects = []
    for py in range(16):
        px = 0
        while px < 16:
            if (px, py) in pset and (px, py) not in used:
                w = 1
                while px + w < 16 and (px + w, py) in pset and (px + w, py) not in used:
                    w += 1
                for i in range(w):
                    used.add((px + i, py))
                rects.append([color_key, px, py, w, 1])
                px += w
            else:
                px += 1
    return rects


def noise_rects(color_key, density, seed_id):
    pixels = []
    for py in range(16):
        for px in range(16):
            if seeded_rand(px, py, seed_id) < density:
                pixels.append((px, py))
    return merge_pixels_to_rects(color_key, pixels)


def swamp_rects(seed_id):
    """Three-color noise: water (<0.2), alt (0.2-0.5), base (>0.5)."""
    water_px, alt_px = [], []
    for py in range(16):
        for px in range(16):
            r = seeded_rand(px, py, seed_id)
            if r < 0.2:
                water_px.append((px, py))
            elif r < 0.5:
                alt_px.append((px, py))
            # else: base (already filled)
    return merge_pixels_to_rects("water", water_px) + merge_pixels_to_rects("alt", alt_px)


def brick_rects(color_key="alt"):
    """Brick mortar pattern: horizontal lines + offset vertical joints."""
    rects = []
    for row in range(0, 16, 4):
        offset = 0 if (row % 8 == 0) else 4
        for col in range(offset, 16, 8):
            rects.append([color_key, col, row, 1, 1])
        rects.append([color_key, 0, row + 3, 16, 1])
    return rects


def grid_rects(color_key="alt", spacing=4):
    rects = []
    for i in range(0, 16, spacing):
        rects.append([color_key, 0, i, 16, 1])
        rects.append([color_key, i, 0, 1, 16])
    return rects


def hstripe_rects(color_key="alt", spacing=4):
    return [[color_key, 0, i, 16, 1] for i in range(0, 16, spacing)]


def vstripe_rects(color_key="alt", spacing=3):
    return [[color_key, i, 0, 1, 16] for i in range(0, 16, spacing)]


def wave_rects(color_key="alt"):
    pixels = []
    for py in range(16):
        for px in range(16):
            if (px + py) % 4 < 2:
                pixels.append((px, py))
    return merge_pixels_to_rects(color_key, pixels)


def ripple_rects(color_key="alt"):
    pixels = []
    for py in range(16):
        for px in range(16):
            if (px + py) % 3 == 0:
                pixels.append((px, py))
    return merge_pixels_to_rects(color_key, pixels)


def rect(color_key, x, y, w, h):
    return [color_key, x, y, w, h]


# Build all 36 tiles
TILES = {}

# 0: grass
TILES[0] = noise_rects("alt", 0.25, 0)

# 1: stone
TILES[1] = grid_rects("alt", 4)

# 2: wood
TILES[2] = hstripe_rects("alt", 4)

# 3: wall_stone
TILES[3] = brick_rects("alt")

# 4: wall_wood
TILES[4] = vstripe_rects("alt", 3)

# 5: water
TILES[5] = wave_rects("alt")

# 6: tree
TILES[6] = [
    rect("trunk",    6, 10, 4, 6),
    rect("#2a7a2a",  2,  1, 12, 10),
    rect("alt",      3,  0, 10, 2),
    rect("alt",      1,  3,  2, 6),
    rect("alt",     13,  3,  2, 6),
    rect("#4a9a3a",  4,  2,  3, 2),
    rect("#4a9a3a",  8,  4,  4, 2),
]

# 7: flowers
TILES[7] = noise_rects("alt", 0.25, 7) + [
    rect("flower1", 4, 4, 2, 2),
    rect("flower2", 10, 8, 2, 2),
    rect("flower1", 6, 12, 2, 2),
    rect("flower2", 12, 4, 2, 2),
]

# 8: dirt
TILES[8] = noise_rects("alt", 0.25, 8)

# 9: stairs_up
TILES[9] = hstripe_rects("alt", 3) + [
    rect("#fff", 7, 3, 2, 8),
    rect("#fff", 5, 5, 2, 2),
    rect("#fff", 9, 5, 2, 2),
]

# 10: stairs_down
TILES[10] = hstripe_rects("alt", 3) + [
    rect("#fff", 7, 3, 2, 8),
    rect("#fff", 5, 9, 2, 2),
    rect("#fff", 9, 9, 2, 2),
]

# 11: anvil — stone floor base then anvil
TILES[11] = [
    rect("#9a9a9a", 0, 0, 16, 16),  # stone floor fill
    rect("#3a3a3a", 4, 6, 8, 4),
    rect("#3a3a3a", 3, 4, 10, 3),
    rect("#3a3a3a", 6, 3, 4, 2),
]

# 12: fireplace
TILES[12] = [
    rect("#3a2010", 0, 0, 16, 16),
    rect("flame", 4, 4, 3, 6),
    rect("flame", 8, 5, 3, 5),
    rect("#f83",  5, 6, 5, 4),
]

# 13: table — wood floor
TILES[13] = [
    rect("#8B6914", 0, 0, 16, 16),
    rect("base", 2, 2, 12, 12),
    rect("alt",  3, 3, 10, 10),
]

# 14: pew — stone floor
TILES[14] = [
    rect("#9a9a9a", 0, 0, 16, 16),
    rect("base", 2, 4, 12, 8),
    rect("alt",  2, 4, 12, 2),
]

# 15: door
TILES[15] = grid_rects("alt", 4)

# 16: sand
TILES[16] = noise_rects("alt", 0.3, 16)

# 17: cactus
TILES[17] = noise_rects("alt", 0.2, 17) + [
    rect("body",  6, 3, 4, 12),
    rect("body",  3, 5, 3, 3),
    rect("body", 10, 7, 3, 3),
    rect("spine", 7, 2, 2, 1),
    rect("spine", 4, 4, 1, 1),
    rect("spine",11, 6, 1, 1),
]

# 18: mountain
TILES[18] = [
    rect("alt",  0, 0, 16, 16),
    rect("base", 2, 4, 12, 12),
    rect("base", 4, 2, 8, 2),
    rect("base", 6, 0, 4, 2),
    rect("snow", 6, 0, 4, 2),
    rect("snow", 5, 2, 6, 1),
]

# 19: cave_floor
TILES[19] = noise_rects("alt", 0.3, 19)

# 20: swamp
TILES[20] = swamp_rects(20)

# 21: dead_tree
TILES[21] = noise_rects("alt", 0.2, 21) + [
    rect("trunk",   6, 6, 4, 10),
    rect("trunk",   5, 4, 6, 3),
    rect("branch",  3, 2, 3, 3),
    rect("branch", 10, 1, 3, 4),
    rect("branch",  4, 0, 2, 3),
    rect("branch", 11, 3, 2, 2),
]

# 22: bridge — water base first
TILES[22] = [
    rect("#2a6aaa", 0, 0, 16, 16),  # water fill
    rect("base", 2, 0, 12, 16),     # wood planks
]
# add horizontal stripes across the bridge
for i in range(0, 16, 3):
    TILES[22].append(rect("alt", 2, i, 12, 1))
# railings
TILES[22].extend([
    rect("plank", 2, 0, 1, 16),
    rect("plank", 13, 0, 1, 16),
])

# 23: gravestone — grass base + noise + stone
TILES[23] = [rect("#3a7a2a", 0, 0, 16, 16)] + \
    noise_rects("#2d6a1e", 0.2, 0) + [
    rect("stone",   5, 4, 6, 8),
    rect("stone",   6, 3, 4, 1),
    rect("#6a6a7a", 7, 5, 2, 1),
    rect("#6a6a7a", 6, 7, 4, 1),
]

# 24: iron_fence — grass base + noise + iron bars
TILES[24] = [rect("#3a7a2a", 0, 0, 16, 16)] + \
    noise_rects("#2d6a1e", 0.2, 0)
# iron bars
for i in range(1, 16, 3):
    TILES[24].append(rect("iron", i, 0, 1, 16))
TILES[24].extend([
    rect("iron", 0, 4, 16, 1),
    rect("iron", 0, 10, 16, 1),
])

# 25: ruins_wall
TILES[25] = brick_rects("alt") + [
    rect("#3a3a3a", 2, 1, 2, 2),
    rect("#3a3a3a",10, 8, 3, 2),
]

# 26: ruins_floor
TILES[26] = noise_rects("alt", 0.3, 26) + [
    rect("#5a5a4a", 3, 2, 1, 8),
    rect("#5a5a4a", 3,10, 6, 1),
    rect("#5a5a4a", 9, 5, 1, 6),
]

# 27: tall_grass
TILES[27] = noise_rects("alt", 0.25, 27)
# tall blade shapes on top
blades = [[2,2],[5,1],[8,3],[11,0],[14,2],[3,8],[7,7],[10,9],[13,6]]
for bx, by in blades:
    TILES[27].append(rect("tip", bx, by, 1, 4))

# 28: road
TILES[28] = noise_rects("alt", 0.2, 28) + [
    rect("#7a6a4a", 4, 0, 1, 16),
    rect("#7a6a4a",11, 0, 1, 16),
]

# 29: cliff
TILES[29] = [rect("face", 0, 0, 16, 8)]
for i in range(0, 16, 3):
    TILES[29].append(rect("alt", 0, i, 16, 1))
TILES[29].append(rect("#4a3a2a", 0, 8, 16, 2))

# 30: shallow_water
TILES[30] = ripple_rects("alt")

# 31: boulder — grass base + noise + rock
TILES[31] = noise_rects("#2d6a1e", 0.2, 0) + [
    rect("rock",    3, 4, 10, 8),
    rect("rock",    4, 3, 8, 1),
    rect("rock",    5,12, 6, 1),
    rect("rock2",   4, 5, 3, 3),
    rect("#8a8a8a", 8, 4, 3, 2),
]

# 32: dungeon_wall
TILES[32] = brick_rects("alt")

# 33: dungeon_floor
TILES[33] = noise_rects("alt", 0.3, 33) + [
    rect("#3a3a3a", 4, 3, 1, 6),
    rect("#3a3a3a", 4, 9, 5, 1),
    rect("#3a3a3a",10, 6, 1, 5),
]

# 34: pillar — dungeon floor base + pillar
TILES[34] = noise_rects("alt", 0.3, 33) + [
    rect("body", 5, 2, 6, 12),
    rect("body", 4, 3, 8, 10),
    rect("cap",  4, 2, 8, 2),
    rect("cap",  5, 1, 6, 1),
    rect("cap",  4,12, 8, 2),
]

# 35: sconce_wall — bricks + torch
TILES[35] = brick_rects("alt") + [
    rect("#5a5a5a", 6, 6, 4, 4),
    rect("#5a5a5a", 7,10, 2, 2),
    rect("flame",   7, 3, 2, 4),
    rect("#f83",    6, 4, 4, 2),
]


# Output as JavaScript
print("const TILE_SPRITE_DATA = {")
for tid in sorted(TILES.keys()):
    layers = TILES[tid]
    parts = []
    for layer in layers:
        ck, x, y, w, h = layer
        parts.append(f'["{ck}",{x},{y},{w},{h}]')

    # Format: multi-line for readability, ~4 rects per line
    lines = []
    for i in range(0, len(parts), 4):
        lines.append("    " + ", ".join(parts[i:i+4]) + ",")
    # remove trailing comma from last line
    if lines:
        lines[-1] = lines[-1].rstrip(",")

    name_comment = {
        0: "grass", 1: "stone", 2: "wood", 3: "wall_stone", 4: "wall_wood",
        5: "water", 6: "tree", 7: "flowers", 8: "dirt", 9: "stairs_up",
        10: "stairs_down", 11: "anvil", 12: "fireplace", 13: "table",
        14: "pew", 15: "door", 16: "sand", 17: "cactus", 18: "mountain",
        19: "cave_floor", 20: "swamp", 21: "dead_tree", 22: "bridge",
        23: "gravestone", 24: "iron_fence", 25: "ruins_wall", 26: "ruins_floor",
        27: "tall_grass", 28: "road", 29: "cliff", 30: "shallow_water",
        31: "boulder", 32: "dungeon_wall", 33: "dungeon_floor", 34: "pillar",
        35: "sconce_wall",
    }

    print(f"  {tid}: [ // {name_comment.get(tid, '')}")
    for line in lines:
        print(line)
    print("  ],")
print("};")
