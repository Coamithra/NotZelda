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
const MOVE_LERP = 0.3;

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
  chatFocused: false,
  infoMessages: [],      // [{text, expires}]

  // Input
  keysDown: {},
  lastMoveTime: 0,

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

  // Health
  myHp: 6,
  myMaxHp: 6,
  hurtFlash: 0,
  invincibleUntil: 0,
  heartPickups: [],      // [{id, x, y}]
  dyingPlayerSelf: null,
  dyingOtherPlayers: {},

  // Transition
  transition: null,      // {direction, oldCanvas, startTime, duration}
  gameLoopStarted: false,

  // Debug
  showDebug: false,
  debugLog: [],
  MAX_DEBUG_LINES: 8,

  // Reconnect
  lastLoginName: "",
  lastLoginDesc: "",
  reconnectTimer: null,
  pingInterval: null,
  reconnectCount: 0,

  // Mobile
  isMobile: false,
};
