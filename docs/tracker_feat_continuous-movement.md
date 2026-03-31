# Tracker: feat/continuous-movement

Trello #89 — Pivot away from tile-based movement

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [ ] Copy `.env` into the worktree

## Phase 2: Research
- [ ] Read current monster movement code (behavior_engine.py, models.py WalkState)
- [ ] Read sword hitbox code (commands.py sword_hitbox())
- [ ] Read collision/contact damage code (combat.py)
- [ ] Read client-side walk interpolation (client.html, renderer.js)
- [ ] Read monster walk networking (net.py, net.js)
- [ ] Trace how monster position is stored, updated, and broadcast
- [ ] Trace how player position differs (continuous vs tile-based)
- [ ] Identify all code that assumes 0.5-tile grid snapping
- [ ] Identify blast radius: what breaks if monsters move fractionally
- [ ] Summarize findings

## Phase 3: Design
- [ ] Draft approach (plan doc)
- [ ] Address netcode concern from Trello comment
- [ ] Check for reusable patterns
- [ ] Align with user

## Phase 4: Implement
- [ ] Make the changes per approved plan
- [ ] Run safety checks

## Phase 5: Verify
- [ ] Smoke test (import mud_server)
- [ ] Run test_api_leak.py
- [ ] Spot-check logic
- [ ] Flag manual testing needs

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md
- [ ] Commit & push
- [ ] Peer review
- [ ] Pull master, re-test
- [ ] Merge to master
- [ ] Clean up worktree/branch
- [ ] Move card to Done + comment
- [ ] Create follow-up tickets if needed
