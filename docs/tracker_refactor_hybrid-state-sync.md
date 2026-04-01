# Tracker: refactor/hybrid-state-sync

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [ ] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into worktree

## Phase 2: Research
- [x] Read syncPosition in client.html
- [x] Read net.js state frame handling
- [x] Read server/commands.py (position_update, attack, dance handling)
- [x] Read server/net.py (player_info, broadcast patterns)
- [x] /research: validate hybrid state sync architecture for multiplayer games → VALIDATED
- [x] Summarize findings → report at docs/RESEARCH_HYBRID_STATE_SYNC.md

## Phase 3: Design
- [ ] Draft approach (context, file-by-file changes, edge cases)
- [ ] Check for reusable patterns
- [ ] Align with user

## Phase 4: Implement
- [ ] Make changes per approved plan
- [ ] Run safety checks if needed

## Phase 5: Verify
- [ ] Smoke test (python -c "import mud_server")
- [ ] Run tests
- [ ] Spot-check diff
- [ ] Flag manual testing needs

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review
- [ ] Pull master, re-test
- [ ] Merge to master
- [ ] Clean up worktree/branch
- [ ] Move card to Done + comment
- [ ] Create follow-up tickets if needed
