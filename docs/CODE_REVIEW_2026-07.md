# Code Review — July 2026

Full-codebase review for correctness and code quality, covering `mud_server.py`, all of
`server/`, all of `client/`, and `worldgen.py`. Findings are grouped by severity; every
item was verified against the source at the cited line before inclusion. Line numbers
refer to the tree at the time of review (branch `claude/game-code-review-bcvja0`).

Areas explicitly checked and found **clean** are listed at the end — they're as much a
review result as the bugs.

---

## High

### H1. One bad payload in `flush_messages` kills the game loop permanently
`server/combat.py:968` (with `mud_server.py:699`)

`game_tick()` runs as an unsupervised `asyncio.create_task` in a `while True` loop. The
tick body is wrapped in `try/except`, but `await flush_messages(msgs)` and
`_send_debug_state_snapshots()` sit **outside** it:

```python
        except Exception:
            traceback.print_exc()
        await flush_messages(msgs)
```

`send_to` only catches `ConnectionClosed`, so any other exception during flush — e.g. a
`TypeError` from `json.dumps` on a single non-serializable value in a batched message —
escapes the loop and silently kills the task. The server process stays up, sockets stay
open, but the game stops ticking for everyone until restart.

**Fix:** move the flush inside the guarded region (or wrap it in its own
`try/except`), and consider `add_done_callback` on the task to log/restart if it ever
exits.

### H2. Reconnect race: orphaned WebSocket causes duplicate login and a "name taken" loop
`client/net.js:35` with `client/input.js:175`

`connect()` never closes or detaches the previous socket before overwriting `G.conn.ws`,
and the visibilitychange handler reconnects whenever `readyState !== OPEN` — which
includes `CONNECTING`:

```js
G.conn.ws = new WebSocket(`${proto}//${wsHost}/ws`);      // old ws never closed
// input.js:
if (!G.conn.ws || G.conn.ws.readyState !== WebSocket.OPEN) { ... connect(...) }
```

On a slow network, a tab resume while socket A is still CONNECTING creates socket B.
A then opens, sends its own `login`, and claims the name server-side; B's login is
rejected ("name is already taken"), B closes, `onclose` schedules another reconnect —
an endless loop, while the orphaned socket A keeps feeding `handleMessage` but
`sendToServer` (bound to `G.conn.ws` = B) drops all input. Each stray `onopen` also
overwrites `G.conn.pingInterval` without clearing the previous one, leaking a 15s ping
interval per orphan.

**Fix:** in `connect()`, close and null out the handlers of any existing socket first;
treat `CONNECTING` as alive in the resume check.

---

## Medium — server: cheating / input validation

### M1. Movement rate limits are per-message, so N messages per tick = N× the budget
`server/commands.py:133-134`, `:330-334` (queue: `server/models.py:64`)

`process_player_commands` drains the **unbounded** `player.command_queue` every tick.
`MAX_INPUTS_PER_TICK` caps inputs *within one* `player_input` message, and
`MAX_MOVE_PER_UPDATE` caps *one* `player_state` frame — but nothing caps messages per
tick. A modified client sending 50 `player_state` frames per tick moves 50×
`MAX_MOVE_PER_UPDATE` through walkable tiles per tick, passing every anti-cheat check
(full speed hack / near-teleport).

**Fix:** cap messages drained per player per tick, or make the distance budget
per-tick rather than per-frame.

### M2. Sword attack anchor is client-supplied with no distance check
`server/commands.py:989-996`

```python
anchor_x = attack_data.get("x")
...
anchor_x = float(anchor_x)
```

The attack hitbox origin comes straight from the client (`attacking.x/y`) with no
sanity check against the avatar's position, so a cheating client can hit any monster
(bosses included) from anywhere in the room. Additionally, `float()` on a non-numeric
value raises into the tick's catch-all, and in `_process_player_state` a truthy
non-dict `attacking` (e.g. `true`) raises `AttributeError` on `.get`.

**Fix:** clamp the anchor to within ~`MAX_MOVE_PER_UPDATE` of the server-side avatar
position; validate types before use.

### M3. Chat text has no length cap
`server/commands.py:1020`

Login name is capped `[:20]` and description `[:80]`, but chat is not:

```python
text = data.get("text", "").strip()
```

A logged-in client can send a ~1 MB chat frame (websockets' default `max_size`) that is
broadcast verbatim to every player in the room, appended to `event_log.txt`, and fed
into the NPC LLM conversation history (ending up in the `claude -p` argv / prompt) —
bandwidth, disk, and LLM cost/latency amplification from a single client.

**Fix:** cap like the other fields (e.g. `[:300]`) and ignore non-string payloads.

---

## Medium — server: gameplay logic

### M4. Item-pickup freeze *resets* revival progress instead of pausing it
`server/combat.py:597-599`

```python
if ts.reviver and ts.revival_start_time > 0:
    # Shift revival start forward so freeze doesn't count as channel time
    ts.revival_start_time = now
```

Setting `revival_start_time = now` on every frozen tick discards all channel time
accumulated *before* the freeze (the comment claims the opposite). A reviver 5s into
the 6.5s channel loses everything when someone picks up an item, while the client's
progress bar (driven by the original `revival_started` duration) shows near-complete.

**Fix:** shift the start by the freeze duration at thaw (or `+= tick_dt` while
frozen) so pre-freeze progress is preserved.

### M5. `_has_los` vacuously returns True off-axis → projectiles through walls
`server/behavior_engine.py:145-157`

```python
if x1 == x2: ...
elif y1 == y2: ...
return True
```

When the rounded points share neither a row nor a column, both branches are skipped
and the function returns `True`. Its only caller passes independently rounded floats
after a `< 0.75` alignment check — e.g. monster x=2.0, player x=2.6 passes alignment
but `round(2.6)=3 ≠ 2`, so the wall check is bypassed entirely. Monsters with
`"los": true` fire projectiles/charges through walls whenever positions round
off-axis.

**Fix:** run the LOS scan along the aligned axis using the rounded shared coordinate
(or fall back to `False`/a supercover raycast when the points don't align).

### M6. Aquatic behavior actions (swim/whirlpool/submerge) are half-implemented dead code
`server/behavior_engine.py:~507-804`, `server/validation.py:15-17`,
`server/models.py:151-153`, `server/combat.py:681`, `server/lifecycle.py:24`

- `VALID_BEHAVIOR_ACTIONS` is `{"move", "hold", "projectile", "charge", "teleport",
  "area"}`, so no registered monster (built-in or AI-generated) can ever use the three
  aquatic actions — ~250 lines of unreachable code duplicating `resolve_move` /
  `_resolve_teleport`.
- The promised submerge invulnerability is dead: `monster._submerged` is written and
  never read; `Monster.intangible` only covers `"teleporting"`. A submerging monster
  is fully hittable and deals contact damage, contradicting the docstring.
- The freeze-thaw timer shift (`combat.py:681`) and `_on_state_exited`
  (`lifecycle.py:24`) omit `"whirlpooling"`/`"submerging"`, and the client has **no
  handler** for `submerge_start`/`submerge_end` — enabling these actions as-is would
  fire instantly after freezes and desync every client.

**Fix:** either finish the feature (validation whitelist + `intangible` + freeze/exit
bookkeeping + client handlers) or delete the three actions.

### M7. Gauntlet permanently clobbers HP and spirit jars
`server/gauntlet.py:230` (also `:284`, `:342`, `:464`)

```python
player.hp = min(GAUNTLET_STARTING_HP, player.max_hp)
player.spirit_jar_count = GAUNTLET_SPIRIT_JARS
```

Entry overwrites the player's real inventory, and no exit path (`on_gauntlet_exit`,
`/gauntlet stop`, the lifecycle exit hook) saves/restores it. A player holding 3
spirit jars runs `/gauntlet` then `/gauntlet stop` and ends up with 1 permanently (or
gains a free jar from 0); HP is likewise left at gauntlet values.

**Fix:** snapshot hp/jars on the session at entry and restore on every exit path.

### M8. `/gauntlet stop` can KeyError and strand the player in a deleted room
`server/gauntlet.py:633`

```python
on_gauntlet_exit(player.name)
player.room = return_room
spawn = game.rooms[return_room]["spawn_points"]["default"]
```

`cmd_gauntlet` calls `on_player_leave_room`, which destroys a dungeon when its last
player leaves — popping every dungeon room, including `session.return_room`, from
`game.rooms`. A solo player who starts `/gauntlet` from inside a dungeon and then
stops gets a KeyError; since the gauntlet rooms and session are already deleted, they
are stranded in a nonexistent room.

**Fix:** validate `return_room` still exists and fall back to the overworld spawn.

### M9. `create_variant` silently drops boss/size/pack stats
`server/variants.py:130-135`

The rebuilt stats dict copies only `hp`, `damage`, `walk_time`, `decision_time` —
dropping `boss`, `width`, `height`, `pack_min`, `pack_max`, all supported by
`register_monster_type`. Both bosses in `data/monsters.json` carry `boss/width/height`,
so a variant of a boss registers as a non-boss with a 1×1 hitbox under a multi-tile
sprite — `monster.is_boss` logic and collision are both wrong.

**Fix:** copy the base stats dict and override only the scaled keys.

---

## Medium — server: infrastructure / AI pipeline

### M10. AI prompt/response dumps are unconditional and unbounded
`server/ai_generator.py:985`, `:1016`

Every AI call writes the full prompt to `tmp_prompts/` (once per attempt) and the raw
response again on success — not gated on any debug flag, never cleaned up. On the
production VPS, background regen writes multi-KB files per call, growing without bound
until disk fills.

**Fix:** gate on `DEBUG_MODE` (dump failures only in prod), and/or prune the directory
on startup.

### M11. Missing `kind` passes validation, then crashes assembly — wasting the whole room
`server/ai_generator.py:1582-1584` vs `:467-469`

`validate_layout` accepts monster groups *missing* `kind` (`k = g.get("kind"); if k and
...`), but assembly does `g["kind"]`:

```python
{"kind": g["kind"], "count": g["fraction"]}
```

A model response containing `{"fraction": 1.0}` validates, then raises `KeyError:
'kind'`; the caller's catch-all discards the room, wasting all the paid
monster/sprite/tile/layout calls that produced it.

**Fix:** either reject kind-less groups in validation or skip them at assembly.

### M12. Tweak console silently ineffective for NPC/guard/gauntlet constants
`server/commands.py:1203-1207`

`_CONSTANTS_CONSUMERS` (the modules whose from-imported bindings get patched on tweak)
omits `server.npc_chat` and `server.gauntlet`, yet `TWEAKABLE_SERVER_CONSTANTS`
exposes `NPC_RESPONSE_DELAY`, `NPC_MAX_RESPONSE_LENGTH`, `NPC_DETECTION_DISTANCE`,
`GUARD_SPAWN_COUNT_MIN/MAX`, and all five `GAUNTLET_*` constants — all from-imported
by those two modules. The console reports the new value; the game keeps using the old
one.

**Fix:** add the two modules to the consumers list (and consider a test that
cross-checks every tweakable constant against its importers).

### M13. `/debug_spawn` silently broken by float tilemap indices
`server/debug_monsters.py:564-566`

```python
nx, ny = player.avatar.x + dx, player.avatar.y + dy
...
if game.is_walkable_tile(tilemap[ny][nx]):
```

`avatar.x/y` are always floats, so `tilemap[ny][nx]` raises `TypeError: list indices
must be integers`. Because the handler runs via `asyncio.ensure_future`, the exception
is swallowed as an unretrieved task exception — the command just silently does
nothing.

**Fix:** `int(round(...))` the coordinates; add a done-callback that logs exceptions
from these fire-and-forget tasks.

---

## Medium — client

### M14. Monster walk-start renders a backward jerk; clamp defeats dead reckoning
`client/net.js:743-746` with `client/client.html:1100`

On `monster_walk_started` the correction offset is computed against an
RTT-fast-forwarded position (`newDX`), but the walk interpolator never starts there:
`clampedProgress = Math.min(progress, trueProgress)` always equals `trueProgress`
(since `effectiveDuration <= duration`), so rendering starts at `from_x`. The monster
therefore jerks *backward* by `(rtt/2)/walk_time` tiles on every step (100ms RTT,
250ms step → 20% of a tile) before the correction decays. The clamp also silently
neutralizes `computeEffectiveDuration()` dead reckoning for all walk/knockback
actions.

**Fix:** either drop the RTT fast-forward from the correction, or let the
interpolator actually start at the fast-forwarded progress.

### M15. Tide Medallion ripples never render for other players
`client/renderer.js:165` with `client/net.js:83-91`

```js
for (const op of Object.values(G.room.otherPlayers)) {
  if (G.room.medallionHolders.has(op.name)) {   // op.name is always undefined
```

Objects built by `createOtherPlayer()` have no `name` property (names are the dict
*keys*), so `has(undefined)` is always false and the multiplayer half of the
water-walk effect is dead. Compare `renderRevealedTiles` (renderer.js:53-56), which
correctly iterates holder names and looks up `otherPlayers[name]`.

**Fix:** iterate `Object.entries` and check the key, as `renderRevealedTiles` does.

### M16. Boss choir never resumes when music is toggled back on
`client/music.js:258` with `:336`

`startChoir()` bails with `if (!playing) return;` *before* creating `choirAudio`, but
`start()` only resumes the choir when the element already exists (`if (choirActive &&
choirAudio)`). A player with music off who walks near a boss and then presses M gets
the base track but no choir until the server happens to resend a choir message.

**Fix:** have `start()` create the choir element when `choirActive && !choirAudio`
(or let `startChoir` create it paused).

### M17. Tweak panel type inference breaks float params with integral defaults
`client/tweak.js:28` (applied at `:437-441`)

```js
type: opts.type || (Number.isInteger(def) && typeof def === "number" ? "int" : "float"),
```

`Number.isInteger(4.0)` is true, so a float tweak like `MOVE_SPEED = 4.0` (step 0.5)
registers as `"int"` and `applyTweakValue` rounds every value: "−" computes 3.5 →
rounds back to 4 (no-op), "+" jumps to 5, and 4.5 can never be entered. Same latent
trap for any monster rule param whose default happens to be whole.

**Fix:** infer int only when no fractional `step` is configured, or require explicit
`type` for numeric tweaks.

### M18. Particle physics are frame-rate dependent
`client/fx.js:49-50` with `client/client.html:980`

Particle motion is applied once per rAF frame un-scaled while lifetime is decremented
with a hardcoded `updateParticles(16.67)`. On a 120/144Hz display every burst moves
~2–2.4× faster and dies ~2–2.4× sooner than at 60Hz. Same class of issue:
`updateProjectiles`' fixed `0.4` per-frame lerp (`renderer.js:312-314`) and the
per-frame `CORRECTION_RATE`/`MONSTER_CORRECTION_RATE` factors (`game_state.js:26-27`).

**Fix:** pass real frame dt into the update and scale velocities/lerp factors by it
(e.g. `1 - Math.pow(1 - rate, dt/16.67)` for the smoothing factors).

---

## Low — server

- **`server/net.py:74-83`** — `broadcast_debug` sends `debug_log` frames to all players
  with no `DEBUG_MODE` gate (unlike `log.py`), and `dungeons.py` calls it
  unconditionally — production players receive internal regen/dungeon telemetry.
- **`server/gauntlet.py:310-312`** — the `TOO HARD` outcome is unreachable: gauntlet
  deaths route to `on_gauntlet_death` *before* the spirit-jar revive branch
  (`combat.py:578-582`), which advances the wave and resets `deaths = 0`, so a room
  clear always sees `deaths == 0`. The granted spirit jars are never consumed either —
  the docstring's "infinite spirit jars" flow is dead or missing.
- **`server/gauntlet.py:747-752`** — `/gt halve` is a silent no-op for rule-level
  params (`cooldown`, `warmup`, `range`, …): `game.monster_stats[kind]` never contains
  those keys, so `default = defaults.get(key, old)` makes `new == old` while still
  printing "halved: cooldown: x→x".
- **`server/gauntlet.py:703-705`** — `/gt <param> <value>` parses with bare
  `int()`/`float()`; `/gt hp abc` raises out of the command, dropping the player's
  remaining queued commands that tick with a stack trace instead of an error message.
- **`server/dungeons.py:876-882`** — `permanent_entries[perm_idx %
  len(permanent_entries)]` raises ZeroDivisionError when the room library has custom
  entries but zero permanent ones (the `real_count == 0` guard passes).
- **`server/dungeon_topology.py:165`** — `dist()` returns 0 for cells absent from the
  BFS cache, making unreachable cells indistinguishable from the origin; if the
  spanning-tree bridge fallback ever skips cells, they score as distance-0 in all
  placement keys and `get_boss_distances`.
- **`server/dungeons.py:464`** — `TRAP_ROOM_MIN_MONSTERS = 3` is referenced nowhere;
  misleading dead constant.
- **`server/rooms.py:189`, `:224-225`, `:235-236`** — entity-line parsing calls
  `int(tokens[...])` outside any try; one typo in a hand-edited `.room` entity line
  aborts server startup instead of skipping the file.
- **`server/npc_chat.py:777-782`** — the generic NPC-gift branch sends `item_obtained`
  with keys `item`/`name`, but the client handler (`client/net.js:1087`) only acts on
  `msg.item_type` — gifts without a `GIFT_EFFECTS` entry are granted with zero client
  feedback.
- **`server/npc_chat.py:870-881`** — `clear_player_history` doesn't clean
  `_last_proximity_dialog` (keyed by `(player, npc)`, only popped on actual chat) —
  slow unbounded growth from players who approach quest NPCs and leave.
- **`server/npc_kv_cache.py:44` / `server/npc_chat.py:518-524`, `:104-108`** — only
  KV-enabled chats take `slot_lock`; non-enabled chats and the per-join warmup ping
  also run through slot 0 and overwrite its KV while `_active_slot` still reports
  "warm" — the next enabled chat silently runs a cold prefill, defeating the cache and
  skewing the latency measurements the spike exists to collect.
- **`mud_server.py:570-574`** — Range parsing: malformed headers (`bytes=abc-`) raise
  `ValueError` → 500, and suffix ranges (`bytes=-500`) are misread as `0-500` (first
  501 bytes) instead of the last 500. The same suffix-range bug exists client-side in
  `client/sw.js:133-137`.
- **`mud_server.py:560-562`** — static serving re-reads whole files (multi-MB MP3s
  included) with blocking I/O on the event loop per request — including full reads to
  serve one Range slice; a missing file raises unhandled `FileNotFoundError` → 500.
  Can stutter the game tick under audio load.
- **`mud_server.py:185`** — `X-Forwarded-For` is trusted unconditionally, but clients
  connect directly to Python (WS bypasses nginx), so the logged "real IP" is fully
  attacker-controlled.
- **`mud_server.py:504-521`, `:672`** — admin Basic Auth endpoints are also served on
  the plaintext `0.0.0.0:8080` listener (password transits base64-in-cleartext if that
  port is reachable) and have no attempt rate-limiting. `compare_digest` is used
  correctly — deployment exposure only.
- **`server/combat.py:133`, `:152-153`** — `flush_messages` appends to `msgs` while
  iterating it (death branch → `broadcast_overworld_player_positions`). Works in
  CPython but is fragile; a snapshot/slice refactor would silently drop death
  notifications.
- **`server/constants.py:50-52` with `server/commands.py:1228`** — `WALK_TIME` is read
  by nothing at runtime (walk durations come from per-kind `monster_stats`), yet it's
  exposed in `/tweak` as "Default Walk Time (s)"; its comment is wrong. `CANCEL_TIME`
  and `LATENCY_COMP` are likewise unused.
- **`server/models.py:145-148`, `:155-157`, `:20-21`, `:77`** — dead code:
  `Monster.tick_interval`, `Monster.occupies()`, `WalkState.room_id/monster_idx` are
  never read. `Player.__init__` hardcodes `Avatar(8.0, 5.0, "down")`, duplicating
  `DEFAULT_SPAWN` and always overwritten at login.
- **`server/state.py:92`, `:98`, `:113-116`, `:125`** — bare `print()` for load-time
  warnings, contradicting the project's logging convention; a lazy `from server import
  log` inside the loaders would comply despite the import-order constraint.
- **`server/lifecycle.py:298-299`, `:531`, `:739`** — `DEBUG_MODE` re-parsed from
  `os.environ` at three sites instead of importing `server.constants.DEBUG_MODE`.
- **`server/combat.py:277-377`** — `_build_spectate_room_msg` duplicates ~60 lines of
  `send_room_enter` (monster walk-state serialization, custom tile/sprite collection)
  that must be kept in sync by hand; same pattern between `_has_potential_revivers`
  and `_find_spectate_target`.

## Low — client

- **`client/net.js:1463-1465`** — on `/tweak` re-open, already-registered server
  constants only get `.default` refreshed; the `get()` closure keeps returning the
  stale `_val` from first registration, so the panel shows a stale "current" value
  while Reset paradoxically applies the true one.
- **`client/net.js:789`** (also `renderer.js:302`, `net.js:883`) — boss-ness is
  inferred from sprite footprint (`width>1 || height>1`) because monster payloads
  omit `is_boss` — contradicting the project convention ("use `monster.is_boss`,
  never hardcode boss checks"). A future 1×1 boss loses the death flash / long shake /
  `boss_roar`; a large non-boss gets them. Fix by serializing `is_boss`.
- **`client/input.js:49-50`** vs `:258-260` — the backtick key toggles
  `showDebug`+`debugCollision` as a pair, but `#debug-btn` toggles only `showDebug`;
  one click permanently inverts the pair.
- **`client/music.js:239-247`** — double-`fadeIn` race in `setRoom`'s buffering path:
  if `readyState` crosses 2 between the check and listener registration, both the
  inline guard and the pending `canplaythrough` once-listener run `fadeIn`, which
  resets `volume = 0` mid-fade — audible drop-and-refade.
- **`client/tweak.js:192`** vs `:279-286` — `renderTweakPanel` early-returns while an
  input is focused, so the focus-restore block at the bottom (and the `isFocused`
  handling) is unreachable dead code; committed values aren't re-formatted until blur.
- **`client/tweak.js:410-418`** — the mid-drag re-render guard for sliders hooks only
  `mousedown`/`mouseup`; on touch devices, dragging fires `input` → re-render, which
  replaces `container.innerHTML` and destroys the slider under the finger.
- **`client/sw.js:133-137`** — `buildRangeResponse` mis-parses suffix ranges
  (`bytes=-500` → first 501 bytes with a wrong `Content-Range`); can break
  seeking/duration probing on offline playback in Safari.
- **`client/ost.html:636`** — "Stored offline" is decided by cache entry *count*
  (`keys.length >= TRACK_URLS.length`), not by checking the current URLs; after a
  track rename, the UI claims everything is stored and disables the button while the
  new track is uncached.
- **`client/renderer.js:129-143`** (also `:96-103`) — `renderWaterMist` allocates up
  to ~80 `CanvasGradient`s per frame (and `renderBrightTiles` one per bright tile per
  frame) — thousands of allocations/sec of GC churn in water-heavy rooms on low-end
  devices.

## Low — worldgen.py

- **`worldgen.py:739`** — the connectivity warning says "Re-running with different
  seed..." but the code actually force-connects unreachable rooms in place; and the
  force-connect only links to already-`reachable` neighbors, so a cluster of mutually
  unreachable cells could survive (moot today: the MST guarantees connectivity).
- **`worldgen.py:322-325`** — the path-widening branch checks the *left* neighbor for
  border but writes to the *right* neighbor; the guard doesn't guard what it writes.
- **`worldgen.py:20`** — header comment says "16x8 biome grid"; the grid is 16×11
  (module docstring gets it right).
- **`worldgen.py:707-711`** — the NPC-tuple `else` branch in `write_room_file`
  re-unpacks 5 fields from an arbitrary-length tuple; it's unreachable given current
  callers but would misbehave for 6-tuples.

---

## Verified clean (explicitly checked, no issues found)

- **Static file serving** uses a dict allowlist (`STATIC_FILES`) — no path traversal.
- **Claude CLI subprocess callers** strip `ANTHROPIC_API_KEY`/`CLAUDECODE` from the
  env and use list argv — no shell injection, no key leak (matches
  `tools/test_api_leak.py`).
- **Debug gating**: all debug slash commands and the `/tweak`/`/draw` processors are
  gated on `DEBUG_MODE`; admin endpoints 404 when `ADMIN_PASSWORD` is unset.
- **Tick resilience**: per-player command processing is individually try/except'd, so
  malformed input can't kill the loop (see H1 for the flush-side exception, which can).
- **OST**: `TRACKS` (ost.html) and `TRACK_URLS` (sw.js) are in sync — same 25 files,
  same order; the service worker correctly passes through everything off its
  allowlist and cleans stale shell caches while preserving audio.
- **Dungeon math**: row/col conventions are consistent across `bfs_reachable`,
  doorway tables, and item/monster placement; all 24 layout grids are fully connected
  with entrances on valid cells; the locked-door zone multigraph matches the key
  solver's edge-counting contract; late-resolved rooms honor already-unlocked doors.
- **Client canvas discipline**: `save`/`restore` balanced; `globalAlpha`, `textAlign`,
  `setLineDash`, `imageSmoothingEnabled` all restored after use.
- **fx arrays** are all capped (particles, corpses, floating text, slash arcs).
- **Reconnect state resets** in `login_ok`/`room_enter` are complete for a fresh
  server session; the `player_hurt` future-dated snapshot is masked by
  `knockbackSlide` priority for exactly its 200ms window.

## Suggested priorities

1. **H1** (tick-loop death) and **H2** (reconnect loop) — both are
   whole-game-breaking failure modes reachable in normal operation.
2. The cheat vectors **M1/M2/M3** — cheap to fix, and the game is publicly hosted.
3. **M7/M8** (gauntlet inventory loss / stranding) and **M4** (revival reset) — player-
   visible progression damage.
4. **M10** (prod disk fill) before the next long regen run on the VPS.
5. Everything else as opportunity arises; the Low list is mostly hygiene and
   latent traps worth burning down gradually.
