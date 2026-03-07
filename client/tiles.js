// ---------------------------------------------------------------------------
// Tile rendering — data-driven with composable operations
// ---------------------------------------------------------------------------
const TILE_COLORS = {
  0:  { name: "grass",       base: "#3a7a2a", alt: "#2d6a1e" },
  1:  { name: "stone",       base: "#9a9a9a", alt: "#8a8a8a" },
  2:  { name: "wood",        base: "#8B6914", alt: "#7a5a10" },
  3:  { name: "wall_stone",  base: "#5a5a6a", alt: "#4a4a5a" },
  4:  { name: "wall_wood",   base: "#5a3a1a", alt: "#4a2a10" },
  5:  { name: "water",       base: "#2a6aaa", alt: "#3a7abb" },
  6:  { name: "tree",        base: "#1a5a1a", alt: "#2a6a2a", trunk: "#5a3a1a" },
  7:  { name: "flowers",     base: "#3a7a2a", alt: "#2d6a1e", flower1: "#e44", flower2: "#ee4" },
  8:  { name: "dirt",        base: "#8a7040", alt: "#7a6030" },
  9:  { name: "stairs_up",   base: "#8B6914", alt: "#7a5a10" },
  10: { name: "stairs_down", base: "#8B6914", alt: "#7a5a10" },
  11: { name: "anvil",       base: "#9a9a9a", alt: "#3a3a3a" },
  12: { name: "fireplace",   base: "#5a3a1a", alt: "#e63", flame: "#fc3" },
  13: { name: "table",       base: "#6a4a1a", alt: "#5a3a10" },
  14: { name: "pew",         base: "#6a4a1a", alt: "#5a3a10" },
  15: { name: "door",        base: "#9a9a9a", alt: "#8a8a8a" },
  16: { name: "sand",        base: "#d4b870", alt: "#c4a860" },
  17: { name: "cactus",      base: "#d4b870", alt: "#c4a860", body: "#2a8a2a", spine: "#4aba4a" },
  18: { name: "mountain",    base: "#7a7a8a", alt: "#6a6a7a", snow: "#dde" },
  19: { name: "cave_floor",  base: "#5a5050", alt: "#4a4040" },
  20: { name: "swamp",       base: "#4a6a30", alt: "#3a5a28", water: "#3a5a4a" },
  21: { name: "dead_tree",   base: "#4a6a30", alt: "#3a5a28", trunk: "#5a4a3a", branch: "#6a5a4a" },
  22: { name: "bridge",      base: "#8B6914", alt: "#6a5010", plank: "#a08030" },
  23: { name: "gravestone",  base: "#3a5a3a", alt: "#2a4a2a", stone: "#8a8a9a" },
  24: { name: "iron_fence",  base: "#3a5a3a", alt: "#2a4a2a", iron: "#4a4a5a" },
  25: { name: "ruins_wall",  base: "#6a6a7a", alt: "#5a5a6a" },
  26: { name: "ruins_floor", base: "#8a8a7a", alt: "#7a7a6a" },
  27: { name: "tall_grass",  base: "#3a7a2a", alt: "#2d6a1e", tip: "#5a9a4a" },
  28: { name: "road",        base: "#9a8a6a", alt: "#8a7a5a" },
  29: { name: "cliff",       base: "#6a5a4a", alt: "#5a4a3a", face: "#7a6a5a" },
  30: { name: "shallow_water", base: "#5a9acc", alt: "#6aaadd" },
  31: { name: "boulder",     base: "#3a7a2a", alt: "#2d6a1e", rock: "#7a7a7a", rock2: "#6a6a6a" },
  32: { name: "dungeon_wall",  base: "#3a3a4a", alt: "#2a2a3a" },
  33: { name: "dungeon_floor", base: "#5a5a5a", alt: "#4a4a4a" },
  34: { name: "pillar",        base: "#5a5a5a", alt: "#4a4a4a", cap: "#7a7a7a", body: "#6a6a6a" },
  35: { name: "sconce_wall",   base: "#3a3a4a", alt: "#2a2a3a", flame: "#fc3" },
};

// Seeded random for consistent tile patterns
function seededRand(x, y, tileId) {
  let h = (x * 374761393 + y * 668265263 + tileId * 1274126177) | 0;
  h = ((h ^ (h >> 13)) * 1274126177) | 0;
  return (h & 0x7fffffff) / 0x7fffffff;
}

// ---------------------------------------------------------------------------
// Shared tile drawing operations
// ---------------------------------------------------------------------------
function drawNoise(c, TS, TILE, S, info, density, colorKey, seedId) {
  const color = info[colorKey] || colorKey;
  for (let py = 0; py < TILE; py++) {
    for (let px = 0; px < TILE; px++) {
      if (seededRand(px, py, seedId) < density) {
        c.fillStyle = color;
        c.fillRect(px * S, py * S, S, S);
      }
    }
  }
}

function drawSwampNoise(c, TS, TILE, S, info, seedId) {
  for (let py = 0; py < TILE; py++) {
    for (let px = 0; px < TILE; px++) {
      const r = seededRand(px, py, seedId);
      c.fillStyle = r < 0.2 ? info.water : r < 0.5 ? info.alt : info.base;
      c.fillRect(px * S, py * S, S, S);
    }
  }
}

function drawBricks(c, TS, TILE, S, info) {
  c.fillStyle = info.alt;
  for (let row = 0; row < TILE; row += 4) {
    const offset = (row % 8 === 0) ? 0 : 4;
    for (let col = offset; col < TILE; col += 8) {
      c.fillRect(col * S, row * S, S, S);
    }
    c.fillRect(0, (row + 3) * S, TS, S);
  }
}

function drawGridLines(c, TS, TILE, S, info, spacing) {
  c.fillStyle = info.alt;
  for (let i = 0; i < TILE; i += spacing) {
    c.fillRect(0, i * S, TS, S);
    c.fillRect(i * S, 0, S, TS);
  }
}

function drawHStripes(c, TS, TILE, S, info, spacing) {
  c.fillStyle = info.alt;
  for (let i = 0; i < TILE; i += spacing) {
    c.fillRect(0, i * S, TS, S);
  }
}

function drawVStripes(c, TS, TILE, S, info, spacing) {
  c.fillStyle = info.alt;
  for (let i = 0; i < TILE; i += spacing) {
    c.fillRect(i * S, 0, S, TS);
  }
}

function drawRects(c, S, info, rects) {
  for (const [colorKey, x, y, w, h] of rects) {
    c.fillStyle = info[colorKey] || TILE_COLORS[colorKey]?.base || colorKey;
    c.fillRect(x * S, y * S, w * S, h * S);
  }
}

function drawWavePattern(c, TS, TILE, S, info) {
  for (let py = 0; py < TILE; py++) {
    for (let px = 0; px < TILE; px++) {
      if ((px + py) % 4 < 2) {
        c.fillStyle = info.alt;
        c.fillRect(px * S, py * S, S, S);
      }
    }
  }
}

function drawRipplePattern(c, TS, TILE, S, info) {
  for (let py = 0; py < TILE; py++) {
    for (let px = 0; px < TILE; px++) {
      c.fillStyle = (px + py) % 3 === 0 ? info.alt : info.base;
      c.fillRect(px * S, py * S, S, S);
    }
  }
}

// ---------------------------------------------------------------------------
// Tile recipes — declarative definitions for each tile type
// Each recipe is a function(c, TS, TILE, S, info) that draws on top of the base fill
// ---------------------------------------------------------------------------
const TILE_GENERATORS = {
  0: (c, TS, TILE, S, info) => { // grass
    drawNoise(c, TS, TILE, S, info, 0.25, "alt", 0);
  },
  1: (c, TS, TILE, S, info) => { // stone
    drawGridLines(c, TS, TILE, S, info, 4);
  },
  2: (c, TS, TILE, S, info) => { // wood
    drawHStripes(c, TS, TILE, S, info, 4);
  },
  3: (c, TS, TILE, S, info) => { // wall_stone
    drawBricks(c, TS, TILE, S, info);
  },
  4: (c, TS, TILE, S, info) => { // wall_wood
    drawVStripes(c, TS, TILE, S, info, 3);
  },
  5: (c, TS, TILE, S, info) => { // water
    drawWavePattern(c, TS, TILE, S, info);
  },
  6: (c, TS, TILE, S, info) => { // tree
    drawRects(c, S, info, [
      ["trunk",    6, 10, 4, 6],
      ["#2a7a2a",  2,  1, 12, 10],
      ["alt",      3,  0, 10, 2],
      ["alt",      1,  3,  2, 6],
      ["alt",     13,  3,  2, 6],
      ["#4a9a3a",  4,  2,  3, 2],
      ["#4a9a3a",  8,  4,  4, 2],
    ]);
  },
  7: (c, TS, TILE, S, info) => { // flowers
    drawNoise(c, TS, TILE, S, info, 0.25, "alt", 7);
    const spots = [[4,4],[10,8],[6,12],[12,4]];
    spots.forEach(([fx,fy]) => {
      c.fillStyle = seededRand(fx,fy,99) > 0.5 ? info.flower1 : info.flower2;
      c.fillRect(fx*S, fy*S, S*2, S*2);
    });
  },
  8: (c, TS, TILE, S, info) => { // dirt
    drawNoise(c, TS, TILE, S, info, 0.25, "alt", 8);
  },
  9: (c, TS, TILE, S, info) => { // stairs_up
    drawHStripes(c, TS, TILE, S, info, 3);
    drawRects(c, S, info, [
      ["#fff", 7, 3, 2, 8],
      ["#fff", 5, 5, 2, 2],
      ["#fff", 9, 5, 2, 2],
    ]);
  },
  10: (c, TS, TILE, S, info) => { // stairs_down
    drawHStripes(c, TS, TILE, S, info, 3);
    drawRects(c, S, info, [
      ["#fff", 7, 3, 2, 8],
      ["#fff", 5, 9, 2, 2],
      ["#fff", 9, 9, 2, 2],
    ]);
  },
  11: (c, TS, TILE, S, info) => { // anvil
    c.fillStyle = TILE_COLORS[1].base;
    c.fillRect(0, 0, TS, TS);
    drawRects(c, S, info, [
      ["#3a3a3a", 4, 6, 8, 4],
      ["#3a3a3a", 3, 4, 10, 3],
      ["#3a3a3a", 6, 3, 4, 2],
    ]);
  },
  12: (c, TS, TILE, S, info) => { // fireplace
    c.fillStyle = "#3a2010";
    c.fillRect(0, 0, TS, TS);
    drawRects(c, S, info, [
      ["flame", 4, 4, 3, 6],
      ["flame", 8, 5, 3, 5],
      ["#f83",  5, 6, 5, 4],
    ]);
  },
  13: (c, TS, TILE, S, info) => { // table
    c.fillStyle = TILE_COLORS[2].base;
    c.fillRect(0, 0, TS, TS);
    drawRects(c, S, info, [
      ["base", 2, 2, 12, 12],
      ["alt",  3, 3, 10, 10],
    ]);
  },
  14: (c, TS, TILE, S, info) => { // pew
    c.fillStyle = TILE_COLORS[1].base;
    c.fillRect(0, 0, TS, TS);
    drawRects(c, S, info, [
      ["base", 2, 4, 12, 8],
      ["alt",  2, 4, 12, 2],
    ]);
  },
  15: (c, TS, TILE, S, info) => { // door
    drawGridLines(c, TS, TILE, S, info, 4);
  },
  16: (c, TS, TILE, S, info) => { // sand
    drawNoise(c, TS, TILE, S, info, 0.3, "alt", 16);
  },
  17: (c, TS, TILE, S, info) => { // cactus
    drawNoise(c, TS, TILE, S, info, 0.2, "alt", 17);
    drawRects(c, S, info, [
      ["body",  6, 3, 4, 12],
      ["body",  3, 5, 3, 3],
      ["body", 10, 7, 3, 3],
      ["spine", 7, 2, 2, 1],
      ["spine", 4, 4, 1, 1],
      ["spine",11, 6, 1, 1],
    ]);
  },
  18: (c, TS, TILE, S, info) => { // mountain
    drawRects(c, S, info, [
      ["alt",  0, 0, 16, 16],
      ["base", 2, 4, 12, 12],
      ["base", 4, 2, 8, 2],
      ["base", 6, 0, 4, 2],
      ["snow", 6, 0, 4, 2],
      ["snow", 5, 2, 6, 1],
    ]);
  },
  19: (c, TS, TILE, S, info) => { // cave_floor
    drawNoise(c, TS, TILE, S, info, 0.3, "alt", 19);
  },
  20: (c, TS, TILE, S, info) => { // swamp
    drawSwampNoise(c, TS, TILE, S, info, 20);
  },
  21: (c, TS, TILE, S, info) => { // dead_tree
    drawNoise(c, TS, TILE, S, info, 0.2, "alt", 21);
    drawRects(c, S, info, [
      ["trunk",   6, 6, 4, 10],
      ["trunk",   5, 4, 6, 3],
      ["branch",  3, 2, 3, 3],
      ["branch", 10, 1, 3, 4],
      ["branch",  4, 0, 2, 3],
      ["branch", 11, 3, 2, 2],
    ]);
  },
  22: (c, TS, TILE, S, info) => { // bridge
    c.fillStyle = TILE_COLORS[5].base;
    c.fillRect(0, 0, TS, TS);
    c.fillStyle = info.base;
    c.fillRect(2*S, 0, 12*S, TS);
    c.fillStyle = info.alt;
    for (let i = 0; i < TILE; i += 3) c.fillRect(2*S, i*S, 12*S, S);
    drawRects(c, S, info, [
      ["plank", 2, 0, 1, 16],
      ["plank",13, 0, 1, 16],
    ]);
  },
  23: (c, TS, TILE, S, info) => { // gravestone
    c.fillStyle = TILE_COLORS[0].base;
    c.fillRect(0, 0, TS, TS);
    drawNoise(c, TS, TILE, S, TILE_COLORS[0], 0.2, "alt", 0);
    drawRects(c, S, info, [
      ["stone",   5, 4, 6, 8],
      ["stone",   6, 3, 4, 1],
      ["#6a6a7a", 7, 5, 2, 1],
      ["#6a6a7a", 6, 7, 4, 1],
    ]);
  },
  24: (c, TS, TILE, S, info) => { // iron_fence
    c.fillStyle = TILE_COLORS[0].base;
    c.fillRect(0, 0, TS, TS);
    drawNoise(c, TS, TILE, S, TILE_COLORS[0], 0.2, "alt", 0);
    c.fillStyle = info.iron;
    for (let i = 1; i < TILE; i += 3) c.fillRect(i*S, 0, S, TS);
    c.fillRect(0, 4*S, TS, S);
    c.fillRect(0, 10*S, TS, S);
  },
  25: (c, TS, TILE, S, info) => { // ruins_wall
    drawBricks(c, TS, TILE, S, info);
    drawRects(c, S, info, [
      ["#3a3a3a", 2, 1, 2, 2],
      ["#3a3a3a",10, 8, 3, 2],
    ]);
  },
  26: (c, TS, TILE, S, info) => { // ruins_floor
    drawNoise(c, TS, TILE, S, info, 0.3, "alt", 26);
    drawRects(c, S, info, [
      ["#5a5a4a", 3, 2, 1, 8],
      ["#5a5a4a", 3,10, 6, 1],
      ["#5a5a4a", 9, 5, 1, 6],
    ]);
  },
  27: (c, TS, TILE, S, info) => { // tall_grass
    drawNoise(c, TS, TILE, S, info, 0.25, "alt", 27);
    c.fillStyle = info.tip;
    const blades = [[2,2],[5,1],[8,3],[11,0],[14,2],[3,8],[7,7],[10,9],[13,6]];
    blades.forEach(([bx,by]) => { c.fillRect(bx*S, by*S, S, 4*S); });
  },
  28: (c, TS, TILE, S, info) => { // road
    drawNoise(c, TS, TILE, S, info, 0.2, "alt", 28);
    drawRects(c, S, info, [
      ["#7a6a4a", 4, 0, 1, 16],
      ["#7a6a4a",11, 0, 1, 16],
    ]);
  },
  29: (c, TS, TILE, S, info) => { // cliff
    drawRects(c, S, info, [
      ["face", 0, 0, 16, 8],
    ]);
    c.fillStyle = info.alt;
    for (let i = 0; i < TILE; i += 3) c.fillRect(0, i*S, TS, S);
    drawRects(c, S, info, [
      ["#4a3a2a", 0, 8, 16, 2],
    ]);
  },
  30: (c, TS, TILE, S, info) => { // shallow_water
    drawRipplePattern(c, TS, TILE, S, info);
  },
  31: (c, TS, TILE, S, info) => { // boulder
    drawNoise(c, TS, TILE, S, TILE_COLORS[0], 0.2, "alt", 0);
    drawRects(c, S, info, [
      ["rock",    3, 4, 10, 8],
      ["rock",    4, 3, 8, 1],
      ["rock",    5,12, 6, 1],
      ["rock2",   4, 5, 3, 3],
      ["#8a8a8a", 8, 4, 3, 2],
    ]);
  },
  32: (c, TS, TILE, S, info) => { // dungeon_wall
    drawBricks(c, TS, TILE, S, info);
  },
  33: (c, TS, TILE, S, info) => { // dungeon_floor
    drawNoise(c, TS, TILE, S, info, 0.3, "alt", 33);
    drawRects(c, S, info, [
      ["#3a3a3a", 4, 3, 1, 6],
      ["#3a3a3a", 4, 9, 5, 1],
      ["#3a3a3a",10, 6, 1, 5],
    ]);
  },
  34: (c, TS, TILE, S, info) => { // pillar
    drawNoise(c, TS, TILE, S, info, 0.3, "alt", 33);
    drawRects(c, S, info, [
      ["body", 5, 2, 6, 12],
      ["body", 4, 3, 8, 10],
      ["cap",  4, 2, 8, 2],
      ["cap",  5, 1, 6, 1],
      ["cap",  4,12, 8, 2],
    ]);
  },
  35: (c, TS, TILE, S, info) => { // sconce_wall
    drawBricks(c, TS, TILE, S, info);
    drawRects(c, S, info, [
      ["#5a5a5a", 6, 6, 4, 4],
      ["#5a5a5a", 7,10, 2, 2],
      ["flame",   7, 3, 2, 4],
      ["#f83",    6, 4, 4, 2],
    ]);
  },
};

// ---------------------------------------------------------------------------
// Custom tile registry — populated at runtime from server data (AI-generated)
// Keys are string tile IDs. Values are recipe objects with colors + operations.
// ---------------------------------------------------------------------------
const customTiles = {};

// Recipe interpreter — runs an operations array using existing draw functions
function runTileRecipe(c, TS, TILE, S, recipe) {
  // Build a color map from the recipe's named colors
  const colors = recipe.colors || {};

  // Fill base color
  const base = colors.base || "#888";
  c.fillStyle = base;
  c.fillRect(0, 0, TS, TS);

  const ops = recipe.operations || [];
  for (const op of ops) {
    // Resolve a color key from the recipe's color palette
    const resolveColor = (key) => colors[key] || key;

    switch (op.op) {
      case "fill":
        c.fillStyle = resolveColor(op.color);
        c.fillRect(0, 0, TS, TS);
        break;
      case "noise": {
        // Build an info-like object where color keys map to recipe colors
        const info = { ...colors };
        const colorKey = op.color || "alt";
        const density = op.density || 0.3;
        const seedId = op.seed || 0;
        drawNoise(c, TS, TILE, S, info, density, colorKey, seedId);
        break;
      }
      case "bricks": {
        const info = { ...colors };
        drawBricks(c, TS, TILE, S, info);
        break;
      }
      case "grid_lines": {
        const info = { ...colors };
        drawGridLines(c, TS, TILE, S, info, op.spacing || 4);
        break;
      }
      case "hstripes": {
        const info = { ...colors };
        drawHStripes(c, TS, TILE, S, info, op.spacing || 4);
        break;
      }
      case "vstripes": {
        const info = { ...colors };
        drawVStripes(c, TS, TILE, S, info, op.spacing || 3);
        break;
      }
      case "wave": {
        const info = { ...colors };
        drawWavePattern(c, TS, TILE, S, info);
        break;
      }
      case "ripple": {
        const info = { ...colors };
        drawRipplePattern(c, TS, TILE, S, info);
        break;
      }
      case "rects": {
        const info = { ...colors };
        drawRects(c, S, info, op.rects || []);
        break;
      }
      // Direct pixel placement for fine-grained control
      case "pixels": {
        for (const [colorKey, x, y] of (op.pixels || [])) {
          c.fillStyle = resolveColor(colorKey);
          c.fillRect(x * S, y * S, S, S);
        }
        break;
      }
    }
  }
}

// Pre-rendered tile cache
const tileCanvases = {};

function createTileCanvas(tileId, TS, TILE, SCALE) {
  const tc = document.createElement("canvas");
  tc.width = TS;
  tc.height = TS;
  const c = tc.getContext("2d");
  const info = TILE_COLORS[tileId] || TILE_COLORS[0];
  const S = SCALE;

  // Fill base color
  c.fillStyle = info.base;
  c.fillRect(0, 0, TS, TS);

  // Apply tile-specific generator
  const generator = TILE_GENERATORS[tileId];
  if (generator) generator(c, TS, TILE, S, info);

  return tc;
}

function getTileCanvas(tileId, TS, TILE, SCALE) {
  if (!tileCanvases[tileId]) {
    // Check custom tile registry for string IDs (AI-generated tiles)
    if (typeof tileId === "string" && customTiles[tileId]) {
      const tc = document.createElement("canvas");
      tc.width = TS;
      tc.height = TS;
      runTileRecipe(tc.getContext("2d"), TS, TILE, SCALE, customTiles[tileId]);
      tileCanvases[tileId] = tc;
    } else {
      tileCanvases[tileId] = createTileCanvas(tileId, TS, TILE, SCALE);
    }
  }
  return tileCanvases[tileId];
}
