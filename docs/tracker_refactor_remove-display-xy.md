# Tracker: refactor/remove-display-xy

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into worktree

## Phase 2: Research
- [ ] Read the referenced code (game_state.js, client.html, renderer.js, net.js)
- [ ] Trace how preciseX/Y and displayX/Y are used
- [ ] Identify all divergence points (knockback, attack, dying)
- [ ] Identify the blast radius (other files touching these fields)
- [ ] Summarize findings

## Phase 3: Design
- [ ] Draft the approach (single position + offset model)
- [ ] Check for reusable patterns
- [ ] Align with the user

## Phase 4: Implement
- [ ] Make the changes per approved plan
- [ ] Run safety checks if needed

## Phase 5: Verify
- [ ] Smoke test (python -c "import mud_server")
- [ ] Run existing tests
- [ ] Spot-check logic (review diff)
- [ ] Flag what needs manual testing

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md
- [ ] Commit & push
- [ ] Peer review (fresh agent)
- [ ] Pull master into branch
- [ ] Re-run smoke tests
- [ ] Merge to master & push
- [ ] Clean up worktree/branch
- [ ] Move card to Done + comment
- [ ] Create follow-up tickets if needed
