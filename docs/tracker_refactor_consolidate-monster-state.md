# Tracker: refactor/consolidate-monster-state

Trello #38 — Consolidate monster state machine

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into worktree
- [x] Push branch to origin

## Phase 2: Research
- [x] Read combat.py:784-852 (monster state machine code)
- [x] Read behavior_engine.py (full file, especially globals at lines 26-42)
- [x] Trace the call chain — how do both files interact?
- [x] Identify the blast radius — what imports/calls these?
- [x] Summarize findings

## Phase 3: Design
- [x] Draft the approach (file-by-file changes)
- [x] Check for reusable patterns
- [x] Align with the user

## Phase 4: Implement
- [x] Make the changes per approved plan
- [x] Run safety checks (test_api_leak.py — all 4 pass)

## Phase 5: Verify
- [x] Smoke test — python -c "import mud_server"
- [x] Run existing tests (test_api_leak.py — all 4 pass)
- [x] Spot-check logic (review diff)
- [ ] Flag what needs manual testing

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review (fresh agent on branch diff)
- [ ] Pull master into branch, resolve conflicts
- [ ] Re-run smoke tests
- [ ] Return to root checkout
- [ ] Merge to master & push
- [ ] Clean up worktree and branch
- [ ] Move card to Done
- [ ] Comment on card with summary
- [ ] Create follow-up tickets if needed
