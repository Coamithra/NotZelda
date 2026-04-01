# Tracker: feat/continuous-movement

Trello #89 — Pivot away from tile-based movement

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy `.env` into the worktree

## Phase 2: Research
- [x] Read current monster movement code (behavior_engine.py, models.py WalkState)
- [x] Read sword hitbox code (commands.py sword_hitbox())
- [x] Read collision/contact damage code (combat.py)
- [x] Read client-side walk interpolation (client.html, renderer.js)
- [x] Read monster walk networking (net.py, net.js)
- [x] Trace how monster position is stored, updated, and broadcast
- [x] Trace how player position differs (continuous vs tile-based)
- [x] Identify all code that assumes 0.5-tile grid snapping
- [x] Identify blast radius: what breaks if monsters move fractionally
- [x] Summarize findings

## Phase 3: Design
- [x] Draft approach (plan doc)
- [x] Address netcode concern from Trello comment
- [x] Check for reusable patterns
- [x] Align with user

## Phase 4: Implement
- [x] Continuous monster movement with float-position collision detection
- [x] Revert half-tile monster steps back to full-tile steps (MOVE_STEP=1.0)
- [x] Client sends precise float positions every frame (throttled ~30fps)
- [x] Server accepts float positions (removed half-tile snap validation)
- [x] Fix stair re-trigger: spawn_stair guard on Avatar
- [x] Shrink player-vs-monster collision box by 40% (PLAYER_COLLISION_MARGIN=0.2)
- [x] Show collision box in /viewserver debug overlay
- [x] Remove collision grace period (smaller hitbox handles corner-scrape)
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
