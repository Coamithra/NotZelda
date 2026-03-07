# AI Room Generator Prompt Audit

Audit of `ai_generator.py` system prompt and few-shot example, performed 2026-03-07.
All issues listed below have been fixed.

## A. Factual Errors in Example Layouts

1. **Asymmetric layout had wrong column count** — Multiple rows were 14 characters instead of 15, teaching the model a wrong grid size.
2. **Asymmetric layout violated doorway rules** — East doorway (col 14, rows 4-6) was all walls, directly contradicting the constraint that those cells must be walkable.
3. **Symmetric layout had rows with 16 characters** — Rows 3 and 7 were too long.

## B. Few-Shot Example Problems

4. **Zero built-in tiles used** — The Ember Chamber tilemap used only custom `ember_floor` and `charred_wall`. Not a single DW, DF, PL, or SC. Trained the model to completely replace the built-in palette.
5. **Empty attacks array at difficulty 4** — Guidelines say medium difficulty (4-6) should have "simple attacks," but the example had `"attacks": []`.
6. **Only one monster type** — Two placements of the same `fire_imp`. Didn't demonstrate creating multiple distinct monsters.
7. **Interior was ~75% walkable** — Prompt says "30-60% of interior walkable" but the example was mostly open floor with scattered walls.
8. **Only 2 tile operations demonstrated** — Used fill+noise+pixels and fill+noise+bricks+pixels. Never showed grid_lines, hstripes, vstripes, wave, ripple, or rects in action.

## C. Inconsistent / Ambiguous Specifications

9. **Behavior rule parameter naming inconsistent** — Template showed `"value": N` as universal, but `player_within` actually uses `"range"`. The model had to reconcile two conflicting patterns.
10. **"Frame 1" was ambiguous** — "Frame 1 is the hop frame" could mean index 0 or index 1. (It means index 1.)
11. **`always` vs `default` never distinguished** — Both listed as conditions with no explanation of the difference. (They're identical; prefer `default`.)

## D. Underspecified Tile Operations

12. **`bricks` uses `alt` color implicitly** — Prompt showed `{"op": "bricks"}` with zero parameters, but the renderer draws mortar lines using the `alt` color key. If the AI's color dict lacks `alt`, bricks renders wrong.
13. **`grid_lines`, `hstripes`, `vstripes` all use `alt` implicitly** — Documented with only `spacing` parameter, but they hardcode `alt` for line color.
14. **`wave` uses `alt` implicitly** — No parameters documented, but draws alternating pixels using `alt`.
15. **`ripple` uses both `alt` and `base`** — Alternates between the two, undocumented.
16. **No `color` parameter on line-drawing ops** — The AI can't control what color these ops draw in; they always use `alt`. Prompt implied configurability that doesn't exist.

## E. Missing Specifications

17. **No `hop_interval` guidance per difficulty** — Stats ranges list 0.2-10.0 but no guidance on what values feel right per difficulty tier. 0.2 is absurdly fast; 10.0 means the monster barely moves.
18. **No monster placement restrictions near doorways** — Coordinate bounds allowed monsters on doorway tiles (e.g. `(7, 0)`), meaning players take damage immediately on room entry.
19. **No guidance on monster spacing** — No mention of whether monsters can share tiles or should be spread out.
20. **Attack type parameters incomplete** — `projectile` range (travel distance), `teleport` range (max distance), `area` range (AoE radius) were all unspecified. `melee` range constraint (must be 1) was unclear.

## F. Template / Format Issues

21. **Response format showed empty arrays** — `"new_tiles": [], "new_monsters": []` subtly signaled that empty is normal, even when the user message demands new content.
22. **`"colorKey"` as a literal key name in tile template** — Looked like a reserved keyword. Should use real examples like `"accent"`.
23. **Stat ranges inline in JSON not valid JSON** — `"hp": 1-100` is documentation embedded in a code block. Could confuse the model into using range notation.
24. **`"base"` color key has a hidden special role** — `runTileRecipe()` auto-fills with `colors.base` before processing operations, but prompt didn't explain this.

## G. Structural / Strategy Issues

25. **Prompt says "Use DW tiles INSIDE" but example didn't** — Guidance named DW for interior walls but the example used only custom tiles.
26. **No room name guidance** — No conventions for length, style, or uniqueness.
27. **Tag guidance was placeholder-level** — `"tags": ["theme", "combat_style"]` were meta-descriptions, not real examples. Model might literally use "theme" as a tag.
28. **"Dominant tile" instruction undermined by example** — Instruction appeared in system prompt, then the few-shot response used 100% custom tiles before the user message repeated it more forcefully.

## Fixes Applied

### System Prompt
- Fixed both ASCII layouts: correct column counts, valid doorways, flood-fill connected
- Documented `base`/`alt` color key requirements for tile operations
- Listed all tile operations with explicit parameter and color descriptions
- Changed "Frame 1" to "The second frame (index 1)"
- Fixed behavior rule parameter naming: explicit per-condition (`"range"` vs `"value"`)
- Clarified `default` vs `always` (identical, prefer `default`)
- Added behavior rule ordering guidance
- Added `hop_interval` ranges to difficulty guidelines
- Added monster placement restrictions (interior only, away from doorways)
- Added "MIX of built-in + custom tiles" guidance
- Fully specified attack type parameters with range bounds and required extra fields
- Replaced placeholder template values with real examples
- Added sprite design tips
- Added room name guidance (rule 8)

### Few-Shot Example
- Uses mixed built-in (DW, PL, SC) + custom tiles (ember_floor)
- Two distinct monster types: fire_imp (melee chaser) and flame_spitter (ranged, holds position)
- Both monsters have attacks (melee and projectile)
- 54% interior walkable (within 30-60% target)
- Three monster placements, all on walkable interior tiles (rows 2-9, cols 2-13)
- Difficulty raised to 5 to match medium tier with attacks
