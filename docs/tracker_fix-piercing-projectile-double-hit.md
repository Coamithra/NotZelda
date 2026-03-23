# Tracker: fix/piercing-projectile-double-hit

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress

## Phase 2: Research
- [x] Read the referenced code (server/combat.py — _tick_projectiles, exec_projectile, Projectile model)
- [x] Trace the call chain (game_tick → _tick_projectiles → player collision loop)
- [x] Identify the blast radius
- [x] Summarize findings

## Phase 3: Design
- [ ] Draft the approach
- [ ] Check for reusable patterns
- [ ] Align with the user

## Phase 4: Branch & Implement
- [x] Create feature branch fix/piercing-projectile-double-hit
- [x] Make the changes
- [x] Run safety checks

## Phase 5: Verify
- [x] Smoke test — python -c "import mud_server"
- [x] Run existing tests
- [x] Spot-check logic
- [ ] Flag what needs manual testing

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md (if needed)
- [ ] Commit & push
- [ ] Peer review (fresh agent)
- [ ] Pull master into branch
- [ ] Re-run smoke tests
- [ ] Merge to master
- [ ] Clean up branch
- [ ] Move card to Done
- [ ] Comment on card
