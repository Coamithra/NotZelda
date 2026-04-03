# ---------------------------------------------------------------------------
# Dungeon layout templates — 8x8 grids where X = room, . = empty
# Each layout has a name, grid, and entrance cell (col, row)
# Inspired by original Zelda dungeon shapes
# ---------------------------------------------------------------------------

DUNGEON_LAYOUTS = [
    {
        # Eagle — wing tips with wide body (15 rooms)
        "name": "eagle",
        "grid": [
            "........",
            "XX...XX.",
            ".XXXXX..",
            "..XXX...",
            "..XXX...",
            "........",
            "........",
            "........",
        ],
        "entrance": (3, 4),
    },
    {
        # Fortress — solid rectangular keep (16 rooms)
        "name": "fortress",
        "grid": [
            "........",
            ".XXXX...",
            ".XXXX...",
            ".XXXX...",
            ".XXXX...",
            "........",
            "........",
            "........",
        ],
        "entrance": (2, 4),
    },
    {
        # Shield — broad top tapering down (15 rooms)
        "name": "shield",
        "grid": [
            "........",
            ".XXXXX..",
            ".XXXXX..",
            "..XXX...",
            "..XX....",
            "........",
            "........",
            "........",
        ],
        "entrance": (2, 4),
    },
    {
        # Hammer — wide head with sturdy handle (16 rooms)
        "name": "hammer",
        "grid": [
            "........",
            ".XXXXX..",
            ".XXXXX..",
            "...XX...",
            "...XX...",
            "...XX...",
            "........",
            "........",
        ],
        "entrance": (3, 5),
    },
    {
        # Lizard — offset body with thick limbs (15 rooms)
        "name": "lizard",
        "grid": [
            "........",
            "..XX....",
            ".XXXX...",
            ".XXXX...",
            "..XXX...",
            "..XX....",
            "........",
            "........",
        ],
        "entrance": (2, 5),
    },
    {
        # Dragon — S-curve body (16 rooms)
        "name": "dragon",
        "grid": [
            "........",
            ".XXX....",
            ".XXXX...",
            "..XXXX..",
            "...XXX..",
            "...XX...",
            "........",
            "........",
        ],
        "entrance": (3, 5),
    },
    {
        # Demon — wide oval head with chin (16 rooms)
        "name": "demon",
        "grid": [
            "........",
            "..XXXX..",
            ".XXXXXX.",
            "..XXXX..",
            "...XX...",
            "........",
            "........",
            "........",
        ],
        "entrance": (3, 4),
    },
    {
        # Lion — mane framing face (17 rooms)
        "name": "lion",
        "grid": [
            "........",
            ".XXXXX..",
            ".XX.XX..",
            ".XXXXX..",
            "..XXX...",
            "........",
            "........",
            "........",
        ],
        "entrance": (3, 4),
    },
    {
        # Death Mountain — diamond peak (16 rooms)
        "name": "death_mountain",
        "grid": [
            "........",
            "...XX...",
            "..XXXX..",
            "..XXXX..",
            "..XXXX..",
            "...XX...",
            "........",
            "........",
        ],
        "entrance": (3, 5),
    },
    {
        # Skull — cranium with eye sockets and jaw (17 rooms)
        "name": "skull",
        "grid": [
            "........",
            "..XXX...",
            ".XX.XX..",
            ".XXXXX..",
            "..XXX...",
            "..XX....",
            "........",
            "........",
        ],
        "entrance": (2, 5),
    },
    {
        # Axe — diamond head with handle (15 rooms)
        "name": "axe",
        "grid": [
            "........",
            "..XXX...",
            ".XXXXX..",
            "..XXX...",
            "...XX...",
            "...XX...",
            "........",
            "........",
        ],
        "entrance": (3, 5),
    },
    {
        # Crown — inverted taper, narrow top to wide base (16 rooms)
        "name": "crown",
        "grid": [
            "........",
            "..XXX...",
            "..XXX...",
            ".XXXXX..",
            ".XXXXX..",
            "........",
            "........",
            "........",
        ],
        "entrance": (3, 4),
    },
]

# ---------------------------------------------------------------------------
# Water temple layouts — 8x8 grids (~20-24 rooms)
# Inspired by aquatic/nautical shapes
# ---------------------------------------------------------------------------

D2_LAYOUTS = [
    {
        # Trident — three prongs with shaft (22 rooms)
        "name": "trident",
        "grid": [
            "X..X..X.",
            "X..X..X.",
            "X..X..X.",
            ".XXXXXX.",
            "...XX...",
            "...XX...",
            "...XX...",
            "........",
        ],
        "entrance": (3, 6),
    },
    {
        # Whirlpool — spiral inward (22 rooms)
        "name": "whirlpool",
        "grid": [
            "........",
            ".XXXXX..",
            ".X...X..",
            ".X.X.X..",
            ".X.XXX..",
            ".X......",
            ".XXXXXX.",
            "........",
        ],
        "entrance": (6, 6),
    },
    {
        # Anchor — nautical shape (21 rooms)
        "name": "anchor",
        "grid": [
            "...XX...",
            "..XXXX..",
            "...XX...",
            "...XX...",
            "...XX...",
            "..XXXX..",
            ".XX..XX.",
            "........",
        ],
        "entrance": (3, 0),
    },
    {
        # Depths — wide cavern (23 rooms)
        "name": "depths",
        "grid": [
            "........",
            "..XXXX..",
            ".XXXXXX.",
            ".XXXXXX.",
            "..XXXX..",
            "...XX...",
            "........",
            "........",
        ],
        "entrance": (3, 5),
    },
    {
        # Serpent — S-curve through water (21 rooms)
        "name": "serpent",
        "grid": [
            "........",
            ".XXX....",
            "..XXXX..",
            "....XXX.",
            ".XXX....",
            "..XXXX..",
            "....XX..",
            "........",
        ],
        "entrance": (1, 1),
    },
    {
        # Coral — branching reef (22 rooms)
        "name": "coral",
        "grid": [
            "........",
            "..XX.XX.",
            "..XXXXX.",
            "..XX....",
            ".XXXX...",
            ".XX.XX..",
            "....XX..",
            "........",
        ],
        "entrance": (4, 6),
    },
    {
        # Tidal Pool — enclosed basin (24 rooms)
        "name": "tidal_pool",
        "grid": [
            "........",
            ".XXXXXX.",
            ".X....X.",
            ".X.XX.X.",
            ".X.XX.X.",
            ".X....X.",
            ".XXXXXX.",
            "........",
        ],
        "entrance": (3, 6),
    },
    {
        # Jellyfish — bell with tentacles (22 rooms)
        "name": "jellyfish",
        "grid": [
            "..XXXX..",
            ".XXXXXX.",
            "..XXXX..",
            "..X..X..",
            ".X..X.X.",
            "X....X..",
            "........",
            "........",
        ],
        "entrance": (3, 4),
    },
    {
        # Shell — nautilus curve (20 rooms)
        "name": "shell",
        "grid": [
            "........",
            "..XXXX..",
            ".XX..XX.",
            ".X..XXX.",
            ".XX.XX..",
            "..XXX...",
            "...X....",
            "........",
        ],
        "entrance": (3, 6),
    },
    {
        # Wave — cresting water (22 rooms)
        "name": "wave",
        "grid": [
            "........",
            "X.......",
            "XX.XXX..",
            "XXXXXXX.",
            ".XXXXXXX",
            "..XXX.XX",
            ".......X",
            "........",
        ],
        "entrance": (0, 1),
    },
    {
        # Kraken — beast with arms (23 rooms)
        "name": "kraken",
        "grid": [
            "........",
            "..XXXX..",
            "..XXXX..",
            ".XXXXXX.",
            "XX....XX",
            "X......X",
            "........",
            "........",
        ],
        "entrance": (3, 3),
    },
    {
        # Abyss — deep vertical shaft (20 rooms)
        "name": "abyss",
        "grid": [
            ".XXXXXX.",
            "..XXXX..",
            "...XX...",
            "..XXXX..",
            "...XX...",
            "..XXXX..",
            ".XXXXXX.",
            "........",
        ],
        "entrance": (3, 6),
    },
]
