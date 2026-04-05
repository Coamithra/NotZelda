# Tracker: feat-priest-npc-directs-players-to-the-castle-for-d1

## Pick Up the Card
- [x] Pull latest master
- [x] Read the card
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into the worktree
- [x] Work inside the worktree

## Research
- [x] Read the referenced code
- [x] Trace the call chain
- [x] Identify the blast radius
- [x] Research unknowns
- [x] Summarize findings

## Design
- [x] Draft the approach
- [x] Check for reusable patterns
- [x] Align with the user

## Implement
- [x] Make the changes
- [x] Run safety checks

## Verify
- [ ] Smoke test startup
- [ ] Run existing tests
- [ ] Spot-check logic
- [ ] Flag what needs manual testing

## Review & Ship
- [ ] Update CLAUDE.md
- [ ] Commit and push
- [ ] Peer review
- [ ] Pull master into the branch
- [ ] Re-run smoke tests
- [ ] Return to the root checkout
- [ ] Update music routes if needed
- [ ] Merge to master
- [ ] Clean up
- [ ] Move card to Done
- [ ] Comment on the card
- [ ] Create follow-up tickets

---

## Plan

### Context

Players starting in Corneria currently have no narrative direction toward the first dungeon (d1). The d1 entrance is in the Shattered Armory (ow_7_9), deep in the castle ruins far to the south. Two NPCs — the Priest and the Ranger — are well-positioned to provide breadcrumbs: the Priest for story context, the Ranger for world geography.

### Overworld Geography (verified from .room files)

The ow_ grid uses `ow_{row}_{col}` — row 0 is north, higher rows are south. Columns go west (low) to east (high).

- **Town:** Corneria village (Town Square, Blacksmith N, Tavern E, Chapel W). Portal to ow_6_7.
- **Clearing → ow_0_7** (forest, Ranger NPC): Just south of town via forest_path → clearing.
- **Mountains:** Northwest (ow_0_3..ow_2_3, rows 0-2, cols 1-4)
- **Desert:** Southwest (ow_3_0..ow_6_1, rows 3-6, cols 0-3)
- **Lake:** South-center (ow_4_5..ow_5_7, rows 4-5, cols 5-8)
- **Graveyard:** East (ow_0_11..ow_2_13, rows 0-2, cols 11-13)
- **Swamp:** Southeast (ow_3_11..ow_6_12, rows 3-6, cols 10-14)
- **Castle ruins:** Far south (ow_7_6..ow_10_9, rows 7-10, cols 6-9). d1 entrance in ow_7_9.

### Approach (file by file)

#### 1. `rooms/old_chapel.room` — Priest personality (line 18)

**Current:** "Elderly, wise priest who tends the Old Chapel. Speaks softly and thoughtfully. Deeply worried about Princess Amara's curse in the sanctum to the west. Believes faith and courage can break the curse. Knows ancient lore about the land. Grew up with the Smith — they're old friends despite their different paths."

**Add to end:** Knowledge that the princess was rescued from the ruined castle far to the south. The Priest should be able to tell players about the castle and direct them there. Keep it concise — one or two sentences.

**New personality:** "Elderly, wise priest who tends the Old Chapel. Speaks softly and thoughtfully. Deeply worried about Princess Amara's curse in the sanctum to the west. Believes faith and courage can break the curse. Knows ancient lore about the land. Grew up with the Smith — they're old friends despite their different paths. Knows the princess was once held captive in the ruined castle far to the south — brave adventurers should seek the Shattered Armory there."

#### 2. `rooms/ow_0_7.room` — Ranger personality (line 18)

**Current:** "Grizzled forest ranger who patrols the border between village and wilderness. Speaks bluntly and knows every trail. Has tracked monsters for decades and respects the forest's dangers."

**Add:** A world overview with directional landmarks so the Ranger can orient players. The Ranger knows the lay of the land.

**New personality:** "Grizzled forest ranger who patrols the border between village and wilderness. Speaks bluntly and knows every trail. Has tracked monsters for decades and respects the forest's dangers. Knows the lay of the land: mountains to the northwest, desert to the southwest, a great lake to the south, graveyard and swamps to the east, and the ruined castle far to the south where the old dungeon entrance lies."

#### 3. `server/prompts/npc_world_context.txt` — Shared world context

**Current:** "Medieval fantasy village called Corneria. Key places: Town Square, Blacksmith (N), Tavern (E), Old Chapel & Chapel Sanctum (W). Wilderness beyond with forests, mountains, desert, swamp, graveyard, ruins. Dungeons below the forest. Princess Amara lies cursed in the Chapel Sanctum. Players are adventurers seeking to lift the curse."

**Fix:** "Dungeons below the forest" is inaccurate — the d1 entrance is in the Shattered Armory (castle ruins to the south). Update to reflect the actual geography.

**New:** "Medieval fantasy village called Corneria. Key places: Town Square, Blacksmith (N), Tavern (E), Old Chapel & Chapel Sanctum (W). Wilderness beyond: forests to the south, mountains northwest, desert southwest, lake south, graveyard east, swamps southeast, ruined castle far south. A dungeon entrance lies in the Shattered Armory deep within the castle ruins. Princess Amara lies cursed in the Chapel Sanctum. Players are adventurers seeking to lift the curse."

### Edge Cases / Risks

- **Prompt length:** Personality additions are ~20 words each. Well within LLM context limits. No risk of bloating.
- **World context shared by all NPCs:** The updated geography is general knowledge — appropriate for all NPCs to know. No NPC-specific info leaked.
- **Priest quest handler:** `quests.py:85-96` overrides greeting dialog, not personality. Changes don't conflict.
- **No pipe characters in new text:** The .room parser splits on `|` for dialog/personality/gift. Our text uses no pipes. Safe.
- **No colon in gift section:** Only relevant for gift-bearing NPCs. Priest and Ranger have no gift section. Safe.
- **Existing NPC conversations:** In-memory conversation history is per-session. Personality changes take effect on next server restart. No mid-conversation issues.
