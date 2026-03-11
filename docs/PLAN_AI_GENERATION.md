# AI-Powered Procedural Content Generation — Staged Plan

## Overview

Use Claude API (Haiku) to procedurally generate dungeon rooms, monsters
(with unique sprites, behaviors, and attacks), and custom tiles at runtime.
Content lives in a self-managing library that grows, ages, and refreshes
automatically. No manual approval. The Hetzner server makes API calls to
Anthropic's cloud; all generated content is pure data interpreted by
engines we build in advance.


## Core Concepts

### The Library System

Each content type (rooms, monsters, tiles) has a library with a fixed
capacity. Some slots hold real content, the rest are **placeholders** —
generation IOUs fulfilled on demand.

Example lifecycle for a room library (capacity 50, expiry 10/day):

```
Day 1: Fresh server. 0 real, 50 placeholders.
  Player enters dungeon, layout needs 25 rooms.
  Shuffle all 50 slots, pick 25.
  ~25 are placeholders → generate via API.
  Library: 25 real, 25 placeholders.

Day 1 later: Another dungeon, needs 20 rooms.
  Shuffle 50, pick 20. ~10 real, ~10 placeholders.
  Generate the 10 placeholders.
  Library: 35 real, 15 placeholders.

Later: All players leave. destroy_dungeon() fires.
  Expiry: 5 oldest rooms (>24h old) → become placeholders.
  Library: 30 real, 20 placeholders.

After several dungeons: Library full. 50 real, 0 placeholders.
  Dungeon picks 25 from existing — no API calls.

Next teardown: Expiry runs. 5 oldest (>24h) → placeholders.
  Library: 45 real, 5 placeholders.
  Next dungeon: ~10% chance per slot of fresh content. Self-balancing.
```

If the API is down or rate-limited, unresolvable placeholders get swapped
for random real rooms from the library. Graceful degradation.

**Lazy generation:** Content is never resolved all at once. When a player
enters a dungeon, only the entrance room is generated (if needed). Each
subsequent room is resolved only when a player walks into it. This keeps
dungeon entry instant and spreads API calls across the play session. At
steady state (~20% placeholders), most room transitions are instant — only
the occasional placeholder triggers a brief ~1-2s generation pause.

### Late Binding & Tags

Everything references everything else. Rooms reference monsters and tiles.
Rotation creates dangling references. Solution: **late binding with
semantic tags.**

Rooms don't hardcode specific monster/tile IDs. They store semantic slots:

```json
{
  "monsters": [
    { "tags": ["fire", "melee"], "preferred": "flame_wyrm" },
    { "tags": ["fire", "ranged"], "preferred": "ember_spitter" }
  ],
  "custom_tiles": {
    "X1": { "tags": ["fire"], "walkable": true, "preferred": "lava_crack" },
    "X2": { "tags": ["wall_mounted"], "walkable": false, "preferred": "brazier" }
  }
}
```

At dungeon build time, each slot resolves:
1. Is `preferred` still in the library? Use it.
2. Gone? Find the best substitute by **tag overlap** — score =
   shared tags / total unique tags. Pick the highest-scoring match.
3. No tag matches? Pick any entry from the library.
4. Nothing? Generate a replacement on the spot — tags become the AI prompt.

**Walkability is a hard constraint for tiles:** a walkable tile can only be
substituted with another walkable tile, and vice versa. This ensures the
room layout stays playable even after substitution.

This means:
- Rooms are durable — they degrade gracefully, almost never become invalid
- Monsters and tiles can rotate freely
- Replacement is semantic ("find me another fire tile that's walkable"),
  scored by tag overlap
- The AI is great at tagging its own output — include the tag vocabulary
  in the system prompt

### Tag Vocabulary

Tags are free-form strings (extendable over time). The AI generates tags
for its own content; these are reference examples:

**Monster tags:** `fire`, `ice`, `shadow`, `undead`, `beast`, `magic`,
`poison`, `flying`, `dungeon`, `cave`, `swamp`, `desert`, `melee`,
`ranged`, `light`, `heavy`, `fodder`, `boss`, `tank`, `swarm`

**Tile tags:** `fire`, `ice`, `shadow`, `stone`, `wood`, `metal`,
`organic`, `magical`, `wall_mounted`, `freestanding`, `dungeon`,
`floor`, `wall`, `pillar`, `decoration`, `light`, `hazard`

Walkability is a separate boolean property on tiles, not a tag.

### The Behavior Engine

Monsters have data-driven AI. A fixed set of conditions and actions are
pre-coded. The AI (or hand-authored data) composes them as JSON. The
server's monster_tick() interprets the rules — no runtime code generation.

```json
{
  "behavior": {
    "rules": [
      { "if": "hp_below_pct", "value": 30, "do": "flee" },
      { "if": "player_within", "range": 2, "do": "chase" },
      { "if": "player_within", "range": 6, "do": "hold" },
      { "default": "wander" }
    ],
    "attacks": [
      { "type": "projectile", "range": 5, "damage": 1, "cooldown": 3.0,
        "sprite_color": "#ff6600" },
      { "type": "melee", "range": 1, "damage": 2, "cooldown": 1.0 }
    ]
  }
}
```

Rules evaluated top-to-bottom, first match wins. All actions and conditions
are pre-coded functions. The AI picks which to use and with what parameters.

### Monster Generation Modes

When the AI creates a monster, it operates in one of two modes:

**Mode A — Brand new:** The AI generates everything from scratch given a
role, tags, and difficulty. Full creative freedom for sprite, behavior,
stats, and name.

**Mode B — Tweak/variant:** The AI receives the full definition of an
existing monster and creates a variation. Like swamp_blob (recolored slime
with different stats). Can change colors, add/remove sprite layers, adjust
behavior parameters, rename. The base monster's silhouette stays
recognizable.

The system controls the ratio (e.g., 30% brand new, 70% tweak). Early on
when the library is sparse, it skews toward brand new. Once the library
has variety, tweaks dominate — cheaper API calls, more consistent quality,
and players see familiar-but-fresh enemies.

### Custom Tile Generation

Tiles are 16x16 grids rendered with composable drawing operations. The AI
generates tile recipes using existing primitives:

```json
{
  "id": "lava_crack",
  "role": "floor_variant",
  "tags": ["fire", "dungeon", "walkable"],
  "colors": { "base": "#3a2020", "alt": "#2a1515", "lava": "#ff6600", "glow": "#ffaa00" },
  "operations": [
    { "op": "fill", "color": "base" },
    { "op": "noise", "density": 0.3, "color": "alt" },
    { "op": "rects", "rects": [
      ["lava", 3, 6, 2, 8],
      ["lava", 7, 2, 1, 5],
      ["glow", 4, 7, 1, 2]
    ]}
  ]
}
```

The client already has all drawing primitives (drawNoise, drawBricks,
drawRects, etc). The tile generator just needs to read recipes from data
in addition to the hardcoded TILE_GENERATORS. Same pattern as sprites:
fixed renderer, data-driven definitions.

Tag-based replacement examples:
- `torch` expires → find `light_source` + `wall_mounted` → `lamp`, `brazier`
- `stone_pillar` expires → find `pillar` + `structural` → `marble_pillar`
- `lava_crack` expires → find `floor_variant` + `fire` → `scorched_stone`


## Staged Implementation Plan

**Current status: Stages 1–7 complete. Async `generate_room()` wired into `resolve_dungeon_room()` for placeholder cells. Remaining polish: late-binding of monster/tile refs, refactor monster_tick to remove awaits.**

### Stage 1: Tag & Metadata System ✅
**Goal:** Define the data structures that everything else builds on.
**Why first:** Rooms, monsters, and tiles all depend on this. Late binding
requires tags from the start.

Tasks:
- [ ] Define `content_library.py` module with:
  - `LibraryEntry` dataclass: id, type, role, tags, created_timestamp,
    preferred references, data payload
  - `ContentLibrary` class: add, remove, query_by_role_and_tags,
    get_or_placeholder, expire_oldest, serialize/deserialize
- [ ] Define tag vocabulary constants (monster roles, tile roles, tags)
- [ ] Define resolution logic: preferred → role+tags → role only → generate
- [ ] Persistence: library saves to JSON files on disk, loads at startup

**Test:** Unit test the library — add entries, query by tags, expire oldest,
verify resolution fallback chain works.

---

### Stage 2: Client Dynamic Registries ✅
**Goal:** Client can render monsters, NPCs, and tiles it has never seen before.
**Why:** Unblocks all generated content. Small change, immediately testable.

Tasks:
- [ ] Add `customMonsterSprites` runtime registry on the client
- [ ] Modify `drawMonsterSprite()`: if kind not in `MONSTER_SPRITE_DATA`,
      check `customMonsterSprites[kind]`
- [ ] Same for `drawMonsterDeath()` — use custom death sprite or generate
      a generic splat from the monster's primary color
- [ ] Add `customTiles` runtime registry on the client
- [ ] Modify `getTileCanvas()`: if tileId not in `TILE_GENERATORS`, check
      `customTiles[tileId]` and run its operations recipe
- [ ] Implement recipe interpreter: reads `operations` array, calls existing
      draw functions (drawNoise, drawBricks, drawRects, drawHStripes, etc.)
- [ ] Extend `room_enter` protocol: optional `custom_sprites` and
      `custom_tiles` fields
- [ ] When client receives custom data, merge into runtime registries

**Test:** Manually craft a `room_enter` message with a custom monster sprite
and a custom tile. Verify both render correctly.

---

### Stage 3: Server Dynamic Registration ✅
**Goal:** Server can register new monster types and tile types at runtime.

Tasks:
- [x] `register_monster_type(data)` — validates then adds to
      `MONSTER_STATS`, `CUSTOM_SPRITES`, and optionally `CUSTOM_DEATH_SPRITES`
- [x] `register_tile_type(data)` — validates then adds to
      `CUSTOM_TILE_RECIPES`
- [x] `send_room_enter()` already attaches custom sprite/tile data (Stage 2)
- [x] Validation functions:
  - `validate_monster(data)` — stat ranges, sprite bounds (16x16), color
    formats (#RRGGBB), behavior rule/condition/action names, attack types
  - `validate_tile(data)` — operation names exist, color formats valid,
    rect/pixel coordinates within 0-15 grid
- [x] Chat command `/debug_spawn <kind>` to test — spawns near player,
      broadcasts custom sprite data to all clients in room. Three built-in
      test monsters: fire_slime, ice_bat, shadow_skull
- [x] Extended `monster_spawned` protocol message to optionally carry
      `custom_sprites`/`custom_death_sprites` so mid-session spawns work

**Test:** Use `/debug_spawn` to register and spawn a custom monster.
Verify client renders it and combat works.

---

### Stage 4: Behavior Engine — Movement ✅
**Goal:** Monsters move based on data-driven behavior rules.
**Why:** Needed before AI generation so generated behaviors have an engine.

Conditions to implement:
- [ ] `player_within` — nearest player within N tiles (Manhattan distance)
- [ ] `player_beyond` — nearest player farther than N tiles
- [ ] `hp_below_pct` — monster HP below X% of max
- [ ] `hp_above_pct` — monster HP above X% of max
- [ ] `random_chance` — X% probability per tick
- [ ] `always` / `default` — fallback (always true)

Movement actions to implement:
- [ ] `wander` — current random hop (already exists)
- [ ] `chase` — move toward nearest player (greedy: pick adjacent tile
      that minimizes distance)
- [ ] `flee` — move away from nearest player (maximize distance)
- [ ] `patrol` — cycle through relative waypoint offsets
- [ ] `hold` — stay still

Engine:
- [ ] Create `behavior_engine.py` with `evaluate_rules(rules, monster,
      room_id)` → action name
- [ ] Action executor functions: `do_wander()`, `do_chase()`, `do_flee()`,
      `do_patrol()`, `do_hold()`
- [ ] Refactor `monster_tick()` to call behavior engine
- [ ] Monsters without behavior data default to `[{"default": "wander"}]`
      (backward compatible)

**Test:** Manually register a chaser slime and a coward bat via chat
commands. Verify chaser follows player, coward runs away.

---

### Stage 5: Behavior Engine — Attacks ✅
**Goal:** Monsters can have ranged attacks, charges, and special abilities.

Attack types:
- [ ] `melee` — contact damage (existing), now with per-attack cooldown
      and damage override
- [ ] `projectile` — fires toward player, travels in a line, damages on
      hit. New protocol: `projectile_spawned`, `projectile_moved`,
      `projectile_hit`, `projectile_gone`
- [ ] `charge` — dash N tiles toward player in a straight line
- [ ] `teleport` — disappear, reappear near player after brief delay
      (warning indicator on target tile)
- [ ] `area` — damage all players within N tiles (ground slam, with
      warning indicator)

Attack conditions (extend behavior rules):
- [ ] `can_attack` — at least one attack's cooldown has elapsed
- [ ] `player_in_attack_range` — player within any attack's range

Client rendering:
- [ ] Projectile sprites (colored dot, color from attack data)
- [ ] Teleport effect (fade out + fade in)
- [ ] Charge trail
- [ ] Area attack ground warning indicator

**Test:** Manually create a skeleton archer (projectile), teleporting ghost,
and charging boar. Verify each attack type works.

---

### Stage 6: Claude API Integration ✅
**Goal:** Server can call Claude Haiku and get valid structured game content.

**Key design: one API call per room, not per content type.** The AI gets a
single prompt that returns a complete room — tilemap, monster placements,
and any new monster/tile definitions inline. The prompt includes existing
library content so the AI can reuse it:

- **Sparse library:** "These monsters and tiles exist: [short list]. Reuse
  them where they fit, but feel free to create new ones."
  → AI creates some new content inline, reuses the rest. One call.
- **Full library:** "These monsters and tiles are available. Use only these,
  do not create new ones."
  → AI just picks and places. Minimal tokens, near-instant.
- **Monster variant mode:** "These monsters exist: [list with full data for
  one base monster]. Create a variant of [base] for this room, or reuse
  existing ones as-is."

This means the first room ever generated is the slowest (most new content).
Each subsequent room gets cheaper as the library fills — the AI reuses more
and invents less. By the time libraries are full, generation is just "arrange
existing pieces" with near-zero new content.

Example response for a room with mixed reuse/new:
```json
{
  "name": "Ember Sanctum",
  "tilemap": [["DW","DW", ... ], ...],
  "new_tiles": [
    { "id": "ember_floor", "role": "floor_variant", "tags": ["fire"],
      "colors": { "base": "#3a2020", "glow": "#ff6600" },
      "operations": [{"op": "fill", "color": "base"}, ...] }
  ],
  "new_monsters": [
    { "kind": "flame_wyrm", "role": "medium_melee", "tags": ["fire"],
      "stats": { "hp": 3, "damage": 2, "hop_interval": 1.0 },
      "sprite": { ... },
      "behavior": { "rules": [...], "attacks": [...] } }
  ],
  "monster_placements": [
    { "kind": "flame_wyrm", "x": 5, "y": 3 },
    { "kind": "skeleton", "x": 10, "y": 7 }
  ],
  "tile_mappings": { "X1": "ember_floor", "X2": "lava_crack" }
}
```

Tasks:
- [ ] Install `anthropic` SDK, add to requirements
- [ ] Create `ai_generator.py` module:
  - System prompt with full spec: sprite format, tile operations, behavior
    vocabulary, tag vocabulary, stat ranges, tile code list
  - Few-shot examples (2-3 complete room responses)
  - `generate_room(theme, difficulty, existing_monsters, existing_tiles)`
    → complete room JSON with inline new content + references to existing
  - Prompt dynamically built: includes existing library content summaries
    (kind/role/tags for monsters, id/role/tags for tiles)
  - When monster/tile libraries are full, prompt says "use only these"
  - When libraries have room, prompt says "reuse if fitting, create new
    if needed"
- [ ] Response validation + single retry on failure:
  - Validate tilemap dimensions (15x11), tile codes exist
  - Validate new monster definitions (stats, sprites, behaviors)
  - Validate new tile definitions (operations, colors)
  - Validate placements (within room bounds, on walkable tiles)
  - On retry, include the validation error in the prompt
- [ ] API key from env var `ANTHROPIC_API_KEY`
- [ ] Rate limiter: max N calls/minute, M calls/day (configurable)
- [ ] Token usage logging to file

**Test:** Run standalone with empty library — verify full room with new
content. Run with a populated library — verify it reuses existing content.
Run with full libraries — verify no new content created, just arrangement.

---

### Stage 6.5: Unified Content Refactor (Prerequisite) ✅
**Goal:** All dungeon content — precreated and AI-generated — uses the
same data-driven system. No hardcoded built-in content in source code.
Precreated content is just library entries with a `permanent` flag.

**Key principle: the dungeon system treats all content uniformly.** A
precreated skeleton and an AI-generated flame_wyrm look identical in the
library. The AI prompt sees a flat list of all available monsters/tiles
with no "built-in vs custom" distinction.

**Sprite delivery (Option B):** All dungeon monster sprites and tile
recipes are defined server-side and sent to clients via `custom_sprites`
/ `custom_tiles` in `room_enter`. Precreated monsters like skeleton/bat
still have static sprites in `sprite_data.js` for overworld use, but
inside dungeons they go through the custom registry pipeline like
everything else. This means zero special-case rendering logic in the
dungeon client path.

#### Precreated Content

**4 Precreated Monsters** (permanent library entries):

| Kind | HP | Tick | Dmg | Behavior |
|---|---|---|---|---|
| skeleton | 2 | 0.5 | 3 | Chase within 5, wander otherwise |
| bat | 1 | 1.0 | 1 | Random movement (fast tick = unpredictable) |
| dungeon_slime | 3 | 0.4 | 1 | Slow tank, chase within 4, wander |
| phantom | 2 | 0.4 | 2 | Teleport near player (warmup 1, cd 4), flee if close |

**7 Precreated Tiles** (permanent library entries):

| Code | Name | Walkable | Description |
|---|---|---|---|
| DW | dungeon_wall | No | Smooth dark stone wall |
| DF | dungeon_floor | Yes | Worn stone floor |
| PL | pillar | No | Stone pillar |
| SC | sconce_wall | No | Wall with torch sconce |
| BZ | brazier | No | Stone pedestal with fire |
| MF | mosaic_floor | Yes | Floor with decorative inlay |
| CF | cracked_floor | Yes | Damaged floor with cracks |

**64 Precreated Rooms** (permanent library entries):
- 32 **primary** rooms — used for the ~50% precreated allocation
- 32 **fallback** rooms — safety net when custom library is empty + API down
- Both loaded from existing `rooms/dungeon1/*.room` files
- Some primary rooms updated to use new monsters (dungeon_slime, phantom)
  and new tiles (BZ, MF, CF)

#### Library Changes

`LibraryEntry` gets a `permanent: bool` field:
- Permanent entries are loaded at startup, never expire, cannot be deleted
- `expire_oldest()` skips permanent entries
- `remove()` refuses to delete permanent entries
- Permanent entries take up slots in the library; the remaining slots
  are placeholders available for custom content

#### Persistence — Separate Files for Permanent vs Custom

Permanent and custom content have **separate** underlying data sources:

- **Permanent** content is loaded from checked-in source files at startup:
  - Monsters/tiles: `server/dungeon_content.py` (Python data dicts)
  - Rooms: `rooms/dungeon1/*.room` (existing `.room` format)
  - These are in git, hand-editable, never overwritten by the server
- **Custom** content persists to gitignored JSON files in `data/`:
  - `data/room_library.json`
  - `data/monster_library.json`
  - `data/tile_library.json`
  - Only custom (non-permanent) entries are serialized/deserialized
  - Server writes these after generation and expiry events

On startup: permanent entries are loaded first (from source), then custom
entries are loaded from `data/*.json` and added to the remaining slots.

#### Library Capacities (total = permanent + custom)

| Library | Permanent | Custom | Total Capacity |
|---|---|---|---|
| Rooms | 64 | 15 | 79 |
| Monsters | 4 | 4 | 8 |
| Tiles | 7 | 7 | 14 |

#### AI Prompt Changes

`_build_layout_prompt()` no longer has hardcoded `base_tiles` and
`builtin_monsters` lists. Instead, the caller passes a single flat list
of all available content from the libraries (permanent + custom).

#### Tasks
- [x] Add `permanent: bool` to `LibraryEntry`, update expiry/remove/serialize
- [x] Add BZ, MF, CF tile IDs to `constants.py` + `TILE_CODES` + `WALKABLE_TILES`
- [x] Add BZ, MF, CF tile art to `client/tiles.js`
- [x] Create `server/dungeon_content.py` with:
  - Full data dicts for 4 precreated monsters (stats, sprite, behavior)
  - Full data dicts for 7 precreated tiles (colors, layers, walkable)
  - Tags for each entry
  - `load_precreated_content()` function to populate libraries at startup
- [x] Create room library entries from `rooms/dungeon1/*.room` files
  (convert existing template format → library entry `data` payload)
- [x] Update `_build_layout_prompt()` — remove hardcoded builtins,
  accept flat list from caller
- [x] Update content viewer — hide delete button for permanent entries
- [x] Update some primary `.room` files to use dungeon_slime, phantom,
  BZ, MF, CF

**Test:** Content viewer shows all precreated content as non-deletable.
`/debug_spawn dungeon_slime` and `/debug_spawn phantom` work.
New tiles render correctly in dungeon rooms.

---

### Stage 7: Library-Managed Dungeon Generation (Lazy) ⚙️
**Goal:** Dungeons are built from the self-managing library. Custom
rooms are generated **lazily** — only when a player actually enters,
not all at once. Precreated rooms are always instant.

> **Detailed sub-steps:** See [PLAN_STAGE7_SUBSTEPS.md](PLAN_STAGE7_SUBSTEPS.md)
> for the step-by-step implementation plan with file lists, risks, and
> dependency ordering.

The key principle: **layout assignment is instant, custom content
resolution is deferred to room entry.**

#### Dungeon Build Flow

1. Pick layout (N cells, 20–38 depending on shape)
2. Randomly flag ~50% of cells as "precreated", ~50% as "custom"
   (capped at 15 custom per dungeon)
3. **Precreated cells** → random pick from 64 permanent room library
   entries (always instant)
4. **Custom cells** → pull from custom room library slots (no
   duplicates — each custom entry used at most once):
   - **Real entry** → use it (instant, late-bind any expired
     monster/tile refs via tag-overlap fallback)
   - **Placeholder** → lazy-generate on player entry via
     `generate_room()` (the AI prompt gets the flat list of ALL
     available monsters and tiles from the libraries)
   - **Fallback** → if API fails, timeout, or library empty: pick
     random from the 32 fallback room library entries

#### Tasks
- [x] Expiry runs inside `destroy_dungeon()`:
  - Expire oldest ~N% of custom (non-permanent) entries per library
  - Only expire entries older than a minimum age
  - **Production defaults:** 10% rate, 24h minimum age
  - **Test defaults:** 50% rate, 5s minimum age
  - Save libraries to disk after expiry
- [x] Refactor `create_dungeon()` — instant, no API calls:
  1. Pick layout (existing logic)
  2. Flag ~50% of cells as precreated, ~50% as custom (capped at 15)
  3. Precreated cells → random pick from permanent room entries
  4. Custom cells → random pick from custom room library slots (no
     wrapping — each entry used at most once)
  5. Store assignments in dungeon instance: `cell → library_entry`
  6. Resolve entrance room immediately (if placeholder, generate it)
  7. Player enters dungeon immediately
- [ ] Add lazy resolution in `on_player_enter_room()`:
  1. Already resolved? Use it (instant). ✅
  2. Real library entry? Late-bind monster/tile refs → instant. **← NOT DONE**
  3. Placeholder? Call `generate_room()` → register monsters/tiles, add to libraries, persist. Falls back to permanent room on failure. ✅
  4. API failure? Use fallback room from permanent entries. ✅
  5. Send all needed custom_sprites/custom_tiles to client. ✅
- [x] **Loading animation** — client-side "conjuring" screen:
  - Server sends `{ type: "room_generating" }` on lazy resolution
  - Dark overlay with flickering torchlight, drifting particles,
    mystical rune circles fading in/out
  - Atmospheric text: "The dungeon shifts..." / "Dark forces stir..."
  - Minimum 1.5s duration (cosmetic for instant rooms)
  - Only on first visit per room — returning uses normal transition
  - Should feel like the dungeon building itself, not a loading screen
- [x] Resolved rooms stay resolved for dungeon lifetime
- [x] Persist libraries to disk after each generation
- [x] **Verbose server log** with `[DUNGEON]` prefix for all events
- [x] **Debug panel** in backtick overlay:
  - Library fill: `Lib: R:72/79 M:6/8 T:10/14`
  - Room source: `Room: precreated` / `Room: custom (library)` /
    `Room: custom (generated)` / `Room: fallback`
  - Only shown for dungeon rooms

**Flow example:**
```
Player enters dungeon → layout assigned (instant)
  → entrance room: precreated → instant → player is in

Player walks north → first visit, precreated room
  → instant (precreated rooms never need generation)

Player walks east → first visit, custom room (real library entry)
  → conjuring animation (1.5s cosmetic) → instant resolution

Player walks south → first visit, custom room (placeholder)
  → conjuring animation → generate_room() API call (~1-2s)
  → room + any new monsters/tiles added to libraries → player is in

Player walks north back → already visited → normal slide transition

API is down? → custom placeholder falls back to one of 32 fallback rooms
```

At steady state (~20% placeholders in custom slots), most transitions
are instant. ~50% of rooms are always precreated (instant). Worst case
for a custom room is 1-2 seconds, never a multi-room stall.

**Test:** Start with empty custom libraries. Enter dungeon — ~50% of
rooms are precreated (instant), ~50% need generation. Walk around —
custom rooms generate on first visit. Walk back — always instant.
Enter another dungeon — more custom rooms come from library (fewer API
calls). Simulate expiry, verify fresh rooms appear. Kill the API —
verify fallback rooms work.

---

### Stage 8: Monster Variant System
**Goal:** AI creates recognizable variants of existing monsters.

Tasks:
- [ ] When generating a monster in mode B (tweak):
  - Pick a base monster from library (weighted toward most-used or
    best-tagged matches)
  - Send full base monster data to AI with instruction to create variant
  - AI can: change colors, add/remove sprite layers, adjust behavior
    parameters, modify stats, rename
  - Validate output against same rules as brand new monsters
- [ ] Track lineage: variant stores `based_on` field pointing to base
- [ ] Control mode ratio: configurable A/B split (default 30/70)
- [ ] Skew toward mode A when library is sparse (< 10 monsters)

**Test:** Generate 10 variants of "slime". Verify they look related but
distinct — different colors, maybe extra sprite layers, tweaked behaviors.

---

### Stage 9: Polish & Resilience
**Goal:** Production-ready. Handles edge cases, feels polished.

Tasks:
- [ ] Generation timeout: if API takes > 5s, fall back to library content
- [ ] Offline mode: if API key not set, dungeon uses only hand-crafted
      templates (current behavior, fully backward compatible)
- [ ] Difficulty scaling: deeper dungeon rooms request harder monsters
- [ ] Themed dungeons: AI gets a theme hint (fire, ice, shadow) that
      influences all generated content in that instance
- [ ] Monster death messages: "You defeated the Flame Wyrm!"
- [ ] Content stats endpoint: `/admin/library-stats` shows library
      composition, generation counts, API usage
- [ ] Stress testing: generate 100 monsters, verify all valid


## Dependency Graph

```
Stage 1: Tags & Metadata ─────────────────────────────┐
    │                                                  │
Stage 2: Client Dynamic Registries                     │
    │                                                  │
Stage 3: Server Dynamic Registration                   │
    │                                                  │
    ├── Stage 4: Behavior Engine (Movement)            │
    │       │                                          │
    │   Stage 5: Behavior Engine (Attacks)             │
    │       │                                          │
    │       └──────────┐                               │
    │                  │                               │
    └── Stage 6: Claude API Integration ◄──────────────┘
                │
        Stage 6.5: Unified Content Refactor
                │
        Stage 7: Library-Managed Dungeons
                │
        Stage 8: Monster Variants
                │
        Stage 9: Polish & Resilience
```

Stage 6.5 unifies all dungeon content into the library system. Precreated
content (rooms, monsters, tiles) uses the same data format as AI-generated
content, with a `permanent` flag to prevent expiry/deletion. The AI prompt
sees a flat list of all available content — no built-in vs custom distinction.


## File Structure

```
mud_server.py              — main server (extended protocol, dungeon builder)
server/
  content_library.py       — library system, tag queries, expiry, persistence
  dungeon_content.py       — precreated dungeon monsters, tiles, room loaders
  behavior_engine.py       — rule evaluator, action functions, attack execution
  ai_generator.py          — Claude API calls, prompts, validation
  dungeons.py              — dungeon instance system (uses libraries)
client/
  client.html              — dynamic sprite/tile registries, projectile rendering
  sprite_data.js           — static sprites (overworld; dungeon uses custom path)
  tiles.js                 — static tiles (overworld; dungeon uses custom path)
data/
  room_library.json        — custom (non-permanent) room templates
  monster_library.json     — custom (non-permanent) monster definitions
  tile_library.json        — custom (non-permanent) tile recipes
  api_usage.json           — token counts + cost tracking per day
rooms/                     — hand-crafted rooms (unchanged, never touched)
rooms/dungeon1/            — precreated dungeon templates (loaded as permanent entries)
```


## Configuration

All tunables in one place (top of `content_library.py`):

```python
# Library capacities (total = permanent + custom placeholders)
ROOM_LIBRARY_CAPACITY = 79     # 64 permanent + 15 custom
MONSTER_LIBRARY_CAPACITY = 8   # 4 permanent + 4 custom
TILE_LIBRARY_CAPACITY = 14     # 7 permanent + 7 custom

# Expiry settings — production (only affects custom entries)
EXPIRY_RATE = 0.10          # expire 10% of library per teardown
EXPIRY_MIN_AGE = 86400      # 24 hours — content lives at least this long

# Expiry settings — testing (uncomment to use)
# EXPIRY_RATE = 0.50        # expire 50% — forces rapid rotation
# EXPIRY_MIN_AGE = 5        # 5 seconds — almost everything is eligible

# AI generation
GENERATION_TIMEOUT = 5.0    # seconds before falling back to library
CONJURING_MIN_DURATION = 1.5  # seconds — animation always plays at least this long
MAX_API_CALLS_PER_MINUTE = 15
MAX_API_CALLS_PER_DAY = 600
VARIANT_MODE_RATIO = 0.70   # 70% tweaks, 30% brand new (when library has >10 monsters)
```


## Cost Estimate

Claude Haiku at ~$0.25/M input, $1.25/M output tokens:
- System prompt + examples: ~1200 tokens input (fixed per call)
- Room generation (layout only): ~500 tokens output → ~$0.001
- Monster generation (design + sprite): ~800 tokens output → ~$0.002
- Tile generation: ~200 tokens output → ~$0.0005
- Typical dungeon: ~15 custom rooms, ~50% placeholder at steady state
  → ~7-8 rooms generated per dungeon, each may create 0-2 monsters/tiles
- First dungeon (empty libraries): ~$0.03 (many new monsters/tiles)
- Steady-state dungeon (~20% placeholders): ~$0.005 (mostly reuse)
- 10 dungeons/day for a month: ~$2-5/month
- With $5 monthly console spending cap: safe
