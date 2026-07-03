# Research: Hybrid State Sync + One-Off Events Architecture for Real-Time Multiplayer Browser Games

## Questions

- Q1: Is the hybrid state sync + events model a well-established pattern? What are the industry-standard names?
- Q2: How do major engines/frameworks handle the state vs. events split?
- Q3: What are the pitfalls of moving attacks from events to continuous state? What are the risks of deriving hitboxes from state frames?
- Q4: Is this architecture appropriate for a WebSocket game at ~30fps with <20 players? How do games solve the late-joiner problem?

---

## Findings

### 1. The Hybrid Model Is the Industry Standard, Not a Novel Idea

The split between **continuous state** (replicated properties / snapshots) and **one-off events** (RPCs / game events / temporary entities) is the dominant architecture in every major multiplayer engine. It is not a single named pattern but rather the convergence of several well-documented patterns:

**Glenn Fiedler (Gaffer On Games)** identifies three fundamental networking strategies for physics simulations, with state synchronization being the most practical for complex games:

- "The basic idea of state synchronization is that, somewhat like deterministic lockstep, we run the simulation on both sides but, unlike deterministic lockstep, we don't just send input, we send both input and state." [S1]
- "Because we send state, we don't need perfect determinism to stay in sync, and because the simulation runs on both sides, objects continue moving forward between updates." [S1]

**Ruoyu Sun (Game Networking Demystified)** frames the core distinction as "State vs. Input":

- In the state approach: "state calculation is done by one authoritative node (host or server) and all other players take it as the ultimate truth." [S7]
- He notes: "game networking is complicated and most games use a mix of different techniques depending on gameplay and limitations." [S7]

**Industry-standard terminology** for the two channels:

| Engine/Framework | Continuous State | One-Off Events |
|---|---|---|
| **Unreal Engine** | Replicated Properties (OnRep) | RPCs (Client/Server/Multicast) |
| **Valve Source** | Networked Entity Properties (snapshots) | Game Events + Temporary Entities |
| **Overwatch** | Replicated State (Statescript) | Command Frames |
| **Unity (Netcode)** | NetworkVariables | ClientRpc / ServerRpc |
| **Generic** | State Sync / Snapshot | Events / Messages / RPCs |

The proposed Legends of Amara refactor -- putting durable player state (position, direction, dancing, attacking) into per-tick sync frames, and keeping one-off effects (chat, item use) as discrete messages -- maps directly onto this universal pattern.

### 2. How Major Engines Handle the Split

#### Valve Source Engine

Source draws a hard line between entity state (snapshots) and events:

- "Most network bandwidth between server and client is spent on entity updates (compressed snapshots)." [S4]
- "The Source Engine uses three different message systems: game events, user messages and entity messages." [S4]
- **Temporary entities** are explicitly fire-and-forget: "Temporary entities are used by the server to create short-lived or one-off effects on clients and are 'fire and forget'; once one has been created, the server has nothing more to do with it." [S10]
- The critical design rule: "Whenever a durable and reliable state must be transmitted, it should be encoded as an entity state and not sent as a message or event. HLTV broadcasts and demos have problems with events and messages since they can play them back, but don't revert their impact when jumping back in time. That process is much easier with entities since they can easily be reverted to any previous state." [S4]

This last quote is directly relevant to the proposed refactor. Dancing and attacking are durable states visible to other players -- they belong in entity state, not events.

#### Unreal Engine

Unreal's networking documentation makes the state/event split explicit with clear guidance on when to use each:

- "Replicated properties should be used for replicating stateful events, while Multicast/Client RPCs are for replicating transient (not stateful) or cosmetic in nature events." [S6]
- "If you want your game to work well with join-in-progress, it's usually best to synchronize important gameplay data via replicated variables." [S6]
- "Multicast and Client RPCs are one-off events that should be only executed from the server that trigger behaviour on all the relevant targets once called... they don't persist any state. New connections have no clue which RPCs were sent recently." [S6]

The Unreal community has codified this into a rule of thumb (from Vorixo's devtricks blog):

- "One of the problems seen repeated lately in Unreal Engine is multiplayer code non resilient to late joiners and relevancy. Most of the time this is because the lack of understanding on how RPCs and replicated variables work at a high level." [S8]
- "If you store and replicate the time at which an action took place, you can figure out by the time someone joins the game where the animation/sound should be at for that client." [S8]

#### Overwatch (Blizzard)

Overwatch uses an ECS architecture with a proprietary scripting language called **Statescript** for weapon/ability state machines:

- "Overwatch uses a proprietary visual scripting language called Statescript to execute the high-level state machines used throughout the game, including the logic driving hero weapons and abilities." [S5]
- Weapons and abilities are modeled as **state machines** with replicated state, not as one-off event messages. "Prediction and replication of script behavior is automated so that common networking problems are handled for the scripter." [S5]
- The client synchronization model: "the local entity stores input and predictions, and when receiving a StatescriptPacket, the system can ignore redundant or out-of-order packets, replicate for remote entities, and then rollback and replicate for local entities." [S11]

This is the most relevant precedent: Overwatch models attacks as **state** (the weapon's state machine is in "firing" state, which is replicated), not as one-off "I fired" events.

#### Gabriel Gambetta

Gambetta's model describes the authoritative server pattern that underpins the hybrid approach:

- "The game state is managed by the server alone. Clients send their actions to the server. The server updates the game state periodically, and then sends the new game state back to clients, who just render it on the screen." [S3]
- The client sends **commands** (inputs/intentions), the server produces **state**: "the client tells the server 'I want to move one square to the right', the server updates its internal state with the new player position, and then replies to the player with the new position." [S3]

### 3. Pitfalls of Moving Attacks from Events to State

#### 3.1 The Missed Input Problem

At a 30fps tick rate (33ms per tick), a sword swing that lasts 180ms spans approximately 5-6 ticks. This is comfortable -- the attack state will appear in multiple sync frames. The risk of missing an attack entirely is negligible at this tick rate for melee combat.

However, there is an important subtlety from Valve's documentation:

- "If a command is received for a tick already executed on the server, the client is told it's too far behind and should increase its latency estimate." [S9]
- "Client and server hitboxes don't exactly match because of small precision errors in time measurement, and even a small difference of a few milliseconds can cause an error of several inches for fast-moving objects." [S9]

For Legends of Amara (tile-based, not pixel-precise), these timing errors are less impactful than in an FPS, but they still matter for contact damage calculations.

#### 3.2 State Staleness

If the server derives "player is attacking" from the latest state frame, there is a potential one-tick delay between the client initiating the attack and the server acting on it. At 33ms per tick, this adds 33ms of latency to hit detection -- acceptable for this game's pace but worth noting.

The current architecture (explicit attack command) processes the attack on the exact tick it arrives. Moving to state-derived attacks trades this precision for architectural simplicity.

#### 3.3 Security Considerations: Deriving Hitboxes from Client State

**This is the most significant risk.** In the current architecture, the client sends an explicit `attack` command with position, and the server validates it. In the proposed model, the server would derive "this player is attacking" from the client's state frame (which includes `attacking: true, direction: "right"`).

The security concern from Gabriel Gambetta:

- "You don't trust the client with the health of the player... the server knows it only has 10%." [S3]
- "You also don't trust the player with its position in the world. If you did, a hacked client would tell the server 'I'm at (10,10)' and a second later 'I'm at (20,10)', possibly going through a wall." [S3]

**Key insight:** The proposed refactor doesn't actually change the trust model. Currently, the client already sends its position in the attack command, and the server already trusts the client's position (within `MAX_MOVE_PER_UPDATE` bounds). Whether the attack arrives as a discrete command with position or as a state frame with `attacking: true` at position, the server is trusting the same data.

The real risk is **bandwidth-induced attack spam**: if the client's state frame says `attacking: true` on every tick for 5 ticks, the server must ensure it only processes one swing. The current `active_attack` system with `hit_set` already handles this, so the migration path is: state frame sets up the attack, but the server's existing per-tick `sword_hit_scan()` logic remains unchanged.

**Recommendation:** Keep the server as the authority on **when an attack starts**. The state frame should include the client's `attacking` flag, but the server should treat the *first frame* where `attacking` transitions from false to true as the attack initiation event (edge-triggered, not level-triggered). This preserves the command semantics while getting the architectural benefits of state sync.

#### 3.4 Bandwidth Considerations

Glenn Fiedler addresses bandwidth for state sync directly:

- "Instead of sending state updates for every object in each packet, we can now send updates for only a few, and if we're smart about how we select the objects for each packet, we can save bandwidth by concentrating updates on the most important objects." [S1]
- The **priority accumulator** pattern: "each frame, the current priority for each object is added to its priority accumulator value, then objects are sorted from largest to smallest priority accumulator value." [S1]

For Legends of Amara with <20 players, bandwidth is not a concern. Adding `attacking`, `dancing`, and `knockback` fields to the position sync frame adds maybe 10-20 bytes per frame per player. At 30fps with 20 players, that is approximately 12KB/s total -- trivial for WebSocket over TCP.

### 4. Appropriateness for This Game's Scale

#### WebSocket at 30fps with <20 Players: Well-Suited

The proposed architecture is neither overkill nor underkill for this game. It is the **right level of complexity**.

From the GameDev.net discussion on WebSocket multiplayer games:

- "For MMOs, FPS logic is often overkill... you can render entities at whatever position the server says they are, with interpolation to smooth things out." [S12]
- "WebSocket using TCP, packets are sent in order and if lost are resent, which simplifies synchronization compared to UDP-based approaches." [S12]

**Why it's not overkill:** The current architecture already sends position updates at 30fps. Adding a few more fields (dancing, attacking, knockback) to those updates is a trivial extension, and it *simplifies* the codebase by removing startDance/stopDance-style event scaffolding.

**Why it's not underkill:** At <20 players, there's no need for priority accumulators, delta compression, or partial state updates. Full player state per frame is fine. The game doesn't need client-side prediction, rollback, or deterministic simulation.

**What TCP/WebSocket means for this design:** TCP's ordered, reliable delivery means state frames always arrive in order. There's no need for sequence numbers or packet loss handling at the application layer. The downside (head-of-line blocking) is acceptable at this scale and tick rate.

### 5. The Late-Joiner Problem

The late-joiner problem is the strongest argument in favor of this refactor.

**The core issue:** When a new player enters a room, they need to see the current state of all other players -- who is dancing, who is mid-attack, who is being knocked back. With the current event-based approach, the server would need to replay or reconstruct these states. With state sync, the late joiner simply receives the latest state frame and sees everything correctly.

**Valve Source** solves this by sending a "full update" (all entity baselines) to new connections:

- "The first update is the final signon stage where the client actually receives an entity." [S10]
- Entity baselines contain all networked properties, so late joiners see the current state of everything.

**Unreal Engine** solves this through replicated properties:

- "The values of replicated variables are sent by the server to the incoming connections, and if a new player becomes relevant, OnReps execute behaviour on clients when the value of such variable changes." [S8]
- "New connections will see the [current state] since they receive the updated properties from the server." [S8]

**Legends of Amara's current situation:** The `room_enter` message already sends a snapshot of the room (players, monsters, items). The refactor would ensure that this snapshot includes the full player state (dancing, attacking, knockback) rather than relying on the new player having "been there" for the startDance event.

This is exactly what the Unreal community warns about:

- "Multicast and Client RPCs are one-off events... they don't persist any state. New connections have no clue which RPCs were sent recently." [S6]

### 6. Recommended Migration Approach

Based on the research, the proposed migration path (dance first, then attacks) is sound. Here is the recommended implementation, grounded in industry patterns:

#### Phase 1: Dance (Low-Risk Proof of Concept)

- Add `dancing: bool` to the player state frame
- Server sets `player.dancing` on the Player/Avatar model
- Remove `startDance`/`stopDance` discrete messages
- `room_enter` snapshot automatically includes dance state (late-joiner solved)
- Client renders dance animation based on state frame, not event memory

#### Phase 2: Attacks (Edge-Triggered State)

- Add `attacking: {direction, start_time}` or `null` to the player state frame
- **Server derives attack initiation from state transitions** (false->true edge), not from the level
- Existing `sword_hit_scan()` per-tick logic remains unchanged
- Remove the discrete `attack` command message
- The client's attack animation is driven by state, and other clients see attacks via state sync

#### Phase 3: Knockback and Other Transient States

- Add `knockback: {dx, dy, start_time}` to the player state frame
- Other clients interpolate knockback from state rather than receiving a one-off event

#### What Stays as Events

These should remain as discrete one-off messages, per the Source/Unreal pattern:

- **Chat messages** (not player state, they're world events)
- **Item pickups** (result persists in the world, not on the player's visual state)
- **Sound effects** (fire-and-forget, like Source's temporary entities)
- **Room transitions** (server-initiated, not continuous state)

---

## Gaps and Uncertainties

- **Overwatch Statescript internals**: The GDC slides describe the architecture at a high level, but the exact mechanism for how weapon state machines are replicated (delta-compressed? full state per frame?) is behind the GDC Vault paywall. The general principle (weapons as replicated state machines) is confirmed, but implementation details are not available.

- **Exact bandwidth impact of TCP head-of-line blocking**: While TCP is appropriate for this game's scale, I could not find quantitative measurements of how much head-of-line blocking degrades state sync at 30fps with typical consumer internet. Anecdotally, browser games at this scale routinely use WebSocket successfully, but hard numbers are lacking.

- **Missed attack edge case at exactly tick boundaries**: If a client's attack lasts exactly one tick (33ms) and the state frame with `attacking: true` is lost or delayed, the server might miss it entirely. This is mitigated by TCP's reliability guarantee (the frame will arrive, just potentially late). The practical risk is near-zero for a 180ms sword swing spanning 5+ ticks, but would matter for instantaneous abilities if added later.

- **No direct quote found on "hybrid state + events" as a named pattern**: While every major engine implements this split, I did not find a single canonical name for the combined approach. It's simply how multiplayer games are built. The closest is Fiedler's "state synchronization" (which implicitly includes events for non-state data) and Unreal's explicit "replicated properties for state, RPCs for events" guidance.

---

## Sources

- **[S1]** [State Synchronization | Gaffer On Games](https://gafferongames.com/post/state_synchronization/) -- Glenn Fiedler's article on state sync for networked physics, including priority accumulator and bandwidth management.
- **[S2]** [Snapshot Interpolation | Gaffer On Games](https://gafferongames.com/post/snapshot_interpolation/) -- Fiedler's article on snapshot-based state sync with jitter buffers.
- **[S3]** [Client-Server Game Architecture | Gabriel Gambetta](https://www.gabrielgambetta.com/client-server-game-architecture.html) -- Overview of authoritative server model with commands and state.
- **[S4]** [Source Multiplayer Networking | Valve Developer Community](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking) -- Valve's documentation on Source engine networking (snapshots, entity updates, events).
- **[S5]** [Overwatch Gameplay Architecture and Netcode | GDC 2017](https://www.gdcvault.com/play/1024001/-Overwatch-Gameplay-Architecture-and) -- Tim Ford's GDC talk on Overwatch's ECS and deterministic netcode.
- **[S6]** [Correct Stateful Replication | Vorixo Devtricks](https://vorixo.github.io/devtricks/stateful-events-multiplayer/) -- Unreal Engine guide on replicated properties vs RPCs for late joiners.
- **[S7]** [Game Networking Demystified, Part I: State vs. Input | Ruoyu Sun](https://ruoyusun.com/2019/03/28/game-networking-1.html) -- Overview of state-based vs input-based networking approaches.
- **[S8]** [Networking Entities | Valve Developer Community](https://developer.valvesoftware.com/wiki/Networking_Entities) -- Valve's docs on entity baselines and client connection signon.
- **[S9]** [Source Multiplayer Networking (lag compensation)](https://developer.valvesoftware.com/wiki/Source_Multiplayer_Networking) -- Valve's docs on tick timing, command processing, and hitbox precision.
- **[S10]** [Temporary Entity | Valve Developer Community](https://developer.valvesoftware.com/wiki/Temporary_Entity) -- Valve's docs on fire-and-forget temporary entities vs networked entities.
- **[S11]** [Networking Scripted Weapons and Abilities in Overwatch | GDC 2017](https://docplayer.net/50726818-Networking-scripted-weapons-and-abilities-in-overwatch-dan-reed-senior-gameplay-engineer-blizzard-entertainment.html) -- Dan Reed's GDC talk on Statescript, weapon state machines, and automated prediction/replication.
- **[S12]** [WebSocket-based realtime multiplayer game communication | GameDev.net](https://www.gamedev.net/forums/topic/686253-websocket-based-realtime-multiplayer-game-client-and-server-communication/) -- Community discussion on WebSocket architecture for browser games.
- **[S13]** [Client-Side Prediction and Server Reconciliation | Gabriel Gambetta](https://www.gabrielgambetta.com/client-side-prediction-server-reconciliation.html) -- Commands, authoritative state, and reconciliation.
- **[S14]** [Entity Interpolation | Gabriel Gambetta](https://www.gabrielgambetta.com/entity-interpolation.html) -- Rendering other players "in the past" using server state.
- **[S15]** [What Every Programmer Needs To Know About Game Networking | Gaffer On Games](https://gafferongames.com/post/what_every_programmer_needs_to_know_about_game_networking/) -- Fiedler's overview of the three networking approaches (lockstep, client/server, state sync).
- **[S16]** [Networking Events & Messages | Valve Developer Community](https://developer.valvesoftware.com/wiki/Networking_Events_%26_Messages) -- Valve's three message systems (game events, user messages, entity messages).
- **[S17]** [RPCs | Unreal Engine Documentation](https://dev.epicgames.com/documentation/en-us/unreal-engine/rpcs) -- Unreal's official docs on RPC types and when to use them vs replicated properties.
- **[S18]** [Authority | coherence Documentation](https://docs.coherence.io/manual/authority) -- Input authority vs state authority split in the coherence networking framework.
