/* Shared game state — all mutable state lives on the G namespace.
   Loaded first, before all other scripts. */

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
  // DOM refs (set during init)
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

  // Connection
  ws: null,

  // Player identity
  myName: "",
  myColorIndex: 0,
  myPlayer: null,        // {x, y, direction, color_index}

  // Other players
  otherPlayers: {},      // name -> {x, y, direction, color_index, displayX, displayY}

  // Current room
  currentRoom: null,     // {name, tilemap, room_id, exits, biome}

  // Chat
  speechBubbles: [],     // [{from, text, expires}]
  npcThinking: {},       // {npcName: startTimestamp} — animated "..." bubble
  chatFocused: false,
  infoMessages: [],      // [{text, expires}]

  // Input
  keysDown: {},
  dirStack: [],            // direction key press order — last entry = active direction
  lastMoveTime: 0,
  lastDirTime: 0,          // timestamp of last frame with a valid dirStack direction

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

  // Dances and attacks
  dancingPlayers: {},    // name -> {frame, nextTime}
  attackingPlayers: {},  // name -> {direction, frame, nextTime}

  // NPCs and monsters
  guards: [],            // [{name, x, y}]
  monsters: [],          // [{id, kind, x, y, displayX, displayY}]
  dyingMonsters: [],     // [{kind, x, y, frame, nextTime}]
  monsterHopFrame: 0,
  monsterHopTimer: 0,

  // Stage 5: Monster attack rendering state
  projectiles: [],       // [{id, x, y, displayX, displayY, dx, dy, color}]
  areaWarnings: [],      // [{x, y, range, startTime, duration}]
  chargeTrails: [],      // [{path, startTime}]
  chargePreps: [],       // [{id, lane, startTime}]
  monsterAttackFlashes: [], // [{x, y, startTime}]

  // Player progression
  playerFlags: new Set(),
  swordPickups: [],      // [{x, y, frame, nextTime}]

  // Dungeon items
  itemPickupActive: null,     // {item_type, item_name, startTime, x, y}
  itemPickupEffects: {},      // name -> {item_type, startTime, x, y}
  dungeonState: null,         // {collected: Set, cells, bossCell, currentCell, lockedEdges}
  dungeonGroundItems: [],     // [{x, y, item_type}]
  keyCount: 0,                // dungeon keys held by this player

  // Health
  myHp: 6,
  myMaxHp: 6,
  hurtFlash: 0,
  invincibleUntil: 0,
  knockbackSlide: null,
  heartPickups: [],      // [{id, x, y}]
  dyingPlayerSelf: null,
  dyingOtherPlayers: {},

  // Boss death effect
  bossDeathEffect: null, // {startTime, duration} — dramatic screen flash/shake on boss kill

  // Transition
  transition: null,      // {direction, oldCanvas, startTime, duration}
  conjuring: null,       // {startTime, pendingRoomEnter, progressSteps[]} — dungeon room generating animation
  gameLoopStarted: false,

  // Debug
  debugMode: false,      // server-controlled via DEBUG_MODE env var
  showDebug: false,
  networkLog: true,      // log sent/received walk messages to console
  dungeonDebug: null,    // {lib_monsters, lib_tiles, lib_rooms, room_source, minimap?} — from server
  debugLog: [],
  MAX_DEBUG_LINES: 12,
  debugCollision: false, // tilde toggle: show AABBs + hit ghosts
  debugGhosts: [],       // [{playerBox, sourcePos, arrowDx, arrowDy, time}]
  viewServer: false,     // /viewserver toggle: show server-side entity positions
  serverState: null,     // latest debug_state snapshot from server

  // Reconnect
  lastLoginName: "",
  lastLoginDesc: "",
  reconnectTimer: null,
  pingInterval: null,
  reconnectCount: 0,

  // Mobile
  isMobile: false,

  // Juice FX
  particles: [],
  screenShake: null,        // {startTime, duration, intensity}
  hitPause: 0,              // timestamp: freeze updates until this time
  slashArcs: [],            // [{x, y, direction, startTime}]
  floatingTexts: [],        // [{x, y, text, startTime, color}]
  roomCorpses: [],          // [{kind, x, y, width, height}]
  damageVignette: 0,        // timestamp for red edge flash
  lastMoveDir: null,        // for dust puff direction-change detection
};
