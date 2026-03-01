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
  }

  return tc;
}

function getTileCanvas(tileId, TS, TILE, SCALE) {
  if (!tileCanvases[tileId]) {
    tileCanvases[tileId] = createTileCanvas(tileId, TS, TILE, SCALE);
  }
  return tileCanvases[tileId];
}
