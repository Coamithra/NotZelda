# Walk System Rewrite Plan

Replaces instant server-side position updates with continuous walk state, cancel windows, midway commits, dead reckoning, and full-state reconciliation.

## Constants

```
WALK_TIME     = 0.250s   # full tile-to-tile walk duration
CANCEL_TIME   = 0.150s   # window to cancel a walk
LATENCY_COMP  = 0.066s   # dead reckoning offset; also the leeway for all timing checks
```

## Wire Protocol

**Client → Server:**
- `{type: "walk", direction, origin: {x, y}}` — request to walk from origin in direction
- `{type: "cancel_walk"}` — cancel current walk (no payload needed)
- `{type: "face", direction}` — turn without walking (blocked tile, etc.)

**Server → Client (to self):**
- `reconcile {x, y, direction, walking, walk_from?, walk_to?, walk_progress?}` — full state snapshot, used for any correction
- `player_moved {name, x, y, direction}` — still broadcast at midway commit (other players see this too)

**Server → Client (to others in room):**
- `walk_started {name, from_x, from_y, to_x, to_y, dir, progress}` — begin walk animation with head start
- `walk_cancelled {name, x, y}` — snap player back to origin
- `walk_complete {name}` — walk finished (clear walk interpolation)
- `player_faced {name, direction}` — turn only (unchanged)

## Steps

### Step 1: Constants + Player Model

**Files:** `server/constants.py`, `server/models.py`

- Add `WALK_TIME`, `CANCEL_TIME`, `LATENCY_COMP` constants
- Add `Player.walk` field: `None` or `{"from_x", "from_y", "to_x", "to_y", "dir", "start_time", "committed"}`
- Keep `MOVE_COOLDOWN` and `last_move_time` alive until Step 3 replaces them

**Behavior change:** None. New fields unused.

### Step 2: Server Walk Tick Loop

**Files:** `server/combat.py`, `mud_server.py`

- New `player_walk_tick_loop()` — async loop at **50ms** intervals (not 250ms monster tick; a 250ms walk needs multiple ticks to catch midway)
- Inner `_tick_player_walks(now, msgs)`:
  - For each player with `player.walk`:
    - Compute `progress = elapsed / WALK_TIME`
    - **Midway commit** (progress >= 0.5, not yet committed): set `player.x/y = target`, `committed = True`, broadcast `player_moved`, check monster collision, heart pickup, guard proximity
    - **Walk complete** (progress >= 1.0): `player.walk = None`, broadcast `walk_complete`
- Start alongside `monster_tick()` in `main()`

**Behavior change:** None. No player has walk state yet.

### Steps 3–6: Server Handler + Client Rewrite (atomic)

These must ship together — the wire protocol changes.

#### Step 3: Server `handle_walk_request` (replaces `handle_move`)

**Files:** `mud_server.py`

`handle_walk_request(player, direction, origin_x, origin_y)`:
1. **Origin validation** — if origin doesn't match `player.x/y`, send `reconcile`
2. **Chain acceptance** — if player is walking and near completion (progress >= `1.0 - LATENCY_COMP/WALK_TIME`), accept as chain; complete current walk immediately
3. Validate direction, set `player.direction`, clear dancing
4. Compute target tile
5. Room exit / stairs → `do_room_transition()` (set `player.walk = None` first)
6. Not walkable / guard → send `reconcile` (stationary at origin)
7. **Start walk**: set `player.walk = {..., start_time: now - LATENCY_COMP}` (dead reckoning via backdated start)
8. Broadcast `walk_started` to others with initial progress

`handle_cancel_walk(player)`:
1. If not walking → ignore
2. If `elapsed <= CANCEL_TIME + LATENCY_COMP` and not committed → cancel, stay at origin, broadcast `walk_cancelled`
3. Otherwise → send `reconcile` with walk state (too late to cancel)

`send_reconcile(player)`:
- Builds full state snapshot: `{x, y, direction, walking, walk_from?, walk_to?, walk_progress?}`

Update message dispatch: `"walk"` → `handle_walk_request`, `"cancel_walk"` → `handle_cancel_walk`

#### Step 4: Client Rewrite

**Files:** `client/game_state.js`, `client/client.html`, `client/net.js`

**game_state.js:**
- Add `WALK_TIME_MS = 250`, `CANCEL_TIME_MS = 150`
- Replace `moveState` with `walkState: null` — `{fromX, fromY, toX, toY, dir, startTime, cancelSent}`
- Replace `inputBuffer` with `walkQueue: null`
- Remove `pendingMoves`, `lastServerMoveTime`, `MOVE_SPEED`, `COMMIT_THRESHOLD`

**client.html — `processWalk()`** (replaces `processMovement`):
- If `walkState` exists:
  - Compute progress from `performance.now()`
  - If pre-cancel and key released/changed: send `cancel_walk`, snap back, optionally start new walk
  - If post-cancel: buffer different direction in `walkQueue`
  - If complete: snap to target, update `myPlayer.x/y`, chain from `walkQueue` or held key
- If no walkState and key held: call `tryStartWalk(dir)`

**client.html — `tryStartWalk(dir)`** (replaces `tryStartMove`):
- If walkable: set `walkState`, send `{type: "walk", direction, origin}`, optimistically set `myPlayer.x/y = target`
- If off-grid/stairs: send walk, let server handle transition
- If blocked: send `{type: "face", direction}`

**net.js — new handlers:**
- `reconcile`: snap `myPlayer`, `displayX/Y`, clear `walkState`/`walkQueue` (or sync to server's walk state)
- `walk_started`: create `walkState` on other player with time-offset interpolation
- `walk_cancelled`: snap other player back
- `walk_complete`: clear other player's walk state

**net.js — other-player interpolation:**
- If player has `walkState`: time-based linear interpolation (constant speed)
- Else: lerp fallback for snaps

#### Step 5: Combat Integration

**Files:** `server/combat.py`, `client/net.js`

- `_apply_damage`: cancel walk (`player.walk = None`) before knockback
- `_death_respawn`: cancel walk on death
- Client `player_hurt` / `you_died`: clear `walkState` + `walkQueue`
- Walk tick midway commit: check monster collision at target tile (replaces the old instant check in `handle_move`)

#### Step 6: Room Transition Integration

**Files:** `mud_server.py`, `server/lifecycle.py`

- `handle_walk_request`: set `player.walk = None` before `do_room_transition`
- `do_room_transition`: set `player.walk = None` at top as safety
- Client `room_enter` already resets all movement state

### Step 7: Walk State in Player Info

**Files:** `server/net.py`, `client/net.js`

- `player_info()`: include walk state (from/to/progress) if player is mid-walk
- Client `room_enter` and `player_entered`: initialize `walkState` on other players if `walking: true`
- Ensures players entering a room see others mid-walk correctly

### Step 8: Attack Interaction + Cleanup

**Files:** `client/input.js`, `mud_server.py`, all files (dead code removal)

- Space/attack: cancel walk before attacking (send `cancel_walk`, clear `walkState`)
- Server attack handler: cancel walk, send `reconcile`
- Remove: `MOVE_COOLDOWN`, `last_move_time`, `MOVE_SPEED`, `COMMIT_THRESHOLD`, old `handle_move`, `pendingMoves`, `inputBuffer`, `lastServerMoveTime`

## Dependency Graph

```
Step 1 (safe to land alone)
  ↓
Step 2 (safe to land alone)
  ↓
Steps 3-6 (ATOMIC — wire protocol changes)
  ↓
Step 7 (safe to land alone)
  ↓
Step 8 (safe to land alone)
```

In practice, ship Steps 1–6 as one commit since they're tightly coupled.

## Key Design Decisions

1. **`player.x/y` = committed tile position.** Before midway: origin. After midway: target. All systems reading position get a valid tile, never fractional.

2. **Dead reckoning via backdated `start_time`** — `start_time = now - LATENCY_COMP`. The tick loop naturally computes correct progress. No separate progress tracking needed.

3. **50ms walk tick** — the 250ms monster tick can't catch midway on a 250ms walk. Separate 50ms loop gives ~5 ticks per walk.

4. **Reconcile = full snapshot** — one message type handles any correction (walls, knockback, lag, desynced state).

5. **Origin in walk request** — lets server detect desync without state rewinding.

6. **No walk queue on server** — only one active walk per player. Chaining is handled by near-completion acceptance.

## Deferred

Moved to Trello: https://trello.com/b/FEqdR6QL/legends-of-amara
