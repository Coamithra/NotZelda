"""Dungeon type configurations — defines properties for each dungeon type."""

from server.dungeon_layouts import DUNGEON_LAYOUTS, D2_LAYOUTS

DUNGEON_TYPES = {
    "d1": {
        "name": "Dark Dungeon",
        "template_dir": "rooms/dungeon1",
        "layouts": DUNGEON_LAYOUTS,
        "music_tracks": [
            "dungeon2", "dungeon4", "dungeon5", "dungeon6",
        ],
        "boss_tracks": ["boss1", "boss2", "boss3"],
        "biome": "dungeon",
        "exit_room": "ow_7_9",
        "entrance_exit": "d1_entrance",
        "boss_template": "d1_boss",
        "treasure_template": "d1_treasure",
        "min_locks": 1,
        "max_locks": 6,
        "difficulty_distribution": {"easy": 0.50, "challenging": 0.30, "hard": 0.20},
        "difficulty_scaling": {"easy": 0.5, "challenging": 1.0, "hard": 1.5},
    },
    "d2": {
        "name": "Water Temple",
        "template_dir": "rooms/dungeon2",
        "layouts": D2_LAYOUTS,
        "music_tracks": ["watertemple1", "watertemple2", "watertemple3"],
        "boss_tracks": ["watertemple_boss1", "watertemple_boss2"],
        "biome": "dungeon",
        "theme": "water_temple",
        "exit_room": "ow_5_12",
        "entrance_exit": "d2_entrance",
        "boss_template": "d2_boss",
        "treasure_template": "d2_treasure",
        "wall_tile": "TW",
        "min_locks": 1,
        "max_locks": 5,
        "difficulty_distribution": {"easy": 0.40, "challenging": 0.35, "hard": 0.25},
        "difficulty_scaling": {"easy": 0.5, "challenging": 1.0, "hard": 1.5},
    },
}

# Reverse lookup: entrance exit value in .room files -> dungeon type ID
ENTRANCE_TO_TYPE = {
    cfg["entrance_exit"]: type_id
    for type_id, cfg in DUNGEON_TYPES.items()
}
