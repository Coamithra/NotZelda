/* Rendering — all render* and update* functions for the game loop. */

const DANCE_FRAME_MS = 200;
const DYING_MONSTER_FRAME_MS = 150;
const ATTACK_FRAME_MS = 150;
const ATTACK_FRAMES = 2;
const ATTACK_GAP_MS = 90;  // vulnerability gap = 0.5 * sword active time (180ms)
const DYING_PLAYER_FRAME_MS = 200;

// Advance a frame-based animation: returns true if the frame advanced
function advanceFrame(obj, duration, now) {
  if (now >= obj.nextTime) {
    obj.frame++;
    obj.nextTime = now + duration;
    return true;
  }
  return false;
}

// Tile-to-screen: center of a tile
function tileCenterX(x) { return x * TS + TS / 2; }
function tileCenterY(y) { return y * TS + TS / 2; }

// Walkable set — populated from server tile data on room enter
const WALKABLE = new Set();
// Water tiles — tiles with "water": true, walkable only with Tide Medallion
const WATER_TILES = new Set();

// Water mist cache (renderer-internal, not part of G namespace)
let _mistStrength;
let _mistRoom;

function renderRoom() {
  if (!G.room.currentRoom) return;
  const tm = G.room.currentRoom.tilemap;
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      G.ui.ctx.drawImage(getTileCanvas(tm[r][c], TS, TILE, SCALE), c * TS, r * TS);
    }
  }
}

function renderRevealedTiles() {
  const reveal = G.room.revealTilemap;
  if (!reveal || !G.room.currentRoom) return;
  const tm = G.room.currentRoom.tilemap;

  // Collect lantern holders with positions
  const lights = [];
  if (G.player.playerFlags.has("has_lantern")) {
    lights.push({ x: G.player.displayX, y: G.player.displayY });
  }
  for (const name of G.room.lanternHolders) {
    if (name === G.player.myName) continue;
    const op = G.room.otherPlayers[name];
    if (op) lights.push({ x: op.displayX, y: op.displayY });
  }
  if (lights.length === 0) return;

  const radiusSq = LANTERN_RADIUS * LANTERN_RADIUS;
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      if (tm[r][c] === reveal[r][c]) continue; // no difference — skip
      // Check if this tile is within any lantern holder's radius
      const tcx = c + 0.5;
      const tcy = r + 0.5;
      let lit = false;
      for (const l of lights) {
        const lx = l.x + 0.5; // player center
        const ly = l.y + 0.5;
        const dx = tcx - lx;
        const dy = tcy - ly;
        if (dx * dx + dy * dy <= radiusSq) { lit = true; break; }
      }
      if (lit) {
        G.ui.ctx.drawImage(getTileCanvas(reveal[r][c], TS, TILE, SCALE), c * TS, r * TS);
      }
    }
  }
}

function renderBrightTiles() {
  if (!G.room.currentRoom) return;
  const tm = G.room.currentRoom.tilemap;
  const t = performance.now() / 1000;
  const ctx = G.ui.ctx;
  ctx.save();
  ctx.globalCompositeOperation = "lighter";
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const recipe = customTiles[tm[r][c]];
      if (!recipe || !recipe.bright) continue;
      const cx = tileCenterX(c);
      const cy = tileCenterY(r);
      // Organic flicker from two sine waves at different frequencies
      const flicker = 0.3 + 0.15 * Math.sin(t * 8.3 + c * 2.1) + 0.1 * Math.sin(t * 13.7 + r * 3.3);
      const radius = TS * 1.8 + TS * 0.4 * Math.sin(t * 5.1 + c + r);
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
      grad.addColorStop(0, `rgba(255, 170, 50, ${flicker * 0.35})`);
      grad.addColorStop(0.5, `rgba(200, 100, 20, ${flicker * 0.12})`);
      grad.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = grad;
      ctx.fillRect(cx - radius, cy - radius, radius * 2, radius * 2);
    }
  }
  ctx.restore();
}

function renderWaterMist() {
  if (!G.room.currentRoom || !G.room.currentRoom.tilemap || G.room.currentRoom.dungeon_type !== "d2") return;
  // Count water tiles: WA = 1 point, SH = 0.5 points, max 40 = full strength
  if (_mistStrength === undefined || _mistRoom !== G.room.currentRoom) {
    let score = 0;
    for (const row of G.room.currentRoom.tilemap) {
      for (const t of row) {
        if (t === "WA") score += 1;
        else if (t === "SH") score += 0.5;
      }
    }
    _mistStrength = Math.min(score / 40, 1.0);
    _mistRoom = G.room.currentRoom;
  }
  const s = _mistStrength;
  if (s <= 0) return;
  const t = performance.now() / 1000;
  const ctx = G.ui.ctx;
  ctx.save();
  // Drifting mist wisps — more wisps with more water, opacity stays constant
  const wispCount = Math.round(8 + 72 * s);
  for (let i = 0; i < wispCount; i++) {
    const speed = 0.3 + (i % 3) * 0.15;
    const baseX = ((i * 97 + t * speed * 40) % (CW + 120)) - 60;
    const baseY = (i * 67) % CH;
    const wobble = Math.sin(t * 0.8 + i * 1.7) * 20;
    const alpha = 0.04 + 0.03 * Math.sin(t * 1.2 + i * 2.3);
    const w = 100 + 40 * Math.sin(t * 0.5 + i);
    const h = 20 + 10 * Math.sin(t * 0.7 + i * 1.1);
    const grad = ctx.createRadialGradient(baseX, baseY + wobble, 0, baseX, baseY + wobble, w / 2);
    grad.addColorStop(0, `rgba(180, 210, 240, ${alpha})`);
    grad.addColorStop(0.6, `rgba(140, 180, 220, ${alpha * 0.5})`);
    grad.addColorStop(1, "rgba(100, 150, 200, 0)");
    ctx.fillStyle = grad;
    ctx.fillRect(baseX - w / 2, baseY + wobble - h, w, h * 2);
  }
  // Subtle overall blue tint
  const tintAlpha = 0.03 + 0.01 * Math.sin(t * 0.6);
  ctx.fillStyle = `rgba(100, 160, 220, ${tintAlpha})`;
  ctx.fillRect(0, 0, CW, CH);
  ctx.restore();
}

// --- Water-walk ripple effect ---
function renderWaterWalkEffect() {
  if (!G.room.currentRoom || !G.room.currentRoom.tilemap) return;
  const tm = G.room.currentRoom.tilemap;
  const ctx = G.ui.ctx;
  const t = performance.now() / 1000;

  // Collect all water-walking players in this room
  const walkers = [];
  if (G.player.playerFlags.has("has_tide_medallion")) {
    walkers.push({ x: G.player.displayX, y: G.player.displayY });
  }
  for (const op of Object.values(G.room.otherPlayers)) {
    if (G.room.medallionHolders.has(op.name)) {
      walkers.push({ x: op.displayX, y: op.displayY });
    }
  }
  if (walkers.length === 0) return;

  ctx.save();
  for (const w of walkers) {
    // Check if standing on a water tile (bottom-half hitbox, foot tile)
    const footTy = Math.floor(w.y + 0.75);
    const footTx = Math.floor(w.x + 0.5);
    if (footTy < 0 || footTy >= ROWS || footTx < 0 || footTx >= COLS) continue;
    if (!WATER_TILES.has(tm[footTy][footTx])) continue;

    // Draw expanding ripple rings at feet
    const cx = (w.x + 0.5) * TS;
    const cy = (w.y + 0.85) * TS;
    for (let ring = 0; ring < 3; ring++) {
      const phase = (t * 1.2 + ring * 0.33) % 1.0;
      const radius = (8 + phase * 18) * SCALE;
      const alpha = 0.35 * (1.0 - phase);
      ctx.beginPath();
      ctx.ellipse(cx, cy, radius, radius * 0.5, 0, 0, Math.PI * 2);
      ctx.strokeStyle = `rgba(140, 200, 255, ${alpha})`;
      ctx.lineWidth = 1.5 * SCALE;
      ctx.stroke();
    }
  }
  ctx.restore();
}

// --- Darkness / Fog-of-war ---
// Offscreen canvas used to composite the darkness overlay
let _darkCanvas = null;
let _darkCtx = null;

const LANTERN_RADIUS = 3.5;
const NO_LANTERN_RADIUS = 0.75;
const BRIGHT_TILE_RADIUS = 3.0;

function renderDarkness() {
  if (!G.room.dark) return;

  // Lazy-init offscreen canvas
  if (!_darkCanvas || _darkCanvas.width !== CW || _darkCanvas.height !== CH) {
    _darkCanvas = document.createElement("canvas");
    _darkCanvas.width = CW;
    _darkCanvas.height = CH;
    _darkCtx = _darkCanvas.getContext("2d");
  }

  const dCtx = _darkCtx;
  const ctx = G.ui.ctx;

  // Fill with darkness
  dCtx.globalCompositeOperation = "source-over";
  dCtx.fillStyle = "black";
  dCtx.fillRect(0, 0, CW, CH);

  // Punch light holes using destination-out
  dCtx.globalCompositeOperation = "destination-out";

  // Helper: punch a radial gradient circle
  function punchLight(cx, cy, radius) {
    const r = radius * TS;
    const grad = dCtx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0, "rgba(0,0,0,1)");
    grad.addColorStop(0.7, "rgba(0,0,0,0.8)");
    grad.addColorStop(1, "rgba(0,0,0,0)");
    dCtx.fillStyle = grad;
    dCtx.fillRect(cx - r, cy - r, r * 2, r * 2);
  }

  // Light flicker — subtle oscillation for atmosphere
  const now = performance.now() / 1000;
  const FLICKER_AMP = 0.12; // tiles of radius variation
  const playerFlicker = Math.sin(now * 2.3) * FLICKER_AMP + Math.sin(now * 5.7) * (FLICKER_AMP * 0.3);

  // Local player light
  const hasLantern = G.player.playerFlags.has("has_lantern");
  const playerRadius = (hasLantern ? LANTERN_RADIUS : NO_LANTERN_RADIUS) + playerFlicker;
  const px = G.player.displayX * TS + TS / 2;
  const py = G.player.displayY * TS + TS / 2;
  punchLight(px, py, playerRadius);

  // Other players with lanterns
  for (const name of G.room.lanternHolders) {
    if (name === G.player.myName) continue;
    const op = G.room.otherPlayers[name];
    if (op) {
      // Offset phase per player so lights don't flicker in sync
      const h = name.charCodeAt(0) * 0.7;
      const otherFlicker = Math.sin(now * 2.3 + h) * FLICKER_AMP + Math.sin(now * 5.7 + h) * (FLICKER_AMP * 0.3);
      punchLight(op.displayX * TS + TS / 2, op.displayY * TS + TS / 2, LANTERN_RADIUS + otherFlicker);
    }
  }

  // Static light sources (sconces, braziers, fireplaces)
  for (let i = 0; i < G.room.lightSources.length; i++) {
    const [col, row] = G.room.lightSources[i];
    // Each light source gets its own phase offset
    const torchFlicker = Math.sin(now * 3.1 + i * 2.0) * FLICKER_AMP + Math.sin(now * 7.3 + i * 1.3) * (FLICKER_AMP * 0.4);
    punchLight(col * TS + TS / 2, row * TS + TS / 2, BRIGHT_TILE_RADIUS + torchFlicker);
  }

  // Composite the darkness onto the main canvas
  // Support variable opacity — numeric dark value (e.g. 0.5) or default 0.93
  dCtx.globalCompositeOperation = "source-over"; // reset
  ctx.save();
  ctx.globalAlpha = typeof G.room.dark === "number" ? G.room.dark : 0.93;
  ctx.drawImage(_darkCanvas, 0, 0);
  ctx.restore();
}

function startDance(name) {
  G.room.dancingPlayers[name] = { frame: 0, nextTime: Date.now() };
  G.room.speechBubbles.push({
    from: name,
    text: "* dances *",
    expires: Date.now() + 3000,
  });
}

function stopDance(name) {
  delete G.room.dancingPlayers[name];
}

function updateDances() {
  const now = Date.now();
  for (const d of Object.values(G.room.dancingPlayers)) {
    advanceFrame(d, DANCE_FRAME_MS, now);
  }
}

function updateDyingMonsters() {
  const now = Date.now();
  G.room.dyingMonsters = G.room.dyingMonsters.filter(dm => {
    const isBoss = (dm.width || 1) > 1 || (dm.height || 1) > 1;
    advanceFrame(dm, isBoss ? 400 : DYING_MONSTER_FRAME_MS, now);
    // Death sprites have up to 4 frames; last frame lingers as a corpse (rendered by renderCorpses)
    const deathSprite = customDeathSprites[dm.kind];
    const maxFrames = deathSprite && deathSprite.frames ? deathSprite.frames.length : 3;
    return dm.frame < maxFrames;
  });
}

function updateProjectiles() {
  for (const p of G.fx.projectiles) {
    p.displayX += (p.x - p.displayX) * 0.4;
    p.displayY += (p.y - p.displayY) * 0.4;
    if (Math.abs(p.x - p.displayX) < 0.05) p.displayX = p.x;
    if (Math.abs(p.y - p.displayY) < 0.05) p.displayY = p.y;
  }
}

function updateAttackEffects() {
  const now = Date.now();
  G.fx.chargeTrails = G.fx.chargeTrails.filter(t => now - t.startTime < 400);
  G.fx.monsterAttackFlashes = G.fx.monsterAttackFlashes.filter(f => now - f.startTime < 200);
}

function renderProjectiles() {
  for (const p of G.fx.projectiles) {
    const px = tileCenterX(p.displayX);
    const py = tileCenterY(p.displayY);
    const r = 3 * SCALE;
    // Glow
    G.ui.ctx.globalAlpha = 0.3;
    G.ui.ctx.fillStyle = p.color;
    G.ui.ctx.beginPath();
    G.ui.ctx.arc(px, py, r * 2, 0, Math.PI * 2);
    G.ui.ctx.fill();
    // Core
    G.ui.ctx.globalAlpha = 1;
    G.ui.ctx.fillStyle = p.color;
    G.ui.ctx.beginPath();
    G.ui.ctx.arc(px, py, r, 0, Math.PI * 2);
    G.ui.ctx.fill();
  }
}

function _renderWarningCircle(x, y, range, aw, ah, progress, elapsed) {
  const pulse = 0.15 + 0.15 * Math.sin(elapsed / 80);
  G.ui.ctx.globalAlpha = pulse;
  G.ui.ctx.fillStyle = progress > 0.85 ? "#ff4400" : "#ff8800";
  for (let dy = -range; dy <= range + ah - 1; dy++) {
    for (let dx = -range; dx <= range + aw - 1; dx++) {
      const nearX = Math.max(0, Math.min(dx, aw - 1));
      const nearY = Math.max(0, Math.min(dy, ah - 1));
      if (Math.abs(dx - nearX) + Math.abs(dy - nearY) <= range) {
        const tx = x + dx, ty = y + dy;
        if (tx >= 0 && tx < COLS && ty >= 0 && ty < ROWS) {
          G.ui.ctx.fillRect(tx * TS, ty * TS, TS, TS);
        }
      }
    }
  }
  G.ui.ctx.globalAlpha = 1;
}

function renderAreaWarnings() {
  const now = performance.now();
  for (const m of G.room.monsters) {
    if (!m.action) continue;
    const a = m.action;
    if (a.type === "area_warmup") {
      const elapsed = now - a.startTime;
      const progress = a.effectiveDuration > 0 ? Math.min(elapsed / a.effectiveDuration, 1.0) : 1.0;
      _renderWarningCircle(a.x, a.y, a.range, a.areaWidth, a.areaHeight, progress, elapsed);
    } else if (a.type === "teleport_warmup" && a.damageRadius > 0 && a.targetX !== undefined) {
      const elapsed = now - a.startTime;
      const progress = a.effectiveDuration > 0 ? Math.min(elapsed / a.effectiveDuration, 1.0) : 1.0;
      _renderWarningCircle(a.targetX, a.targetY, a.damageRadius, 1, 1, progress, elapsed);
    }
  }
}

function renderChargePreps() {
  const now = performance.now();
  for (const m of G.room.monsters) {
    if (!m.action || m.action.type !== "charge_warmup") continue;
    const a = m.action;
    const age = now - a.startTime;
    const pulse = 0.25 + 0.15 * Math.sin(age / 80);
    G.ui.ctx.globalAlpha = pulse;
    G.ui.ctx.fillStyle = "#ff4422";
    for (const [tx, ty] of a.lane) {
      G.ui.ctx.fillRect(tx * TS + 1*SCALE, ty * TS + 1*SCALE, TS - 2*SCALE, TS - 2*SCALE);
    }
    G.ui.ctx.globalAlpha = 1;
  }
}

function renderChargeTrails() {
  const now = Date.now();
  for (const t of G.fx.chargeTrails) {
    const age = now - t.startTime;
    const alpha = Math.max(0, 0.5 - age / 800);
    G.ui.ctx.globalAlpha = alpha;
    G.ui.ctx.fillStyle = "#ffcc44";
    for (const [tx, ty] of t.path) {
      G.ui.ctx.fillRect(tx * TS + 2*SCALE, ty * TS + 2*SCALE, TS - 4*SCALE, TS - 4*SCALE);
    }
    G.ui.ctx.globalAlpha = 1;
  }
}

function renderMonsterAttackFlashes() {
  const now = Date.now();
  for (const f of G.fx.monsterAttackFlashes) {
    const age = now - f.startTime;
    const alpha = Math.max(0, 0.6 - age / 333);
    G.ui.ctx.globalAlpha = alpha;
    G.ui.ctx.fillStyle = "#ffffff";
    if (f.range != null) {
      // Area attack flash — render the same footprint-aware diamond as the warning
      const aw = f.width || 1, ah = f.height || 1;
      for (let dy = -f.range; dy <= f.range + ah - 1; dy++) {
        for (let dx = -f.range; dx <= f.range + aw - 1; dx++) {
          const nearX = Math.max(0, Math.min(dx, aw - 1));
          const nearY = Math.max(0, Math.min(dy, ah - 1));
          if (Math.abs(dx - nearX) + Math.abs(dy - nearY) <= f.range) {
            const tx = f.x + dx, ty = f.y + dy;
            if (tx >= 0 && tx < COLS && ty >= 0 && ty < ROWS) {
              G.ui.ctx.fillRect(tx * TS, ty * TS, TS, TS);
            }
          }
        }
      }
    } else {
      G.ui.ctx.fillRect(f.x * TS, f.y * TS, TS, TS);
    }
    G.ui.ctx.globalAlpha = 1;
  }
}

function updateDyingOtherPlayers() {
  const now = Date.now();
  for (const [name, dp] of Object.entries(G.room.dyingOtherPlayers)) {
    advanceFrame(dp, DYING_PLAYER_FRAME_MS, now);
    if (dp.frame > 5) {
      // If a tombstone exists for this player, keep the dying entry
      // (stops advancing but stays so tombstone can take over rendering)
      if (!G.room.tombstones[name]) {
        delete G.room.dyingOtherPlayers[name];
      }
    }
  }
}

function renderHeartPickups() {
  for (const h of G.room.heartPickups) {
    const bounceFrame = Math.floor(Date.now() / 400) % 2;
    drawHeartPickup(G.ui.ctx, h.x * TS, h.y * TS, bounceFrame, SCALE);
  }
}

const ITEM_PICKUP_DURATION = 2500;

function renderDungeonGroundItems() {
  for (const item of G.room.dungeonGroundItems) {
    if (item.item_type === "lantern" || item.item_type === "tide_medallion") {
      // Treasure items live inside a chest — draw closed chest
      drawGroundChest(G.ui.ctx, item.x * TS, item.y * TS, false, SCALE);
    } else {
      drawGroundItem(G.ui.ctx, item.x * TS, item.y * TS, item.item_type, SCALE);
    }
  }
  // Opened chests persist visually after pickup (client-local state)
  for (const ch of G.room.openedChests) {
    drawGroundChest(G.ui.ctx, ch.x * TS, ch.y * TS, true, SCALE);
  }
  // Ghost items: collected by this player, but others still need them
  for (const item of G.room.ghostItems) {
    G.ui.ctx.save();
    G.ui.ctx.globalAlpha = 0.35;
    G.ui.ctx.filter = "grayscale(1)";
    drawGroundItem(G.ui.ctx, item.x * TS, item.y * TS, item.item_type, SCALE);
    G.ui.ctx.filter = "none";
    G.ui.ctx.globalAlpha = 1;
    G.ui.ctx.restore();
  }
}

function updateItemPickups() {
  const now = Date.now();
  if (G.player.itemPickupActive && now - G.player.itemPickupActive.startTime >= ITEM_PICKUP_DURATION) {
    G.player.itemPickupActive = null;
  }
  for (const [name, eff] of Object.entries(G.player.itemPickupEffects)) {
    if (now - eff.startTime >= ITEM_PICKUP_DURATION) {
      delete G.player.itemPickupEffects[name];
    }
  }
}

function renderItemPickups() {
  const now = Date.now();
  if (G.player.itemPickupActive) {
    const pu = G.player.itemPickupActive;
    const progress = Math.min((now - pu.startTime) / ITEM_PICKUP_DURATION, 1.0);
    drawItemPickupOverlay(G.ui.ctx, pu.x * TS, pu.y * TS, pu.item_type, progress, SCALE);
  }
  for (const [name, eff] of Object.entries(G.player.itemPickupEffects)) {
    const progress = Math.min((now - eff.startTime) / ITEM_PICKUP_DURATION, 1.0);
    drawItemPickupOverlay(G.ui.ctx, eff.x * TS, eff.y * TS, eff.item_type, progress, SCALE);
  }
}

function renderDeathAnimation() {
  if (!G.player.dyingPlayerSelf) return;
  const elapsed = Date.now() - G.player.dyingPlayerSelf.startTime;
  const duration = 5000;

  // After death animation: hold black + "You died!" until server sends
  // waiting_for_revival (tombstone path) or room_enter (auto-respawn path).
  // No gap — client stays dark regardless of network timing.
  if (elapsed >= duration) {
    if (G.player.waitingForRevival) {
      renderRevivalWaiting();
    } else {
      G.ui.ctx.fillStyle = "rgba(0,0,0,1)";
      G.ui.ctx.fillRect(0, 0, CW, CH);
      G.ui.ctx.font = "bold 28px monospace";
      G.ui.ctx.fillStyle = "#cc3333";
      const txt = "You died!";
      G.ui.ctx.fillText(txt, CW / 2 - G.ui.ctx.measureText(txt).width / 2, CH / 2);
    }
    return;
  }

  const px = G.player.dyingPlayerSelf.x * TS;
  const py = G.player.dyingPlayerSelf.y * TS;

  if (elapsed < 2000) {
    // Spin phase — 2s with ease-in darkening so you can watch the spin
    const dirs = ["down", "left", "up", "right"];
    const spinDir = dirs[Math.floor(elapsed / 80) % 4];
    const t = elapsed / 2000;
    const easeIn = t * t;  // quadratic ease-in
    const playerAlpha = Math.max(0, 1 - easeIn);
    G.ui.ctx.globalAlpha = playerAlpha;
    drawPlayer(G.ui.ctx, px, py, spinDir, G.player.myColorIndex, 0, SCALE);
    G.ui.ctx.globalAlpha = 1;
    G.ui.ctx.fillStyle = `rgba(0,0,0,${easeIn * 0.7})`;
    G.ui.ctx.fillRect(0, 0, CW, CH);
  } else if (elapsed < 2500) {
    // Transition to full black
    const blackAlpha = 0.7 + 0.3 * ((elapsed - 2000) / 500);
    G.ui.ctx.fillStyle = `rgba(0,0,0,${blackAlpha})`;
    G.ui.ctx.fillRect(0, 0, CW, CH);
  } else {
    G.ui.ctx.fillStyle = "rgba(0,0,0,1)";
    G.ui.ctx.fillRect(0, 0, CW, CH);
  }

  if (elapsed > 1600) {
    const textAlpha = Math.min(1, (elapsed - 1600) / 500);
    G.ui.ctx.globalAlpha = textAlpha;
    G.ui.ctx.font = "bold 28px monospace";
    G.ui.ctx.fillStyle = "#cc3333";
    const txt = "You died!";
    const tw = G.ui.ctx.measureText(txt).width;
    G.ui.ctx.fillText(txt, CW/2 - tw/2, CH/2);
    G.ui.ctx.globalAlpha = 1;
  }
}

// Respawn button dimensions (canvas coordinates) — shared between render and input
const RESPAWN_BTN = {
  w: 160, h: 40,
  get x() { return CW / 2 - this.w / 2; },
  get y() { return CH / 2 + 80; },
};

function renderRevivalWaiting() {
  const ctx = G.ui.ctx;
  const now = Date.now();

  const waitStart = G.player._revivalWaitStart || (G.player._revivalWaitStart = now);
  const elapsed = now - waitStart;

  // Smoothstep: overlay fades from 1.0 (fully black, matching death screen)
  // down to 0.20 over 5 seconds so the dead player can watch the action
  const FADE_DURATION = 5000;
  const t = Math.min(elapsed / FADE_DURATION, 1.0);
  const smooth = t * t * (3 - 2 * t);
  const overlayAlpha = 1.0 - (1.0 - 0.20) * smooth;
  ctx.fillStyle = `rgba(0, 0, 0, ${overlayAlpha})`;
  ctx.fillRect(0, 0, CW, CH);

  // "You died!" fades out over first 1.5s, "Waiting for revival..." fades in
  const TEXT_CROSSFADE = 1500;
  const crossfade = Math.min(elapsed / TEXT_CROSSFADE, 1.0);

  if (crossfade < 1.0) {
    // "You died!" text fading out
    ctx.globalAlpha = 1.0 - crossfade;
    ctx.font = "bold 28px monospace";
    ctx.fillStyle = "#cc3333";
    const died = "You died!";
    ctx.fillText(died, CW / 2 - ctx.measureText(died).width / 2, CH / 2);
    ctx.globalAlpha = 1;
  }

  // "Waiting for revival..." fades in, then pulses
  const waitAlpha = crossfade < 1.0
    ? crossfade
    : 0.5 + 0.5 * Math.sin(now / 600);
  ctx.globalAlpha = waitAlpha;
  ctx.font = "bold 18px monospace";
  ctx.fillStyle = "#e0d0a0";
  const waitTxt = "Waiting for revival...";
  ctx.fillText(waitTxt, CW / 2 - ctx.measureText(waitTxt).width / 2, CH / 2 - 10);
  ctx.globalAlpha = 1;

  // Revival progress bar (when someone is channeling)
  if (G.player.revivalProgress) {
    const rp = G.player.revivalProgress;
    const progress = Math.min((now - rp.startTime) / rp.duration, 1.0);

    const barW = 200, barH = 16;
    const barX = CW / 2 - barW / 2;
    const barY = CH / 2 + 20;

    ctx.fillStyle = "#333";
    ctx.fillRect(barX, barY, barW, barH);

    const fillW = barW * progress;
    const grad = ctx.createLinearGradient(barX, barY, barX + barW, barY);
    grad.addColorStop(0, "#ffcc00");
    grad.addColorStop(1, "#ffe066");
    ctx.fillStyle = grad;
    ctx.fillRect(barX, barY, fillW, barH);

    ctx.strokeStyle = "#888";
    ctx.lineWidth = 1;
    ctx.strokeRect(barX, barY, barW, barH);

    ctx.font = "14px monospace";
    ctx.fillStyle = "#ccc";
    const revTxt = `Being revived by ${rp.reviverName}...`;
    ctx.fillText(revTxt, CW / 2 - ctx.measureText(revTxt).width / 2, barY + barH + 20);
  }

  // "Watching: PlayerName" label when spectating another room
  if (G.player.spectateData) {
    ctx.font = "12px monospace";
    ctx.fillStyle = "rgba(200, 200, 200, 0.7)";
    const watchTxt = `Watching: ${G.player.spectateData.target_name}`;
    ctx.fillText(watchTxt, CW / 2 - ctx.measureText(watchTxt).width / 2, CH / 2 - 35);
  }

  // Respawn button — fade in with the waiting text
  const btnAlpha = Math.min(crossfade, 1.0);
  ctx.globalAlpha = btnAlpha;
  const btn = RESPAWN_BTN;
  const hover = G.player._respawnBtnHover;
  ctx.fillStyle = hover ? "#554433" : "#3a2a1a";
  ctx.strokeStyle = "#aa8855";
  ctx.lineWidth = 2;
  _roundRect(ctx, btn.x, btn.y, btn.w, btn.h, 6);
  ctx.fill();
  ctx.stroke();

  ctx.font = "bold 16px monospace";
  ctx.fillStyle = hover ? "#ffe0a0" : "#ccaa77";
  const btnTxt = "Respawn";
  ctx.fillText(btnTxt, CW / 2 - ctx.measureText(btnTxt).width / 2, btn.y + 26);
  ctx.globalAlpha = 1;
}

function _roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

const SPIRIT_JAR_ANIM_DURATION = 2500; // ms — spirit jar revival overlay

function renderSpiritJarRevive() {
  const sj = G.player.spiritJarRevive;
  if (!sj) return;
  const ctx = G.ui.ctx;
  const elapsed = Date.now() - sj.startTime;
  const t = Math.min(elapsed / SPIRIT_JAR_ANIM_DURATION, 1.0);

  if (t >= 1.0) {
    G.player.spiritJarRevive = null;
    return;
  }

  // Phase 1 (0-40%): black screen, jar fades in rising from center
  // Phase 2 (40-70%): jar visible, glow pulses, text appears
  // Phase 3 (70-100%): everything fades out, revealing the room

  // Overlay opacity: fully black → transparent
  let overlayAlpha;
  if (t < 0.4) {
    overlayAlpha = 1.0;
  } else {
    overlayAlpha = 1.0 - ((t - 0.4) / 0.6);
  }
  ctx.fillStyle = `rgba(0, 0, 0, ${overlayAlpha})`;
  ctx.fillRect(0, 0, CW, CH);

  // Jar sprite — fades in and rises
  const jarAlpha = t < 0.1 ? t / 0.1 : (t > 0.7 ? 1.0 - (t - 0.7) / 0.3 : 1.0);
  const riseY = (1.0 - t) * 20 * SCALE;
  const jarX = CW / 2 - 4 * SCALE;
  const jarY = CH / 2 - 5 * SCALE + riseY;

  // Ghostly glow behind jar
  if (jarAlpha > 0) {
    const glowT = elapsed / 1000;
    const glowR = (30 + 10 * Math.sin(glowT * 4)) * SCALE;
    ctx.globalAlpha = jarAlpha * 0.4;
    const grad = ctx.createRadialGradient(
      CW / 2, jarY + 5 * SCALE, 0,
      CW / 2, jarY + 5 * SCALE, glowR
    );
    grad.addColorStop(0, "rgba(102, 255, 170, 0.6)");
    grad.addColorStop(0.5, "rgba(102, 255, 170, 0.2)");
    grad.addColorStop(1, "rgba(102, 255, 170, 0)");
    ctx.fillStyle = grad;
    ctx.fillRect(CW / 2 - glowR, jarY + 5 * SCALE - glowR, glowR * 2, glowR * 2);
    ctx.globalAlpha = 1;

    // Draw jar sprite
    ctx.globalAlpha = jarAlpha;
    drawItemSpiritJar(ctx, jarX, jarY, SCALE);
    ctx.globalAlpha = 1;
  }

  // Ghostly particles rising from jar
  if (t > 0.15 && t < 0.85) {
    const partAlpha = jarAlpha * 0.7;
    ctx.globalAlpha = partAlpha;
    const partCount = 6;
    for (let i = 0; i < partCount; i++) {
      const seed = i * 137.5;
      const px = CW / 2 + Math.sin(seed + elapsed / 300) * 15 * SCALE;
      const py = jarY - (elapsed / 8 + seed * 2) % (40 * SCALE);
      const size = (1 + Math.sin(seed)) * SCALE;
      ctx.fillStyle = i % 2 === 0 ? "#aaffcc" : "#66ffaa";
      ctx.fillRect(px, py, size, size);
    }
    ctx.globalAlpha = 1;
  }

  // Text: "Spirit Jar!" — fades in at 25%, out at 75%
  const textAlpha = t < 0.25 ? 0 : (t < 0.4 ? (t - 0.25) / 0.15 : (t > 0.75 ? 1.0 - (t - 0.75) / 0.25 : 1.0));
  if (textAlpha > 0) {
    ctx.globalAlpha = textAlpha;
    ctx.font = "bold 24px monospace";
    ctx.fillStyle = "#aaffcc";
    const txt = "Spirit Jar!";
    const tw = ctx.measureText(txt).width;
    ctx.fillText(txt, CW / 2 - tw / 2, CH / 2 + 50 * SCALE);
    ctx.globalAlpha = 1;
  }
}

function renderTombstones() {
  const ctx = G.ui.ctx;
  const now = Date.now();
  for (const [name, ts] of Object.entries(G.room.tombstones)) {
    const px = ts.x * TS;
    const py = ts.y * TS;

    // Draw tombstone sprite
    drawTombstone(ctx, px, py, SCALE);

    // Player name label below
    ctx.font = "bold 10px monospace";
    ctx.fillStyle = "#999";
    const tw = ctx.measureText(name).width;
    ctx.fillText(name, px + TS / 2 - tw / 2, py + TS + 12);

    // Revival progress ring (for the reviver looking at it)
    if (G.room.activeRevival && G.room.activeRevival.targetName === name) {
      const ar = G.room.activeRevival;
      const progress = Math.min((now - ar.startTime) / ar.duration, 1.0);
      const cx = px + TS / 2;
      const cy = py + TS / 2;
      const radius = TS * 0.6;

      // Background ring
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, Math.PI * 2);
      ctx.strokeStyle = "rgba(100, 80, 40, 0.4)";
      ctx.lineWidth = 3;
      ctx.stroke();

      // Progress arc
      ctx.beginPath();
      ctx.arc(cx, cy, radius, -Math.PI / 2, -Math.PI / 2 + progress * Math.PI * 2);
      ctx.strokeStyle = "#ffcc00";
      ctx.lineWidth = 3;
      ctx.stroke();
    }
  }
}

function renderReviverGlow() {
  if (!G.room.activeRevival || !G.player.myPlayer) return;
  const ctx = G.ui.ctx;
  const now = performance.now() / 1000;
  const pulse = 0.3 + 0.15 * Math.sin(now * 4);
  const cx = G.player.displayX * TS + TS / 2;
  const cy = G.player.displayY * TS + TS / 2;
  const radius = TS * 0.8;
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
  grad.addColorStop(0, `rgba(255, 200, 50, ${pulse})`);
  grad.addColorStop(0.6, `rgba(255, 180, 30, ${pulse * 0.3})`);
  grad.addColorStop(1, "rgba(0, 0, 0, 0)");
  ctx.fillStyle = grad;
  ctx.fillRect(cx - radius, cy - radius, radius * 2, radius * 2);
}

function startAttack(name, direction) {
  stopDance(name);
  G.room.attackingPlayers[name] = { direction, frame: 0, nextTime: Date.now() + ATTACK_FRAME_MS };
}

function updateAttacks() {
  const now = Date.now();
  for (const [name, a] of Object.entries(G.room.attackingPlayers)) {
    if (advanceFrame(a, ATTACK_FRAME_MS, now) && a.frame >= ATTACK_FRAMES) {
      delete G.room.attackingPlayers[name];
    }
  }
}

function renderPlayers() {
  if (!G.player.myPlayer) return;

  const all = [];
  if (!G.player.dyingPlayerSelf) {
    let skipSelf = false;
    if (Date.now() < G.player.invincibleUntil) {
      skipSelf = Math.floor(Date.now() / 100) % 2 === 1;
    }
    if (!skipSelf) {
      all.push({
        name: G.player.myName,
        x: G.player.displayX,
        y: G.player.displayY,
        direction: G.player.myPlayer.direction,
        color_index: G.player.myPlayer.color_index,
        hurtFlash: Date.now() < G.player.hurtFlash,
      });
    }
  }
  for (const [name, p] of Object.entries(G.room.otherPlayers)) {
    all.push({
      name: name,
      x: p.displayX,
      y: p.displayY,
      direction: p.direction,
      color_index: p.color_index,
      hurtFlash: p.hurtFlash && Date.now() < p.hurtFlash,
    });
  }

  for (const g of G.room.guards) {
    all.push({ name: g.name, x: g.x, y: g.y, isGuard: true, sprite: g.sprite || "guard" });
  }

  for (const m of G.room.monsters) {
    // Derive teleportAlpha and chargePrep from unified action for rendering
    const isTpWarmup = m.action && m.action.type === "teleport_warmup";
    const tpAlpha = isTpWarmup
      ? Math.max(0, 1 - Math.min((performance.now() - m.action.startTime) / m.action.effectiveDuration, 1.0))
      : undefined;
    const cpPrep = (m.action && m.action.type === "charge_warmup") ? m.action.startTime : null;
    all.push({ x: m.displayX, y: m.displayY, isMonster: true, kind: m.kind, hitFlash: m.hitFlash, teleportAlpha: tpAlpha, chargePrep: cpPrep, width: m.width || 1, height: m.height || 1, walkHop: m.walkHop, spawnTime: m.spawnTime });
  }

  all.sort((a, b) => a.y - b.y);

  for (const dm of G.room.dyingMonsters) {
    const dx = dm.x * TS, dy = dm.y * TS;
    const dmScale = SCALE * Math.max(dm.width || 1, dm.height || 1);
    drawMonsterDeath(G.ui.ctx, dx, dy, dm.kind, dm.frame, dmScale);
  }

  for (const p of all) {
    const px = p.x * TS;
    const py = p.y * TS;
    if (p.isMonster) {
      const mw = p.width || 1;
      const mh = p.height || 1;
      const mScale = SCALE * Math.max(mw, mh);
      let shakeX = 0;
      if (p.chargePrep) {
        shakeX = Math.round(Math.sin(Date.now() / 30) * 2) * SCALE;
      }
      if (p.teleportAlpha !== undefined && p.teleportAlpha < 1) {
        G.ui.ctx.globalAlpha = Math.max(0, p.teleportAlpha);
      }
      // Spawn pop scale effect
      const popScale = getSpawnPopScale(p.spawnTime);
      if (popScale !== 1) {
        const centerX = px + mw * TS / 2;
        const centerY = py + mh * TS / 2;
        G.ui.ctx.save();
        G.ui.ctx.translate(centerX, centerY);
        G.ui.ctx.scale(popScale, popScale);
        G.ui.ctx.translate(-centerX, -centerY);
      }
      const hopFrame = p.walkHop !== undefined ? p.walkHop : G.room.monsterHopFrame;
      drawMonsterSprite(G.ui.ctx, px + shakeX, py, p.kind, hopFrame, mScale);
      if (popScale !== 1) G.ui.ctx.restore();
      G.ui.ctx.globalAlpha = 1;
      if (p.hitFlash && Date.now() < p.hitFlash) {
        G.ui.ctx.globalAlpha = 0.5;
        G.ui.ctx.fillStyle = "#ffffff";
        G.ui.ctx.fillRect(px, py, TS * mw, TS * mh);
        G.ui.ctx.globalAlpha = 1;
      }
      continue;
    } else if (p.isGuard) {
      drawNPC(G.ui.ctx, px, py, p.sprite, SCALE);
    } else if ((p.name === G.player.myName && G.player.itemPickupActive) || G.player.itemPickupEffects[p.name]) {
      drawPlayerHoldItem(G.ui.ctx, px, py, p.color_index, SCALE);
    } else if (G.room.attackingPlayers[p.name]) {
      const atk = G.room.attackingPlayers[p.name];
      drawPlayerAttack(G.ui.ctx, px, py, atk.direction, p.color_index, atk.frame, SCALE);
      drawSwordAttack(G.ui.ctx, px, py, atk.direction, atk.frame, SCALE);
    } else if (G.room.dancingPlayers[p.name]) {
      drawPlayerDance(G.ui.ctx, px, py, p.color_index, G.room.dancingPlayers[p.name].frame, SCALE);
    } else {
      const moving = (p.name === G.player.myName) ? G.player.isMoving : (G.room.otherPlayers[p.name]?.moving || false);
      drawPlayer(G.ui.ctx, px, py, p.direction, p.color_index, moving ? G.player.animFrame : 0, SCALE);
    }

    if (p.hurtFlash) {
      G.ui.ctx.globalAlpha = 0.4;
      G.ui.ctx.fillStyle = "#ff0000";
      G.ui.ctx.fillRect(px + 3*SCALE, py, 10*SCALE, 15*SCALE);
      G.ui.ctx.globalAlpha = 1;
    }

    G.ui.ctx.font = "bold 11px monospace";
    const tw = G.ui.ctx.measureText(p.name).width;
    const labelX = px + TS / 2 - tw / 2;
    const labelY = py - 6;
    G.ui.ctx.fillStyle = "rgba(0,0,0,0.6)";
    G.ui.ctx.fillRect(labelX - 3, labelY - 10, tw + 6, 14);
    G.ui.ctx.fillStyle = "#fff";
    G.ui.ctx.fillText(p.name, labelX, labelY);
  }

  for (const [name, dp] of Object.entries(G.room.dyingOtherPlayers)) {
    const dpx = dp.x * TS;
    const dpy = dp.y * TS;
    drawPlayerFallOver(G.ui.ctx, dpx, dpy, dp.color_index, dp.frame, SCALE);
  }
}

function renderSpeechBubbles() {
  const now = Date.now();
  G.room.speechBubbles = G.room.speechBubbles.filter(b => now < b.expires);

  for (const bubble of G.room.speechBubbles) {
    let px, py;
    if (bubble.from === G.player.myName) {
      px = tileCenterX(G.player.displayX);
      py = G.player.displayY * TS - 16;
    } else if (G.room.otherPlayers[bubble.from]) {
      const p = G.room.otherPlayers[bubble.from];
      px = tileCenterX(p.displayX);
      py = p.displayY * TS - 16;
    } else {
      const guard = G.room.guards.find(g => g.name === bubble.from);
      if (guard) {
        px = tileCenterX(guard.x);
        py = guard.y * TS - 16;
      } else {
        continue;
      }
    }

    const timeLeft = bubble.expires - now;
    const alpha = timeLeft < 500 ? timeLeft / 500 : 1;
    G.ui.ctx.globalAlpha = alpha;

    G.ui.ctx.font = "11px monospace";
    const maxWidth = 200;
    const maxLines = 3;
    const words = bubble.text.split(" ");
    const lines = [];
    let line = "";
    for (const word of words) {
      const test = line ? line + " " + word : word;
      if (G.ui.ctx.measureText(test).width > maxWidth) {
        if (line) lines.push(line);
        line = word;
      } else {
        line = test;
      }
    }
    if (line) lines.push(line);
    if (lines.length > maxLines) {
      lines.length = maxLines;
      const last = lines[maxLines - 1];
      if (G.ui.ctx.measureText(last + "...").width > maxWidth) {
        // Trim words until "..." fits
        const words2 = last.split(" ");
        while (words2.length > 1 && G.ui.ctx.measureText(words2.join(" ") + "...").width > maxWidth) words2.pop();
        lines[maxLines - 1] = words2.join(" ") + "...";
      } else {
        lines[maxLines - 1] = last + "...";
      }
    }

    const lineHeight = 14;
    const pad = 6;
    const bw = Math.min(maxWidth, Math.max(...lines.map(l => G.ui.ctx.measureText(l).width))) + pad * 2;
    const bh = lines.length * lineHeight + pad * 2;
    const bx = px - bw / 2;
    const by = py - bh - 8;

    G.ui.ctx.fillStyle = "rgba(255,255,255,0.95)";
    G.ui.ctx.beginPath();
    roundRect(G.ui.ctx, bx, by, bw, bh, 6);
    G.ui.ctx.fill();

    G.ui.ctx.beginPath();
    G.ui.ctx.moveTo(px - 5, by + bh);
    G.ui.ctx.lineTo(px, by + bh + 6);
    G.ui.ctx.lineTo(px + 5, by + bh);
    G.ui.ctx.fill();

    G.ui.ctx.strokeStyle = "rgba(0,0,0,0.2)";
    G.ui.ctx.lineWidth = 1;
    G.ui.ctx.beginPath();
    roundRect(G.ui.ctx, bx, by, bw, bh, 6);
    G.ui.ctx.stroke();

    G.ui.ctx.fillStyle = "#111";
    for (let i = 0; i < lines.length; i++) {
      G.ui.ctx.fillText(lines[i], bx + pad, by + pad + 10 + i * lineHeight);
    }

    G.ui.ctx.globalAlpha = 1;
  }
}

function renderNpcListening() {
  if (G.player.waitingForRevival || G.player.itemPickupActive) return;
  const now = Date.now();
  const bob = Math.sin(now / 750) * 2;
  const alpha = 0.65 + 0.15 * Math.sin(now / 900);

  for (const guard of G.room.guards) {
    const dx = Math.abs(G.player.displayX - guard.x);
    const dy = Math.abs(G.player.displayY - guard.y);
    if (dx + dy > 2.25) continue;

    if (G.room.speechBubbles.some(b => b.from === guard.name)) continue;
    if (G.room.npcThinking[guard.name]) continue;

    const px = tileCenterX(guard.x);
    const py = guard.y * TS - 16;

    const iw = 14, ih = 11;
    const ix = px - iw / 2;
    const iy = py - ih - 10 + bob;

    G.ui.ctx.globalAlpha = alpha;

    // Bubble body
    G.ui.ctx.fillStyle = "rgba(255,255,255,0.95)";
    G.ui.ctx.beginPath();
    roundRect(G.ui.ctx, ix, iy, iw, ih, 3);
    G.ui.ctx.fill();

    // Tail
    G.ui.ctx.beginPath();
    G.ui.ctx.moveTo(px - 2, iy + ih);
    G.ui.ctx.lineTo(px, iy + ih + 3);
    G.ui.ctx.lineTo(px + 2, iy + ih);
    G.ui.ctx.fill();

    // Border
    G.ui.ctx.strokeStyle = "rgba(0,0,0,0.25)";
    G.ui.ctx.lineWidth = 1;
    G.ui.ctx.beginPath();
    roundRect(G.ui.ctx, ix, iy, iw, ih, 3);
    G.ui.ctx.stroke();

    // Three dots
    G.ui.ctx.fillStyle = "rgba(100,100,100,0.8)";
    const dotR = 1.5;
    const dotY = iy + ih / 2;
    for (let d = -1; d <= 1; d++) {
      G.ui.ctx.beginPath();
      G.ui.ctx.arc(px + d * 4, dotY, dotR, 0, Math.PI * 2);
      G.ui.ctx.fill();
    }

    G.ui.ctx.globalAlpha = 1;
  }
}

function renderNpcThinking() {
  const now = Date.now();
  for (const [name, startTime] of Object.entries(G.room.npcThinking)) {
    // Timeout after 60s in case server never clears it
    if (now - startTime > 60000) { delete G.room.npcThinking[name]; continue; }
    // Don't show thinking bubble if there's already a speech bubble from this NPC
    if (G.room.speechBubbles.some(b => b.from === name)) continue;

    const guard = G.room.guards.find(g => g.name === name);
    if (!guard) continue;

    const px = tileCenterX(guard.x);
    const py = guard.y * TS - 16;

    // Animate dots: cycle through ".", "..", "..." every 500ms
    const dotCount = (Math.floor((now - startTime) / 500) % 3) + 1;
    const text = ".".repeat(dotCount);

    G.ui.ctx.font = "bold 13px monospace";
    const pad = 6;
    const bw = G.ui.ctx.measureText("...").width + pad * 2;
    const bh = 14 + pad * 2;
    const bx = px - bw / 2;
    const by = py - bh - 8;

    // Bubble background
    G.ui.ctx.fillStyle = "rgba(255,255,255,0.9)";
    G.ui.ctx.beginPath();
    roundRect(G.ui.ctx, bx, by, bw, bh, 6);
    G.ui.ctx.fill();

    // Tail
    G.ui.ctx.beginPath();
    G.ui.ctx.moveTo(px - 5, by + bh);
    G.ui.ctx.lineTo(px, by + bh + 6);
    G.ui.ctx.lineTo(px + 5, by + bh);
    G.ui.ctx.fill();

    // Border
    G.ui.ctx.strokeStyle = "rgba(0,0,0,0.2)";
    G.ui.ctx.lineWidth = 1;
    G.ui.ctx.beginPath();
    roundRect(G.ui.ctx, bx, by, bw, bh, 6);
    G.ui.ctx.stroke();

    // Dots
    G.ui.ctx.fillStyle = "#666";
    G.ui.ctx.fillText(text, bx + pad, by + pad + 11);
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
}

function renderUI() {
  if (!G.room.currentRoom) return;

  G.ui.ctx.font = "bold 13px monospace";
  const name = G.room.currentRoom.name;
  const tw = G.ui.ctx.measureText(name).width;
  G.ui.ctx.fillStyle = "rgba(0,0,0,0.6)";
  G.ui.ctx.fillRect(8, 8, tw + 16, 22);
  G.ui.ctx.fillStyle = "#e6b422";
  G.ui.ctx.fillText(name, 16, 24);

  const version = "v0.6";
  G.ui.ctx.font = "10px monospace";
  const vw = G.ui.ctx.measureText(version).width;
  G.ui.ctx.fillStyle = "rgba(255,255,255,0.3)";
  G.ui.ctx.fillText(version, CW - vw - 10, 20);

  const now = Date.now();
  G.ui.infoMessages = G.ui.infoMessages.filter(m => now < m.expires);
  G.ui.ctx.font = "12px monospace";
  for (let i = 0; i < G.ui.infoMessages.length; i++) {
    const msg = G.ui.infoMessages[i];
    const alpha = Math.min(1, (msg.expires - now) / 1000);
    G.ui.ctx.globalAlpha = alpha;
    G.ui.ctx.fillStyle = "rgba(0,0,0,0.7)";
    const mw = G.ui.ctx.measureText(msg.text).width;
    G.ui.ctx.fillRect(CW/2 - mw/2 - 8, CH - 60 - i*20, mw + 16, 18);
    G.ui.ctx.fillStyle = "#79c0ff";
    G.ui.ctx.fillText(msg.text, CW/2 - mw/2, CH - 47 - i*20);
    G.ui.ctx.globalAlpha = 1;
  }

}

function renderCollisionDebug() {
  if (!G.debug.debugCollision) return;
  const ctx = G.ui.ctx;

  // Draw player AABB (bottom-half hitbox: y+0.5 to y+1)
  if (G.player.myPlayer) {
    ctx.strokeStyle = "lime";
    ctx.lineWidth = 2;
    ctx.strokeRect(G.player.myPlayer.x * TS, (G.player.myPlayer.y + 0.5) * TS, TS, 0.5 * TS);
    // Full tile outline (dimmer)
    ctx.strokeStyle = "rgba(0,255,0,0.3)";
    ctx.strokeRect(G.player.myPlayer.x * TS, G.player.myPlayer.y * TS, TS, TS);
  }

  // Draw monster AABBs
  ctx.strokeStyle = "red";
  ctx.lineWidth = 2;
  for (const m of G.room.monsters) {
    const w = m.width || 1;
    const h = m.height || 1;
    ctx.strokeRect(m.displayX * TS, m.displayY * TS, w * TS, h * TS);
  }

  // Draw hit ghosts (fade out over 5 seconds)
  const now = Date.now();
  G.debug.debugGhosts = G.debug.debugGhosts.filter(g => now - g.time < 5000);
  for (const g of G.debug.debugGhosts) {
    const alpha = 1 - (now - g.time) / 5000;
    // Player ghost box (pre-knockback)
    ctx.strokeStyle = `rgba(0,255,255,${alpha})`;
    ctx.lineWidth = 2;
    ctx.strokeRect(g.playerX * TS, g.playerY * TS, TS, TS);
    // Source AABB (current monster pos at hit time)
    ctx.strokeStyle = `rgba(255,0,0,${alpha})`;
    ctx.lineWidth = 2;
    ctx.strokeRect(g.sourceX * TS, g.sourceY * TS, g.sourceW * TS, g.sourceH * TS);
    // Previous source AABB (where monster was before — used for knockback calc)
    if (g.prevSourceX != null && (g.prevSourceX !== g.sourceX || g.prevSourceY !== g.sourceY)) {
      ctx.strokeStyle = `rgba(255,0,0,${alpha * 0.5})`;
      ctx.setLineDash([4, 4]);
      ctx.strokeRect(g.prevSourceX * TS, g.prevSourceY * TS, g.sourceW * TS, g.sourceH * TS);
      ctx.setLineDash([]);
    }
    // Knockback destination
    ctx.strokeStyle = `rgba(255,255,0,${alpha})`;
    ctx.setLineDash([4, 4]);
    ctx.strokeRect(g.knockX * TS, g.knockY * TS, TS, TS);
    ctx.setLineDash([]);
    // Arrow from prev source to prev player (the delta knockback is based on)
    const psx = g.prevSourceX != null ? g.prevSourceX : g.sourceX;
    const psy = g.prevSourceY != null ? g.prevSourceY : g.sourceY;
    const ppx = g.prevPlayerX != null ? g.prevPlayerX : g.playerX;
    const ppy = g.prevPlayerY != null ? g.prevPlayerY : g.playerY;
    const fromX = tileCenterX(psx);
    const fromY = tileCenterY(psy);
    const toX = tileCenterX(ppx);
    const toY = tileCenterY(ppy);
    ctx.strokeStyle = `rgba(255,128,0,${alpha})`;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(fromX, fromY);
    ctx.lineTo(toX, toY);
    ctx.stroke();
    // Arrowhead
    const angle = Math.atan2(toY - fromY, toX - fromX);
    ctx.beginPath();
    ctx.moveTo(toX, toY);
    ctx.lineTo(toX - 10 * Math.cos(angle - 0.4), toY - 10 * Math.sin(angle - 0.4));
    ctx.lineTo(toX - 10 * Math.cos(angle + 0.4), toY - 10 * Math.sin(angle + 0.4));
    ctx.closePath();
    ctx.fillStyle = `rgba(255,128,0,${alpha})`;
    ctx.fill();
  }
}

function renderServerDebug() {
  if (!G.debug.viewServer || !G.debug.serverState) return;
  const ctx = G.ui.ctx;
  const s = G.debug.serverState;
  ctx.globalAlpha = 0.45;

  // Players — full tile (faint red) + collision box (bright red)
  for (const p of s.players) {
    ctx.fillStyle = "#ff0000";
    ctx.globalAlpha = 0.2;
    ctx.fillRect(p.x * TS, p.y * TS, TS, TS);
    const cm = p.cm || 0;
    ctx.globalAlpha = 0.45;
    ctx.fillRect((p.x + cm) * TS, (p.y + cm) * TS, (1 - cm * 2) * TS, (1 - cm * 2) * TS);
  }
  ctx.globalAlpha = 0.45;

  // Monsters — red (darker for dead)
  for (const m of s.monsters) {
    ctx.fillStyle = m.alive ? "#ff0000" : "#660000";
    ctx.fillRect(m.x * TS, m.y * TS, (m.w || 1) * TS, (m.h || 1) * TS);
  }

  // Projectiles — orange
  ctx.fillStyle = "#ff6600";
  for (const p of s.projectiles) {
    ctx.fillRect(p.x * TS + TS * 0.25, p.y * TS + TS * 0.25, TS * 0.5, TS * 0.5);
  }

  // Hearts — pink
  ctx.fillStyle = "#ff66aa";
  for (const h of s.hearts) {
    ctx.fillRect(h.x * TS + TS * 0.2, h.y * TS + TS * 0.2, TS * 0.6, TS * 0.6);
  }

  // Ground items — yellow
  ctx.fillStyle = "#ffcc00";
  for (const it of s.items) {
    ctx.fillRect(it.x * TS + TS * 0.15, it.y * TS + TS * 0.15, TS * 0.7, TS * 0.7);
  }

  // Active sword hitboxes — cyan
  ctx.fillStyle = "#00ffff";
  for (const sw of (s.swords || [])) {
    ctx.fillRect(sw.x * TS, sw.y * TS, sw.w * TS, sw.h * TS);
  }

  ctx.globalAlpha = 1;

  // Labels (fully opaque, small text)
  ctx.font = "10px monospace";
  ctx.fillStyle = "#ff4444";
  for (const p of s.players) {
    ctx.fillText(p.name, p.x * TS + 2, p.y * TS - 2);
  }
  for (const m of s.monsters) {
    if (m.alive) ctx.fillText(m.kind, m.x * TS + 2, m.y * TS - 2);
  }
}

function renderHeartsHUD() {
  const heartScale = SCALE * 0.45;
  const heartW = 12 * heartScale + 2;
  const heartH = 11 * heartScale + 2;
  const totalHearts = Math.ceil(G.player.myMaxHp / 2);
  const maxPerRow = 10;
  const rows = Math.ceil(totalHearts / maxPerRow);
  for (let i = 0; i < totalHearts; i++) {
    const row = Math.floor(i / maxPerRow);
    const col = i % maxPerRow;
    const heartsInRow = Math.min(maxPerRow, totalHearts - row * maxPerRow);
    const x = CW - heartsInRow * heartW - 14 + col * heartW;
    const y = 8 + row * heartH;
    const hpForHeart = G.player.myHp - i * 2;
    let state = "empty";
    if (hpForHeart >= 2) state = "full";
    else if (hpForHeart === 1) state = "half";
    drawHeart(G.ui.ctx, x, y, state, heartScale);
  }
}

function renderKeyHUD() {
  if (!G.room.dungeonState || G.player.keyCount <= 0) return;
  const ctx = G.ui.ctx;
  const x = 8, y = 34;
  // Background
  ctx.fillStyle = "rgba(0,0,0,0.55)";
  ctx.fillRect(x, y, 52, 20);
  // Tiny key icon
  const ks = SCALE * 0.2;
  ctx.fillStyle = "#d4a830";
  ctx.fillRect(x+4+2*ks, y+4, 4*ks, ks);
  ctx.fillRect(x+4+ks, y+4+ks, 6*ks, ks);
  ctx.fillRect(x+4+ks, y+4+2*ks, 2*ks, ks);
  ctx.fillRect(x+4+5*ks, y+4+2*ks, 2*ks, ks);
  ctx.fillRect(x+4+ks, y+4+3*ks, 6*ks, ks);
  ctx.fillRect(x+4+3*ks, y+4+4*ks, 2*ks, 4*ks);
  ctx.fillRect(x+4+5*ks, y+4+6*ks, 2*ks, ks);
  // Count text
  ctx.font = "bold 12px monospace";
  ctx.fillStyle = "#e6b422";
  ctx.fillText("x" + G.player.keyCount, x + 26, y + 15);
}

function renderSpiritJarHUD() {
  const count = G.player.spiritJarCount || 0;
  if (count <= 0) return;
  const ctx = G.ui.ctx;
  // Position below key HUD (or at y=34 if no keys shown)
  const hasKeys = G.room.dungeonState && G.player.keyCount > 0;
  const x = 8, y = hasKeys ? 58 : 34;
  // Background
  ctx.fillStyle = "rgba(0,0,0,0.55)";
  ctx.fillRect(x, y, 28, 22);
  // Tiny spirit jar icon
  const s = SCALE * 0.18;
  // Jar body
  ctx.fillStyle = "#88cccc";
  ctx.fillRect(x+5+2*s, y+4+3*s, 4*s, 5*s);
  ctx.fillRect(x+5+s, y+4+4*s, 6*s, 3*s);
  // Lid
  ctx.fillStyle = "#8a7060";
  ctx.fillRect(x+5+2*s, y+4+s, 4*s, 2*s);
  // Wisp
  ctx.fillStyle = "#66ffaa";
  ctx.fillRect(x+5+3*s, y+4+5*s, 2*s, s);
  ctx.fillRect(x+5+4*s, y+4+4*s, s, s);
  // Show count if more than 1
  if (count > 1) {
    ctx.font = "bold 10px monospace";
    ctx.fillStyle = "#e6b422";
    ctx.fillText("x" + count, x + 16, y + 18);
  }
}

function renderTransition(now) {
  if (!G.ui.transition) return;
  const elapsed = now - G.ui.transition.startTime;
  const progress = Math.min(1, elapsed / G.ui.transition.duration);

  if (G.ui.transition.type === "fade") {
    if (progress < 0.5) {
      G.ui.ctx.drawImage(G.ui.transition.oldCanvas, 0, 0);
      G.ui.ctx.fillStyle = `rgba(0,0,0,${progress * 2})`;
      G.ui.ctx.fillRect(0, 0, CW, CH);
    } else {
      renderRoom();
      renderBrightTiles();
      renderPlayers();
      renderDarkness();
      renderUI();
      G.ui.ctx.fillStyle = `rgba(0,0,0,${(1 - progress) * 2})`;
      G.ui.ctx.fillRect(0, 0, CW, CH);
    }
  } else {
    const dir = G.ui.transition.direction;
    let ox = 0, oy = 0;
    if (dir === "north") oy =  CH * progress;
    if (dir === "south") oy = -CH * progress;
    if (dir === "west")  ox =  CW * progress;
    if (dir === "east")  ox = -CW * progress;

    G.ui.ctx.save();
    if (dir === "north") G.ui.ctx.translate(0, oy - CH);
    if (dir === "south") G.ui.ctx.translate(0, oy + CH);
    if (dir === "west")  G.ui.ctx.translate(ox - CW, 0);
    if (dir === "east")  G.ui.ctx.translate(ox + CW, 0);
    renderRoom();
    renderBrightTiles();
    renderPlayers();
    renderDarkness();
    renderUI();
    G.ui.ctx.restore();

    G.ui.ctx.drawImage(G.ui.transition.oldCanvas, ox, oy);
  }

  if (progress >= 1) {
    G.ui.transition = null;
  }
}

const CONJURE_TEXTS = [
  "The dungeon shifts...",
  "Dark forces stir...",
  "Ancient stones rearrange...",
  "Shadows coalesce...",
  "The air grows heavy...",
];

function renderConjuring(now) {
  if (!G.ui.conjuring) return false;
  const elapsed = now - G.ui.conjuring.startTime;
  const t = elapsed / 1000; // seconds

  // Fade from previous room into the conjuring screen over 500ms
  const FADE_IN_MS = 500;
  if (elapsed < FADE_IN_MS && G.ui.conjuring.oldCanvas) {
    G.ui.ctx.drawImage(G.ui.conjuring.oldCanvas, 0, 0);
    G.ui.ctx.fillStyle = `rgba(10, 10, 18, ${elapsed / FADE_IN_MS})`;
    G.ui.ctx.fillRect(0, 0, CW, CH);
    return true;
  }

  // Dark background
  G.ui.ctx.fillStyle = "#0a0a12";
  G.ui.ctx.fillRect(0, 0, CW, CH);

  // Flickering torchlight — two torch sources
  const torches = [
    { x: CW * 0.25, y: CH * 0.4 },
    { x: CW * 0.75, y: CH * 0.4 },
  ];
  for (const torch of torches) {
    const flicker = 0.3 + 0.15 * Math.sin(t * 8.3) + 0.1 * Math.sin(t * 13.7);
    const r = 80 + 30 * Math.sin(t * 5.1);
    const grad = G.ui.ctx.createRadialGradient(torch.x, torch.y, 0, torch.x, torch.y, r);
    grad.addColorStop(0, `rgba(255, 170, 50, ${flicker * 0.4})`);
    grad.addColorStop(0.6, `rgba(200, 100, 20, ${flicker * 0.15})`);
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    G.ui.ctx.fillStyle = grad;
    G.ui.ctx.fillRect(0, 0, CW, CH);

    // Torch flame
    const fw = 6 + 2 * Math.sin(t * 9);
    const fh = 12 + 4 * Math.sin(t * 7);
    G.ui.ctx.fillStyle = `rgba(255, 200, 60, ${0.6 + 0.3 * Math.sin(t * 11)})`;
    G.ui.ctx.fillRect(torch.x - fw/2, torch.y - fh, fw, fh);
    G.ui.ctx.fillStyle = `rgba(255, 100, 20, ${0.4 + 0.2 * Math.sin(t * 8)})`;
    G.ui.ctx.fillRect(torch.x - fw/2 - 1, torch.y - fh * 0.6, fw + 2, fh * 0.6);
  }

  // Drifting particles
  const seed = G.ui.conjuring.startTime;
  for (let i = 0; i < 12; i++) {
    const px = ((seed * 7 + i * 137) % CW);
    const py = CH - ((t * 30 + i * 50) % CH);
    const alpha = 0.2 + 0.3 * Math.sin(t * 2 + i);
    const size = 1 + (i % 3);
    G.ui.ctx.fillStyle = `rgba(180, 160, 120, ${alpha})`;
    G.ui.ctx.fillRect(px + Math.sin(t * 1.5 + i * 0.7) * 10, py, size, size);
  }

  // Atmospheric text
  const textIdx = Math.floor(t / 2) % CONJURE_TEXTS.length;
  const textAlpha = 0.5 + 0.3 * Math.sin(t * 2);
  G.ui.ctx.font = "18px monospace";
  G.ui.ctx.fillStyle = `rgba(180, 170, 140, ${textAlpha})`;
  G.ui.ctx.textAlign = "center";
  G.ui.ctx.fillText(CONJURE_TEXTS[textIdx], CW / 2, CH * 0.65);

  // Debug progress steps (sent when DEBUG_MODE is on)
  const steps = G.ui.conjuring.progressSteps;
  if (steps && steps.length > 0) {
    // Backend/model header (from "init" step) — persistent dim text
    const initStep = steps.find(s => s.step === "init");
    if (initStep) {
      G.ui.ctx.font = "10px monospace";
      G.ui.ctx.fillStyle = "rgba(120, 120, 100, 0.5)";
      G.ui.ctx.fillText(initStep.detail, CW / 2, CH * 0.73);
    }

    // Generation steps (skip "init")
    G.ui.ctx.font = "12px monospace";
    const work = steps.filter(s => s.step !== "init");
    const visible = work.slice(-5);
    for (let i = 0; i < visible.length; i++) {
      const s = visible[i];
      const age = (Date.now() - s.time) / 1000;
      const isLatest = i === visible.length - 1;
      // Latest step pulses, older steps are dim
      const a = isLatest ? 0.5 + 0.3 * Math.sin(t * 3) : Math.max(0.15, 0.4 - age * 0.03);
      const prefix = isLatest ? "> " : "  ";
      G.ui.ctx.fillStyle = isLatest
        ? `rgba(120, 220, 160, ${a})`
        : `rgba(140, 140, 120, ${a})`;
      G.ui.ctx.fillText(prefix + s.detail, CW / 2, CH * 0.77 + i * 16);
    }
  }

  G.ui.ctx.textAlign = "start";

  return true; // signal that conjuring is active
}

function renderDungeonDebug() {
  if (!G.debug.showDebug) return;
  const d = G.debug.dungeonDebug;
  const hasLog = G.debug.debugLog.length > 0;
  const lines = [];
  if (d) {
    if (d.room_source) lines.push("src: " + d.room_source);
    if (d.lib_rooms) lines.push("rooms: " + d.lib_rooms);
    if (d.lib_monsters) lines.push("monsters: " + d.lib_monsters);
    if (d.lib_tiles) lines.push("tiles: " + d.lib_tiles);
  }
  if (lines.length === 0 && !hasLog) return;

  G.ui.ctx.font = "9px monospace";
  const lineH = 12;
  const padding = 4;
  const boxW = 200;

  // Dungeon info lines + separator + debugLog lines
  const logLines = hasLog ? G.debug.debugLog : [];
  const totalLines = lines.length + (lines.length > 0 && hasLog ? 1 : 0) + logLines.length;
  const boxH = totalLines * lineH + padding * 2;
  const boxX = CW - boxW - 4;
  const boxY = 24;

  G.ui.ctx.fillStyle = "rgba(0,0,0,0.75)";
  G.ui.ctx.fillRect(boxX, boxY, boxW, boxH);
  G.ui.ctx.fillStyle = "#8af";
  let row = 0;
  for (let i = 0; i < lines.length; i++, row++) {
    G.ui.ctx.fillText(lines[i], boxX + padding, boxY + padding + (row + 1) * lineH - 2);
  }
  if (lines.length > 0 && hasLog) {
    // Dim separator line
    G.ui.ctx.fillStyle = "rgba(255,255,255,0.15)";
    const sepY = boxY + padding + row * lineH + 2;
    G.ui.ctx.fillRect(boxX + padding, sepY, boxW - padding * 2, 1);
    row++;
  }
  G.ui.ctx.fillStyle = "#0f0";
  for (let i = 0; i < logLines.length; i++, row++) {
    G.ui.ctx.fillText(logLines[i], boxX + padding, boxY + padding + (row + 1) * lineH - 2);
  }

  // Library icons with actual sprites/tiles (just below the room name)
  const libs = d && d.libraries;
  if (libs) {
    const iconS = 16;   // icon size (matches 16x16 sprite grid at S=1)
    const iconG = 2;    // gap between icons
    const rowG = 12;    // gap between rows (label + spacing)
    const perRow = 5;   // max icons per row
    const lx = 4, ly = 32;
    const statusBorder = {
      pre: "#58a0f0",  // blue — precreated
      cus: "#50d878",  // green — custom
      dep: "#e05040",  // red — deprecated
    };

    let nextY = ly;

    // Helper: draw a grid of icons with wrapping at perRow
    function drawIconGrid(items, emptyCount, label, drawIcon) {
      const total = items.length + emptyCount;
      if (total === 0) return;
      G.ui.ctx.font = "8px monospace";
      G.ui.ctx.fillStyle = "rgba(180, 180, 160, 0.7)";
      G.ui.ctx.fillText(label, lx, nextY);
      nextY += 3;
      let idx = 0;
      for (let i = 0; i < items.length; i++, idx++) {
        const col = idx % perRow, row = Math.floor(idx / perRow);
        const ix = lx + (iconS + iconG) * col;
        const iy = nextY + (iconS + iconG) * row;
        G.ui.ctx.fillStyle = "#0a0a12";
        G.ui.ctx.fillRect(ix, iy, iconS, iconS);
        drawIcon(items[i], ix, iy);
        G.ui.ctx.strokeStyle = statusBorder[items[i].s] || "#888";
        G.ui.ctx.lineWidth = 1.5;
        G.ui.ctx.strokeRect(ix + 0.5, iy + 0.5, iconS - 1, iconS - 1);
      }
      for (let i = 0; i < emptyCount; i++, idx++) {
        const col = idx % perRow, row = Math.floor(idx / perRow);
        const ix = lx + (iconS + iconG) * col;
        const iy = nextY + (iconS + iconG) * row;
        G.ui.ctx.fillStyle = "#0a0a12";
        G.ui.ctx.fillRect(ix, iy, iconS, iconS);
        G.ui.ctx.strokeStyle = "#333";
        G.ui.ctx.lineWidth = 1;
        G.ui.ctx.setLineDash([2, 2]);
        G.ui.ctx.strokeRect(ix + 0.5, iy + 0.5, iconS - 1, iconS - 1);
        G.ui.ctx.setLineDash([]);
      }
      G.ui.ctx.lineWidth = 1;
      const rows = Math.ceil((items.length + emptyCount) / perRow);
      nextY += rows * (iconS + iconG) + rowG - iconG;
    }

    // Monster icons
    drawIconGrid(libs.monsters || [], libs.monster_empty || 0, "monsters", (m, ix, iy) => {
      drawMonsterSprite(G.ui.ctx, ix, iy, m.id, 0, 1);
    });

    // Tile icons
    drawIconGrid(libs.tiles || [], libs.tile_empty || 0, "tiles", (ti, ix, iy) => {
      const tc = getTileCanvas(ti.id, TS, TILE, SCALE);
      if (tc) {
        G.ui.ctx.imageSmoothingEnabled = false;
        G.ui.ctx.drawImage(tc, 0, 0, tc.width, tc.height, ix, iy, iconS, iconS);
        G.ui.ctx.imageSmoothingEnabled = true;
      } else {
        G.ui.ctx.fillStyle = ti.color;
        G.ui.ctx.fillRect(ix, iy, iconS, iconS);
      }
    });
  }
}

function renderBossDeathEffect() {
  if (!G.fx.bossDeathEffect) return;
  const elapsed = Date.now() - G.fx.bossDeathEffect.startTime;
  if (elapsed > G.fx.bossDeathEffect.duration) {
    G.fx.bossDeathEffect = null;
    return;
  }

  // Phase 1 (0-400ms): bright white flash
  if (elapsed < 400) {
    const flashAlpha = Math.max(0, 0.7 * (1 - elapsed / 400));
    G.ui.ctx.fillStyle = `rgba(255, 255, 255, ${flashAlpha})`;
    G.ui.ctx.fillRect(0, 0, CW, CH);
  }

  // Phase 2: screen shake now handled by triggerShake() in net.js monster_killed handler

  // Phase 3 (400-2000ms): particle explosion from center
  if (elapsed > 400) {
    const t = (elapsed - 400) / 1600;
    const numParticles = 20;
    for (let i = 0; i < numParticles; i++) {
      const angle = (i / numParticles) * Math.PI * 2 + elapsed * 0.001;
      const dist = t * 200 * (0.5 + (i % 3) * 0.3);
      const px = CW / 2 + Math.cos(angle) * dist;
      const py = CH / 2 + Math.sin(angle) * dist;
      const alpha = Math.max(0, 1 - t);
      const size = (3 - (i % 3)) * SCALE;
      const colors = ["#ff6644", "#cc33ff", "#ffcc33", "#ff2200"];
      G.ui.ctx.fillStyle = colors[i % colors.length];
      G.ui.ctx.globalAlpha = alpha * 0.8;
      G.ui.ctx.fillRect(px - size / 2, py - size / 2, size, size);
    }
    G.ui.ctx.globalAlpha = 1;
  }
}

function renderDungeonMinimap() {
  const mm = G.debug.dungeonDebug && G.debug.dungeonDebug.minimap;
  if (!mm || !mm.cells || mm.cells.length === 0) return;

  const ds = G.room.dungeonState;
  const hasMap = ds && ds.collected.has("map");
  const hasCompass = ds && ds.collected.has("compass");
  const isDebug = G.debug.showDebug;

  // In non-debug mode, minimap shows when map or compass is collected
  if (!isDebug && !hasMap && !hasCompass) return;

  const cells = mm.cells;
  const pc = mm.player; // [col, row] of player's current cell
  const conns = mm.connections || [];

  // Find grid bounds
  let minC = Infinity, maxC = -Infinity, minR = Infinity, maxR = -Infinity;
  for (const cell of cells) {
    if (cell.c < minC) minC = cell.c;
    if (cell.c > maxC) maxC = cell.c;
    if (cell.r < minR) minR = cell.r;
    if (cell.r > maxR) maxR = cell.r;
  }
  const gridW = maxC - minC + 1;
  const gridH = maxR - minR + 1;

  const cellSize = 10;
  const gap = 2;
  const step = cellSize + gap;
  const pad = 8;

  const mapW = gridW * step - gap + pad * 2;
  const mapH = gridH * step - gap + pad * 2;
  const mapX = CW - mapW - 6;
  const mapY = CH - mapH - 6;

  // Semi-transparent background
  G.ui.ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
  G.ui.ctx.beginPath();
  roundRect(G.ui.ctx, mapX, mapY, mapW, mapH, 4);
  G.ui.ctx.fill();

  // Helper: get center of a cell on the minimap
  const cellCenter = (c, r) => ({
    x: mapX + pad + (c - minC) * step + cellSize / 2,
    y: mapY + pad + (r - minR) * step + cellSize / 2,
  });

  // Draw connections between cells (debug only)
  if (isDebug) {
    G.ui.ctx.strokeStyle = "rgba(160, 160, 160, 0.5)";
    G.ui.ctx.lineWidth = 2;
    for (const conn of conns) {
      const a = cellCenter(conn[0], conn[1]);
      const b = cellCenter(conn[2], conn[3]);
      G.ui.ctx.beginPath();
      G.ui.ctx.moveTo(a.x, a.y);
      G.ui.ctx.lineTo(b.x, b.y);
      G.ui.ctx.stroke();
    }
    G.ui.ctx.lineWidth = 1;
  }

  // Draw locked door indicators (debug only — hidden from player map)
  const lockedEdges = (ds && ds.lockedEdges) || [];
  if (isDebug && lockedEdges.length > 0) {
    G.ui.ctx.strokeStyle = "#cc3333";
    G.ui.ctx.lineWidth = 3;
    for (const edge of lockedEdges) {
      // edge = [[c1,r1], [c2,r2]]
      const a = cellCenter(edge[0][0], edge[0][1]);
      const b = cellCenter(edge[1][0], edge[1][1]);
      const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
      // Draw a short perpendicular bar at the midpoint
      const dx = b.x - a.x, dy = b.y - a.y;
      const len = 4;
      if (Math.abs(dx) > Math.abs(dy)) {
        // Horizontal connection — vertical bar
        G.ui.ctx.beginPath();
        G.ui.ctx.moveTo(mx, my - len);
        G.ui.ctx.lineTo(mx, my + len);
        G.ui.ctx.stroke();
      } else {
        // Vertical connection — horizontal bar
        G.ui.ctx.beginPath();
        G.ui.ctx.moveTo(mx - len, my);
        G.ui.ctx.lineTo(mx + len, my);
        G.ui.ctx.stroke();
      }
    }
    G.ui.ctx.lineWidth = 1;
  }

  // Compass-only: fill entire bounding box so layout is hidden
  if (!isDebug && hasCompass && !hasMap) {
    for (let r = minR; r <= maxR; r++) {
      for (let c = minC; c <= maxC; c++) {
        const cx = mapX + pad + (c - minC) * step;
        const cy = mapY + pad + (r - minR) * step;
        G.ui.ctx.fillStyle = "rgba(30, 35, 50, 0.45)";
        G.ui.ctx.fillRect(cx, cy, cellSize, cellSize);
      }
    }
  }

  // Key layout debug overlay (from /keylayout command)
  const keyLayout = ds && ds.keyLayout;
  if (keyLayout) {
    const zoneColors = [
      "rgba(220, 80, 80, 0.7)",   "rgba(80, 180, 220, 0.7)",
      "rgba(80, 220, 120, 0.7)",  "rgba(220, 180, 40, 0.7)",
      "rgba(180, 80, 220, 0.7)",  "rgba(220, 140, 60, 0.7)",
      "rgba(60, 220, 200, 0.7)",  "rgba(220, 80, 180, 0.7)",
      "rgba(140, 220, 60, 0.7)",  "rgba(100, 100, 220, 0.7)",
      "rgba(220, 220, 80, 0.7)",  "rgba(80, 140, 140, 0.7)",
    ];
    // Build cell→zone lookup
    const cellZone = {};
    for (const zone of keyLayout) {
      for (const [c, r] of zone.cells) {
        cellZone[c + "," + r] = zone;
      }
    }
    // Draw zone-colored cells
    for (const cell of cells) {
      const cx = mapX + pad + (cell.c - minC) * step;
      const cy = mapY + pad + (cell.r - minR) * step;
      const zone = cellZone[cell.c + "," + cell.r];
      if (zone) {
        G.ui.ctx.fillStyle = zoneColors[zone.zone_id % zoneColors.length];
        G.ui.ctx.fillRect(cx, cy, cellSize, cellSize);
      }
    }
    // Draw key count on the first cell of each zone
    G.ui.ctx.font = "bold 8px monospace";
    G.ui.ctx.textAlign = "center";
    G.ui.ctx.textBaseline = "middle";
    for (const zone of keyLayout) {
      if (zone.cells.length === 0) continue;
      const [fc, fr] = zone.cells[0];
      const cx = mapX + pad + (fc - minC) * step + cellSize / 2;
      const cy = mapY + pad + (fr - minR) * step + cellSize / 2;
      G.ui.ctx.fillStyle = "#fff";
      G.ui.ctx.fillText(String(zone.keys), cx, cy);
    }
    G.ui.ctx.textAlign = "start";
    G.ui.ctx.textBaseline = "alphabetic";
  }

  // Draw each cell
  for (const cell of cells) {
    const cx = mapX + pad + (cell.c - minC) * step;
    const cy = mapY + pad + (cell.r - minR) * step;

    if (keyLayout) {
      // Skip normal cell rendering when keylayout overlay is active
    } else if (isDebug) {
      // Debug mode — color by room type and state
      if (cell.boss) {
        G.ui.ctx.fillStyle = cell.res ? "rgba(220, 60, 60, 0.8)" : "rgba(220, 60, 60, 0.3)";
        G.ui.ctx.fillRect(cx, cy, cellSize, cellSize);
      } else if (cell.treasure) {
        G.ui.ctx.fillStyle = cell.res ? "rgba(255, 200, 40, 0.8)" : "rgba(255, 200, 40, 0.3)";
        G.ui.ctx.fillRect(cx, cy, cellSize, cellSize);
      } else if (!cell.res && !cell.gen) {
        G.ui.ctx.strokeStyle = "rgba(100, 100, 100, 0.6)";
        G.ui.ctx.setLineDash([2, 2]);
        G.ui.ctx.strokeRect(cx + 0.5, cy + 0.5, cellSize - 1, cellSize - 1);
        G.ui.ctx.setLineDash([]);
      } else if (!cell.res) {
        G.ui.ctx.strokeStyle = "rgba(140, 140, 100, 0.7)";
        G.ui.ctx.strokeRect(cx + 0.5, cy + 0.5, cellSize - 1, cellSize - 1);
      } else if (cell.src === "precreated") {
        G.ui.ctx.fillStyle = "rgba(80, 140, 220, 0.7)";
        G.ui.ctx.fillRect(cx, cy, cellSize, cellSize);
      } else {
        G.ui.ctx.fillStyle = "rgba(80, 200, 120, 0.7)";
        G.ui.ctx.fillRect(cx, cy, cellSize, cellSize);
      }
    } else if (hasMap) {
      // Map — reveals which cells are actual rooms
      G.ui.ctx.fillStyle = "rgba(100, 120, 160, 0.65)";
      G.ui.ctx.fillRect(cx, cy, cellSize, cellSize);
    }
    // Compass-only: cells already drawn as full grid above

    // Debug item icons (tiny text labels on cells)
    if (isDebug && cell.items && cell.items.length > 0) {
      G.ui.ctx.font = "bold 7px monospace";
      G.ui.ctx.textAlign = "center";
      G.ui.ctx.textBaseline = "middle";
      const iconMap = {map: "M", compass: "C", lantern: "T"};
      const label = cell.items.map(i => iconMap[i] || "?").join("");
      // White text with dark outline for readability
      const tx = cx + cellSize / 2, ty = cy + cellSize / 2;
      G.ui.ctx.fillStyle = "rgba(0,0,0,0.7)";
      G.ui.ctx.fillText(label, tx + 0.5, ty + 0.5);
      G.ui.ctx.fillStyle = "#fff";
      G.ui.ctx.fillText(label, tx, ty);
      G.ui.ctx.textAlign = "start";
      G.ui.ctx.textBaseline = "alphabetic";
    }

    // Entrance marker (map only, non-debug)
    if (cell.ent && (isDebug || hasMap)) {
      G.ui.ctx.fillStyle = "rgba(80, 220, 80, 0.9)";
      const mx = cx + cellSize / 2, my = cy + cellSize / 2;
      G.ui.ctx.beginPath();
      G.ui.ctx.arc(mx, my, 2, 0, Math.PI * 2);
      G.ui.ctx.fill();
    }

    // Boss room marker (compass collected, non-debug only)
    if (!isDebug && hasCompass && ds.bossCell &&
        cell.c === ds.bossCell[0] && cell.r === ds.bossCell[1]) {
      G.ui.ctx.fillStyle = "rgba(220, 40, 40, 0.9)";
      G.ui.ctx.fillRect(cx + 3, cy + 3, cellSize - 6, cellSize - 6);
    }
    // Treasure chest marker (compass collected, treasure not yet picked up)
    if (!isDebug && hasCompass && ds.treasureCell &&
        cell.c === ds.treasureCell[0] && cell.r === ds.treasureCell[1]) {
      const pulse = 0.7 + 0.3 * Math.sin(Date.now() / 400);
      G.ui.ctx.fillStyle = `rgba(220, 180, 40, ${pulse})`;
      G.ui.ctx.fillRect(cx + 2, cy + 2, cellSize - 4, cellSize - 4);
    }
  }

  // Other players — colored blinking dots (compass or debug only)
  const otherPlayers = (hasCompass || isDebug) && ds ? ds.otherPlayers : null;
  if (otherPlayers && otherPlayers.length > 0) {
    const blink = Math.sin(Date.now() / 300) > 0; // slightly slower blink than self
    if (blink) {
      for (const op of otherPlayers) {
        const opx = mapX + pad + (op.c - minC) * step + cellSize / 2;
        const opy = mapY + pad + (op.r - minR) * step + cellSize / 2;
        const color = SHIRT_COLORS[op.color_index % SHIRT_COLORS.length];
        G.ui.ctx.fillStyle = color;
        G.ui.ctx.beginPath();
        G.ui.ctx.arc(opx, opy, 2, 0, Math.PI * 2);
        G.ui.ctx.fill();
      }
    }
  }

  // Player position — pulsing indicator
  if (pc) {
    const px = mapX + pad + (pc[0] - minC) * step;
    const py = mapY + pad + (pc[1] - minR) * step;
    if (hasCompass || isDebug) {
      // Compass/debug: blinking yellow dot showing current room
      const blink = Math.sin(Date.now() / 200) > 0;
      if (blink) {
        G.ui.ctx.fillStyle = "rgba(255, 230, 50, 0.9)";
        const mx = px + cellSize / 2, my = py + cellSize / 2;
        G.ui.ctx.beginPath();
        G.ui.ctx.arc(mx, my, 2.5, 0, Math.PI * 2);
        G.ui.ctx.fill();
      }
    }
  }

  // Layout name (debug only)
  if (isDebug && mm.layout) {
    G.ui.ctx.font = "7px monospace";
    G.ui.ctx.fillStyle = "rgba(180, 180, 180, 0.6)";
    G.ui.ctx.fillText(mm.layout, mapX + pad, mapY + mapH + 8);
  }
}

// ---------------------------------------------------------------------------
// Edge arrows — directional indicators for players in other rooms
// ---------------------------------------------------------------------------

function _drawArrowTriangle(ctx, cx, cy, direction, color, size) {
  ctx.fillStyle = color;
  ctx.beginPath();
  switch (direction) {
    case "north": ctx.moveTo(cx, cy - size); ctx.lineTo(cx - size / 2, cy); ctx.lineTo(cx + size / 2, cy); break;
    case "south": ctx.moveTo(cx, cy + size); ctx.lineTo(cx - size / 2, cy); ctx.lineTo(cx + size / 2, cy); break;
    case "east":  ctx.moveTo(cx + size, cy); ctx.lineTo(cx, cy - size / 2); ctx.lineTo(cx, cy + size / 2); break;
    case "west":  ctx.moveTo(cx - size, cy); ctx.lineTo(cx, cy - size / 2); ctx.lineTo(cx, cy + size / 2); break;
  }
  ctx.closePath();
  ctx.fill();
}

function _drawSkullIcon(ctx, cx, cy, color) {
  ctx.font = "bold 12px monospace";
  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("\u2620", cx, cy);
  ctx.textAlign = "start";
  ctx.textBaseline = "alphabetic";
}

function _getDirectionToCell(myCell, theirCell) {
  const dc = theirCell[0] - myCell[0]; // positive = east
  const dr = theirCell[1] - myCell[1]; // positive = south
  const dirs = [];
  if (dr < 0) dirs.push("north");
  if (dr > 0) dirs.push("south");
  if (dc < 0) dirs.push("west");
  if (dc > 0) dirs.push("east");
  return dirs;
}

function renderPlayerArrows() {
  // Skip when dead or in death animation
  if (G.player.waitingForRevival || G.player.dyingPlayerSelf) return;
  if (!G.room.currentRoom) return;

  const ctx = G.ui.ctx;
  const arrowSize = 7;
  const spacing = 18;

  // Collect arrows by direction: { north: [{color, dead}], ... }
  const dirArrows = { north: [], south: [], east: [], west: [] };

  const isDungeon = !!G.room.dungeonState;

  if (isDungeon) {
    // Dungeon mode: compare cell coords
    const mm = G.debug.dungeonDebug && G.debug.dungeonDebug.minimap;
    const ds = G.room.dungeonState;
    const otherPlayers = ds ? ds.otherPlayers : null;
    if (!otherPlayers || otherPlayers.length === 0) return;
    const myCell = mm && mm.player;
    if (!myCell) return;

    for (const op of otherPlayers) {
      const dirs = _getDirectionToCell(myCell, [op.c, op.r]);
      if (dirs.length === 0) continue;
      const color = SHIRT_COLORS[op.color_index % SHIRT_COLORS.length];
      // For diagonal, add to each direction component
      for (const d of dirs) {
        dirArrows[d].push({ color, dead: op.dead, name: op.name });
      }
    }
  } else {
    // Overworld mode: use nearbyPlayers with pre-computed direction
    const nearby = G.room.nearbyPlayers;
    if (!nearby || nearby.length === 0) return;

    for (const np of nearby) {
      const d = np.direction;
      if (!dirArrows[d]) continue;
      const color = SHIRT_COLORS[np.color_index % SHIRT_COLORS.length];
      dirArrows[d].push({ color, dead: np.dead, name: np.name });
    }
  }

  // Check if there's anything to draw
  const totalArrows = dirArrows.north.length + dirArrows.south.length +
                      dirArrows.east.length + dirArrows.west.length;
  if (totalArrows === 0) return;

  // Gentle pulse for visibility
  const pulse = 0.7 + 0.3 * Math.sin(Date.now() / 500);
  ctx.globalAlpha = pulse;

  // Draw arrows for each direction
  // North: y=30, centered horizontally, stack left-to-right
  if (dirArrows.north.length > 0) {
    const arr = dirArrows.north;
    const totalW = arr.length * spacing;
    const startX = CW / 2 - totalW / 2 + spacing / 2;
    for (let i = 0; i < arr.length; i++) {
      const x = startX + i * spacing;
      const y = 30;
      if (arr[i].dead) {
        _drawSkullIcon(ctx, x, y, arr[i].color);
      } else {
        _drawArrowTriangle(ctx, x, y, "north", arr[i].color, arrowSize);
      }
    }
  }

  // South: y=CH-20, centered horizontally
  if (dirArrows.south.length > 0) {
    const arr = dirArrows.south;
    const totalW = arr.length * spacing;
    const startX = CW / 2 - totalW / 2 + spacing / 2;
    for (let i = 0; i < arr.length; i++) {
      const x = startX + i * spacing;
      const y = CH - 20;
      if (arr[i].dead) {
        _drawSkullIcon(ctx, x, y, arr[i].color);
      } else {
        _drawArrowTriangle(ctx, x, y, "south", arr[i].color, arrowSize);
      }
    }
  }

  // West: x=20, centered vertically, stack top-to-bottom
  if (dirArrows.west.length > 0) {
    const arr = dirArrows.west;
    const totalH = arr.length * spacing;
    const startY = CH / 2 - totalH / 2 + spacing / 2;
    for (let i = 0; i < arr.length; i++) {
      const x = 20;
      const y = startY + i * spacing;
      if (arr[i].dead) {
        _drawSkullIcon(ctx, x, y, arr[i].color);
      } else {
        _drawArrowTriangle(ctx, x, y, "west", arr[i].color, arrowSize);
      }
    }
  }

  // East: x=CW-30, centered vertically
  if (dirArrows.east.length > 0) {
    const arr = dirArrows.east;
    const totalH = arr.length * spacing;
    const startY = CH / 2 - totalH / 2 + spacing / 2;
    for (let i = 0; i < arr.length; i++) {
      const x = CW - 30;
      const y = startY + i * spacing;
      if (arr[i].dead) {
        _drawSkullIcon(ctx, x, y, arr[i].color);
      } else {
        _drawArrowTriangle(ctx, x, y, "east", arr[i].color, arrowSize);
      }
    }
  }

  ctx.globalAlpha = 1.0;
}
