// ---------------------------------------------------------------------------
// Sprite data — declarative pixel-art definitions
// Each sprite is an array of [colorKey, x, y, w, h] layers drawn in order.
// Color keys resolve as: sprite local colors > PALETTE globals > literal hex.
// ---------------------------------------------------------------------------

const PALETTE = {
  SKIN: "#e8c898", HAIR: "#4a3020", PANTS: "#3a4a8a", BOOTS: "#3a2a1a",
};

// ---------------------------------------------------------------------------
// NPC sprite data
// ---------------------------------------------------------------------------
const NPC_SPRITE_DATA = {
  guard: {
    colors: { helmet: "#8090a0", helmet_dark: "#606e7a", armor: "#9aa8b8" },
    layers: [
      ["helmet",      4, 0, 8, 2],
      ["helmet",      4, 2, 8, 1],
      ["helmet_dark", 4, 2, 8, 1],
      ["SKIN",        5, 3, 6, 3],
      ["#222",        6, 3, 1, 1],
      ["#222",        9, 3, 1, 1],
      ["armor",       4, 6, 8, 5],
      ["armor",       3, 6, 1, 4],
      ["armor",      12, 6, 1, 4],
      ["SKIN",        3,10, 1, 1],
      ["SKIN",       12,10, 1, 1],
      ["PANTS",       5,11, 6, 2],
      ["BOOTS",       5,13, 2, 2],
      ["BOOTS",       9,13, 2, 2],
    ],
  },
  smith: {
    colors: { hair: "#5a3a2a", dark_shirt: "#4a4a4a", apron: "#8a5a2a", strap: "#6a4010" },
    layers: [
      ["hair",        5, 0, 6, 2],
      ["SKIN",        5, 2, 6, 4],
      ["#222",        6, 3, 1, 1],
      ["#222",        9, 3, 1, 1],
      ["hair",        6, 5, 4, 1],
      ["dark_shirt",  4, 6, 8, 5],
      ["apron",       5, 6, 6, 5],
      ["strap",       6, 7, 4, 1],
      ["SKIN",        3, 7, 1, 3],
      ["SKIN",       12, 7, 1, 3],
      ["SKIN",        3,10, 1, 1],
      ["SKIN",       12,10, 1, 1],
      ["PANTS",       5,11, 6, 2],
      ["BOOTS",       5,13, 2, 2],
      ["BOOTS",       9,13, 2, 2],
    ],
  },
  priest: {
    colors: { hair: "#6a5040", smile: "#a06060", robe: "#e8e0d0", cross: "#d4a840", robe_dark: "#d8d0c0", sandal: "#8a6a3a" },
    layers: [
      ["SKIN",        5, 0, 6, 6],
      ["hair",        5, 0, 6, 1],
      ["hair",        5, 0, 1, 2],
      ["hair",       10, 0, 1, 2],
      ["#222",        6, 3, 1, 1],
      ["#222",        9, 3, 1, 1],
      ["smile",       7, 5, 2, 1],
      ["robe",        4, 6, 8, 5],
      ["robe",        3, 7, 1, 3],
      ["robe",       12, 7, 1, 3],
      ["cross",       7, 7, 2, 1],
      ["cross",       7, 8, 2, 2],
      ["SKIN",        3,10, 1, 1],
      ["SKIN",       12,10, 1, 1],
      ["robe_dark",   4,11, 8, 2],
      ["sandal",      5,13, 2, 2],
      ["sandal",      9,13, 2, 2],
    ],
  },
  barmaid: {
    colors: { hair: "#8a3020", smile: "#c06060", dress: "#3a8a3a", apron: "#e8e8e8", shoe: "#4a2a1a" },
    layers: [
      ["hair",        4, 0, 8, 2],
      ["hair",        4, 2, 2, 4],
      ["hair",       10, 2, 2, 4],
      ["SKIN",        5, 2, 6, 4],
      ["#222",        6, 3, 1, 1],
      ["#222",        9, 3, 1, 1],
      ["smile",       7, 5, 2, 1],
      ["dress",       4, 6, 8, 5],
      ["apron",       5, 7, 6, 4],
      ["dress",       3, 7, 1, 3],
      ["dress",      12, 7, 1, 3],
      ["SKIN",        3,10, 1, 1],
      ["SKIN",       12,10, 1, 1],
      ["dress",       4,11, 8, 2],
      ["shoe",        5,13, 2, 2],
      ["shoe",        9,13, 2, 2],
    ],
  },
  witch: {
    colors: { hat: "#2a1a3a", skin: "#c8d898", eyes: "#aa44cc", robe: "#3a1a4a", robe_dark: "#2a1040" },
    layers: [
      ["hat",         7, 0, 2, 1],
      ["hat",         6, 1, 4, 1],
      ["hat",         5, 2, 6, 2],
      ["hat",         3, 4,10, 1],
      ["skin",        5, 5, 6, 3],
      ["eyes",        6, 5, 1, 1],
      ["eyes",        9, 5, 1, 1],
      ["robe",        4, 8, 8, 5],
      ["robe",        3, 9, 1, 3],
      ["robe",       12, 9, 1, 3],
      ["skin",        3,12, 1, 1],
      ["skin",       12,12, 1, 1],
      ["robe_dark",   3,13,10, 2],
    ],
  },
  ghost: {
    colors: { body: "#c0d0e8", eyes: "#223" },
    effects: { bob: 600, alpha: 0.55 },
    layers: [
      ["body",        5, 1, 6, 4],
      ["body",        4, 5, 8, 6],
      ["body",        4,11, 2, 2],
      ["body",        7,11, 2, 3],
      ["body",       10,11, 2, 2],
      ["eyes",        6, 3, 2, 2],
      ["eyes",        9, 3, 2, 2],
      ["eyes",        7, 5, 2, 1],
    ],
  },
  ghost_knight: {
    colors: { helmet: "#8898b0", visor: "#607080", eyes: "#dd3333", face: "#a0b0c8", armor: "#7888a0", bottom: "#6878a0" },
    effects: { bob: 700, alpha: 0.5 },
    layers: [
      ["helmet",      4, 0, 8, 3],
      ["visor",       4, 2, 8, 1],
      ["eyes",        6, 2, 1, 1],
      ["eyes",        9, 2, 1, 1],
      ["face",        5, 3, 6, 3],
      ["armor",       4, 6, 8, 5],
      ["armor",       3, 6, 1, 4],
      ["armor",      12, 6, 1, 4],
      ["bottom",      4,11, 2, 2],
      ["bottom",      7,11, 2, 3],
      ["bottom",     10,11, 2, 2],
    ],
  },
  ranger: {
    colors: { hood: "#3a6a2a", tunic: "#4a7a3a", belt: "#6a4a1a", buckle: "#c8a838", pants: "#6a5a3a", boot: "#4a3a1a" },
    layers: [
      ["hood",        4, 0, 8, 3],
      ["hood",        4, 0, 1, 4],
      ["hood",       11, 0, 1, 4],
      ["SKIN",        5, 2, 6, 4],
      ["#222",        6, 3, 1, 1],
      ["#222",        9, 3, 1, 1],
      ["tunic",       4, 6, 8, 5],
      ["tunic",       3, 6, 1, 4],
      ["tunic",      12, 6, 1, 4],
      ["belt",        4, 9, 8, 1],
      ["buckle",      7, 9, 2, 1],
      ["SKIN",        3,10, 1, 1],
      ["SKIN",       12,10, 1, 1],
      ["pants",       5,11, 6, 2],
      ["boot",        5,13, 2, 2],
      ["boot",        9,13, 2, 2],
    ],
  },
  farmer: {
    colors: { hat: "#c8a838", hat_mid: "#b89828", skin: "#d8b880", tunic: "#8a7a5a", pants: "#5a5040" },
    layers: [
      ["hat",         5, 0, 6, 1],
      ["hat",         3, 1,10, 1],
      ["hat_mid",     5, 2, 6, 1],
      ["skin",        5, 3, 6, 3],
      ["#222",        6, 4, 1, 1],
      ["#222",        9, 4, 1, 1],
      ["tunic",       4, 6, 8, 5],
      ["tunic",       3, 7, 1, 3],
      ["tunic",      12, 7, 1, 3],
      ["skin",        3,10, 1, 1],
      ["skin",       12,10, 1, 1],
      ["pants",       5,11, 6, 2],
      ["BOOTS",       5,13, 2, 2],
      ["BOOTS",       9,13, 2, 2],
    ],
  },
  nomad: {
    colors: { wrap: "#d8c8a0", skin: "#c8a070", robe: "#c0a870", sash: "#8a3030", pants: "#a89868", sandal: "#8a6a3a" },
    layers: [
      ["wrap",        5, 0, 6, 3],
      ["wrap",        4, 1, 1, 2],
      ["wrap",       11, 1, 1, 2],
      ["wrap",       11, 3, 1, 3],
      ["skin",        5, 3, 6, 3],
      ["#222",        6, 4, 1, 1],
      ["#222",        9, 4, 1, 1],
      ["robe",        4, 6, 8, 5],
      ["robe",        3, 7, 1, 3],
      ["robe",       12, 7, 1, 3],
      ["sash",        4, 8, 8, 1],
      ["skin",        3,10, 1, 1],
      ["skin",       12,10, 1, 1],
      ["pants",       5,11, 6, 2],
      ["sandal",      5,13, 2, 2],
      ["sandal",      9,13, 2, 2],
    ],
  },
  merchant: {
    colors: { hat: "#6a2a2a", stache: "#5a3a20", shirt: "#e8e0d0", vest: "#8a2a2a", button: "#d4a840", pants: "#3a3a5a" },
    layers: [
      ["hat",         4, 0, 8, 2],
      ["hat",         3, 2,10, 1],
      ["SKIN",        5, 3, 6, 3],
      ["#222",        6, 3, 1, 1],
      ["#222",        9, 3, 1, 1],
      ["stache",      6, 5, 1, 1],
      ["stache",      9, 5, 1, 1],
      ["shirt",       4, 6, 8, 5],
      ["vest",        5, 6, 6, 5],
      ["button",      7, 7, 2, 1],
      ["button",      7, 9, 2, 1],
      ["shirt",       3, 7, 1, 3],
      ["shirt",      12, 7, 1, 3],
      ["SKIN",        3,10, 1, 1],
      ["SKIN",       12,10, 1, 1],
      ["pants",       5,11, 6, 2],
      ["BOOTS",       5,13, 2, 2],
      ["BOOTS",       9,13, 2, 2],
    ],
  },
  elder: {
    colors: { hair: "#b0a8a0", skin: "#d0b888", beard: "#c0b8b0", robe: "#6a5a3a", robe_dark: "#5a4a2a", sandal: "#8a6a3a" },
    layers: [
      ["hair",        5, 0, 6, 2],
      ["hair",        4, 1, 1, 4],
      ["hair",       11, 1, 1, 4],
      ["skin",        5, 2, 6, 4],
      ["#222",        6, 3, 1, 1],
      ["#222",        9, 3, 1, 1],
      ["beard",       6, 5, 4, 1],
      ["beard",       6, 6, 4, 2],
      ["beard",       7, 8, 2, 1],
      ["robe",        4, 6, 2, 5],
      ["robe",       10, 6, 2, 5],
      ["robe",        4, 8, 8, 3],
      ["robe",        3, 8, 1, 2],
      ["robe",       12, 8, 1, 2],
      ["skin",        3,10, 1, 1],
      ["skin",       12,10, 1, 1],
      ["robe_dark",   4,11, 8, 2],
      ["sandal",      5,13, 2, 2],
      ["sandal",      9,13, 2, 2],
    ],
  },
  fisher: {
    colors: { hat: "#5a7a8a", skin: "#d0a870", stubble: "#9a8a6a", vest: "#5a7080", pants: "#5a5040", boot: "#4a3a2a" },
    layers: [
      ["hat",         5, 0, 6, 2],
      ["hat",         3, 2,10, 1],
      ["skin",        5, 3, 6, 3],
      ["#222",        6, 4, 1, 1],
      ["#222",        9, 4, 1, 1],
      ["stubble",     6, 5, 4, 1],
      ["vest",        4, 6, 8, 5],
      ["vest",        3, 7, 1, 3],
      ["vest",       12, 7, 1, 3],
      ["skin",        3,10, 1, 1],
      ["skin",       12,10, 1, 1],
      ["pants",       5,11, 6, 2],
      ["boot",        5,13, 2, 2],
      ["boot",        9,13, 2, 2],
    ],
  },
  amara: {
    colors: { dress: "#b8c8e8", dress_dark: "#8898b8", hair: "#d4a840", crown: "#e6b422", altar: "#606870", altar_dark: "#505860", eyes: "#666" },
    effects: { pulse: { speed: 800, baseAlpha: 0.08, range: 0.12, color: [180, 200, 255], rect: [2, 0, 12, 10] } },
    layers: [
      ["altar",       1, 9,14, 3],
      ["altar_dark",  2, 8,12, 1],
      ["hair",        2, 3, 3, 4],
      ["hair",        1, 4, 1, 3],
      ["crown",       3, 3, 2, 1],
      ["crown",       4, 2, 1, 1],
      ["SKIN",        5, 3, 3, 4],
      ["eyes",        5, 5, 2, 1],
      ["dress",       8, 3, 5, 4],
      ["dress_dark",  8, 6, 5, 1],
      ["SKIN",        9, 3, 2, 1],
      ["dress",      13, 4, 1, 3],
    ],
  },
};

// ---------------------------------------------------------------------------
// Monster sprite data — keyed by kind, with per-frame layers
// yOff: per-frame vertical offset (for hop animation)
// ---------------------------------------------------------------------------
const MONSTER_SPRITE_DATA = {
  slime: {
    colors: { body: "#44cc44", dark: "#228822", eyes: "#222", highlight: "#88ee88" },
    frames: [
      // Frame 0 — squished
      [
        ["dark",      2, 9,12, 6],
        ["body",      3, 8,10, 6],
        ["body",      4, 7, 8, 1],
        ["eyes",      5, 9, 2, 2],
        ["eyes",      9, 9, 2, 2],
        ["highlight", 5, 8, 2, 1],
      ],
      // Frame 1 — stretched
      [
        ["dark",      4,12, 8, 2],
        ["body",      4, 4, 8, 9],
        ["body",      5, 3, 6, 1],
        ["body",      5,13, 6, 1],
        ["dark",      4,11, 8, 2],
        ["eyes",      5, 6, 2, 2],
        ["eyes",      9, 6, 2, 2],
        ["highlight", 5, 4, 2, 1],
      ],
    ],
  },
  bat: {
    colors: { body: "#3a2a4a", wing: "#5a3a6a", eyes: "#ff4444" },
    frames: [
      // Frame 0 — wings up
      [
        ["body",      6, 6, 4, 4],
        ["wing",      1, 3, 5, 4],
        ["wing",     10, 3, 5, 4],
        ["wing",      2, 2, 3, 1],
        ["wing",     11, 2, 3, 1],
        ["eyes",      6, 7, 1, 1],
        ["eyes",      9, 7, 1, 1],
      ],
      // Frame 1 — wings down
      [
        ["body",      6, 5, 4, 4],
        ["wing",      1, 7, 5, 4],
        ["wing",     10, 7, 5, 4],
        ["wing",      2,11, 3, 1],
        ["wing",     11,11, 3, 1],
        ["eyes",      6, 6, 1, 1],
        ["eyes",      9, 6, 1, 1],
      ],
    ],
  },
  scorpion: {
    colors: { body: "#8a5a2a", dark: "#6a4a1a", claw: "#aa7a3a", tail: "#7a4a1a" },
    yOff: [0, -1],
    frames: [
      [
        ["body",      5, 8, 6, 4],
        ["dark",      6, 9, 4, 2],
        ["claw",      2, 7, 3, 2],
        ["claw",     11, 7, 3, 2],
        ["claw",      1, 6, 2, 1],
        ["claw",     13, 6, 2, 1],
        ["tail",      7, 5, 2, 3],
        ["tail",      7, 3, 2, 2],
        ["tail",      8, 2, 2, 2],
        ["#cc4444",   9, 1, 1, 2],
        ["dark",      4,12, 1, 2],
        ["dark",     11,12, 1, 2],
        ["dark",      3,11, 1, 2],
        ["dark",     12,11, 1, 2],
      ],
      // Frame 1 — same rects, yOff applied by renderer
      [
        ["body",      5, 8, 6, 4],
        ["dark",      6, 9, 4, 2],
        ["claw",      2, 7, 3, 2],
        ["claw",     11, 7, 3, 2],
        ["claw",      1, 6, 2, 1],
        ["claw",     13, 6, 2, 1],
        ["tail",      7, 5, 2, 3],
        ["tail",      7, 3, 2, 2],
        ["tail",      8, 2, 2, 2],
        ["#cc4444",   9, 1, 1, 2],
        ["dark",      4,12, 1, 2],
        ["dark",     11,12, 1, 2],
        ["dark",      3,11, 1, 2],
        ["dark",     12,11, 1, 2],
      ],
    ],
  },
  skeleton: {
    colors: { bone: "#ddd8cc", dark: "#aaa89a", eyes: "#222" },
    yOff: [0, -1],
    frames: [
      [
        ["bone",      5, 1, 6, 5],
        ["eyes",      6, 3, 2, 2],
        ["eyes",      9, 3, 2, 2],
        ["eyes",      7, 5, 2, 1],
        ["bone",      6, 6, 4, 5],
        ["dark",      7, 7, 2, 1],
        ["dark",      7, 9, 2, 1],
        ["bone",      4, 7, 2, 1],
        ["bone",      3, 8, 1, 3],
        ["bone",     10, 7, 2, 1],
        ["bone",     12, 8, 1, 3],
        ["bone",      6,11, 2, 3],
        ["bone",      9,11, 2, 3],
        ["dark",      5,14, 3, 1],
        ["dark",      9,14, 3, 1],
      ],
      [
        ["bone",      5, 1, 6, 5],
        ["eyes",      6, 3, 2, 2],
        ["eyes",      9, 3, 2, 2],
        ["eyes",      7, 5, 2, 1],
        ["bone",      6, 6, 4, 5],
        ["dark",      7, 7, 2, 1],
        ["dark",      7, 9, 2, 1],
        ["bone",      4, 7, 2, 1],
        ["bone",      3, 8, 1, 3],
        ["bone",     10, 7, 2, 1],
        ["bone",     12, 8, 1, 3],
        ["bone",      6,11, 2, 3],
        ["bone",      9,11, 2, 3],
        ["dark",      5,14, 3, 1],
        ["dark",      9,14, 3, 1],
      ],
    ],
  },
  swamp_blob: {
    colors: { body: "#5a7a3a", dark: "#3a5a2a", eyes: "#cc2", highlight: "#7a9a5a" },
    frames: [
      [
        ["dark",      2, 9,12, 6],
        ["body",      3, 8,10, 6],
        ["body",      4, 7, 8, 1],
        ["eyes",      5, 9, 2, 2],
        ["eyes",      9, 9, 2, 2],
        ["highlight", 5, 8, 2, 1],
      ],
      [
        ["dark",      4,12, 8, 2],
        ["body",      4, 4, 8, 9],
        ["body",      5, 3, 6, 1],
        ["body",      5,13, 6, 1],
        ["dark",      4,11, 8, 2],
        ["eyes",      5, 6, 2, 2],
        ["eyes",      9, 6, 2, 2],
        ["highlight", 5, 4, 2, 1],
      ],
    ],
  },
};

// ---------------------------------------------------------------------------
// Death animation data — 3 frames per monster type
// Frame with alpha property gets ctx.globalAlpha set before drawing
// ---------------------------------------------------------------------------
const DEATH_SPRITE_DATA = {
  slime: {
    colors: { splat: "#44cc44", dark: "#228822" },
    frames: [
      [["dark", 2,12,12, 2], ["splat", 3,11,10, 2], ["splat", 1,12,14, 1]],
      [["splat", 1,12, 3, 2], ["splat", 6,11, 4, 2], ["splat",12,12, 3, 2], ["splat", 3, 9, 2, 2], ["splat",10, 8, 2, 2], ["dark", 5,13, 2, 1], ["dark", 9,13, 2, 1]],
      { alpha: 0.4, layers: [["splat", 0,13, 2, 1], ["splat", 6,12, 3, 1], ["splat",13,13, 2, 1], ["splat", 3, 8, 1, 1], ["splat",11, 7, 1, 1]] },
    ],
  },
  bat: {
    colors: { clr: "#3a2a4a" },
    frames: [
      [["clr", 3,11,10, 2], ["clr", 1,12,14, 1]],
      [["clr", 1,12, 3, 2], ["clr", 6,11, 4, 2], ["clr",12,12, 3, 2]],
      { alpha: 0.4, layers: [["clr", 0,13, 2, 1], ["clr", 7,12, 2, 1], ["clr",13,13, 2, 1]] },
    ],
  },
  scorpion: {
    colors: { clr: "#8a5a2a" },
    frames: [
      [["clr", 3,11,10, 2], ["clr", 1,12,14, 1]],
      [["clr", 1,12, 3, 2], ["clr", 7,11, 3, 2], ["clr",12,12, 2, 2]],
      { alpha: 0.4, layers: [["clr", 0,13, 2, 1], ["clr", 7,12, 2, 1], ["clr",14,13, 2, 1]] },
    ],
  },
  skeleton: {
    colors: { clr: "#ddd8cc" },
    frames: [
      [["clr", 3,11,10, 3], ["clr", 5,10, 6, 1]],
      [["clr", 1,12, 3, 2], ["clr", 5,13, 2, 1], ["clr", 8,11, 3, 2], ["clr",12,13, 3, 1]],
      { alpha: 0.4, layers: [["clr", 0,13, 2, 1], ["clr", 6,14, 2, 1], ["clr",13,13, 2, 1]] },
    ],
  },
  swamp_blob: {
    colors: { splat: "#5a7a3a", dark: "#3a5a2a" },
    frames: [
      [["dark", 2,12,12, 2], ["splat", 3,11,10, 2], ["splat", 1,12,14, 1]],
      [["splat", 1,12, 3, 2], ["splat", 6,11, 4, 2], ["splat",12,12, 3, 2]],
      { alpha: 0.4, layers: [["splat", 0,13, 2, 1], ["splat", 6,12, 3, 1], ["splat",13,13, 2, 1]] },
    ],
  },
};

// ---------------------------------------------------------------------------
// Player dance frames — uses SHIRT placeholder resolved at draw time
// ---------------------------------------------------------------------------
const DANCE_FRAMES = [
  // Frame 0 — lean left, right arm up
  [
    ["HAIR",  4, 0, 6, 2], ["SKIN",  4, 2, 6, 4],
    ["#222",  5, 3, 1, 1], ["#222",  8, 3, 1, 1], ["#222",  6, 5, 2, 1],
    ["SHIRT", 3, 6, 8, 5], ["SHIRT", 1, 7, 2, 1], ["SKIN",  0, 7, 1, 1],
    ["SHIRT",11, 4, 1, 3], ["SKIN", 11, 3, 1, 1],
    ["PANTS", 3,11, 3, 2], ["PANTS", 8,11, 3, 2],
    ["BOOTS", 2,13, 3, 2], ["BOOTS", 9,13, 3, 2],
  ],
  // Frame 1 — lean right, left arm up
  [
    ["HAIR",  6, 0, 6, 2], ["SKIN",  6, 2, 6, 4],
    ["#222",  7, 3, 1, 1], ["#222", 10, 3, 1, 1], ["#222",  8, 5, 2, 1],
    ["SHIRT", 5, 6, 8, 5], ["SHIRT",13, 7, 2, 1], ["SKIN", 15, 7, 1, 1],
    ["SHIRT", 4, 4, 1, 3], ["SKIN",  4, 3, 1, 1],
    ["PANTS", 5,11, 3, 2], ["PANTS",10,11, 3, 2],
    ["BOOTS", 4,13, 3, 2], ["BOOTS",11,13, 3, 2],
  ],
  // Frame 2 — both arms up, squat
  [
    ["HAIR",  5, 1, 6, 2], ["SKIN",  5, 3, 6, 4],
    ["#222",  6, 4, 1, 1], ["#222",  9, 4, 1, 1], ["#222",  7, 6, 2, 1],
    ["SHIRT", 4, 7, 8, 5], ["SHIRT", 3, 5, 1, 3], ["SHIRT",12, 5, 1, 3],
    ["SKIN",  3, 4, 1, 1], ["SKIN", 12, 4, 1, 1],
    ["PANTS", 4,12, 3, 2], ["PANTS", 9,12, 3, 2],
    ["BOOTS", 3,14, 3, 1], ["BOOTS",10,14, 3, 1],
  ],
  // Frame 3 — arms crossed, cool pause
  [
    ["HAIR",  5, 0, 6, 2], ["SKIN",  5, 2, 6, 4],
    ["#222",  6, 3, 1, 1], ["#222",  9, 3, 1, 1], ["#222",  7, 5, 2, 1],
    ["SHIRT", 4, 6, 8, 5],
    ["SKIN",  4, 8, 2, 1], ["SKIN", 10, 8, 2, 1],
    ["PANTS", 5,11, 6, 2],
    ["BOOTS", 5,13, 2, 2], ["BOOTS", 9,13, 2, 2],
  ],
];

// ---------------------------------------------------------------------------
// Player walk frames — [direction][animFrame] -> layers
// Uses SHIRT placeholder
// ---------------------------------------------------------------------------
const PLAYER_WALK_FRAMES = {
  down: [
    [
      ["HAIR", 5, 0, 6, 2], ["SKIN", 5, 2, 6, 4], ["#222", 6, 3, 1, 1], ["#222", 9, 3, 1, 1],
      ["SHIRT", 4, 6, 8, 5], ["SHIRT", 3, 6, 1, 4], ["SHIRT",12, 6, 1, 4],
      ["SKIN", 3,10, 1, 1], ["SKIN",12,10, 1, 1],
      ["PANTS", 5,11, 6, 2], ["BOOTS", 5,13, 2, 2], ["BOOTS", 9,13, 2, 2],
    ],
    [
      ["HAIR", 5, 0, 6, 2], ["SKIN", 5, 2, 6, 4], ["#222", 6, 3, 1, 1], ["#222", 9, 3, 1, 1],
      ["SHIRT", 4, 6, 8, 5], ["SHIRT", 3, 6, 1, 4], ["SHIRT",12, 6, 1, 4],
      ["SKIN", 3,10, 1, 1], ["SKIN",12,10, 1, 1],
      ["PANTS", 5,11, 6, 2], ["BOOTS", 4,13, 2, 2], ["BOOTS",10,13, 2, 2],
    ],
  ],
  up: [
    [
      ["HAIR", 5, 0, 6, 5], ["SKIN", 4, 3, 1, 2], ["SKIN",11, 3, 1, 2],
      ["SHIRT", 4, 6, 8, 5], ["SHIRT", 3, 6, 1, 4], ["SHIRT",12, 6, 1, 4],
      ["SKIN", 3,10, 1, 1], ["SKIN",12,10, 1, 1],
      ["PANTS", 5,11, 6, 2], ["BOOTS", 5,13, 2, 2], ["BOOTS", 9,13, 2, 2],
    ],
    [
      ["HAIR", 5, 0, 6, 5], ["SKIN", 4, 3, 1, 2], ["SKIN",11, 3, 1, 2],
      ["SHIRT", 4, 6, 8, 5], ["SHIRT", 3, 6, 1, 4], ["SHIRT",12, 6, 1, 4],
      ["SKIN", 3,10, 1, 1], ["SKIN",12,10, 1, 1],
      ["PANTS", 5,11, 6, 2], ["BOOTS", 4,13, 2, 2], ["BOOTS",10,13, 2, 2],
    ],
  ],
  left: [
    [
      ["HAIR", 4, 0, 6, 2], ["HAIR", 8, 2, 2, 4],
      ["SKIN", 4, 2, 4, 4], ["#222", 4, 3, 1, 1],
      ["SHIRT", 5, 6, 6, 5], ["SHIRT", 4, 7, 1, 3], ["SKIN", 4,10, 1, 1],
      ["PANTS", 5,11, 5, 2], ["BOOTS", 5,13, 3, 2],
    ],
    [
      ["HAIR", 4, 0, 6, 2], ["HAIR", 8, 2, 2, 4],
      ["SKIN", 4, 2, 4, 4], ["#222", 4, 3, 1, 1],
      ["SHIRT", 5, 6, 6, 5], ["SHIRT", 4, 7, 1, 3], ["SKIN", 4,10, 1, 1],
      ["PANTS", 5,11, 5, 2], ["BOOTS", 4,13, 3, 2],
    ],
  ],
  right: [
    [
      ["HAIR", 6, 0, 6, 2], ["HAIR", 6, 2, 2, 4],
      ["SKIN", 8, 2, 4, 4], ["#222",11, 3, 1, 1],
      ["SHIRT", 5, 6, 6, 5], ["SHIRT",11, 7, 1, 3], ["SKIN",11,10, 1, 1],
      ["PANTS", 6,11, 5, 2], ["BOOTS", 8,13, 3, 2],
    ],
    [
      ["HAIR", 6, 0, 6, 2], ["HAIR", 6, 2, 2, 4],
      ["SKIN", 8, 2, 4, 4], ["#222",11, 3, 1, 1],
      ["SHIRT", 5, 6, 6, 5], ["SHIRT",11, 7, 1, 3], ["SKIN",11,10, 1, 1],
      ["PANTS", 6,11, 5, 2], ["BOOTS", 9,13, 3, 2],
    ],
  ],
};

// ---------------------------------------------------------------------------
// Player fall-over frames — uses SHIRT placeholder
// ---------------------------------------------------------------------------
const PLAYER_FALL_FRAMES = [
  // Frame 0 — leaning
  [
    ["HAIR", 6, 1, 6, 2], ["SKIN", 6, 3, 6, 3],
    ["SHIRT", 5, 6, 8, 5],
    ["PANTS", 5,11, 6, 2],
    ["BOOTS", 5,13, 2, 2], ["BOOTS", 9,13, 2, 2],
  ],
  // Frame 1 — sideways
  [
    ["HAIR", 1, 8, 2, 4], ["SKIN", 3, 8, 3, 4],
    ["SHIRT", 6, 7, 5, 5],
    ["PANTS",11, 8, 2, 4],
    ["BOOTS",13, 8, 2, 2],
  ],
  // Frame 2 — flat on ground (alpha handled by renderer)
  [
    ["HAIR", 1,10, 2, 3], ["SKIN", 3,10, 3, 3],
    ["SHIRT", 6, 9, 5, 4],
    ["PANTS",11,10, 2, 3],
    ["BOOTS",13,10, 2, 2],
  ],
];
