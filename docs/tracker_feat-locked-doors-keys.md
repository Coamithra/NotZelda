# Tracker: feat/locked-doors-keys

Trello card #52 — Locked doors and keys

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [ ] Move card to In Progress
- [x] Create tracker doc

## Phase 2: Research
- [ ] Read dungeon system code (dungeons.py, dungeon_types.py)
- [ ] Read item/pickup system (how map/compass spawn and get collected)
- [ ] Read trap room logic (locked rooms, item reveal after monsters slain)
- [ ] Read tile system (tiles.json, constants.py) for door tile patterns
- [ ] Read client item pickup flow (sprites.js, net.js, renderer.js)
- [ ] Trace the call chain for dungeon creation → room resolution → item placement
- [ ] Identify blast radius (what other systems this touches)
- [ ] Summarize findings

## Phase 3: Design
- [ ] Draft approach: key item data model (Player field, tiles.json entry, sprite)
- [ ] Draft approach: locked door tiles (LD, KD tile definitions)
- [ ] Draft approach: dungeon generation — lock placement algorithm
- [ ] Draft approach: key placement algorithm (floodfill reachability guarantee)
- [ ] Draft approach: server-side unlock logic (walk into locked door with key)
- [ ] Draft approach: client-side rendering (locked door tiles, key item pickup)
- [ ] Draft approach: edge cases (multiplayer key hoarding, persistence across exits)
- [ ] Align with user

## Phase 4: Branch & Implement
- [ ] Create feature branch
- [ ] Implement tile definitions (LD, KD in tiles.json)
- [ ] Implement key item on Player model
- [ ] Implement lock/key placement in dungeon generation
- [ ] Implement server-side unlock logic
- [ ] Implement client-side locked door rendering
- [ ] Implement key pickup animation (reuse item_obtained flow)
- [ ] Implement key count in HUD

## Phase 5: Verify
- [ ] Smoke test — `python -c "import mud_server"`
- [ ] Run `python tools/test_api_leak.py`
- [ ] Spot-check diff
- [ ] Flag manual testing needs

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review (fresh agent)
- [ ] Pull master, re-test
- [ ] Merge to master
- [ ] Move card to Done
- [ ] Comment on card
