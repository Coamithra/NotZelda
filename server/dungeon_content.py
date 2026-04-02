"""Dungeon content configuration — which monsters and tiles belong to each dungeon.

All monster and tile recipes live in data/monsters.json and data/tiles.json.
This module just declares which IDs are permanent members of each dungeon's
content library, and handles populating those libraries at startup.

# TODO: These ID lists could be moved to a data file (e.g. data/d1_content.json)
# for full data-driven config, but that's probably overengineering for this
# size of game. The IDs rarely change and are easy to maintain here.
"""

from server.content_library import LibraryEntry, ContentLibrary
from server.state import game
from server import log

# ---------------------------------------------------------------------------
# Per-dungeon permanent content IDs
# ---------------------------------------------------------------------------

PRECREATED_CONTENT = {
    "d1": {
        "monsters": ["skeleton", "bat", "dungeon_slime", "phantom"],
        "boss": "dungeon_warden",
        "tiles": ["DW", "DF", "PL", "SC", "BZ", "MF", "CF"],
    },
    "d2": {
        "monsters": ["water_serpent", "drowned_one"],
        "boss": "temple_guardian",
        "tiles": ["TW", "TF", "CR"],
    },
}


# ---------------------------------------------------------------------------
# Runtime registration — make precreated types available in the game engine
# ---------------------------------------------------------------------------

def register_precreated_types() -> None:
    """Register all precreated monster and tile types for all dungeon types.

    Since all recipes are now loaded from data/monsters.json and data/tiles.json
    at startup, this just verifies the IDs exist and prints confirmation.
    """
    for type_id, content in PRECREATED_CONTENT.items():
        for kind in content["monsters"]:
            if kind in game.monster_stats:
                log.server(f"[CONTENT] Registered monster type: {kind}")
            else:
                log.debug(f"[CONTENT] WARNING: Monster '{kind}' not found in data/monsters.json")

        boss_kind = content["boss"]
        if boss_kind in game.monster_stats:
            log.server(f"[CONTENT] Registered boss type: {boss_kind}")
        else:
            log.debug(f"[CONTENT] WARNING: Boss '{boss_kind}' not found in data/monsters.json")

        for tile_id in content["tiles"]:
            if tile_id in game.custom_tile_recipes:
                log.server(f"[CONTENT] Registered tile type: {tile_id}")
            else:
                log.debug(f"[CONTENT] WARNING: Tile '{tile_id}' not found in data/tiles.json")


def _template_to_room_data(template: dict) -> dict:
    """Convert a parsed dungeon template to library-compatible room data.

    Input: {"name", "tilemap" (list[list[str]]), "monsters" (list[dict]), "guards"}
    Output: {"name", "tilemap" (list[list[str]]), "monster_placements" (list[dict])}
    """
    placements = []
    for m in template.get("monsters", []):
        placements.append({"kind": m["kind"], "x": m["x"], "y": m["y"]})

    result = {
        "name": template.get("name", "Dungeon Room"),
        "tilemap": [list(row) for row in template["tilemap"]],
        "monster_placements": placements,
    }
    if template.get("monster_groups"):
        result["monster_groups"] = [
            {"kind": g["kind"], "count": g["count"]}
            for g in template["monster_groups"]
        ]
    return result


def _build_monster_data(kind: str) -> dict:
    """Build a library-compatible monster data dict from loaded registries."""
    data = {"kind": kind}

    # Stats
    if kind in game.monster_stats:
        data["stats"] = dict(game.monster_stats[kind])
    # Tags (stored during load from monsters.json via _monster_tags)
    if kind in _monster_tags:
        data["tags"] = list(_monster_tags[kind])
    # Sprite
    if kind in game.custom_sprites:
        data["sprite"] = game.custom_sprites[kind]
    # Death sprite
    if kind in game.custom_death_sprites:
        data["death_sprite"] = game.custom_death_sprites[kind]
    # Behavior
    if kind in game.monster_behaviors:
        data["behavior"] = game.monster_behaviors[kind]

    return data


def _build_tile_data(tile_id: str) -> dict:
    """Build a library-compatible tile data dict from loaded registries."""
    recipe = game.custom_tile_recipes.get(tile_id, {})
    data = {"id": tile_id}
    data.update(recipe)
    # Include tags if present
    if "tags" in recipe:
        data["tags"] = recipe["tags"]
    return data


# Tag cache — populated during load_precreated_content from monsters.json
_monster_tags = {}


# ---------------------------------------------------------------------------
# Startup loader
# ---------------------------------------------------------------------------

def load_precreated_content(
    monster_lib: ContentLibrary,
    tile_lib: ContentLibrary,
    room_lib: ContentLibrary,
    dungeon_templates: dict,
    special_rooms: set | None = None,
    type_id: str = "d1",
) -> None:
    """Populate libraries with precreated permanent entries at startup.

    All monster/tile recipes are already loaded into game registries from
    data/monsters.json and data/tiles.json. This function creates library
    entries pointing to those recipes.
    """
    import json
    import time
    from pathlib import Path

    now = time.time()

    if special_rooms is None:
        special_rooms = {"d1_boss", "d1_treasure"}

    content = PRECREATED_CONTENT.get(type_id, PRECREATED_CONTENT.get("d1", {}))
    monster_ids = content.get("monsters", [])
    tile_ids = content.get("tiles", [])

    # Load tags from monsters.json for library entries
    monsters_path = Path(__file__).parent.parent / "data" / "monsters.json"
    if monsters_path.exists():
        all_monsters = json.loads(monsters_path.read_text(encoding="utf-8"))
        for kind, mdata in all_monsters.items():
            _monster_tags[kind] = mdata.get("tags", [])

    # --- Monsters ---
    for kind in monster_ids:
        mdata = _build_monster_data(kind)
        tags = mdata.get("tags", [])
        entry = LibraryEntry(
            id=kind,
            content_type="monster",
            tags=list(tags),
            created_at=now,
            data=mdata,
            permanent=True,
        )
        monster_lib.add(entry)
    log.server(f"[CONTENT] [{type_id}] Loaded {len(monster_ids)} permanent monsters: "
               f"{monster_ids}")

    # --- Tiles ---
    for tile_id in tile_ids:
        tdata = _build_tile_data(tile_id)
        tags = tdata.get("tags", [])
        entry = LibraryEntry(
            id=tile_id,
            content_type="tile",
            tags=list(tags),
            created_at=now,
            data=tdata,
            permanent=True,
        )
        tile_lib.add(entry)
    log.server(f"[CONTENT] [{type_id}] Loaded {len(tile_ids)} permanent tiles: "
               f"{tile_ids}")

    # --- Rooms (from dungeon templates) ---
    room_count = 0
    for template_id in sorted(dungeon_templates.keys()):
        if template_id in special_rooms:
            continue
        template = dungeon_templates[template_id]
        room_data = _template_to_room_data(template)

        # Determine tags based on content
        tags = ["dungeon"]
        kinds = {m["kind"] for m in room_data["monster_placements"]}
        kinds |= {g["kind"] for g in room_data.get("monster_groups", [])}
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

    log.server(f"[CONTENT] Loaded {room_count} permanent rooms from dungeon templates")
    log.server(f"[CONTENT] Libraries: {monster_lib}, {tile_lib}, {room_lib}")
