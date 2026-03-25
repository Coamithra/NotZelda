# Tracker: feat/compass-shows-players

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress
- [x] Create worktree and branch
- [x] Push branch to remote

## Phase 2: Research
- [ ] Read compass/minimap rendering code (renderer.js)
- [ ] Read how player positions are broadcast (server state)
- [ ] Understand dungeon instance player tracking
- [ ] Check how player shirt colors work

## Phase 3: Design
- [ ] Draft approach for server + client changes
- [ ] Align with user

## Phase 4: Implement
- [ ] Server: include other player positions in dungeon state
- [ ] Client: render colored blinking dots for other players on compass

## Phase 5: Verify
- [ ] Smoke test: python -c "import mud_server"
- [ ] Spot-check diff
- [ ] Flag manual testing needs

## Phase 6: Review & Ship
- [ ] Commit & push
- [ ] Peer review
- [ ] Merge to master
- [ ] Clean up worktree/branch
- [ ] Move card to Done
- [ ] Comment on card
