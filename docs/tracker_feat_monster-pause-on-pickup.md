# Tracker: feat/monster-pause-on-pickup

Trello #51 — Monster pause when picking up item

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into worktree
- [x] Push branch to remote

## Phase 2: Research
- [ ] Read item pickup flow (item_obtained / item_effect messages)
- [ ] Read monster behavior tick (behavior_engine.py)
- [ ] Trace how monsters target players and deal damage
- [ ] Identify the blast radius — what systems touch this code

## Phase 3: Design
- [ ] Draft approach (where to pause, how to resume, edge cases)
- [ ] Align with user

## Phase 4: Implement
- [ ] Server-side: pause monsters during item pickup
- [ ] Client-side: any needed changes (if any)

## Phase 5: Verify
- [ ] Smoke test: `python -c "import mud_server"`
- [ ] Run `python tools/test_api_leak.py`
- [ ] Spot-check diff for issues

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review (fresh agent)
- [ ] Pull master, re-smoke
- [ ] Merge to master
- [ ] Clean up worktree + branch
- [ ] Move card to Done + comment
