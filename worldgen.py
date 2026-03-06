"""
World generator — creates ~121 .room files for the overworld grid.

Run:  python worldgen.py
Output: rooms/*.room files

The 16x8 biome grid, MST connectivity, feature composition, NPC/monster placement.
"""

import os
import random
from pathlib import Path

random.seed(42)  # reproducible generation

ROOMS_DIR = Path(__file__).parent / "rooms"
ROOMS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# 16x8 biome grid (row, col) — "." means empty
# ---------------------------------------------------------------------------
# F=Forest M=Mountain D=Desert S=Swamp G=Graveyard C=Castle P=Plains L=Lake R=River
BIOME_GRID = [
    # Col: 0    1    2    3    4    5    6    7    8    9   10   11   12   13   14   15
    [".",  ".",  ".",  "M",  "M",  "F",  "F",  "F",  "F",  "F",  "F",  "G",  "G",  "G",  ".",  "."],   # Row 0
    [".",  ".",  "M",  "M",  "M",  "F",  "F",  "F",  "F",  "F",  "G",  "G",  "G",  "G",  ".",  "."],   # Row 1
    [".",  "M",  "M",  "M",  "P",  "P",  "F",  "P",  "P",  "P",  "P",  "P",  "G",  "G",  ".",  "."],   # Row 2
    ["D",  "D",  "D",  "D",  "P",  "P",  "R",  "R",  "R",  "P",  "P",  "S",  "S",  "S",  "S",  "."],   # Row 3
    ["D",  "D",  "D",  "D",  "P",  "L",  "L",  "L",  "L",  "P",  "S",  "S",  "S",  "S",  "S",  "."],   # Row 4
    ["D",  "D",  "D",  "P",  "P",  "L",  "L",  "L",  "P",  "P",  "S",  "S",  "S",  ".",  ".",  "."],   # Row 5
    [".",  "D",  "P",  "P",  "P",  "P",  "P",  "P",  "P",  "P",  "P",  "P",  "S",  ".",  ".",  "."],   # Row 6
    [".",  ".",  ".",  "P",  "P",  "P",  "C",  "C",  "C",  "C",  "P",  "P",  ".",  ".",  ".",  "."],   # Row 7
]

BIOME_FULL = {
    "F": "forest", "M": "mountain", "D": "desert", "S": "swamp",
    "G": "graveyard", "C": "castle", "P": "plains", "L": "lake",
    "R": "river",
}

# ---------------------------------------------------------------------------
# Tile code constants
# ---------------------------------------------------------------------------
GR = "GR"  # grass
ST = "ST"  # stone
WD = "WD"  # wood
WS = "WS"  # wall_stone
WW = "WW"  # wall_wood
WA = "WA"  # water
TR = "TR"  # tree
FL = "FL"  # flowers
DT = "DT"  # dirt
SU = "SU"  # stairs_up
SD = "SD"  # stairs_down
DR = "DR"  # door
AN = "AN"  # anvil
FP = "FP"  # fireplace
TB = "TB"  # table
PW = "PW"  # pew
SA = "SA"  # sand
CC = "CC"  # cactus
MT = "MT"  # mountain
CV = "CV"  # cave_floor
SM = "SM"  # swamp
DK = "DK"  # dead_tree
BR = "BR"  # bridge
GS = "GS"  # gravestone
IF = "IF"  # iron_fence
RW = "RW"  # ruins_wall
RF = "RF"  # ruins_floor
TG = "TG"  # tall_grass
RD = "RD"  # road
CL = "CL"  # cliff
SH = "SH"  # shallow_water
BO = "BO"  # boulder

COLS = 15
ROWS = 11

# Consolidated biome config — one dict to rule them all
BIOME_CONFIG = {
    "forest":    {"base": GR, "border": TR, "decor": [TR, FL, TG, BO], "walkable": [GR, FL, TG, DT], "music": "forest",    "monsters": ["slime", "slime"]},
    "mountain":  {"base": ST, "border": MT, "decor": [MT, BO, CL, ST], "walkable": [ST, CV, DT],      "music": "chapel",    "monsters": ["bat"]},
    "desert":    {"base": SA, "border": CC, "decor": [CC, BO, SA, SA], "walkable": [SA, DT, RD],      "music": "overworld",  "monsters": ["scorpion"]},
    "swamp":     {"base": SM, "border": DK, "decor": [DK, SH, SM, WA], "walkable": [SM, DT, SH],      "music": "overworld",  "monsters": ["swamp_blob", "swamp_blob"]},
    "graveyard": {"base": GR, "border": IF, "decor": [GS, DK, IF, GR], "walkable": [GR, DT, RD],      "music": "chapel",    "monsters": ["skeleton"]},
    "castle":    {"base": RF, "border": RW, "decor": [RW, RF, ST, BO], "walkable": [RF, ST, DT, RD],  "music": "tavern",    "monsters": ["skeleton", "bat"]},
    "plains":    {"base": GR, "border": TR, "decor": [FL, TG, BO, TR], "walkable": [GR, FL, TG, DT, RD], "music": "overworld", "monsters": ["slime"]},
    "lake":      {"base": WA, "border": GR, "decor": [WA, SH, GR, FL], "walkable": [GR, SH, BR, FL],  "music": "overworld",  "monsters": []},
    "river":     {"base": GR, "border": TR, "decor": [WA, SH, BR, GR], "walkable": [GR, DT, BR, RD],  "music": "overworld",  "monsters": ["slime"]},
}

# ---------------------------------------------------------------------------
# Name generation per biome
# ---------------------------------------------------------------------------
BIOME_NAME_PARTS = {
    "forest": {
        "adj": ["Verdant", "Mossy", "Shaded", "Ancient", "Dense", "Misty", "Quiet", "Twisted",
                "Deep", "Old", "Dim", "Hidden", "Tall", "Dark", "Wild", "Lush", "Silent", "Fern"],
        "noun": ["Grove", "Thicket", "Glade", "Wood", "Hollow", "Dell", "Copse", "Brake",
                 "Glen", "Trail", "Path", "Clearing", "Stand", "Canopy", "Shade", "Bower"],
    },
    "mountain": {
        "adj": ["Rocky", "Craggy", "Windswept", "Steep", "Frozen", "High", "Bare", "Iron",
                "Grey", "Cold", "Narrow", "Jagged", "Stone", "Peak", "Stark", "Lonely"],
        "noun": ["Pass", "Ridge", "Cliff", "Summit", "Ledge", "Crag", "Bluff", "Slope",
                 "Overlook", "Pinnacle", "Heights", "Ascent", "Plateau", "Shelf", "Face"],
    },
    "desert": {
        "adj": ["Scorching", "Barren", "Dusty", "Endless", "Sun-baked", "Dry", "Arid",
                "Golden", "Cracked", "Blazing", "Desolate", "Sandy", "Parched", "Red", "Vast"],
        "noun": ["Dunes", "Wastes", "Expanse", "Flats", "Basin", "Sands", "Mesa",
                 "Barrens", "Stretch", "Reach", "Badlands", "Plain", "Ridge", "Gulch"],
    },
    "swamp": {
        "adj": ["Murky", "Fetid", "Foggy", "Boggy", "Dark", "Sinking", "Rotting", "Damp",
                "Stagnant", "Gloomy", "Tangled", "Black", "Sunken", "Thick", "Mossy", "Oozing"],
        "noun": ["Bog", "Marsh", "Mire", "Fen", "Swamp", "Bayou", "Morass", "Quagmire",
                 "Pool", "Creek", "Slough", "Wetland", "Hollow", "Bottom", "Sink"],
    },
    "graveyard": {
        "adj": ["Haunted", "Forgotten", "Silent", "Cursed", "Ancient", "Crumbling", "Unholy",
                "Moonlit", "Cold", "Grey", "Withered", "Bleak", "Lonely", "Dark", "Lost"],
        "noun": ["Cemetery", "Graveyard", "Crypt", "Tombs", "Barrow", "Burial Grounds",
                 "Rest", "Yard", "Mausoleum", "Graves", "Necropolis", "Field", "Memorial"],
    },
    "castle": {
        "adj": ["Ruined", "Fallen", "Crumbling", "Ancient", "Dark", "Shattered", "Forsaken",
                "Grand", "Stone", "Mossy", "Silent", "Broken", "Lost", "Old", "Vast"],
        "noun": ["Keep", "Hall", "Court", "Gate", "Tower", "Chamber", "Ruins", "Walls",
                 "Corridor", "Throne Room", "Armory", "Ramparts", "Bailey", "Bastion"],
    },
    "plains": {
        "adj": ["Rolling", "Open", "Wide", "Gentle", "Green", "Windy", "Broad", "Sunny",
                "Golden", "Quiet", "Flat", "Wild", "Vast", "Peaceful", "Warm", "Tall"],
        "noun": ["Plains", "Fields", "Meadow", "Steppe", "Grassland", "Prairie", "Downs",
                 "Lea", "Heath", "Vale", "Pasture", "Flatland", "Expanse", "Green"],
    },
    "lake": {
        "adj": ["Crystal", "Tranquil", "Still", "Deep", "Azure", "Mirror", "Calm", "Sacred",
                "Blue", "Silver", "Clear", "Glassy", "Serene", "Cool", "Silent", "Wide"],
        "noun": ["Lake", "Shore", "Bank", "Waters", "Pool", "Lagoon", "Shallows", "Inlet",
                 "Coast", "Beach", "Landing", "Edge", "Depths", "Bay", "Cove"],
    },
    "river": {
        "adj": ["Rushing", "Winding", "Swift", "Broad", "Rocky", "Muddy", "Clear", "Deep"],
        "noun": ["River", "Ford", "Crossing", "Rapids", "Bank", "Bend", "Falls", "Stream"],
    },
}

used_names = set()

def gen_room_name(biome):
    parts = BIOME_NAME_PARTS.get(biome, BIOME_NAME_PARTS["plains"])
    for _ in range(50):
        name = f"{random.choice(parts['adj'])} {random.choice(parts['noun'])}"
        if name not in used_names:
            used_names.add(name)
            return name
    # Fallback with number
    name = f"{random.choice(parts['adj'])} {random.choice(parts['noun'])} {random.randint(1,99)}"
    used_names.add(name)
    return name

# ---------------------------------------------------------------------------
# Get all filled grid cells
# ---------------------------------------------------------------------------
def get_grid_rooms():
    """Return list of (row, col, biome) for all non-empty cells."""
    rooms = []
    for r in range(8):
        for c in range(16):
            b = BIOME_GRID[r][c]
            if b != ".":
                rooms.append((r, c, BIOME_FULL[b]))
    return rooms

def room_id(r, c):
    return f"ow_{r}_{c}"

# ---------------------------------------------------------------------------
# Connection graph — MST + probabilistic extras
# ---------------------------------------------------------------------------
def build_connections(rooms):
    """Build exit connections using MST + random extra edges."""
    cells = {(r, c) for r, c, _ in rooms}
    biome_at = {(r, c): b for r, c, b in rooms}

    # All possible edges between grid-adjacent cells
    all_edges = []
    for r, c in cells:
        for dr, dc, direction, reverse in [(0, 1, "east", "west"), (1, 0, "south", "north")]:
            nr, nc = r + dr, c + dc
            if (nr, nc) in cells:
                all_edges.append(((r, c), (nr, nc), direction, reverse))

    # Randomized Kruskal's MST
    parent = {cell: cell for cell in cells}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
            return True
        return False

    random.shuffle(all_edges)
    mst_edges = []
    extra_edges = []

    for a, b, d, rev in all_edges:
        if union(a, b):
            mst_edges.append((a, b, d, rev))
        else:
            extra_edges.append((a, b, d, rev))

    # Start with MST edges
    connections = {}  # (r,c) -> {direction: (nr, nc)}
    for cell in cells:
        connections[cell] = {}

    for a, b, d, rev in mst_edges:
        connections[a][d] = b
        connections[b][rev] = a

    # Add extra edges with probability based on position
    for a, b, d, rev in extra_edges:
        r_avg = (a[0] + b[0]) / 2
        c_avg = (a[1] + b[1]) / 2

        # Central rooms get more connections
        row_central = 2 <= r_avg <= 5
        col_central = 4 <= c_avg <= 10
        if row_central and col_central:
            prob = 0.70
        elif row_central or col_central:
            prob = 0.40
        else:
            prob = 0.15

        # Cross-biome borders are slightly harder to connect
        if biome_at[a] != biome_at[b]:
            prob *= 0.8

        if random.random() < prob:
            connections[a][d] = b
            connections[b][rev] = a

    return connections

# ---------------------------------------------------------------------------
# Tilemap generation
# ---------------------------------------------------------------------------
def make_tilemap(biome, exits):
    """Generate a 11x15 tilemap for a room with given biome and exits."""
    cfg = BIOME_CONFIG[biome]
    base = cfg["base"]
    border = cfg["border"]
    decor = cfg["decor"]
    walkable = cfg["walkable"]

    # Start with base fill
    tm = [[base for _ in range(COLS)] for _ in range(ROWS)]

    # Add border walls/trees on edges
    for c in range(COLS):
        tm[0][c] = border
        tm[ROWS-1][c] = border
    for r in range(ROWS):
        tm[r][0] = border
        tm[r][COLS-1] = border

    # Open exits (3-tile wide openings)
    if "north" in exits:
        for c in range(6, 9):
            tm[0][c] = DR if biome in ("castle",) else base
    if "south" in exits:
        for c in range(6, 9):
            tm[ROWS-1][c] = DR if biome in ("castle",) else base
    if "east" in exits:
        for r in range(4, 7):
            tm[r][COLS-1] = DR if biome in ("castle",) else base
    if "west" in exits:
        for r in range(4, 7):
            tm[r][0] = DR if biome in ("castle",) else base

    # Carve paths between exits using dirt/road
    exit_points = []
    if "north" in exits:
        exit_points.append((1, 7))
    if "south" in exits:
        exit_points.append((ROWS-2, 7))
    if "east" in exits:
        exit_points.append((5, COLS-2))
    if "west" in exits:
        exit_points.append((5, 1))

    path_tile = RD if biome in ("plains", "castle", "graveyard") else DT
    if biome == "desert":
        path_tile = SA
    elif biome == "swamp":
        path_tile = SM
    elif biome == "lake":
        path_tile = SH
    elif biome == "river":
        path_tile = GR

    # Connect all exits through center (5, 7)
    center = (5, 7)
    for er, ec in exit_points:
        # Vertical path from exit to center row
        r1, r2 = min(er, center[0]), max(er, center[0])
        for r in range(r1, r2 + 1):
            tm[r][ec] = path_tile
            if ec > 0 and tm[r][ec-1] == border:
                pass  # don't widen into border
            elif ec < COLS - 1:
                tm[r][min(ec+1, COLS-1)] = path_tile if random.random() < 0.3 else tm[r][min(ec+1, COLS-1)]

        # Horizontal path from exit column to center column
        c1, c2 = min(ec, center[1]), max(ec, center[1])
        for c in range(c1, c2 + 1):
            tm[center[0]][c] = path_tile

    # Scatter decoration
    for _ in range(random.randint(5, 15)):
        r = random.randint(1, ROWS-2)
        c = random.randint(1, COLS-2)
        if tm[r][c] == base:
            tile = random.choice(decor)
            tm[r][c] = tile

    # Lake/river rooms: fill interior with water, carve walkable shore
    if biome == "lake":
        for r in range(2, ROWS-2):
            for c in range(2, COLS-2):
                if tm[r][c] != SH and tm[r][c] not in (DR,):
                    tm[r][c] = WA
        # Shore around edges
        for r in range(1, ROWS-1):
            for c in range(1, COLS-1):
                if tm[r][c] == WA:
                    for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                        nr, nc = r+dr, c+dc
                        if 0 <= nr < ROWS and 0 <= nc < COLS and tm[nr][nc] in (border, base):
                            tm[r][c] = SH
                            break
        # Re-open exits with shallow water
        if "north" in exits:
            for c in range(6, 9):
                tm[1][c] = SH
                tm[2][c] = SH
        if "south" in exits:
            for c in range(6, 9):
                tm[ROWS-2][c] = SH
                tm[ROWS-3][c] = SH
        if "east" in exits:
            for r in range(4, 7):
                tm[r][COLS-2] = SH
                tm[r][COLS-3] = SH
        if "west" in exits:
            for r in range(4, 7):
                tm[r][1] = SH
                tm[r][2] = SH

    # River rooms: carve a river through the middle
    if biome == "river":
        river_c = 7
        for r in range(ROWS):
            for dc in range(-1, 2):
                c = river_c + dc + random.randint(-1, 1)
                c = max(1, min(c, COLS-2))
                if tm[r][c] not in (border,) or r == 0 or r == ROWS-1:
                    tm[r][c] = WA
            river_c += random.randint(-1, 1)
            river_c = max(3, min(river_c, COLS-4))
        # Add bridges at exits
        if "north" in exits or "south" in exits:
            for c in range(6, 9):
                for r in range(ROWS):
                    if tm[r][c] == WA:
                        tm[r][c] = BR

    return tm

# ---------------------------------------------------------------------------
# Place features (small tile patterns) on top of base tilemap
# ---------------------------------------------------------------------------
FEATURES = {
    "forest": [
        # Mushroom ring — 3x3 flowers in a circle
        {"name": "mushroom_ring", "w": 3, "h": 3, "tiles": [
            [FL, GR, FL],
            [GR, FL, GR],
            [FL, GR, FL],
        ]},
        # Fallen log
        {"name": "fallen_log", "w": 5, "h": 2, "tiles": [
            [GR, BO, BO, BO, GR],
            [GR, GR, TG, GR, GR],
        ]},
        # Dense thicket
        {"name": "dense_thicket", "w": 3, "h": 3, "tiles": [
            [TR, TR, TR],
            [TR, TG, TR],
            [TR, TR, TR],
        ]},
    ],
    "mountain": [
        # Boulder field
        {"name": "boulder_field", "w": 4, "h": 3, "tiles": [
            [BO, ST, BO, ST],
            [ST, BO, ST, BO],
            [BO, ST, BO, ST],
        ]},
        # Cave mouth
        {"name": "cave_mouth", "w": 3, "h": 3, "tiles": [
            [MT, MT, MT],
            [MT, CV, MT],
            [ST, CV, ST],
        ]},
    ],
    "desert": [
        # Cactus grove
        {"name": "cactus_grove", "w": 4, "h": 3, "tiles": [
            [SA, CC, SA, CC],
            [CC, SA, CC, SA],
            [SA, CC, SA, SA],
        ]},
        # Bones
        {"name": "bones", "w": 3, "h": 2, "tiles": [
            [SA, SA, SA],
            [SA, SA, SA],  # just sand (no bone tile), but marks a spot
        ]},
    ],
    "swamp": [
        # Bubbling pool
        {"name": "bubbling_pool", "w": 3, "h": 3, "tiles": [
            [SM, SH, SM],
            [SH, WA, SH],
            [SM, SH, SM],
        ]},
        # Dead grove
        {"name": "dead_grove", "w": 3, "h": 3, "tiles": [
            [DK, SM, DK],
            [SM, SM, SM],
            [DK, SM, DK],
        ]},
    ],
    "graveyard": [
        # Grave rows
        {"name": "grave_rows", "w": 5, "h": 3, "tiles": [
            [GS, GR, GS, GR, GS],
            [GR, GR, GR, GR, GR],
            [GS, GR, GS, GR, GS],
        ]},
        # Iron gate
        {"name": "iron_gate", "w": 5, "h": 2, "tiles": [
            [IF, IF, DR, IF, IF],
            [GR, GR, GR, GR, GR],
        ]},
    ],
    "castle": [
        # Crumbling hall
        {"name": "crumbling_hall", "w": 5, "h": 3, "tiles": [
            [RW, RF, RF, RF, RW],
            [RF, RF, RF, RF, RF],
            [RW, RF, RF, RF, RW],
        ]},
        # Collapsed wall
        {"name": "collapsed_wall", "w": 4, "h": 2, "tiles": [
            [RW, BO, RW, RW],
            [RF, RF, BO, RF],
        ]},
    ],
    "plains": [
        # Stone circle
        {"name": "stone_circle", "w": 3, "h": 3, "tiles": [
            [GR, BO, GR],
            [BO, FL, BO],
            [GR, BO, GR],
        ]},
        # Wildflower field
        {"name": "wildflower_field", "w": 4, "h": 3, "tiles": [
            [FL, TG, FL, TG],
            [TG, FL, TG, FL],
            [FL, TG, FL, TG],
        ]},
    ],
    "lake": [
        # Dock
        {"name": "dock", "w": 3, "h": 4, "tiles": [
            [GR, WD, GR],
            [SH, WD, SH],
            [WA, WD, WA],
            [WA, WD, WA],
        ]},
    ],
    "river": [
        # Ford crossing
        {"name": "ford", "w": 5, "h": 3, "tiles": [
            [GR, GR, BR, GR, GR],
            [WA, WA, BR, WA, WA],
            [GR, GR, BR, GR, GR],
        ]},
    ],
}

def place_feature(tm, feature):
    """Try to place a feature at a random position. Returns True if placed."""
    fw, fh = feature["w"], feature["h"]
    for _ in range(20):
        r = random.randint(2, ROWS - 2 - fh)
        c = random.randint(2, COLS - 2 - fw)
        # Check area is base tile (no paths or exits)
        ok = True
        for fr in range(fh):
            for fc in range(fw):
                tile = tm[r+fr][c+fc]
                if tile in (DR, RD, DT, BR, SU, SD):
                    ok = False
                    break
            if not ok:
                break
        if ok:
            for fr in range(fh):
                for fc in range(fw):
                    tm[r+fr][c+fc] = feature["tiles"][fr][fc]
            return True
    return False


# ---------------------------------------------------------------------------
# NPC data
# ---------------------------------------------------------------------------
NPCS = {
    (0, 7):  ("Ranger", "ranger", "Stay on the roads if you value your life."),
    (1, 3):  ("Mountain_Hermit", "elder", "The caves below hold ancient secrets."),
    (3, 1):  ("Desert_Nomad", "nomad", "Water is scarce. The oasis lies to the south."),
    (4, 11): ("Swamp_Witch", "witch", "Beware the deep waters. Not all who sink are found."),
    (1, 12): ("Ghost", "ghost", "This land was not always dead. The castle fell, and darkness spread."),
    (7, 6):  ("Castle_Guardian", "guard", "None shall pass... oh wait, the door's already broken."),
}

# ---------------------------------------------------------------------------
# Interior rooms
# ---------------------------------------------------------------------------
def make_interior_rooms():
    """Create special interior rooms (caves, oasis, witch hut)."""
    interiors = []

    # Cave Interior 1 — accessed from a mountain room
    interiors.append({
        "id": "cave_interior_1",
        "name": "Crystal Cavern",
        "biome": "cave",
        "music": "chapel",
        "exits": {"up": "ow_1_3"},  # connected to mountain hermit room
        "tilemap": make_cave_tilemap(),
        "monsters": [("bat", 4, 3), ("bat", 10, 7)],
        "npcs": [],
    })

    # Cave Interior 2
    interiors.append({
        "id": "cave_interior_2",
        "name": "Deep Tunnels",
        "biome": "cave",
        "music": "chapel",
        "exits": {"up": "ow_0_4"},
        "tilemap": make_cave_tilemap(),
        "monsters": [("bat", 5, 5), ("bat", 9, 4), ("bat", 7, 8)],
        "npcs": [],
    })

    # Desert Oasis Interior
    interiors.append({
        "id": "desert_oasis",
        "name": "Hidden Oasis",
        "biome": "desert",
        "music": "overworld",
        "exits": {"up": "ow_5_2"},
        "tilemap": make_oasis_tilemap(),
        "monsters": [],
        "npcs": [("Oasis_Keeper", 7, 3, "elder", "Rest here, traveler. The desert shows no mercy.")],
    })

    # Swamp Witch Hut Interior
    interiors.append({
        "id": "swamp_hut",
        "name": "Witch's Hut",
        "biome": "swamp",
        "music": "chapel",
        "exits": {"up": "ow_4_11"},
        "tilemap": make_hut_tilemap(),
        "monsters": [],
        "npcs": [("Witch", 7, 4, "witch", "Eye of newt, wing of bat... oh, a visitor!")],
    })

    return interiors


def make_cave_tilemap():
    tm = [[MT for _ in range(COLS)] for _ in range(ROWS)]
    # Carve out cave interior
    for r in range(2, ROWS-2):
        for c in range(2, COLS-2):
            tm[r][c] = CV
    # Rough edges
    for r in range(1, ROWS-1):
        for c in range(1, COLS-1):
            if tm[r][c] == MT and random.random() < 0.3:
                tm[r][c] = CV
    # Stairs up
    tm[5][7] = SU
    return tm


def make_oasis_tilemap():
    tm = [[SA for _ in range(COLS)] for _ in range(ROWS)]
    # Border of cacti
    for c in range(COLS):
        tm[0][c] = CC
        tm[ROWS-1][c] = CC
    for r in range(ROWS):
        tm[r][0] = CC
        tm[r][COLS-1] = CC
    # Central oasis pool
    for r in range(3, 8):
        for c in range(5, 10):
            tm[r][c] = WA
    for r in range(4, 7):
        for c in range(4, 11):
            if tm[r][c] == SA:
                tm[r][c] = SH
    # Path and stairs
    tm[5][7] = SU
    tm[1][7] = SA
    tm[2][7] = SA
    # Some flowers (oasis greenery)
    tm[2][5] = FL
    tm[2][9] = FL
    tm[8][6] = FL
    tm[8][8] = FL
    return tm


def make_hut_tilemap():
    tm = [[WW for _ in range(COLS)] for _ in range(ROWS)]
    # Wood floor interior
    for r in range(1, ROWS-1):
        for c in range(1, COLS-1):
            tm[r][c] = WD
    # Furniture
    tm[2][2] = TB
    tm[2][3] = TB
    tm[8][12] = FP
    tm[8][11] = FP
    # Stairs
    tm[5][7] = SU
    return tm


# ---------------------------------------------------------------------------
# Flood fill validation
# ---------------------------------------------------------------------------
def validate_connectivity(connections, start):
    """Verify all rooms are reachable from start via BFS."""
    visited = set()
    queue = [start]
    visited.add(start)
    while queue:
        current = queue.pop(0)
        for d, neighbor in connections.get(current, {}).items():
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return visited


# ---------------------------------------------------------------------------
# Write .room file
# ---------------------------------------------------------------------------
def write_room_file(room_id, name, biome, music, exits, tilemap, npcs=None, monsters=None):
    """Write a single .room file."""
    lines = []
    lines.append(f"name: {name}")
    lines.append(f"biome: {biome}")
    lines.append(f"music: {music}")
    exit_str = " ".join(f"{d}={t}" for d, t in exits.items())
    lines.append(f"exits: {exit_str}")
    lines.append("---")
    for row in tilemap:
        lines.append(" ".join(row))
    lines.append("---")
    if npcs:
        for npc in npcs:
            if len(npc) == 5:
                npc_name, nx, ny, npc_sprite, dialog = npc
            elif len(npc) == 4:
                npc_name, nx, ny, dialog = npc
                npc_sprite = "guard"
            else:
                npc_name, nx, ny, npc_sprite, dialog = npc[0], npc[1], npc[2], "guard", npc[3]
            lines.append(f"npc {npc_name} {nx} {ny} {npc_sprite} {dialog}")
    if monsters:
        for m in monsters:
            kind, mx, my = m
            lines.append(f"monster {kind} {mx} {my}")

    filepath = ROOMS_DIR / f"{room_id}.room"
    filepath.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------
def generate():
    print("Generating overworld rooms...")

    grid_rooms = get_grid_rooms()
    print(f"  Grid cells: {len(grid_rooms)}")

    # Build connection graph
    connections = build_connections(grid_rooms)

    # Validate connectivity from ow_0_7 (the village gate room)
    all_cells = {(r, c) for r, c, _ in grid_rooms}
    reachable = validate_connectivity(connections, (0, 7))
    unreachable = all_cells - reachable
    if unreachable:
        print(f"  WARNING: {len(unreachable)} unreachable rooms! Re-running with different seed...")
        # Force-connect unreachable rooms
        for cell in unreachable:
            # Find nearest reachable neighbor
            r, c = cell
            for dr, dc, d, rev in [(0,1,"east","west"),(0,-1,"west","east"),(1,0,"south","north"),(-1,0,"north","south")]:
                nr, nc = r+dr, c+dc
                if (nr, nc) in reachable:
                    connections[cell][d] = (nr, nc)
                    connections[(nr, nc)][rev] = cell
                    reachable.add(cell)
                    break

    print(f"  Reachable rooms: {len(reachable)}")

    # Count connections
    total_edges = sum(len(v) for v in connections.values()) // 2
    print(f"  Total connections: {total_edges}")

    # Generate each grid room
    biome_at = {(r, c): b for r, c, b in grid_rooms}
    room_count = 0

    for r, c, biome in grid_rooms:
        rid = room_id(r, c)
        exits = {}
        for d, target_cell in connections[(r, c)].items():
            exits[d] = room_id(*target_cell)

        # Special: ow_0_7 connects north to clearing
        if (r, c) == (0, 7):
            exits["north"] = "clearing"

        # Generate tilemap
        tm = make_tilemap(biome, exits)

        # Place features
        biome_features = FEATURES.get(biome, [])
        if biome_features:
            num_features = random.randint(1, min(3, len(biome_features)))
            selected = random.sample(biome_features, num_features)
            for feat in selected:
                place_feature(tm, feat)

        # Room name
        name = gen_room_name(biome)

        # Music
        music = BIOME_CONFIG.get(biome, {}).get("music", "overworld")

        # NPCs
        npcs = []
        if (r, c) in NPCS:
            npc_name, npc_sprite, dialog = NPCS[(r, c)]
            npcs.append((npc_name, 7, 3, npc_sprite, dialog))

        # Monsters — place based on biome
        room_monsters = []
        monster_kinds = BIOME_CONFIG.get(biome, {}).get("monsters", [])
        if monster_kinds and random.random() < 0.6:  # 60% chance room has monsters
            num = random.randint(1, min(3, len(monster_kinds) + 1))
            for _ in range(num):
                kind = random.choice(monster_kinds)
                # Find a walkable spot
                for __ in range(20):
                    mx = random.randint(2, COLS-3)
                    my = random.randint(2, ROWS-3)
                    if tm[my][mx] in (GR, SA, SM, RF, CV, DT, RD, TG, FL, SH):
                        room_monsters.append((kind, mx, my))
                        break

        # Add stairs down for rooms that connect to interiors
        if (r, c) == (1, 3):
            # Mountain hermit room → cave_interior_1
            exits["down"] = "cave_interior_1"
            tm[8][7] = SD
        elif (r, c) == (0, 4):
            exits["down"] = "cave_interior_2"
            tm[8][7] = SD
        elif (r, c) == (5, 2):
            exits["down"] = "desert_oasis"
            tm[8][7] = SD
        elif (r, c) == (4, 11):
            exits["down"] = "swamp_hut"
            tm[8][7] = SD

        write_room_file(rid, name, biome, music, exits, tm, npcs, room_monsters)
        room_count += 1

    # Generate interior rooms
    interiors = make_interior_rooms()
    for interior in interiors:
        write_room_file(
            interior["id"], interior["name"], interior["biome"],
            interior["music"], interior["exits"], interior["tilemap"],
            interior.get("npcs", []), interior.get("monsters", []),
        )
        room_count += 1

    # Also update the parent rooms to connect back
    # (already handled by exits dict in the grid room generation above)

    print(f"  Generated {room_count} room files in {ROOMS_DIR}/")

    # Summary stats
    biome_counts = {}
    for _, _, b in grid_rooms:
        biome_counts[b] = biome_counts.get(b, 0) + 1
    print("\n  Biome distribution:")
    for b, cnt in sorted(biome_counts.items()):
        print(f"    {b:12s}: {cnt}")

    print(f"\n  Total rooms (grid + interiors): {room_count}")
    print(f"  + 7 village rooms = {room_count + 7} total")

    return connections, biome_at


if __name__ == "__main__":
    connections, biome_at = generate()
    print("\nDone! Room files written to rooms/")
