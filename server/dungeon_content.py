"""Precreated dungeon content — monsters, tiles, and room library entries.

All precreated content is defined here as data dicts and loaded into the
content libraries at startup as permanent entries. This is the single source
of truth for dungeon base content — no hardcoded content elsewhere.

The AI prompt sees these entries alongside custom (AI-generated) entries
with no distinction.
"""

from pathlib import Path

from server.content_library import LibraryEntry, ContentLibrary
from server.constants import TILE_CODES, WALKABLE_TILES, ROOM_COLS, ROOM_ROWS

# ---------------------------------------------------------------------------
# Reverse map: numeric tile ID -> 2-char string code (for room conversion)
# ---------------------------------------------------------------------------

_TILE_ID_TO_CODE = {v: k for k, v in TILE_CODES.items()}

# ---------------------------------------------------------------------------
# Precreated monsters (4)
# ---------------------------------------------------------------------------

PRECREATED_MONSTERS = [
    {
        "kind": "skeleton",
        "tags": ["undead", "melee", "dungeon"],
        "stats": {"hp": 2, "tick_rate": 0.5, "damage": 3},
        "behavior": {"rules": [
            {"if": "player_within", "range": 5, "do": "move", "direction": "player"},
            {"if": "always", "do": "move", "direction": "random"},
        ]},
        "sprite": {
            "colors": {"bone": "#ddd8cc", "dark": "#aaa89a", "eyes": "#222222"},
            "yOff": [0, -1],
            "frames": [
                [
                    ["bone", 5, 1, 6, 5], ["eyes", 6, 3, 2, 2], ["eyes", 9, 3, 2, 2],
                    ["eyes", 7, 5, 2, 1], ["bone", 6, 6, 4, 5], ["dark", 7, 7, 2, 1],
                    ["dark", 7, 9, 2, 1], ["bone", 4, 7, 2, 1], ["bone", 3, 8, 1, 3],
                    ["bone", 10, 7, 2, 1], ["bone", 12, 8, 1, 3], ["bone", 6, 11, 2, 3],
                    ["bone", 9, 11, 2, 3], ["dark", 5, 14, 3, 1], ["dark", 9, 14, 3, 1],
                ],
                [
                    ["bone", 5, 1, 6, 5], ["eyes", 6, 3, 2, 2], ["eyes", 9, 3, 2, 2],
                    ["eyes", 7, 5, 2, 1], ["bone", 6, 6, 4, 5], ["dark", 7, 7, 2, 1],
                    ["dark", 7, 9, 2, 1], ["bone", 4, 7, 2, 1], ["bone", 3, 8, 1, 3],
                    ["bone", 10, 7, 2, 1], ["bone", 12, 8, 1, 3], ["bone", 6, 11, 2, 3],
                    ["bone", 9, 11, 2, 3], ["dark", 5, 14, 3, 1], ["dark", 9, 14, 3, 1],
                ],
            ],
        },
        "death_sprite": {
            "colors": {"clr": "#ddd8cc"},
            "frames": [
                [["clr", 3, 11, 10, 3], ["clr", 5, 10, 6, 1]],
                [["clr", 1, 12, 3, 2], ["clr", 5, 13, 2, 1], ["clr", 8, 11, 3, 2], ["clr", 12, 13, 3, 1]],
                {"alpha": 0.4, "layers": [["clr", 0, 13, 2, 1], ["clr", 6, 14, 2, 1], ["clr", 13, 13, 2, 1]]},
            ],
        },
    },
    {
        "kind": "bat",
        "tags": ["cave", "flying", "dungeon"],
        "stats": {"hp": 1, "tick_rate": 1.0, "damage": 1},
        "behavior": {"rules": [
            {"if": "always", "do": "move", "direction": "random"},
        ]},
        "sprite": {
            "colors": {"body": "#3a2a4a", "wing": "#5a3a6a", "eyes": "#ff4444"},
            "frames": [
                [
                    ["body", 6, 6, 4, 4], ["wing", 1, 3, 5, 4], ["wing", 10, 3, 5, 4],
                    ["wing", 2, 2, 3, 1], ["wing", 11, 2, 3, 1],
                    ["eyes", 6, 7, 1, 1], ["eyes", 9, 7, 1, 1],
                ],
                [
                    ["body", 6, 5, 4, 4], ["wing", 1, 7, 5, 4], ["wing", 10, 7, 5, 4],
                    ["wing", 2, 11, 3, 1], ["wing", 11, 11, 3, 1],
                    ["eyes", 6, 6, 1, 1], ["eyes", 9, 6, 1, 1],
                ],
            ],
        },
        "death_sprite": {
            "colors": {"clr": "#3a2a4a"},
            "frames": [
                [["clr", 3, 11, 10, 3], ["clr", 5, 10, 6, 1]],
                [["clr", 1, 12, 3, 2], ["clr", 5, 13, 2, 1], ["clr", 8, 11, 3, 2], ["clr", 12, 13, 3, 1]],
                {"alpha": 0.4, "layers": [["clr", 0, 13, 2, 1], ["clr", 6, 14, 2, 1], ["clr", 13, 13, 2, 1]]},
            ],
        },
    },
    {
        "kind": "dungeon_slime",
        "tags": ["dungeon", "melee", "tank"],
        "stats": {"hp": 3, "tick_rate": 0.4, "damage": 1},
        "behavior": {"rules": [
            {"if": "player_within", "range": 4, "do": "move", "direction": "player", "speed": 2},
            {"if": "always", "do": "move", "direction": "random", "speed": 2},
        ]},
        "sprite": {
            "colors": {"body": "#5a4a6a", "dark": "#3a2a4a", "eyes": "#cc4444", "highlight": "#8a7a9a"},
            "frames": [
                [
                    ["dark", 2, 9, 12, 6], ["body", 3, 8, 10, 6], ["body", 4, 7, 8, 1],
                    ["eyes", 5, 9, 2, 2], ["eyes", 9, 9, 2, 2], ["highlight", 5, 8, 2, 1],
                ],
                [
                    ["dark", 4, 12, 8, 2], ["body", 4, 4, 8, 9], ["body", 5, 3, 6, 1],
                    ["body", 5, 13, 6, 1], ["dark", 4, 11, 8, 2],
                    ["eyes", 5, 6, 2, 2], ["eyes", 9, 6, 2, 2], ["highlight", 5, 4, 2, 1],
                ],
            ],
        },
        "death_sprite": {
            "colors": {"clr": "#5a4a6a"},
            "frames": [
                [["clr", 3, 11, 10, 3], ["clr", 5, 10, 6, 1]],
                [["clr", 1, 12, 3, 2], ["clr", 5, 13, 2, 1], ["clr", 8, 11, 3, 2], ["clr", 12, 13, 3, 1]],
                {"alpha": 0.4, "layers": [["clr", 0, 13, 2, 1], ["clr", 6, 14, 2, 1], ["clr", 13, 13, 2, 1]]},
            ],
        },
    },
    {
        "kind": "phantom",
        "tags": ["undead", "magic", "dungeon", "flying"],
        "stats": {"hp": 2, "tick_rate": 0.4, "damage": 2},
        "behavior": {"rules": [
            {"if": "player_within", "range": 6, "do": "teleport",
             "target": "player", "drift": 2, "range": 6, "damage": 2,
             "warmup": 1, "cooldown": 4},
            {"if": "player_within", "range": 2, "do": "move", "direction": "away"},
            {"if": "always", "do": "move", "direction": "random"},
        ]},
        "sprite": {
            "colors": {"body": "#8888cc", "dark": "#5555aa", "eyes": "#ffffff", "glow": "#aaaaee"},
            "frames": [
                [
                    ["dark", 5, 8, 6, 6], ["body", 4, 3, 8, 9], ["body", 5, 2, 6, 1],
                    ["glow", 5, 3, 2, 1], ["eyes", 5, 5, 2, 2], ["eyes", 9, 5, 2, 2],
                    ["dark", 4, 12, 2, 2], ["dark", 10, 12, 2, 2],
                    ["dark", 6, 14, 1, 1], ["dark", 9, 14, 1, 1],
                ],
                [
                    ["dark", 5, 7, 6, 6], ["body", 4, 2, 8, 9], ["body", 5, 1, 6, 1],
                    ["glow", 5, 2, 2, 1], ["eyes", 5, 4, 2, 2], ["eyes", 9, 4, 2, 2],
                    ["dark", 4, 11, 2, 2], ["dark", 10, 11, 2, 2],
                    ["dark", 6, 13, 1, 1], ["dark", 9, 13, 1, 1],
                ],
            ],
        },
        "death_sprite": {
            "colors": {"clr": "#8888cc"},
            "frames": [
                [["clr", 3, 11, 10, 3], ["clr", 5, 10, 6, 1]],
                [["clr", 1, 12, 3, 2], ["clr", 5, 13, 2, 1], ["clr", 8, 11, 3, 2], ["clr", 12, 13, 3, 1]],
                {"alpha": 0.4, "layers": [["clr", 0, 13, 2, 1], ["clr", 6, 14, 2, 1], ["clr", 13, 13, 2, 1]]},
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Precreated tiles (7) — server-side tile recipes for custom registry
# ---------------------------------------------------------------------------

PRECREATED_TILES = [
    {
        "id": "DW",
        "walkable": False,
        "tags": ["dungeon", "wall", "stone"],
        "colors": {"base": "#3a3a4a", "alt": "#2a2a3a"},
        "layers": [
            ["alt", 0, 0, 1, 1], ["alt", 8, 0, 1, 1], ["alt", 0, 3, 16, 1],
            ["alt", 4, 4, 1, 1], ["alt", 12, 4, 1, 1], ["alt", 0, 7, 16, 1],
            ["alt", 0, 8, 1, 1], ["alt", 8, 8, 1, 1], ["alt", 0, 11, 16, 1],
            ["alt", 4, 12, 1, 1], ["alt", 12, 12, 1, 1], ["alt", 0, 15, 16, 1],
        ],
    },
    {
        "id": "DF",
        "walkable": True,
        "tags": ["dungeon", "floor", "stone"],
        "colors": {"base": "#5a5a5a", "alt": "#4a4a4a"},
        "layers": [
            ["alt", 0, 0, 1, 1], ["alt", 3, 0, 1, 1], ["alt", 8, 0, 2, 1],
            ["alt", 15, 0, 1, 1], ["alt", 1, 1, 1, 1], ["alt", 13, 1, 2, 1],
            ["alt", 3, 2, 1, 1], ["alt", 6, 2, 3, 1], ["alt", 12, 2, 1, 1],
            ["alt", 2, 3, 1, 1], ["alt", 4, 3, 1, 1], ["alt", 14, 3, 2, 1],
            ["alt", 15, 4, 1, 1], ["alt", 0, 5, 1, 1], ["alt", 6, 5, 2, 1],
            ["alt", 9, 5, 2, 1], ["alt", 13, 5, 1, 1], ["alt", 1, 6, 1, 1],
            ["alt", 5, 6, 1, 1], ["alt", 10, 6, 2, 1], ["alt", 6, 7, 2, 1],
            ["alt", 11, 7, 1, 1], ["alt", 13, 7, 3, 1], ["alt", 1, 8, 2, 1],
            ["alt", 4, 8, 1, 1], ["alt", 12, 8, 1, 1], ["alt", 4, 9, 1, 1],
            ["alt", 15, 9, 1, 1], ["alt", 4, 10, 1, 1], ["alt", 11, 10, 1, 1],
            ["alt", 13, 10, 2, 1], ["alt", 3, 11, 1, 1], ["alt", 7, 11, 2, 1],
            ["alt", 12, 11, 1, 1], ["alt", 15, 11, 1, 1], ["alt", 1, 12, 1, 1],
            ["alt", 7, 12, 1, 1], ["alt", 10, 12, 1, 1], ["alt", 3, 13, 1, 1],
            ["alt", 5, 13, 2, 1], ["alt", 11, 13, 1, 1], ["alt", 14, 13, 1, 1],
            ["alt", 1, 14, 1, 1], ["alt", 4, 14, 2, 1], ["alt", 8, 14, 1, 1],
            ["alt", 4, 15, 1, 1], ["alt", 7, 15, 1, 1], ["alt", 9, 15, 1, 1],
            ["#3a3a3a", 4, 3, 1, 6], ["#3a3a3a", 4, 9, 5, 1], ["#3a3a3a", 10, 6, 1, 5],
        ],
    },
    {
        "id": "PL",
        "walkable": False,
        "tags": ["dungeon", "wall", "decorative"],
        "colors": {"base": "#5a5a5a", "alt": "#4a4a4a", "cap": "#7a7a7a", "body": "#6a6a6a"},
        "layers": [
            ["alt", 0, 0, 1, 1], ["alt", 3, 0, 1, 1], ["alt", 8, 0, 2, 1],
            ["alt", 15, 0, 1, 1], ["alt", 1, 1, 1, 1], ["alt", 13, 1, 2, 1],
            ["alt", 3, 2, 1, 1], ["alt", 6, 2, 3, 1], ["alt", 12, 2, 1, 1],
            ["alt", 2, 3, 1, 1], ["alt", 4, 3, 1, 1], ["alt", 14, 3, 2, 1],
            ["alt", 15, 4, 1, 1], ["alt", 0, 5, 1, 1], ["alt", 6, 5, 2, 1],
            ["alt", 9, 5, 2, 1], ["alt", 13, 5, 1, 1], ["alt", 1, 6, 1, 1],
            ["alt", 5, 6, 1, 1], ["alt", 10, 6, 2, 1], ["alt", 6, 7, 2, 1],
            ["alt", 11, 7, 1, 1], ["alt", 13, 7, 3, 1], ["alt", 1, 8, 2, 1],
            ["alt", 4, 8, 1, 1], ["alt", 12, 8, 1, 1], ["alt", 4, 9, 1, 1],
            ["alt", 15, 9, 1, 1], ["alt", 4, 10, 1, 1], ["alt", 11, 10, 1, 1],
            ["alt", 13, 10, 2, 1], ["alt", 3, 11, 1, 1], ["alt", 7, 11, 2, 1],
            ["alt", 12, 11, 1, 1], ["alt", 15, 11, 1, 1], ["alt", 1, 12, 1, 1],
            ["alt", 7, 12, 1, 1], ["alt", 10, 12, 1, 1], ["alt", 3, 13, 1, 1],
            ["alt", 5, 13, 2, 1], ["alt", 11, 13, 1, 1], ["alt", 14, 13, 1, 1],
            ["alt", 1, 14, 1, 1], ["alt", 4, 14, 2, 1], ["alt", 8, 14, 1, 1],
            ["alt", 4, 15, 1, 1], ["alt", 7, 15, 1, 1], ["alt", 9, 15, 1, 1],
            ["body", 5, 2, 6, 12], ["body", 4, 3, 8, 10],
            ["cap", 4, 2, 8, 2], ["cap", 5, 1, 6, 1], ["cap", 4, 12, 8, 2],
        ],
    },
    {
        "id": "SC",
        "walkable": False,
        "tags": ["dungeon", "wall", "light"],
        "colors": {"base": "#3a3a4a", "alt": "#2a2a3a", "flame": "#ffcc33"},
        "layers": [
            ["alt", 0, 0, 1, 1], ["alt", 8, 0, 1, 1], ["alt", 0, 3, 16, 1],
            ["alt", 4, 4, 1, 1], ["alt", 12, 4, 1, 1], ["alt", 0, 7, 16, 1],
            ["alt", 0, 8, 1, 1], ["alt", 8, 8, 1, 1], ["alt", 0, 11, 16, 1],
            ["alt", 4, 12, 1, 1], ["alt", 12, 12, 1, 1], ["alt", 0, 15, 16, 1],
            ["#5a5a5a", 6, 6, 4, 4], ["#5a5a5a", 7, 10, 2, 2],
            ["flame", 7, 3, 2, 4], ["#ff8833", 6, 4, 4, 2],
        ],
    },
    {
        "id": "BZ",
        "walkable": False,
        "tags": ["dungeon", "decoration", "light", "freestanding"],
        "colors": {"base": "#5a5a5a", "alt": "#4a4a4a", "pedestal": "#7a7a7a",
                   "flame": "#ffcc33", "ember": "#ff8833"},
        "layers": [
            ["alt", 0, 0, 1, 1], ["alt", 3, 1, 1, 1], ["alt", 13, 0, 1, 1],
            ["alt", 1, 14, 1, 1], ["alt", 14, 14, 1, 1], ["alt", 1, 15, 1, 1],
            ["alt", 12, 15, 1, 1],
            ["pedestal", 5, 10, 6, 5], ["pedestal", 6, 8, 4, 3],
            ["#6a6a6a", 4, 7, 8, 2],
            ["flame", 5, 2, 6, 6], ["ember", 6, 3, 4, 4], ["#fff4aa", 7, 2, 2, 2],
        ],
    },
    {
        "id": "MF",
        "walkable": True,
        "tags": ["dungeon", "floor", "decorative"],
        "colors": {"base": "#5a5a5a", "alt": "#4a4a4a", "pattern": "#7a6a5a",
                   "highlight": "#8a7a6a"},
        "layers": [
            ["alt", 1, 1, 1, 1], ["alt", 14, 1, 1, 1],
            ["alt", 1, 14, 1, 1], ["alt", 14, 14, 1, 1],
            ["pattern", 0, 0, 16, 1], ["pattern", 0, 15, 16, 1],
            ["pattern", 0, 0, 1, 16], ["pattern", 15, 0, 1, 16],
            ["pattern", 7, 3, 2, 1], ["pattern", 6, 4, 4, 1],
            ["pattern", 5, 5, 6, 1], ["pattern", 4, 6, 8, 1],
            ["pattern", 3, 7, 10, 1], ["pattern", 4, 8, 8, 1],
            ["pattern", 5, 9, 6, 1], ["pattern", 6, 10, 4, 1],
            ["pattern", 7, 11, 2, 1],
            ["highlight", 7, 7, 2, 1],
        ],
    },
    {
        "id": "CF",
        "walkable": True,
        "tags": ["dungeon", "floor", "hazard"],
        "colors": {"base": "#5a5a5a", "alt": "#4a4a4a", "crack": "#3a3a3a",
                   "deep": "#2a2a2a"},
        "layers": [
            ["alt", 2, 0, 1, 1], ["alt", 9, 1, 1, 1], ["alt", 14, 0, 1, 1],
            ["alt", 0, 5, 1, 1], ["alt", 12, 7, 1, 1], ["alt", 1, 12, 1, 1],
            ["alt", 10, 14, 1, 1],
            ["crack", 3, 0, 1, 3], ["crack", 4, 2, 1, 2], ["crack", 5, 3, 1, 3],
            ["crack", 4, 5, 1, 2], ["crack", 3, 6, 1, 2], ["crack", 2, 7, 1, 3],
            ["crack", 3, 9, 1, 2],
            ["crack", 10, 1, 1, 2], ["crack", 11, 2, 1, 3], ["crack", 12, 4, 1, 2],
            ["crack", 11, 5, 1, 2],
            ["crack", 5, 11, 3, 1], ["crack", 7, 12, 3, 1], ["crack", 9, 11, 2, 1],
            ["deep", 4, 3, 1, 1], ["deep", 3, 7, 1, 1], ["deep", 11, 3, 1, 1],
            ["deep", 7, 12, 1, 1],
        ],
    },
]


# ---------------------------------------------------------------------------
# Runtime registration — make precreated types available in the game engine
# ---------------------------------------------------------------------------

def register_precreated_types() -> None:
    """Register all precreated monster and tile types in the game engine.

    All 4 monsters get sprites/behaviors/stats registered so send_room_enter()
    can send custom_sprites to clients for dungeon rooms. skeleton/bat stats
    already exist as built-in but their sprites and behaviors still need
    registration.

    All 7 tiles get registered as custom_tile_recipes so dungeon rooms using
    string tile codes (DW, DF, etc.) work through the custom tile pipeline.
    """
    from server.validation import register_monster_type, register_tile_type
    from server.state import game

    for mdata in PRECREATED_MONSTERS:
        kind = mdata["kind"]
        ok, errors = register_monster_type(mdata)
        if not ok:
            print(f"[CONTENT] WARNING: Failed to register {kind}: {errors}")
        else:
            print(f"[CONTENT] Registered monster type: {kind}")

    for tdata in PRECREATED_TILES:
        tile_id = tdata["id"]
        ok, errors = register_tile_type(tdata)
        if not ok:
            print(f"[CONTENT] WARNING: Failed to register tile {tile_id}: {errors}")
        else:
            print(f"[CONTENT] Registered tile type: {tile_id}")


# ---------------------------------------------------------------------------
# Room conversion: .room file -> library entry data
# ---------------------------------------------------------------------------

def _convert_room_template(template: dict) -> dict:
    """Convert a parsed dungeon template (numeric tilemap) to library-compatible data.

    Input: {"name", "tilemap" (list[list[int]]), "monsters" (list[dict]), "guards"}
    Output: {"name", "tilemap" (list[list[str]]), "monster_placements" (list[dict])}
    """
    # Convert numeric tilemap to string tile codes
    str_tilemap = []
    for row in template["tilemap"]:
        str_row = []
        for tile_id in row:
            code = _TILE_ID_TO_CODE.get(tile_id, "DF")
            str_row.append(code)
        str_tilemap.append(str_row)

    # Convert monster templates to placements
    placements = []
    for m in template.get("monsters", []):
        placements.append({"kind": m["kind"], "x": m["x"], "y": m["y"]})

    return {
        "name": template.get("name", "Dungeon Room"),
        "tilemap": str_tilemap,
        "monster_placements": placements,
    }


# ---------------------------------------------------------------------------
# Startup loader
# ---------------------------------------------------------------------------

def load_precreated_content(
    monster_lib: ContentLibrary,
    tile_lib: ContentLibrary,
    room_lib: ContentLibrary,
    dungeon_templates: dict,
) -> None:
    """Populate libraries with precreated permanent entries at startup.

    Args:
        monster_lib: Monster content library to populate
        tile_lib: Tile content library to populate
        room_lib: Room content library to populate
        dungeon_templates: Parsed dungeon templates from game.dungeon_templates
            (populated by rooms.py load_dungeon_templates)
    """
    import time
    now = time.time()

    # --- Monsters ---
    for mdata in PRECREATED_MONSTERS:
        entry = LibraryEntry(
            id=mdata["kind"],
            content_type="monster",
            tags=list(mdata["tags"]),
            created_at=now,
            data=mdata,
            permanent=True,
        )
        monster_lib.add(entry)
    print(f"[CONTENT] Loaded {len(PRECREATED_MONSTERS)} permanent monsters: "
          f"{[m['kind'] for m in PRECREATED_MONSTERS]}")

    # --- Tiles ---
    for tdata in PRECREATED_TILES:
        entry = LibraryEntry(
            id=tdata["id"],
            content_type="tile",
            tags=list(tdata["tags"]),
            created_at=now,
            data=tdata,
            permanent=True,
        )
        tile_lib.add(entry)
    print(f"[CONTENT] Loaded {len(PRECREATED_TILES)} permanent tiles: "
          f"{[t['id'] for t in PRECREATED_TILES]}")

    # --- Rooms (from dungeon templates) ---
    room_count = 0
    for template_id in sorted(dungeon_templates.keys()):
        template = dungeon_templates[template_id]
        room_data = _convert_room_template(template)

        # Determine tags based on content
        tags = ["dungeon"]
        kinds = {m["kind"] for m in room_data["monster_placements"]}
        if "skeleton" in kinds:
            tags.append("undead")
        if "bat" in kinds:
            tags.append("cave")

        entry = LibraryEntry(
            id=template_id,
            content_type="room",
            tags=tags,
            created_at=now,
            data=room_data,
            permanent=True,
        )
        room_lib.add(entry)
        room_count += 1

    print(f"[CONTENT] Loaded {room_count} permanent rooms from dungeon templates")
    print(f"[CONTENT] Libraries: {monster_lib}, {tile_lib}, {room_lib}")
