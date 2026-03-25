# Tracker: fix/tile-sprite-name-collision

Trello #15 — Custom tile/sprite registration silently overwrites

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch

## Phase 2: Research
- [ ] Read server/validation.py:269-320
- [ ] Trace how custom tiles/sprites are registered
- [ ] Identify where name collisions cause silent overwrites
- [ ] Identify blast radius

## Phase 3: Design
- [ ] Draft the approach
- [ ] Align with user

## Phase 4: Implement
- [ ] Make changes per approved plan
- [ ] Run safety checks if needed

## Phase 5: Verify
- [ ] Smoke test (import mud_server)
- [ ] Spot-check logic / review diff
- [ ] Flag what needs manual testing

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review
- [ ] Pull master, re-smoke
- [ ] Merge to master & push
- [ ] Clean up worktree/branch
- [ ] Move card to Done + comment
