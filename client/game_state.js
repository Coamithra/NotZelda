/* Shared game state — all mutable state lives on the G namespace.
   Loaded first, before all other scripts.
   Sub-objects: conn, player, room, ui, fx, debug */

// Constants
const TILE = 16;
const SCALE = 3;
const TS = TILE * SCALE; // 48 — tile size on screen
const COLS = 15;
const ROWS = 11;
const CW = COLS * TS; // 720
const CH = ROWS * TS; // 528
let MOVE_LERP = 0.3;            // lerp factor for other players & monsters (fallback)

// Half-tile free movement constants
let MOVE_SPEED = 4.0;                  // tiles/sec
let HALF_TILE = 0.5;
// (position reporting triggers when Math.round(pos*2)/2 changes — see maybeReportPosition)
let HALF_WALK_TIME_MS = 125;           // other player animation duration (ms)

// Entity interpolation — remote player smoothing
let INTERP_DELAY = 66;                 // ms behind real-time to render remote players (~2 server ticks)
let INTERP_BUFFER_SIZE = 6;            // max snapshots to keep per remote player

// Client-side prediction + server reconciliation
let CORRECTION_RATE = 0.15;            // per-frame lerp factor for smooth correction decay
let MONSTER_CORRECTION_RATE = 0.2;     // per-frame decay for monster dead reckoning offset

// Shared mutable game state
const G = {
  // Connection/session
  conn: {
    ws: null,
    pingInterval: null,
    reconnectTimer: null,
    reconnectCount: 0,
    lastLoginName: "",
    lastLoginDesc: "",
    networkLog: true,      // log sent/received walk messages to console
    rtt: 0,                // round-trip time in ms (measured from ping/pong)
  },

  // Local player identity, position, movement, combat, progression
  player: {
    myName: "",
    myColorIndex: 0,
    myPlayer: null,        // {x, y, direction, color_index}

    // Player state machine
    state: "idle",           // "idle" | "attacking" | "attack_cooldown" | "dying"
    stateData: {},           // state-scoped data, replaced on every transition

    // Free movement (sub-tile)
    lastTickTime: 0,         // for deltaTime

    // Animation
    animFrame: 0,
    animTimer: 0,
    isMoving: false,
    displayX: 0,             // render position (computed: myPlayer.x/y + knockbackOffset)
    displayY: 0,
    lastMoveDir: null,       // for dust puff direction-change detection

    // Input
    keysDown: {},
    dirStack: [],            // direction key press order — last entry = active direction
    lastMoveTime: 0,

    // Health & combat
    myHp: 6,
    myMaxHp: 6,
    hurtFlash: 0,
    invincibleUntil: 0,
    knockbackSlide: null,     // {initialOffsetX, initialOffsetY, startTime, duration}
    knockbackOffsetX: 0,      // visual offset during knockback (decays to 0)
    knockbackOffsetY: 0,
    dyingPlayerSelf: null,
    stunUntil: 0,

    // Progression
    playerFlags: new Set(),
    keyCount: 0,                // dungeon keys held by this player
    itemPickupActive: null,     // {item_type, item_name, startTime, x, y}
    itemPickupEffects: {},      // name -> {item_type, startTime, x, y}

    // Server reconciliation (input-based movement)
    inputSeq: 0,                // monotonic input counter
    inputBuffer: [],            // [{seq, dir, dt, predX, predY}] — unacked predicted inputs
    pendingInputs: [],          // accumulated since last sync flush
    correctionOffset: { x: 0, y: 0 },  // smooth visual correction (decays to 0)

    // Revival
    waitingForRevival: false,   // True when dead + tombstone placed, showing waiting UI
    revivalProgress: null,      // {reviverName, startTime, duration} when being revived
    spiritJarRevive: null,      // {startTime} when spirit jar auto-revive animation is playing
    _respawnBtnHover: false,    // Respawn button hover state (set by mousemove in input.js)
    spectateData: null,         // {room_id, tilemap, players: {}, tombstones: {}, monsters: [], target_name, ...} when spectating another room (death camera)
  },

  // Current room, entities, dungeon state
  room: {
    currentRoom: null,     // {name, tilemap, room_id, exits, biome}

    // Other players
    otherPlayers: {},      // name -> {x, y, direction, color_index, displayX, displayY}

    // NPCs and monsters
    guards: [],            // [{name, x, y}]
    monsters: [],          // [{id, kind, x, y, displayX, displayY}]
    monsterHopFrame: 0,
    monsterHopTimer: 0,
    dyingMonsters: [],     // [{kind, x, y, frame, nextTime}]

    // Other player states
    dancingPlayers: {},    // name -> {frame, nextTime}
    attackingPlayers: {},  // name -> {direction, frame, nextTime}
    dyingOtherPlayers: {},
    tombstones: {},            // name -> {x, y, color_index}
    activeRevival: null,       // {targetName, startTime, duration} when local player channels

    // Chat
    speechBubbles: [],     // [{from, text, expires}]
    npcThinking: {},       // {npcName: startTimestamp} — animated "..." bubble

    // Items
    heartPickups: [],      // [{id, x, y}]

    // Dungeon
    dungeonState: null,         // {collected: Set, cells, bossCell, currentCell, lockedEdges}
    dungeonGroundItems: [],     // [{x, y, item_type}]
    ghostItems: [],             // [{x, y, item_type}] — collected by us, visible as ghosts for others
    openedChests: [],           // [{x, y}] — chests opened this visit (client-local)
    monsterFreeze: null,        // {start, duration} — monsters paused during item pickup

    // Darkness
    dark: false,                    // current room is dark (true or numeric opacity)
    lightSources: [],               // [[col, row], ...] — sconce/brazier positions
    lanternHolders: new Set(),      // player names with lanterns in this room
    medallionHolders: new Set(),    // player names with Tide Medallion in this room
    revealTilemap: null,            // [[tile_code, ...], ...] — hidden terrain under water

    // Corpses
    roomCorpses: [],          // [{kind, x, y, width, height}]

    // Nearby players in adjacent rooms (overworld edge arrows)
    nearbyPlayers: [],        // [{name, room_id, color_index, dead, direction}]
  },

  // DOM refs, chat, login, screens
  ui: {
    canvas: null,
    ctx: null,
    loginScreen: null,
    gameScreen: null,
    loginError: null,
    nameInput: null,
    descInput: null,
    connectBtn: null,
    chatInput: null,
    chatBar: null,
    chatHint: null,
    chatFocused: false,
    chatLog: null,
    serverLog: null,
    infoMessages: [],      // [{text, expires}]

    // Transition
    transition: null,      // {direction, oldCanvas, startTime, duration}
    conjuring: null,       // {startTime, pendingRoomEnter, progressSteps[]} — dungeon room generating animation
    gameLoopStarted: false,

    // Mobile
    isMobile: false,
  },

  // Visual effects & combat rendering
  fx: {
    particles: [],
    screenShake: null,        // {startTime, duration, intensity}
    hitPause: 0,              // timestamp: freeze updates until this time
    slashArcs: [],            // [{x, y, direction, startTime}]
    floatingTexts: [],        // [{x, y, text, startTime, color}]
    damageVignette: 0,        // timestamp for red edge flash
    projectiles: [],       // [{id, x, y, displayX, displayY, dx, dy, color}]
    chargeTrails: [],      // [{path, startTime}]
    monsterAttackFlashes: [], // [{x, y, startTime}]
    bossDeathEffect: null, // {startTime, duration} — dramatic screen flash/shake on boss kill
  },

  // Debug/dev tools
  debug: {
    debugMode: false,      // server-controlled via DEBUG_MODE env var
    showDebug: false,
    debugCollision: false, // tilde toggle: show AABBs + hit ghosts
    debugGhosts: [],       // [{playerBox, sourcePos, arrowDx, arrowDy, time}]
    debugLog: [],
    MAX_DEBUG_LINES: 12,
    dungeonDebug: null,    // {lib_monsters, lib_tiles, lib_rooms, room_source, minimap?} — from server
    viewServer: false,     // /viewserver toggle: show server-side entity positions
    serverState: null,     // latest debug_state snapshot from server
    drawMode: false,       // /draw toggle: click tiles to swap wall/walkable
    drawHover: null,       // {row, col} — tile under mouse cursor when draw mode active
    drawLMB: null,         // tile code bound to left mouse button
    drawRMB: null,         // tile code bound to right mouse button
    builtinTileIds: [],    // built-in tile IDs from server (for "All Tiles" palette)
    tweakMode: false,      // /tweak toggle: gamefeel parameter console
  },
};
