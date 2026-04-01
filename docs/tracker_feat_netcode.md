# Tracker: feat/netcode

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into worktree

## Phase 2: Research
- [x] Read current player sync code (client: net.js, input.js, game_state.js)
- [x] Read current player sync code (server: commands.py, net.py, combat.py)
- [x] Trace the player_state send/receive path end-to-end
- [x] Read remote player rendering (renderer.js — how other players are drawn)
- [x] Read monster interpolation code (client-side) for comparison
- [x] Read sword hitbox / attack code (commands.py, combat.py)
- [x] Read external netcode research docs (C:\Programming\doom\research\)
- [x] Identify blast radius — what systems touch position data
- [x] Summarize findings

## Phase 3: Design
- [x] Draft approach: entity interpolation for remote players
- [x] Draft approach: client-side prediction + server reconciliation
- [x] Draft approach: lag compensation for combat
- [x] Write plan doc (docs/PLAN_NETCODE.md)
- [x] Align with user on plan

## Phase 4: Implement
- [x] Phase A: Entity interpolation (snapshot buffer, lerp between server snapshots)
- [x] Phase B: Server-authoritative movement (input-based, simulateMove, reconciliation)
- [x] Phase C: Lag compensation (RTT measurement, position history, hit rewind)
- [x] Phase D deferred to follow-up card (client-side monster prediction)

## Phase 5: Verify
- [x] Smoke test: python -c "import mud_server"
- [x] Manual testing (movement, attacks, room transitions, multiplayer)
- [ ] Spot-check diff for logic issues
- [ ] Flag what needs manual testing

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md
- [ ] Commit & push
- [ ] Peer review (spawn fresh agent)
- [ ] Pull master, resolve conflicts
- [ ] Re-run smoke tests
- [ ] Merge to master
- [ ] Clean up worktree
- [ ] Move card to Done + comment
- [x] Create follow-up ticket (Phase D — client-side monster prediction, #69cda4c4)
