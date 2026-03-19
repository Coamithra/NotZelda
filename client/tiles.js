// ---------------------------------------------------------------------------
// Tile rendering — all tiles are data-driven via server-sent recipes
// ---------------------------------------------------------------------------

// Tile registry — populated from server data on room enter
const customTiles = {};

// Recipe interpreter — renders a tile from its colors + layers
function runTileRecipe(c, TS, TILE, S, recipe) {
  const colors = recipe.colors || {};

  // Fill base color
  c.fillStyle = colors.base || "#888";
  c.fillRect(0, 0, TS, TS);

  // Draw rect layers
  const layers = recipe.layers || [];
  for (const [colorKey, x, y, w, h] of layers) {
    c.fillStyle = colors[colorKey] || colorKey;
    c.fillRect(x * S, y * S, w * S, h * S);
  }
}

// Pre-rendered tile cache
const tileCanvases = {};

function getTileCanvas(tileId, TS, TILE, SCALE) {
  if (!tileCanvases[tileId]) {
    const recipe = customTiles[tileId];
    if (recipe) {
      const tc = document.createElement("canvas");
      tc.width = TS;
      tc.height = TS;
      runTileRecipe(tc.getContext("2d"), TS, TILE, SCALE, recipe);
      tileCanvases[tileId] = tc;
    } else {
      // Fallback: magenta tile for unknown IDs
      const tc = document.createElement("canvas");
      tc.width = TS;
      tc.height = TS;
      const c = tc.getContext("2d");
      c.fillStyle = "#ff00ff";
      c.fillRect(0, 0, TS, TS);
      tileCanvases[tileId] = tc;
    }
  }
  return tileCanvases[tileId];
}
