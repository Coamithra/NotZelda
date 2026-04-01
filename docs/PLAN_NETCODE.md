# Plan: Netcode — Client Prediction, Interpolation, Lag Compensation

**Trello card:** #69cc6bd2 — Netcode: client prediction, interpolation, and lag compensation  
**Branch:** `feat/netcode`

---

## Context

With continuous float-based player positions, network latency artifacts are visible. Remote players snap to received positions (comment in `client.html:658`: "netcode card will add proper smoothing"). Local player already moves immediately (effective client-side prediction), but there's no reconciliation mechanism when the server corrects position. Combat uses client-supplied anchor positions (partial lag compensation) but remote players have no position history for rewinding.

### Current Data Flow
```
Local player:  playerTick() → myPlayer.x/y → syncPlayerState() @33ms → server
Server:        validate distance/walkable → update avatar.x/y → broadcast player_state_update
Remote player: receive player_state_update → snap op.x/y directly (no interpolation)
```

---

## Approach: Three Phases

The work is ordered by **impact vs. risk**. Each phase is independently shippable.

### Phase A: Entity Interpolation (Remote Players)

**The biggest visual win.** Currently remote players teleport between server snapshots. This adds smooth interpolation.

#### Client Changes (`client.html`, `game_state.js`)

1. **Snapshot buffer** on each `otherPlayers[name]`:
   ```js
   snapshots: []  // [{x, y, direction, timestamp}, ...] — ring buffer, max 5
   ```

2. **On `player_state_update`** (`net.js`): push snapshot instead of snapping:
   ```js
   op.snapshots.push({x: msg.x, y: msg.y, dir: msg.direction, t: performance.now()});
   // Keep last 5, discard oldest
   ```

3. **Interpolation in gameLoop** (`client.html`): each frame, for each remote player:
   - `renderTime = now - INTERP_DELAY` (2 ticks = ~66ms)
   - Find the two snapshots bracketing `renderTime`
   - Lerp between them: `displayX = s0.x + (s1.x - s0.x) * progress`
   - If only 1 snapshot available, snap (first frame after join)
   - If `renderTime` is past all snapshots (packet loss), extrapolate briefly then freeze

4. **Constants**:
   - `INTERP_DELAY = 66` ms (2 server ticks)
   - `INTERP_BUFFER_SIZE = 5` snapshots
   - `EXTRAP_MAX = 100` ms (max extrapolation before freezing)

#### What NOT to change
- Local player movement — untouched (Phase B)
- Server broadcast logic — identical `player_state_update` messages
- Monster interpolation — already works via `walkState`
- Knockback — already uses separate `knockbackSlide` system, stays as-is

#### Edge Cases
- **Room transition**: clear snapshot buffer on `room_enter`/`player_left`
- **Player joins mid-room**: first snapshot has no predecessor, snap directly
- **Direction changes**: direction updates instantly (no lerp on direction)
- **Dancing state**: no position interpolation during dance (snap to dance position)

---

### Phase B: Client-Side Prediction + Server Reconciliation

**Improves responsiveness for the local player.** Currently the client is already authoritative on movement (server validates and can reject), but there's no replay mechanism on correction.

#### Client Changes

1. **Sequence numbers**: add monotonically increasing `seq` to each `player_state` frame:
   ```js
   {type: "player_state", seq: 42, x, y, direction, dancing?, attacking?}
   ```

2. **Input buffer**: store recent inputs with their seq and resulting position:
   ```js
   G.player.inputBuffer = []; // [{seq, x, y, direction, dx, dy, dt}, ...]
   ```
   - Push each frame's input in `playerTick()`
   - Trim entries older than `lastAckedSeq`

3. **On `reconcile` message from server**: instead of hard-snapping:
   - Accept server position as ground truth
   - Discard all inputs up to and including `acked_seq`
   - Replay remaining inputs on top of server position
   - If the resulting position differs from current by more than a threshold (e.g. 0.1 tiles), apply a smooth correction over ~100ms instead of teleporting

#### Server Changes (`commands.py`)

1. **Echo `seq` back**: include the client's sequence number in the `reconcile` message and in a new `ack` field on `player_state_update` broadcasts (so the client knows which inputs the server has processed):
   ```python
   # In _process_player_state:
   avatar.last_acked_seq = msg.get("seq", 0)
   # In broadcast: include ack_seq for the originating player
   ```

2. **No other server changes needed** — validation logic stays the same.

#### Edge Cases
- **Knockback**: during knockback, client is not processing inputs — no replay needed. Clear input buffer on knockback.
- **Room transition**: clear input buffer on `room_enter`
- **Attack anchor**: attack still uses client-supplied x/y, unaffected

---

### Phase C: Lag Compensation (Combat)

**Fairness for multiplayer combat.** Currently attacks use client-supplied position (decent), but monster positions are server-side with no rewind. This matters when a player attacks a moving monster — at high ping, the monster has moved by the time the server processes the swing.

#### Server Changes (`commands.py`, `combat.py`)

1. **Position history buffer** on `Monster`:
   ```python
   position_history: deque  # [(timestamp, x, y), ...] — last 300ms
   ```
   - Updated every tick in `_tick_all_monsters()`
   - Trimmed to `LAG_COMP_WINDOW` (200ms)

2. **Rewind for sword_hit_scan**: when `_initiate_attack()` fires:
   - Estimate client's perceived time: `server_time - player_rtt / 2`
   - Find monster positions at that time in history
   - Run hitbox test against rewound positions
   - Apply damage at current position (no visual mismatch)

3. **RTT tracking**: server already has ping/pong — store `player.rtt` from pong response time.

#### What NOT to change
- Client-side hit feedback — unchanged (already uses client position)
- Monster AI — unchanged
- Contact collision — NOT rewound (only sword swings; contact is continuous)

#### Edge Cases
- **Cap rewind at 200ms** — high-ping players don't get unfair advantage
- **Dead monsters** — don't rewind dead monsters (check `alive` flag in history)
- **Boss rooms** — same logic, no special casing

---

## Bandwidth Considerations

Not a separate phase — minor optimizations folded into the above:
- **Already good**: room-based interest management (only replicate current room)
- **Low priority**: delta compression (positions are 2 floats, not much to delta at 30Hz)
- **Skip for now**: position quantization, input redundancy (TCP/WebSocket handles reliability)

---

## Files Modified

| File | Phase | Changes |
|------|-------|---------|
| `client/game_state.js` | A, B | Snapshot buffer on otherPlayers, input buffer, constants |
| `client/client.html` | A, B | Interpolation loop, prediction replay, smooth correction |
| `client/net.js` | A, B | Snapshot push on player_state_update, reconcile handler |
| `server/commands.py` | B, C | Seq echo, RTT tracking, position rewind for hit scan |
| `server/combat.py` | C | Position history buffer updates, rewind lookup |
| `server/models.py` | B, C | seq field on Avatar, position_history on Monster |
| `server/net.py` | B | ack_seq in player_state_update for originating player |

---

## Risk Assessment

- **Phase A (interpolation)** — Low risk. Only affects remote player rendering. No server changes. Easy to A/B test by toggling `INTERP_DELAY`.
- **Phase B (prediction/reconciliation)** — Medium risk. Touches input pipeline. Incorrect replay could cause jitter worse than current state. Mitigated by smooth correction fallback.
- **Phase C (lag compensation)** — Medium risk. Rewinding monster positions for hit detection. Incorrect rewind could cause phantom hits or misses. Mitigated by 200ms cap.

---

## Manual Testing Checklist

- [ ] Two players in same room — remote player moves smoothly (no snapping)
- [ ] Walk into a wall as remote player — observer sees smooth approach and stop
- [ ] Kill a monster with another player watching — hit connects visually for both
- [ ] Add artificial latency (Chrome DevTools > Network throttling) — local player stays responsive
- [ ] Room transition with another player — no ghost sprites, clean entry/exit
- [ ] Knockback on both local and remote player — animations still correct
- [ ] Dance emote visible to other player — no interpolation artifact
- [ ] `/viewserver` overlay — server-side positions still match expectations
