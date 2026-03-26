# Tracker: fix/ai-room-reachability

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into the worktree
- [x] Push branch to remote

## Phase 2: Research
- [x] Read the referenced code (_resolve_room_from_entry, _find_item_tile, patch_doorway_tiles)
- [x] Trace the call chain (dungeon room resolution → walling off exits → item/monster placement)
- [x] Identify the blast radius
- [x] Summarize findings

## Phase 3: Design
- [x] Draft the approach
- [x] Check for reusable patterns (bfs_reachable, etc.)
- [x] Align with the user

## Phase 4: Implement
- [x] Make the changes
- [x] Run safety checks

## Phase 5: Verify
- [x] Smoke test (python -c "import mud_server")
- [x] Run existing tests
- [x] Spot-check logic
- [ ] Flag what needs manual testing

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review
- [ ] Pull master into branch
- [ ] Re-run smoke tests
- [ ] Return to root checkout
- [ ] Merge to master & push
- [ ] Clean up worktree and branch
- [ ] Move card to Done
- [ ] Comment on card
