# Tracker: refactor/split-log-locations

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [ ] Copy .env into worktree (user must do manually)

## Phase 2: Research
- [ ] Find all server-side print() / logging calls
- [ ] Find all client-side debug log / chat window patterns
- [ ] Find existing server log file writes
- [ ] Identify stdout usage patterns
- [ ] Summarize findings

## Phase 3: Design
- [ ] Draft approach for 3-destination logging
- [ ] Align with user

## Phase 4: Implement
- [ ] Make changes per approved plan

## Phase 5: Verify
- [ ] Smoke test: python -c "import mud_server"
- [ ] Run tests: python tools/test_api_leak.py
- [ ] Spot-check logic
- [ ] Flag what needs manual testing

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review
- [ ] Pull master, re-test
- [ ] Merge to master
- [ ] Clean up worktree/branch
- [ ] Move card to Done + comment
- [ ] Create follow-up tickets if needed
