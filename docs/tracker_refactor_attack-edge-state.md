# Tracker: refactor/attack-edge-state

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into worktree
- [x] Push branch to remote

## Phase 2: Research
- [ ] Read client/client.html — current attack sending in player_state
- [ ] Read client/input.js — current attack input handling
- [ ] Read client/net.js — current attack message handling + player_state_update
- [ ] Read server/commands.py — _process_attack, sword_hit_scan, active_attack
- [ ] Read server/models.py — Player/Avatar fields
- [ ] Read server/net.py — player_info for room_enter
- [ ] Trace the full attack call chain (client input → server processing → broadcast)
- [ ] Identify blast radius

## Phase 3: Design
- [ ] Draft approach (file-by-file changes)
- [ ] Identify edge cases
- [ ] Align with user

## Phase 4: Implement
- [ ] Add attacking to player_state frame (client.html)
- [ ] Remove discrete attack message, add forced sync (input.js)
- [ ] Handle attacking in player_state_update + room_enter (net.js)
- [ ] Edge-triggered attack detection in commands.py
- [ ] Add _prev_attacking tracking to models.py
- [ ] Add attacking to player_info in net.py
- [ ] Run safety checks if needed

## Phase 5: Verify
- [ ] python -c "import mud_server" smoke test
- [ ] python tools/test_api_leak.py
- [ ] Spot-check diff for issues
- [ ] Flag manual testing items

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review (spawn fresh agent)
- [ ] Fix peer review findings
- [ ] Pull master into branch
- [ ] Re-run smoke tests
- [ ] Merge to master
- [ ] Clean up worktree + branch
- [ ] Move card to Done
- [ ] Comment on card
- [ ] Create follow-up tickets if any
