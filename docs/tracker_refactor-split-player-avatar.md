# Tracker: refactor/split-player-avatar

## Phase 1: Pick Up the Card
- [x] Pull latest master
- [x] Read the card (description, comments, linked docs)
- [x] Move card to In Progress

## Phase 2: Research
- [x] Read the Player class in models.py
- [x] Trace all player.x/y/room/direction access sites
- [x] Identify blast radius (~200 refs across 11 files)
- [x] Understand room transition pop/try/finally pattern
- [x] Understand combat targeting via players_in_room()

## Phase 3: Design
- [x] Draft approach — Avatar class, player.room stays on Player
- [x] Plan attribute access strategies (pass avatar, local alias)
- [x] Align with user — approved

## Phase 4: Branch & Implement
- [ ] Create feature branch
- [ ] Add Avatar class, update Player in models.py
- [ ] Update net.py (players_in_room, broadcast_to_room, player_info)
- [ ] Update lifecycle.py (do_room_transition, send_room_enter)
- [ ] Update combat.py (_apply_damage, _respawn_player, collisions)
- [ ] Update commands.py (position_update, attack, face, chat)
- [ ] Update behavior_engine.py (_nearest_player, conditions)
- [ ] Update npc_chat.py (find_adjacent_npc, handle_npc_chat, gifts)
- [ ] Update quests.py (quest handlers)
- [ ] Update debug_monsters.py
- [ ] Update mud_server.py (login, disconnect)
- [ ] Update dungeons.py

## Phase 5: Verify
- [ ] Smoke test: `python -c "import mud_server"`
- [ ] Run `python tools/test_api_leak.py`
- [ ] Spot-check diff for logic errors
- [ ] Flag manual testing needs

## Phase 6: Review & Ship
- [ ] Update CLAUDE.md if needed
- [ ] Commit & push
- [ ] Peer review (fresh agent)
- [ ] Merge to master
- [ ] Move card to Done
- [ ] Comment on card
