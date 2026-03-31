# Tracker: feat/gauntlet

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into worktree
- [x] Create tracker doc

## Phase 2: Research
- [x] Read monster definitions in data/monsters.json (bat, skeleton, ghost stats)
- [x] Read behavior_engine.py — understand script execution, timing, cooldown, windup
- [x] Read dungeon creation code — how trap rooms work, how monsters spawn
- [x] Read combat.py — spirit jar auto-revive, HP reset between rooms
- [x] Trace the tuneable parameters: script_time, cooldown, windup, teleport radius
- [x] Understand how dungeon instances work (linear layout feasibility)
- [x] Summarize findings and identify approach

## Phase 3: Design
- [x] Draft the gauntlet approach (linear dungeon, live tuning, logging)
- [x] Identify which parameters to expose and how
- [x] Check for reusable patterns (dungeon creation, trap rooms, spirit jar)
- [x] Align with user on design

## Phase 4: Implement
- [x] Build gauntlet dungeon generator (linear trap rooms)
- [x] Build tuning interface (/gt command)
- [x] Add auto-revive + HP reset per room
- [x] Add per-room result logging (settings used, HP lost)
- [x] Safety checks (smoke test passes)

## Phase 5: Verify
- [x] Smoke test — does it start?
- [x] Test gauntlet entry and room progression (manual)
- [x] Verify logging output (manual)
- [x] Flag what needs manual testing

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review
- [ ] Pull master into branch
- [ ] Re-run smoke tests
- [ ] Merge to master
- [ ] Clean up worktree/branch
- [ ] Move card to Done + comment
- [ ] Create follow-up tickets
