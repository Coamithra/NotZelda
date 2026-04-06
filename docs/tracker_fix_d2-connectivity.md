# Tracker: fix/d2-connectivity

Trello cards:
- D2: Spanning tree crash — KeyError (69d408b3)
- D2: Rooms structurally disconnected (69d408b7)

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the cards (description, comments, linked docs)
- [x] Move cards to In Progress
- [x] Create worktree and branch
- [x] Copy .env into worktree (skipped — not needed for tests)

## Phase 2: Research
- [x] Read server/dungeons.py — D2 layout generation, _build_spanning_tree()
- [x] Trace the call chain for D2 dungeon creation
- [x] Identify why cells missing from adjacency dict (crash bug)
- [x] Identify why rooms get structurally disconnected
- [x] Check dungeon_topology.py for related logic
- [x] Summarize findings

## Phase 3: Design
- [x] Draft approach for both fixes
- [x] Align with user

## Phase 4: Implement
- [x] Make the changes in worktree
- [x] Run safety checks if needed (no ai_generator/env changes)

## Phase 5: Verify
- [x] Smoke test — python -c "import mud_server"
- [x] Run test_reachability.py — D2 bugs fixed (remaining failures are pre-existing D1/key-solver issues)
- [ ] Run full integration test suite
- [ ] Spot-check diff
- [ ] Flag manual testing needs

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review (fresh agent)
- [ ] Pull master, re-test
- [ ] Merge to master & push
- [ ] Clean up worktree/branch
- [ ] Move cards to Done, comment on cards
- [ ] Create follow-up tickets if needed
