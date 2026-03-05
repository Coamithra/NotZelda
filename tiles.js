// ---------------------------------------------------------------------------
// Tile colors — procedural drawing
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
};

// Seeded random for consistent tile patterns
function seededRand(x, y, tileId) {
  let h = (x * 374761393 + y * 668265263 + tileId * 1274126177) | 0;
  h = ((h ^ (h >> 13)) * 1274126177) | 0;
  return (h & 0x7fffffff) / 0x7fffffff;
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

  // Fill base
  c.fillStyle = info.base;
  c.fillRect(0, 0, TS, TS);

  if (tileId === 0 || tileId === 7 || tileId === 8) {
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        if (seededRand(px, py, tileId) < 0.25) {
          c.fillStyle = info.alt;
          c.fillRect(px * S, py * S, S, S);
        }
      }
    }
    if (tileId === 7) {
      const spots = [[4,4],[10,8],[6,12],[12,4]];
      spots.forEach(([fx,fy]) => {
        c.fillStyle = seededRand(fx,fy,99) > 0.5 ? info.flower1 : info.flower2;
        c.fillRect(fx*S, fy*S, S*2, S*2);
      });
    }
  } else if (tileId === 1 || tileId === 15) {
    c.fillStyle = info.alt;
    for (let i = 0; i < TILE; i += 4) {
      c.fillRect(0, i * S, TS, S);
      c.fillRect(i * S, 0, S, TS);
    }
  } else if (tileId === 2) {
    c.fillStyle = info.alt;
    for (let i = 0; i < TILE; i += 4) {
      c.fillRect(0, i * S, TS, S);
    }
  } else if (tileId === 3) {
    c.fillStyle = info.alt;
    for (let row = 0; row < TILE; row += 4) {
      const offset = (row % 8 === 0) ? 0 : 4;
      for (let col = offset; col < TILE; col += 8) {
        c.fillRect(col * S, row * S, S, S);
      }
      c.fillRect(0, (row + 3) * S, TS, S);
    }
  } else if (tileId === 4) {
    c.fillStyle = info.alt;
    for (let i = 0; i < TILE; i += 3) {
      c.fillRect(i * S, 0, S, TS);
    }
  } else if (tileId === 5) {
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        if ((px + py) % 4 < 2) {
          c.fillStyle = info.alt;
          c.fillRect(px * S, py * S, S, S);
        }
      }
    }
  } else if (tileId === 6) {
    c.fillStyle = info.base;
    c.fillRect(0, 0, TS, TS);
    c.fillStyle = info.trunk;
    c.fillRect(6*S, 10*S, 4*S, 6*S);
    c.fillStyle = "#2a7a2a";
    c.fillRect(2*S, 1*S, 12*S, 10*S);
    c.fillStyle = info.alt;
    c.fillRect(3*S, 0, 10*S, 2*S);
    c.fillRect(1*S, 3*S, 2*S, 6*S);
    c.fillRect(13*S, 3*S, 2*S, 6*S);
    c.fillStyle = "#4a9a3a";
    c.fillRect(4*S, 2*S, 3*S, 2*S);
    c.fillRect(8*S, 4*S, 4*S, 2*S);
  } else if (tileId === 9) {
    c.fillStyle = info.alt;
    for (let i = 0; i < TILE; i += 3) {
      c.fillRect(0, i*S, TS, S);
    }
    c.fillStyle = "#fff";
    c.fillRect(7*S, 3*S, 2*S, 8*S);
    c.fillRect(5*S, 5*S, 2*S, 2*S);
    c.fillRect(9*S, 5*S, 2*S, 2*S);
  } else if (tileId === 10) {
    c.fillStyle = info.alt;
    for (let i = 0; i < TILE; i += 3) {
      c.fillRect(0, i*S, TS, S);
    }
    c.fillStyle = "#fff";
    c.fillRect(7*S, 3*S, 2*S, 8*S);
    c.fillRect(5*S, 9*S, 2*S, 2*S);
    c.fillRect(9*S, 9*S, 2*S, 2*S);
  } else if (tileId === 11) {
    c.fillStyle = TILE_COLORS[1].base;
    c.fillRect(0, 0, TS, TS);
    c.fillStyle = "#3a3a3a";
    c.fillRect(4*S, 6*S, 8*S, 4*S);
    c.fillRect(3*S, 4*S, 10*S, 3*S);
    c.fillRect(6*S, 3*S, 4*S, 2*S);
  } else if (tileId === 12) {
    c.fillStyle = "#3a2010";
    c.fillRect(0, 0, TS, TS);
    c.fillStyle = info.flame;
    c.fillRect(4*S, 4*S, 3*S, 6*S);
    c.fillRect(8*S, 5*S, 3*S, 5*S);
    c.fillStyle = "#f83";
    c.fillRect(5*S, 6*S, 5*S, 4*S);
  } else if (tileId === 13) {
    c.fillStyle = TILE_COLORS[2].base;
    c.fillRect(0, 0, TS, TS);
    c.fillStyle = info.base;
    c.fillRect(2*S, 2*S, 12*S, 12*S);
    c.fillStyle = info.alt;
    c.fillRect(3*S, 3*S, 10*S, 10*S);
  } else if (tileId === 14) {
    c.fillStyle = TILE_COLORS[1].base;
    c.fillRect(0, 0, TS, TS);
    c.fillStyle = info.base;
    c.fillRect(2*S, 4*S, 12*S, 8*S);
    c.fillStyle = info.alt;
    c.fillRect(2*S, 4*S, 12*S, 2*S);
  } else if (tileId === 16) {
    // Sand — dithered dunes
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        c.fillStyle = seededRand(px, py, 16) < 0.3 ? info.alt : info.base;
        c.fillRect(px*S, py*S, S, S);
      }
    }
  } else if (tileId === 17) {
    // Cactus on sand
    c.fillStyle = info.base;
    c.fillRect(0, 0, TS, TS);
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        if (seededRand(px, py, 17) < 0.2) { c.fillStyle = info.alt; c.fillRect(px*S, py*S, S, S); }
      }
    }
    c.fillStyle = info.body;
    c.fillRect(6*S, 3*S, 4*S, 12*S);
    c.fillRect(3*S, 5*S, 3*S, 3*S);
    c.fillRect(10*S, 7*S, 3*S, 3*S);
    c.fillStyle = info.spine;
    c.fillRect(7*S, 2*S, 2*S, S);
    c.fillRect(4*S, 4*S, S, S);
    c.fillRect(11*S, 6*S, S, S);
  } else if (tileId === 18) {
    // Mountain — rocky peak
    c.fillStyle = info.alt;
    c.fillRect(0, 0, TS, TS);
    c.fillStyle = info.base;
    c.fillRect(2*S, 4*S, 12*S, 12*S);
    c.fillRect(4*S, 2*S, 8*S, 2*S);
    c.fillRect(6*S, 0, 4*S, 2*S);
    c.fillStyle = info.snow;
    c.fillRect(6*S, 0, 4*S, 2*S);
    c.fillRect(5*S, 2*S, 6*S, S);
  } else if (tileId === 19) {
    // Cave floor — dark stone
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        c.fillStyle = seededRand(px, py, 19) < 0.3 ? info.alt : info.base;
        c.fillRect(px*S, py*S, S, S);
      }
    }
  } else if (tileId === 20) {
    // Swamp — murky green with water patches
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        const r = seededRand(px, py, 20);
        c.fillStyle = r < 0.2 ? info.water : r < 0.5 ? info.alt : info.base;
        c.fillRect(px*S, py*S, S, S);
      }
    }
  } else if (tileId === 21) {
    // Dead tree — bare branches on swamp
    c.fillStyle = info.base;
    c.fillRect(0, 0, TS, TS);
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        if (seededRand(px, py, 21) < 0.2) { c.fillStyle = info.alt; c.fillRect(px*S, py*S, S, S); }
      }
    }
    c.fillStyle = info.trunk;
    c.fillRect(6*S, 6*S, 4*S, 10*S);
    c.fillRect(5*S, 4*S, 6*S, 3*S);
    c.fillStyle = info.branch;
    c.fillRect(3*S, 2*S, 3*S, 3*S);
    c.fillRect(10*S, 1*S, 3*S, 4*S);
    c.fillRect(4*S, 0, 2*S, 3*S);
    c.fillRect(11*S, 3*S, 2*S, 2*S);
  } else if (tileId === 22) {
    // Bridge — wooden planks over water
    c.fillStyle = TILE_COLORS[5].base;
    c.fillRect(0, 0, TS, TS);
    c.fillStyle = info.base;
    c.fillRect(2*S, 0, 12*S, TS);
    c.fillStyle = info.alt;
    for (let i = 0; i < TILE; i += 3) {
      c.fillRect(2*S, i*S, 12*S, S);
    }
    c.fillStyle = info.plank;
    c.fillRect(2*S, 0, S, TS);
    c.fillRect(13*S, 0, S, TS);
  } else if (tileId === 23) {
    // Gravestone on grass
    c.fillStyle = TILE_COLORS[0].base;
    c.fillRect(0, 0, TS, TS);
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        if (seededRand(px, py, 0) < 0.2) { c.fillStyle = TILE_COLORS[0].alt; c.fillRect(px*S, py*S, S, S); }
      }
    }
    c.fillStyle = info.stone;
    c.fillRect(5*S, 4*S, 6*S, 8*S);
    c.fillRect(6*S, 3*S, 4*S, S);
    c.fillStyle = "#6a6a7a";
    c.fillRect(7*S, 5*S, 2*S, S);
    c.fillRect(6*S, 7*S, 4*S, S);
  } else if (tileId === 24) {
    // Iron fence on grass
    c.fillStyle = TILE_COLORS[0].base;
    c.fillRect(0, 0, TS, TS);
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        if (seededRand(px, py, 0) < 0.2) { c.fillStyle = TILE_COLORS[0].alt; c.fillRect(px*S, py*S, S, S); }
      }
    }
    c.fillStyle = info.iron;
    for (let i = 1; i < TILE; i += 3) {
      c.fillRect(i*S, 0, S, TS);
    }
    c.fillRect(0, 4*S, TS, S);
    c.fillRect(0, 10*S, TS, S);
  } else if (tileId === 25) {
    // Ruins wall — crumbling stone bricks
    c.fillStyle = info.base;
    c.fillRect(0, 0, TS, TS);
    c.fillStyle = info.alt;
    for (let row = 0; row < TILE; row += 4) {
      const offset = (row % 8 === 0) ? 0 : 4;
      for (let col = offset; col < TILE; col += 8) {
        c.fillRect(col*S, row*S, S, S);
      }
      c.fillRect(0, (row+3)*S, TS, S);
    }
    // Damage holes
    c.fillStyle = "#3a3a3a";
    c.fillRect(2*S, 1*S, 2*S, 2*S);
    c.fillRect(10*S, 8*S, 3*S, 2*S);
  } else if (tileId === 26) {
    // Ruins floor — cracked stone
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        c.fillStyle = seededRand(px, py, 26) < 0.3 ? info.alt : info.base;
        c.fillRect(px*S, py*S, S, S);
      }
    }
    c.fillStyle = "#5a5a4a";
    c.fillRect(3*S, 2*S, S, 8*S);
    c.fillRect(3*S, 10*S, 6*S, S);
    c.fillRect(9*S, 5*S, S, 6*S);
  } else if (tileId === 27) {
    // Tall grass — grass with taller blades
    c.fillStyle = info.base;
    c.fillRect(0, 0, TS, TS);
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        if (seededRand(px, py, 27) < 0.25) {
          c.fillStyle = info.alt; c.fillRect(px*S, py*S, S, S);
        }
      }
    }
    c.fillStyle = info.tip;
    const blades = [[2,2],[5,1],[8,3],[11,0],[14,2],[3,8],[7,7],[10,9],[13,6]];
    blades.forEach(([bx,by]) => { c.fillRect(bx*S, by*S, S, 4*S); });
  } else if (tileId === 28) {
    // Road — packed earth with wheel ruts
    c.fillStyle = info.base;
    c.fillRect(0, 0, TS, TS);
    c.fillStyle = info.alt;
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        if (seededRand(px, py, 28) < 0.2) c.fillRect(px*S, py*S, S, S);
      }
    }
    c.fillStyle = "#7a6a4a";
    c.fillRect(4*S, 0, S, TS);
    c.fillRect(11*S, 0, S, TS);
  } else if (tileId === 29) {
    // Cliff — steep rock face
    c.fillStyle = info.base;
    c.fillRect(0, 0, TS, TS);
    c.fillStyle = info.face;
    c.fillRect(0, 0, TS, 8*S);
    c.fillStyle = info.alt;
    for (let i = 0; i < TILE; i += 3) {
      c.fillRect(0, i*S, TS, S);
    }
    c.fillStyle = "#4a3a2a";
    c.fillRect(0, 8*S, TS, 2*S);
  } else if (tileId === 30) {
    // Shallow water — lighter blue with ripples
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        c.fillStyle = (px + py) % 3 === 0 ? info.alt : info.base;
        c.fillRect(px*S, py*S, S, S);
      }
    }
  } else if (tileId === 31) {
    // Boulder on grass
    c.fillStyle = info.base;
    c.fillRect(0, 0, TS, TS);
    for (let py = 0; py < TILE; py++) {
      for (let px = 0; px < TILE; px++) {
        if (seededRand(px, py, 0) < 0.2) { c.fillStyle = info.alt; c.fillRect(px*S, py*S, S, S); }
      }
    }
    c.fillStyle = info.rock;
    c.fillRect(3*S, 4*S, 10*S, 8*S);
    c.fillRect(4*S, 3*S, 8*S, S);
    c.fillRect(5*S, 12*S, 6*S, S);
    c.fillStyle = info.rock2;
    c.fillRect(4*S, 5*S, 3*S, 3*S);
    c.fillStyle = "#8a8a8a";
    c.fillRect(8*S, 4*S, 3*S, 2*S);
  }

  return tc;
}

function getTileCanvas(tileId, TS, TILE, SCALE) {
  if (!tileCanvases[tileId]) {
    tileCanvases[tileId] = createTileCanvas(tileId, TS, TILE, SCALE);
  }
  return tileCanvases[tileId];
}
