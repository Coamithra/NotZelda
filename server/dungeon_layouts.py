# ---------------------------------------------------------------------------
# Dungeon layout templates — 8x8 grids where X = room, . = empty
# Each layout has a name, grid, and entrance cell (col, row)
# Inspired by original Zelda dungeon shapes
# ---------------------------------------------------------------------------

DUNGEON_LAYOUTS = [
    {
        # Eagle — spread wings with body
        "name": "eagle",
        "grid": [
            "........",
            ".XXXXX..",
            "XXXXXXX.",
            "...X....",
            "..XXX...",
            ".XXXXX..",
            "XX...XX.",
            "........",
        ],
        "entrance": (3, 3),
    },
    {
        # Fortress — thick walled keep
        "name": "fortress",
        "grid": [
            ".XXXXX..",
            ".XXXXX..",
            ".XX.XX..",
            ".XXXXX..",
            ".XXXXX..",
            ".XX.XX..",
            ".XXXXX..",
            "........",
        ],
        "entrance": (2, 6),
    },
    {
        # Shield — broad defensive shape
        "name": "shield",
        "grid": [
            "XXXXXXX.",
            "XXXXXXX.",
            "XXXXXXX.",
            ".XXXXX..",
            ".XXXXX..",
            "..XXX...",
            "..XXX...",
            "...X....",
        ],
        "entrance": (3, 7),
    },
    {
        # Hammer — heavy head with handle
        "name": "hammer",
        "grid": [
            "XXXXXXX.",
            "XXXXXXX.",
            "XXXXXXX.",
            "...X....",
            "..XXX...",
            "..XXX...",
            "..XXX...",
            "........",
        ],
        "entrance": (3, 6),
    },
    {
        # Lizard — body with legs and tail
        "name": "lizard",
        "grid": [
            "..X.....",
            ".XXX....",
            "..XX....",
            ".XXXX...",
            "XXXXXX..",
            "..XX....",
            "..X.....",
            "..X.....",
        ],
        "entrance": (2, 7),
    },
    {
        # Dragon — large sprawling shape with thick body
        "name": "dragon",
        "grid": [
            ".XXXXX..",
            "XXXXXXX.",
            "XXXXXXX.",
            ".XXXXX..",
            "..XXX...",
            ".XXXXX..",
            "XX...XX.",
            "........",
        ],
        "entrance": (0, 6),
    },
    {
        # Demon — horned head shape
        "name": "demon",
        "grid": [
            "X.....X.",
            "XX...XX.",
            ".XXXXX..",
            ".XXXXX..",
            "..XXX...",
            "..XXX...",
            "...X....",
            "........",
        ],
        "entrance": (3, 6),
    },
    {
        # Lion — mane and face
        "name": "lion",
        "grid": [
            "XXXXXXX.",
            "X.XXX.X.",
            ".XXXXX..",
            ".XX.XX..",
            ".XXXXX..",
            "..XXX...",
            "...X....",
            "........",
        ],
        "entrance": (3, 6),
    },
    {
        # Death Mountain — large pyramid
        "name": "death_mountain",
        "grid": [
            "...X....",
            "..XXX...",
            ".XXXXX..",
            "XXXXXXX.",
            "XXXXXXX.",
            ".XXXXX..",
            "..XXX...",
            "...X....",
        ],
        "entrance": (3, 7),
    },
    {
        # Skull — skull shape
        "name": "skull",
        "grid": [
            "..XXXX..",
            ".XXXXXX.",
            ".XX..XX.",
            ".XXXXXX.",
            "..XXXX..",
            "...XX...",
            "..XXXX..",
            "........",
        ],
        "entrance": (3, 6),
    },
    {
        # Axe — broad head with handle
        "name": "axe",
        "grid": [
            "..XXXX..",
            ".XXXXXX.",
            ".XXXXXX.",
            "..XXXX..",
            "...XX...",
            "...XX...",
            "...XX...",
            "...XX...",
        ],
        "entrance": (3, 7),
    },
    {
        # Crown — royal crown shape
        "name": "crown",
        "grid": [
            "X..X..X.",
            "X..X..X.",
            "XX.X.XX.",
            "XXXXXXX.",
            ".XXXXX..",
            ".XXXXX..",
            "........",
            "........",
        ],
        "entrance": (0, 0),
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
