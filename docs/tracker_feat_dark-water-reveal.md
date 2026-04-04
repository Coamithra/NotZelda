# Tracker: feat/dark-water-reveal

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy `.env` into the worktree

## Phase 2: Research
- [x] Read the Sinking Marsh room file (ow_5_12.room) — d2 entrance area
- [x] Read darkness rendering system (renderer.js renderDarkness)
- [x] Read water-walking tile system (renderer.js WATER_TILES, commands.py water walk)
- [x] Read dungeon entrance logic (how stairs/transitions work)
- [x] Read tile definitions for water and dark tiles (tiles.json)
- [x] Trace the call chain for room enter + tile rendering
- [x] Identify blast radius (what other systems this touches)
- [x] Summarize findings

## Phase 3: Design
- [x] Draft approach (file-by-file changes)
- [x] Check for reusable patterns
- [x] Align with user

## Phase 4: Implement
- [x] Make the changes
- [x] Run safety checks if needed

## Phase 5: Verify
- [x] Smoke test (python -c "import mud_server")
- [x] Run test_api_leak.py
- [x] Spot-check logic (found + fixed spawn_stair guard bug)
- [ ] Flag what needs manual testing

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review
- [ ] Pull master into branch
- [ ] Re-run smoke tests
- [ ] Merge to master & push
- [ ] Clean up worktree + branch
- [ ] Move card to Done
- [ ] Comment on card
- [ ] Create follow-up tickets if needed
