# Tracker: refactor/client-dedup

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into the worktree

## Phase 2: Research
- [x] Read all duplicated patterns in net.js, renderer.js, fx.js, sprites.js
- [x] Identify walk state init (5 occurrences — 2 identical player inits, 3 varied walk states)
- [x] Identify custom content registration (2 occurrences — room_enter full, monster_spawned partial)
- [x] Identify coordinate conversion (13 center-of-tile, 31+ top-left)
- [x] Identify animation .nextTime pattern (5 occurrences, 1 dead)
- [x] Discover dead swordPickups code (never populated)

## Phase 3: Design
- [x] Draft approach and get user approval

## Phase 4: Implement
- [x] Extract createOtherPlayer() — dedups player object init in room_enter + player_entered
- [x] Extract registerCustomContent() — dedups sprite/tile registration in room_enter + monster_spawned
- [x] Extract tileCenterX/Y — dedups x*TS+TS/2 in renderer.js, fx.js, net.js
- [x] Extract advanceFrame() — dedups animation frame advancement in 4 update functions
- [x] Remove dead swordPickups code — constants, update/render functions, game_state, game loop calls, drawSwordPickup sprite

## Phase 5: Verify
- [x] Smoke test: python -c "import mud_server"
- [ ] Peer review
- [ ] Manual browser testing (user)

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review agent
- [ ] Pull master, re-smoke
- [ ] Merge to master
- [ ] Clean up worktree
- [ ] Move card to Done + comment
