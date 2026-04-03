# Tracker: feat/d2-water-walking

Trello card: 69d01680 — D2: Water-walking mechanic

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into worktree

## Phase 2: Research
- [ ] Read WA tile definition in tiles.json
- [ ] Read walkability check code (state.py: is_walkable_tile)
- [ ] Trace has_lantern pattern (server + client) as reference
- [ ] Read d2 dungeon type config (dungeon_types.py)
- [ ] Read d2 treasure chest placement code
- [ ] Read d2 boss room layout (.room file)
- [ ] Read client water rendering code
- [ ] Summarize findings

## Phase 3: Design
- [ ] Draft approach
- [ ] Check for reusable patterns
- [ ] Get user approval

## Phase 4: Implement
- [ ] Server: add has_water_walking flag to Player
- [ ] Server: make WA walkable for flagged players
- [ ] Server: add treasure item to d2 chest
- [ ] Client: visual indicator for water-walking
- [ ] Update d2 boss room layout (more WA)
- [ ] Update pre-boss room to gate on water-walking

## Phase 5: Verify
- [ ] python -c "import mud_server" smoke test
- [ ] python tools/test_api_leak.py
- [ ] Spot-check diff

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md
- [ ] Commit & push
- [ ] Peer review
- [ ] Pull master, re-test
- [ ] Merge to master
- [ ] Clean up worktree/branch
- [ ] Move card to Done + comment
- [ ] Create follow-up tickets if needed
