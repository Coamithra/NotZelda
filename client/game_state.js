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
const MOVE_LERP = 0.3;            // lerp factor for other players & monsters (fallback)

// Half-tile free movement constants
const MOVE_SPEED = 4.0;                  // tiles/sec
const HALF_TILE = 0.5;
// (position reporting triggers when Math.round(pos*2)/2 changes — see maybeReportPosition)
const HALF_WALK_TIME_MS = 125;           // other player animation duration (ms)

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
  },

  // Local player identity, position, movement, combat, progression
  player: {
    myName: "",
    myColorIndex: 0,
    myPlayer: null,        // {x, y, direction, color_index}

    // Player state machine
    state: "idle",           // "idle" | "attacking" | "dying"
    stateData: {},           // state-scoped data, replaced on every transition

    // Free movement (sub-tile)
    preciseX: 0,             // pixel-precise position (local only)
    preciseY: 0,
    lastReportedX: 0,        // last position sent to server
    lastReportedY: 0,
    lastTickTime: 0,         // for deltaTime

    // Animation
    animFrame: 0,
    animTimer: 0,
    isMoving: false,
    displayX: 0,
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
    knockbackSlide: null,
    dyingPlayerSelf: null,
    stunUntil: 0,

    // Progression
    playerFlags: new Set(),
    keyCount: 0,                // dungeon keys held by this player
    itemPickupActive: null,     // {item_type, item_name, startTime, x, y}
    itemPickupEffects: {},      // name -> {item_type, startTime, x, y}
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

    // Chat
    speechBubbles: [],     // [{from, text, expires}]
    npcThinking: {},       // {npcName: startTimestamp} — animated "..." bubble

    // Items
    heartPickups: [],      // [{id, x, y}]

    // Dungeon
    dungeonState: null,         // {collected: Set, cells, bossCell, currentCell, lockedEdges}
    dungeonGroundItems: [],     // [{x, y, item_type}]
    monsterFreeze: null,        // {start, duration} — monsters paused during item pickup

    // Corpses
    roomCorpses: [],          // [{kind, x, y, width, height}]
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
    areaWarnings: [],      // [{x, y, range, startTime, duration}]
    chargeTrails: [],      // [{path, startTime}]
    chargePreps: [],       // [{id, lane, startTime}]
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
  },
};
