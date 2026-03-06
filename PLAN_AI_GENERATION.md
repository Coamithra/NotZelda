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
    { "role": "medium_melee", "tags": ["fire"], "preferred": "flame_wyrm" },
    { "role": "ranged",       "tags": ["fire"], "preferred": "ember_spitter" }
  ],
  "custom_tiles": {
    "X1": { "role": "floor_variant", "tags": ["fire"], "preferred": "lava_crack" },
    "X2": { "role": "light_source",  "tags": ["wall_mounted"], "preferred": "brazier" }
  }
}
```

At dungeon build time, each slot resolves:
1. Is `preferred` still in the library? Use it.
2. Gone? Search for any content matching `role` + `tags`.
3. No tag match? Match by `role` alone.
4. Nothing? Generate a replacement on the spot — role and tags become
   the AI prompt.

This means:
- Rooms are durable — they degrade gracefully, almost never become invalid
- Monsters and tiles can rotate freely
- Replacement is semantic ("find me another wall-mounted light source"),
  not fuzzy name matching
- The AI is great at tagging its own output — include the tag vocabulary
  in the system prompt

### Tag Vocabulary

Roles and tags are a fixed vocabulary (extendable over time):

**Monster roles:** `fodder`, `light_melee`, `medium_melee`, `heavy_melee`,
`ranged`, `tank`, `boss`, `swarm`

**Monster tags:** `fire`, `ice`, `shadow`, `undead`, `beast`, `magic`,
`poison`, `flying`, `dungeon`, `cave`, `swamp`, `desert`

**Tile roles:** `floor_base`, `floor_variant`, `wall_base`, `wall_variant`,
`pillar`, `structural`, `light_source`, `decoration`, `hazard`,
`container`, `furniture`

**Tile tags:** `fire`, `ice`, `shadow`, `stone`, `wood`, `metal`,
`organic`, `magical`, `wall_mounted`, `freestanding`, `dungeon`,
`walkable`, `blocking`

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

**Current status: Stages 1–5 complete. Next up: Stage 6 (Claude API Integration).**

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

### Stage 6: Claude API Integration
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

### Stage 7: Library-Managed Dungeon Generation (Lazy)
**Goal:** Dungeons are built from the self-managing library. Content is
generated **lazily** — only when a player actually enters a room, not all
at once. This keeps dungeon entry instant.

The key principle: **layout assignment is instant, content resolution is
deferred to room entry.**

Tasks:
- [ ] Create room library (capacity 50), monster library (capacity 40),
      tile library (capacity 30) — all with placeholder slots
- [ ] Expiry runs inside `destroy_dungeon()` (when all players leave) —
      the one moment when nothing references library content:
  - Expire oldest ~N% of each library (configurable)
  - Only expire entries older than a minimum age (configurable)
  - If nothing qualifies (all content is recent), nothing expires
  - Save libraries to disk after expiry
  - No separate timer/cron needed — piggybacking on dungeon teardown
    avoids "is the dungeon active?" race conditions entirely
  - **Production defaults:** 10% expiry rate, 24 hour minimum age
  - **Test defaults:** 50% expiry rate, 5 second minimum age (forces
    rapid rotation so you can observe the full lifecycle quickly)
- [ ] Refactor `create_dungeon()` — instant, no API calls:
  1. Pick layout (existing logic)
  2. Shuffle room library (real + placeholders), assign slots to cells
  3. Store assignments in dungeon instance: `cell → library_slot`
  4. Only resolve the entrance room (1 API call max if placeholder)
  5. Player enters dungeon immediately
- [ ] Add lazy resolution in `on_player_enter_room()`:
  1. Is this dungeon room already resolved? Use it (instant).
  2. Not yet? Check the assigned library slot:
     - **Real entry** → room template already exists. Resolve any
       monster/tile references that may have expired since the
       template was created (late binding fallback chain). Instant.
     - **Placeholder** → call `generate_room()` (single API call).
       The prompt includes existing library content, so the AI
       reuses known monsters/tiles where fitting and only creates
       new ones if needed. Any new monsters/tiles are added to
       their respective libraries. The room itself is added to the
       room library.
  3. Register any new custom sprites/tiles with the client, build
     the room, send `room_enter` to client.
- [ ] The AI prompt adapts to library fullness:
  - Monster library has room → "reuse these if fitting, create new
    if needed: [list of kind/role/tags]"
  - Monster library full → "use only these monsters: [list]"
  - Same for tiles
  - This means early rooms are slower (more new content per call)
    and later rooms are faster (AI just arranges existing pieces)
- [ ] **Loading animation** — client-side "conjuring" screen shown while
      a room is being generated:
  - Server sends `{ type: "room_generating" }` when lazy resolution
    starts an API call
  - Client shows a full-screen dark overlay with animated effects:
    flickering torchlight (orange glow pulsing), drifting particles
    (small dots floating upward), mystical rune circles or arcane
    symbols fading in and out
  - Atmospheric text: "The dungeon shifts..." or "Dark forces stir..."
    (could be AI-generated too, or a random pick from a list)
  - Seamlessly transitions into the normal room-enter slide/fade
    when the room is ready
  - Animation has a **minimum duration** (e.g., 1.5s) even if the room
    resolves instantly from library. For instant rooms the animation
    is purely cosmetic; for generated rooms the API call happens
    behind it
  - **Only plays on first visit** to a room within a dungeon instance.
    Returning to an already-visited room uses the normal slide/fade
    transition. The dungeon instance tracks which rooms the player
    has seen
  - Animation should feel like the dungeon is alive and building
    itself, not like a loading screen
- [ ] Fallback: if API fails or times out (>5s), swap placeholder for
      random real library entry — player never gets stuck
- [ ] Resolved rooms stay resolved for the dungeon's lifetime — walking
      back into an already-visited room is always instant
- [ ] Persist libraries to disk after each generation
- [ ] **Verbose server log** — written to `generation_log.txt` using
      existing `log_event()` system. Logged for every generation event:
  - `[GEN] Room generated: "Ember Sanctum" (placeholder #23, 1.8s,
    482 tokens, 2 new monsters, 1 new tile)`
  - `[GEN] Room resolved from library: "Frost Chamber" (slot #7, instant,
    3 monsters reused, 0 new)`
  - `[GEN] Monster created: "flame_wyrm" (mode A, medium_melee, fire)`
  - `[GEN] Monster variant: "frost_wyrm" based on "flame_wyrm" (mode B)`
  - `[GEN] Tile created: "lava_crack" (floor_variant, fire)`
  - `[GEN] Expiry: removed 5 rooms, 4 monsters, 3 tiles (oldest >24h)`
  - `[GEN] Fallback: API timeout, swapped placeholder #12 for library
    room "Shadow Hall"`
  - `[GEN] Library status: rooms 45/50, monsters 38/40, tiles 28/30`
  - `[GEN] API error: <error message> (retry 1/1)`
- [ ] **In-game debug panel** — condensed version shown in the existing
      debug overlay (backtick / pi button toggle):
  - Current library fill: `Lib: R:45/50 M:38/40 T:28/30`
  - Last generation: `Gen: "Ember Sanctum" 1.8s 482tok`
  - Room source: `Room: generated` or `Room: library #7` or
    `Room: fallback`
  - API stats: `API: 12 calls today, $0.008`
  - Shown only for dungeon rooms (no clutter in overworld)

**Flow example:**
```
Player enters dungeon → layout assigned (instant)
  → entrance room resolved (1 API call if placeholder, ~1-2s)
  → player is in

Player walks north → first visit, room is a real library entry
  → conjuring animation (1.5s min) → player is in

Player walks east → next room is a placeholder
  → "conjuring" animation plays → API call (~1-2s)
  → room generated, added to library → animation ends → player is in

Player walks west back → already visited → normal slide transition
```

At steady state (~20% placeholders), most room transitions are instant.
Worst case is 1-2 seconds for a single room, never a multi-room stall.

**Test:** Start with empty libraries. Enter dungeon — entrance loads in
~2s. Walk around — some rooms instant, some pause briefly. Walk back —
always instant. Enter another dungeon — verify more rooms are instant
(library has grown). Simulate expiry, verify fresh rooms appear.

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
        Stage 7: Library-Managed Dungeons
                │
        Stage 8: Monster Variants
                │
        Stage 9: Polish & Resilience
```

Stages 4-5 (behavior engine) and Stage 6 (API integration) can be built
in parallel — they converge at Stage 7.


## File Structure

```
mud_server.py              — main server (extended protocol, dungeon builder)
content_library.py         — library system, tag queries, expiry, persistence
behavior_engine.py         — rule evaluator, action functions, attack execution
ai_generator.py            — Claude API calls, prompts, validation
client.html                — dynamic sprite/tile registries, projectile rendering
sprite_data.js             — static sprites (unchanged, backward compat)
tiles.js                   — static tiles + dynamic recipe interpreter
generation_config.json     — tunables (capacities, expiry rate, timeouts)
data/
  room_library.json        — generated room templates with metadata
  monster_library.json     — generated monster definitions with metadata
  tile_library.json        — generated tile recipes with metadata
  generation_log.txt       — verbose event log (room created, expiry, errors)
  api_usage.json           — token counts + cost tracking per day
rooms/                     — hand-crafted rooms (unchanged, never touched)
rooms/dungeon1/            — hand-crafted dungeon templates (unchanged)
```


## Configuration

All tunables in one place (e.g., top of `content_library.py` or a
`generation_config.json`):

```python
# Library capacities
ROOM_LIBRARY_CAPACITY = 50
MONSTER_LIBRARY_CAPACITY = 40
TILE_LIBRARY_CAPACITY = 30

# Expiry settings — production
EXPIRY_RATE = 0.10          # expire 10% of library per teardown
EXPIRY_MIN_AGE = 86400      # 24 hours — content lives at least this long

# Expiry settings — testing (uncomment to use)
# EXPIRY_RATE = 0.50        # expire 50% — forces rapid rotation
# EXPIRY_MIN_AGE = 5        # 5 seconds — almost everything is eligible

# AI generation
GENERATION_TIMEOUT = 5.0    # seconds before falling back to library
CONJURING_MIN_DURATION = 1.5  # seconds — animation always plays at least this long
MAX_API_CALLS_PER_MINUTE = 5
MAX_API_CALLS_PER_DAY = 100
VARIANT_MODE_RATIO = 0.70   # 70% tweaks, 30% brand new (when library has >10 monsters)

# Monster behavior defaults
DEFAULT_BEHAVIOR = {"rules": [{"default": "wander"}], "attacks": []}
```


## Cost Estimate

Claude Haiku at ~$0.25/M input, $1.25/M output tokens:
- System prompt + examples: ~1200 tokens input (fixed per call)
- Room generation: ~500 tokens output → ~$0.001
- Monster generation: ~400 tokens output → ~$0.0008
- Tile generation: ~200 tokens output → ~$0.0005
- Full dungeon (5 rooms + 8 monsters + 4 tiles): ~$0.01
- 10 dungeons/day for a month: ~$3/month
- With $5 monthly console spending cap: impossible to overspend
