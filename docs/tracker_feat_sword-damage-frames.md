# Tracker: feat/sword-damage-frames

Trello card #65 — Sword multiple damage frames

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into worktree

## Phase 2: Research
- [x] Read server combat code (_process_attack in commands.py)
- [x] Read client attack input, animation, rendering
- [x] Understand game tick loop (30Hz, ~33ms per tick)
- [x] Identify current single-frame damage check
- [x] Understand attack cooldown (400ms) vs animation (300ms)

## Phase 3: Design
- [ ] Draft approach for multi-frame sword damage
- [ ] Align with user on design

## Phase 4: Implement
- [ ] Add active_attack state to Player model
- [ ] Split _process_attack into initiation + per-tick check
- [ ] Add _tick_active_attacks to game_tick loop
- [ ] Add SWORD_ACTIVE_DURATION constant

## Phase 5: Verify
- [ ] Smoke test (python -c "import mud_server")
- [ ] Spot-check logic (review diff)
- [ ] Flag manual testing needs

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md
- [ ] Commit & push
- [ ] Peer review
- [ ] Pull master, re-test
- [ ] Merge to master
- [ ] Clean up worktree
- [ ] Move card to Done + add comment
