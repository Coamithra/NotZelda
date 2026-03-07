# Prompt Improvement Plan

Follow-up to `PROMPT_AUDIT.md`. These are remaining issues found in
`tmp_prompts/prompt_20260307_121507.txt` after the first round of fixes.

---

## A. Tile Agnosticism (items 1, 6, 7, 11)

The prompt currently leaks "built-in vs custom" concepts in multiple places,
biasing the model toward DW/DF and fire-themed naming. Fix this throughout.

### A1. Remove built-in tile list from TILEMAP FORMAT section
**Problem:** The TILEMAP FORMAT section hardcodes `DW, DF, PL, SC` as "built-in dungeon tile codes." Then the USER section repeats them as "available tiles," and again in the dynamic area. Three redundant mentions that anchor the model to these four codes.
**Fix:** Remove the built-in tile list from TILEMAP FORMAT entirely. The only place tiles are listed is the dynamic USER section, which says "these are the tiles you can use" (and that the AI can add 1-2 of its own). The system prompt should describe tile *mechanics* (walkable vs non-walkable, doorway constraints) without naming specific tile codes.

### A2. Use generic X/Y in response format example
**Problem:** The response format template shows `"DW"` and `"DF"` in the example tilemap row, biasing the model to default to these two codes.
**Fix:** Replace with placeholder labels: "Assume X is a non-walkable tile and Y is a walkable tile" and use `X`/`Y` in the example row. This keeps the format clear without anchoring to specific tile IDs.

### A3. Replace DW/DF in the ASSISTANT few-shot example
**Problem:** The Ember Sanctum example tilemap is full of `"DW"` references, reinforcing built-in tile dominance.
**Fix:** Replace all `DW` with a generic non-walkable name (e.g. `"stone_wall"`) and any `DF` with a generic walkable name. Use names like `"wall1"`, `"floor1"` or thematic-but-neutral names. PL and SC should also become generic names. The point: every tile in the example should come from the "available tiles" list or `new_tiles`, with no hardcoded built-in codes.

### A4. Use neutral custom tile names to prevent theme bias
**Problem:** The fire-themed example (`ember_floor`, `fire_imp`, `flame_spitter`) is the only few-shot. When generating ice/shadow/dungeon rooms the model borrows warm naming and fire aesthetics.
**Fix:** Rename the example's custom tiles to neutral names like `alt_floor`, `alt_wall`. Keep color values present (they demonstrate the format) but make naming generic so the model doesn't anchor on fire vocabulary.

### A5. Fix rule 1 to be tile-agnostic
**Problem:** Rule 1 says "All tile codes must be either a built-in code (DW, DF, PL, SC) or defined in new_tiles or in the available tiles list."
**Fix:** Change to: "All tile codes in the tilemap must be part of the set defined in available tiles, or defined in new_tiles."

---

## B. Sprite Animation Overhaul (item 2)

### B1. Remove "hop frame" constraint, allow 1-4 frames
**Problem:** The current spec demands exactly 2 frames where frame 1 is a "hop" (shift all layers up 1-2px). This produces boring, uniform animations — every monster just bounces up and down identically.
**Fix:**
- Allow 1-4 frames per sprite (not locked to 2)
- Remove the "shift all layers up 1-2px" hop instruction
- Instead, say frames should show interesting animation: stretching, pulsing, limb movement, shape changes, eye blinks, etc.
- Reference the slime sprite (`sprite_data.js:298-321`) as the gold standard:
  - Frame 0 (squished): wide body (x=3, w=10) sitting low (y=8), eyes at y=9
  - Frame 1 (stretched): narrow body (x=4, w=8) reaching up (y=4), eyes at y=6
  - The entire shape changes between frames — not just a y-offset
- Similarly the bat (`sprite_data.js:323-345`): wings up vs wings down, completely different wing positions
- Update the sprite format section and the few-shot example to show a 2+ frame sprite with actual animation, not just a y-offset hop

---

## C. Example Layout Improvements (item 5)

### C1. Richer legend for ASCII example layouts
**Problem:** Current legend is `x=wall, .=walkable, P=pillar, S=sconce` — ties to specific built-in tiles and doesn't distinguish common vs decorative.
**Fix:** New legend:
- `x` = non-walkable (common/structural)
- `o` = non-walkable (uncommon/decorative)
- `.` = walkable (common)
- `_` = walkable (decorative)

Update both example maps (asymmetric and symmetric) to use all four symbols, showing how decorative tiles are scattered among common ones. This teaches the model to vary tile usage without naming specific tile types.

---

## D. Remove Theme Guidelines (item 4)

### D1. Delete the THEME GUIDELINES section
**Problem:** The theme guidelines section (`fire: oranges/reds...`, `ice: blues/whites...`, etc.) is hand-holdy. The AI can be trusted to pick appropriate colors/creatures for a given theme.
**Fix:** Remove the entire `## THEME GUIDELINES` section. Can be re-added later if outputs degrade.

---

## E. Specification Text Fixes (from audit round 2)

### E1. Fix "`default` is a fallback action" wording
**Problem:** Line 55 says "`default` is the fallback action." But `default` is a condition/rule, not an action. Could lead to `{"do": "default"}`.
**Fix:** Change to: "`default` is the fallback condition (always matches). Use it for the last rule."

### E2. Distinguish `stats.damage` from `attacks[].damage`
**Problem:** Both exist but their relationship is never explained. `stats.damage` = contact damage, `attacks[].damage` = per-attack damage.
**Fix:** Add: "`stats.damage` is **contact damage** when the monster touches a player. `attacks[].damage` is separate per-attack damage. Both can coexist."

### E3. State sprite layer rendering order
**Problem:** Never stated that layers render in array order (first = back, last = front).
**Fix:** Add: "Layers render in array order — first layer is the back, last layer is the front. Put shadows/bases first, details/eyes last."

### E4. Explain attack array priority
**Problem:** `execute_monster_attack()` picks the first usable attack. Model doesn't know this.
**Fix:** Add: "Attacks are tried in array order — first usable attack fires. Put preferred/ranged attacks first, close-range fallbacks last."

### E5. Cap custom tile count
**Problem:** "At least 1" with no upper bound.
**Fix:** Change to: "Create 1-2 new custom tiles that fit the theme."

### E6. Mark `walkable` as required on custom tiles
**Problem:** Shown in format but never called out as mandatory. Omission wastes an API call.
**Fix:** Add: "The `walkable` field is REQUIRED."

### E7. Add tag count guidance
**Problem:** No stated range for tag count.
**Fix:** Add: "Use 3-5 tags per monster and per tile."

### E8. Demonstrate more tile operations in few-shot
**Problem:** Only `fill` + `noise` + `pixels` shown. `bricks`, `hstripes`, `wave`, `rects` etc. never demonstrated.
**Fix:** Add a second custom tile to the example (non-walkable) using different ops like `bricks` or `hstripes`. This also fills the gap of never demonstrating a custom wall tile.

---

## Implementation Order

Group by what they touch to minimize churn:

### Pass 1: System prompt text (E1-E7, D1)
One-liner spec fixes plus theme guidelines removal. Low risk, all independent.

### Pass 2: Example layouts (C1)
Rewrite the two ASCII layouts with the new 4-symbol legend. Independent of other changes.

### Pass 3: Tile agnosticism in spec text (A1, A2, A5)
Remove built-in tile references from TILEMAP FORMAT, response format, and rule 1. These are text-only changes to the system prompt.

### Pass 4: Few-shot example overhaul (A3, A4, B1, E8)
The big one — rework the ASSISTANT example:
- Replace all DW/DF/PL/SC with generic tile names from a fake "available tiles" list
- Rename custom tiles to neutral names
- Rework sprite frames to show real animation (not hop)
- Add a second custom tile with different ops
- Update the USER prompt in the few-shot to match (provide a neutral "available tiles" list)

### Pass 5: Verify
Re-dump a prompt with `python ai_generator.py` and check the output file for consistency.
