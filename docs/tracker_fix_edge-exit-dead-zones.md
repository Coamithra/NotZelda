# Tracker: fix/edge-exit-dead-zones

Trello #10 — Edge exit dead zones
Card: https://trello.com/c/F5Jjxuw6

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch

## Phase 2: Research
- [x] Read the referenced code (_check_edge_exit_float in server/commands.py)
- [x] Read DOORWAY_TILES in server/constants.py
- [x] Trace the call chain (position_update → _check_edge_exit_float → do_room_transition)
- [x] Identify the blast radius (server/commands.py only, no client changes needed)
- [x] Summarize findings

## Phase 3: Design
- [ ] Draft the approach
- [ ] Align with user

## Phase 4: Implement
- [ ] Replace hardcoded ranges with DOORWAY_TILES-derived values
- [ ] Run safety checks (no ai_generator/content_viewer/.env changes, so test_api_leak not needed)

## Phase 5: Verify
- [ ] Smoke test: python -c "import mud_server"
- [ ] Spot-check the diff
- [ ] Flag manual testing notes

## Phase 6: Review & Ship
- [ ] Commit & push
- [ ] Peer review
- [ ] Pull master into branch
- [ ] Re-run smoke tests
- [ ] Merge to master & push
- [ ] Clean up worktree + branch
- [ ] Move card to Done + add comment
