# Tracker: feat/player-revival

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Copy .env into worktree

## Phase 2: Research
- [x] Read death/respawn system (combat.py, lifecycle.py, models.py)
- [x] Read client death flow (net.js, renderer.js, client.html)
- [x] Read dungeon/area player tracking (dungeons.py)
- [x] Trace room transition system
- [x] Identify blast radius

## Phase 3: Design
- [x] Draft approach (plan file)
- [x] User feedback: tombstone as separate game object
- [x] Revised plan approved

## Phase 4: Implement
- [x] Server constants (REVIVAL_DURATION, REVIVAL_PROXIMITY)
- [x] Server models (Tombstone class, Player fields)
- [x] Server state (tombstones dict)
- [x] Server combat (death flow, _tick_revivals, _revive_player, _has_potential_revivers)
- [x] Server lifecycle (tombstones in room_enter)
- [x] Server disconnect (tombstone cleanup in mud_server.py)
- [x] Client state (game_state.js new fields)
- [x] Client sprites (tombstone sprite + drawTombstone)
- [x] Client message handlers (net.js — 7 new handlers)
- [x] Client rendering (death screen, tombstones, revival progress, reviver glow)
- [x] Client input (respawn button click/touch)

## Phase 5: Verify
- [x] Smoke test: `python -c "import mud_server"` passes
- [x] API leak test: all 4 tests pass
- [ ] Peer review agent
- [ ] Manual testing notes for user

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md
- [ ] Commit & push
- [ ] Peer review fixes
- [ ] Pull master into branch
- [ ] Re-run smoke tests
- [ ] Merge to master
- [ ] Clean up worktree
- [ ] Move card to Done + add summary comment
- [ ] Create follow-up tickets
