# Code Review

## Bugs & Problems

### Critical

1. **Room transition race condition** — `server/lifecycle.py:306-372`
   Player is removed from `game.players` during `do_room_transition()`, and if `entering_dungeon=False`, dungeon teardown can destroy rooms before `send_room_enter()` runs. Player gets stuck with no room data.

2. **Death respawn websocket reuse** — `server/combat.py:101-146`
   If a player disconnects and a new player connects on the same websocket, the old player's `_death_respawn` task can teleport the new player unexpectedly.

### High

3. **Orphaned async tasks on disconnect** — `mud_server.py:79-81`
   `asyncio.ensure_future(p.ws.send(msg))` creates tasks that accumulate when players disconnect, leaking memory.

4. **Silent exception swallowing in monster tick** — `server/combat.py:646-647`
   `except Exception: traceback.print_exc()` hides errors and leaves monsters in corrupted state.

5. **Walking through guards** — `server/combat.py:547-552`
   Guard collision only checked at walk midpoint. A guard moving into the target tile after walk starts allows 125ms of visual overlap.

6. **Missing room existence check in projectile tick** — `server/combat.py:683-685`
   `game.rooms[room_id]` accessed without checking the room still exists. Crashes if a room is destroyed mid-tick.

7. **Player state mutation during iteration** — `server/combat.py:525-576`
   `_flush_walk_messages()` is awaited between checking and modifying player state, allowing disconnects to invalidate references.

8. **Piercing projectiles double-hit multi-tile monsters** — `server/combat.py:692-706`
   No tracking of already-hit monsters means a piercing projectile can damage the same large monster twice.

### Medium

9. **Unbounded custom sprite/tile growth** — `server/state.py:26-28`
   Dictionaries grow without limit in long-running servers.

10. **Edge exit dead zones** — `mud_server.py:99-110`
    Hardcoded exit zones don't cover all intended tiles.

11. **Walk chaining unreliable with rapid tapping** — `client/client.html:480-482`
    `walkQueue` only set if direction differs from current.

12. **Monster walk message ordering** — `client/net.js:543-550`
    Stale `monster_walk_complete` after a charge can corrupt visual state.

13. **Boss distance BFS crash** — `server/dungeons.py:868-887`
    Malformed connections or null `boss_cell` can crash or silently return empty distances.

14. **Login name not character-validated** — `mud_server.py:372`
    Truncated to 20 chars but no special character filtering.

15. **Custom tile/sprite registration silently overwrites** — `server/validation.py:269-320`
    Name collisions during AI generation lose content.

16. **Patrol routes not path-validated** — `server/validation.py:164-170`
    Only character set checked, not whether tiles are walkable.

17. **Dungeon room resolution assumes valid state** — `server/dungeons.py:335-374`
    Returns `True` for already-resolved rooms without validating data integrity.

18. **Monster `_nearest_player` missing attribute guards** — `server/behavior_engine.py:52-73`
    Uses `monster.x`/`monster.y` without null checks.

19. **Client-server desync on rapid monster state changes** — `client/net.js`
    Walk/charge handlers don't sequence-check messages.

---

## Clean Code & Refactoring

### Top 5 High-Impact Refactors

1. **G namespace is a 124-property god object** — `client/game_state.js:17-124`
   Connection state, room data, UI state, rendering, and debug all in one object. Split into `connection`, `player`, `room`, `ui`, `rendering`, `debug` sub-objects.

2. **Monolithic chat handler: 17 elif branches** — `mud_server.py:262-339`
   Extract to a command registry pattern with `CHAT_COMMANDS = {"who": handle_cmd_who, ...}`.

3. **`DEBUG_MODE` string check repeated 7 times** — `mud_server.py` throughout
   Extract to a constant in `server/constants.py`.

4. **Walk state is a raw dict with 7 keys** — `server/models.py:23`, `server/combat.py:210-216`
   Replace with a `@dataclass Walk(from_x, from_y, to_x, to_y, direction, start_time, committed)`.

5. **Two near-identical message flush functions** — `server/combat.py:85-98` and `578-595`
   Differ only in `guard_chat` handling. Merge into one.

### Duplication

6. **Client walk state setup duplicated 3x** — `client/net.js` in `room_enter`, `walk_started`, and `player_entered` handlers. Extract `initializeWalkState()`.

7. **Guard despawn has 3 identical loops** — `server/combat.py:731-782`
   Extract `_despawn_guards()`.

8. **Custom sprite/tile registration duplicated** — `client/net.js:199-223` and `578-590`
   Extract `registerCustomContent()`.

9. **14+ inline message dict constructions** in `server/combat.py`
   Create message factory functions.

10. **Coordinate conversion `x * TS + TS/2` scattered** — `client/renderer.js` throughout
    Extract `screenCoordsCenter()`.

11. **Animation `.nextTime` pattern repeated** for dances, deaths, sword pickups, attacks.
    Create an `Animation` class.

### Structural Issues

12. **Behavior engine uses module-level globals** — `server/behavior_engine.py:26-42`
    Six globals injected via `init()`. Refactor to a class with constructor injection.

13. **Monster state machine split across two files** — `server/combat.py:784-852` + `server/behavior_engine.py`
    Adding an action type requires changes in both.

14. **Constants scattered across 3+ files** — `WALK_TIME` in `server/constants.py`, `WALK_TIME_MS` in `client/game_state.js`, animation durations in `client/renderer.js`. No single source of truth.

15. **Dead code: legacy `monster_tick()`** — `server/combat.py:854-860`
    Sleeps forever "so mud_server.py doesn't need changes." Remove it and update the caller.

16. **Magic number `0.033`** — `server/combat.py:653`
    Should be `TICK_INTERVAL = 1.0 / 30`.

17. **Guard despawn constants not in constants.py** — `server/combat.py:726-728`
    Move to centralized config.

18. **Client canvas context swap is fragile** — `client/net.js:111-116`
    Swapping `G.ctx` without try-finally means errors leave it corrupted.

19. **Validation rules mixed with registration** — `server/validation.py`
    320 lines of deeply nested validation. Extract to a schema/rule-table approach.

20. **Player model properties undocumented** — `server/models.py:25-28`
    `guard_cooldowns`, `quests`, `flags` have no type hints or valid-value documentation.
