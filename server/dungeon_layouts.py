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
# Water temple layouts — 3x3 grids (5-9 rooms)
# ---------------------------------------------------------------------------

D2_LAYOUTS = [
    {
        "name": "trident",
        "grid": [
            "XXX.....",
            ".X......",
            "XXX.....",
            "........",
            "........",
            "........",
            "........",
            "........",
        ],
        "entrance": (1, 2),
    },
    {
        "name": "cross",
        "grid": [
            ".X......",
            "XXX.....",
            ".X......",
            "........",
            "........",
            "........",
            "........",
            "........",
        ],
        "entrance": (1, 2),
    },
    {
        "name": "bend",
        "grid": [
            "X.......",
            "XX......",
            "XXX.....",
            "........",
            "........",
            "........",
            "........",
            "........",
        ],
        "entrance": (0, 0),
    },
    {
        "name": "flood",
        "grid": [
            "XXX.....",
            "XXX.....",
            "XXX.....",
            "........",
            "........",
            "........",
            "........",
            "........",
        ],
        "entrance": (1, 2),
    },
    {
        "name": "depths",
        "grid": [
            "X.X.....",
            "X.X.....",
            "XXX.....",
            "........",
            "........",
            "........",
            "........",
            "........",
        ],
        "entrance": (1, 2),
    },
    {
        "name": "current",
        "grid": [
            "XX......",
            ".XX.....",
            "..X.....",
            "........",
            "........",
            "........",
            "........",
            "........",
        ],
        "entrance": (0, 0),
    },
]
