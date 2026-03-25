// ---------------------------------------------------------------------------
// Sprite renderer — draws sprites from data definitions in sprite_data.js
// ---------------------------------------------------------------------------
const SHIRT_COLORS = ["#c8383c", "#3868c8", "#38a838", "#c8a838", "#a838c8", "#38c8c8"];
const SKIN = "#e8c898";
const HAIR = "#4a3020";
const PANTS = "#3a4a8a";
const BOOTS = "#3a2a1a";

// Core renderer — draws an array of [colorKey, x, y, w, h] layers
function drawLayers(ctx, px, py, layers, S, colorMap) {
  for (const layer of layers) {
    const [key, x, y, w, h] = layer;
    ctx.fillStyle = colorMap[key] || PALETTE[key] || key;
    ctx.fillRect(px + x * S, py + y * S, w * S, h * S);
  }
}

// ---------------------------------------------------------------------------
// NPC sprites — data-driven from server
// ---------------------------------------------------------------------------
function drawNPCSprite(ctx, px, py, spriteKey, S) {
  const sprite = customNPCSprites[spriteKey];
  if (!sprite) { if (spriteKey !== "guard") drawNPCSprite(ctx, px, py, "guard", S); return; }

  const effects = sprite.effects || {};
  let drawY = py;

  // Bob effect (ghost, ghost_knight)
  if (effects.bob) {
    drawY += Math.sin(Date.now() / effects.bob) * S;
  }
  if (effects.alpha != null) {
    ctx.globalAlpha = effects.alpha;
  }

  // Pulse glow (amara)
  if (effects.pulse) {
    const p = effects.pulse;
    const pulse = (Math.sin(Date.now() / p.speed) + 1) / 2;
    const glowAlpha = p.baseAlpha + pulse * p.range;
    const [r, g, b] = p.color;
    ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${glowAlpha})`;
    const [rx, ry, rw, rh] = p.rect;
    ctx.fillRect(px + rx * S, drawY + ry * S, rw * S, rh * S);
  }

  drawLayers(ctx, px, drawY, sprite.layers, S, sprite.colors);

  if (effects.alpha != null) {
    ctx.globalAlpha = 1;
  }
}

function drawNPC(ctx, px, py, sprite, S) {
  drawNPCSprite(ctx, px, py, sprite || "guard", S);
}

// ---------------------------------------------------------------------------
// Monster sprites — data-driven from server
// ---------------------------------------------------------------------------
function drawMonsterSprite(ctx, px, py, kind, hopFrame, S) {
  const sprite = customMonsterSprites[kind];
  if (!sprite) return;
  const frame = hopFrame % sprite.frames.length;
  const yOffset = sprite.yOff ? sprite.yOff[frame] * S : 0;
  drawLayers(ctx, px, py + yOffset, sprite.frames[frame], S, sprite.colors);
}

function drawMonsterDeath(ctx, px, py, kind, deathFrame, S) {
  const sprite = customDeathSprites[kind];
  if (!sprite) {
    // Generate a generic splat from the monster's primary color
    const monsterSprite = customMonsterSprites[kind];
    if (!monsterSprite) return;
    const clr = monsterSprite.colors[Object.keys(monsterSprite.colors)[0]] || "#888";
    const genericFrames = [
      [["c", 2,12,12,2], ["c", 3,11,10,2], ["c", 1,12,14,1]],
      [["c", 1,12,3,2], ["c", 6,11,4,2], ["c",12,12,3,2]],
      { alpha: 0.4, layers: [["c", 0,13,2,1], ["c", 6,12,3,1], ["c",13,13,2,1]] },
    ];
    const frame = genericFrames[Math.min(deathFrame, genericFrames.length - 1)];
    const colors = { c: clr };
    if (frame.alpha != null) {
      ctx.globalAlpha = frame.alpha;
      drawLayers(ctx, px, py, frame.layers, S, colors);
      ctx.globalAlpha = 1;
    } else {
      drawLayers(ctx, px, py, frame, S, colors);
    }
    return;
  }
  const frame = sprite.frames[Math.min(deathFrame, sprite.frames.length - 1)];
  if (frame.alpha != null) {
    ctx.globalAlpha = frame.alpha;
    drawLayers(ctx, px, py, frame.layers, S, sprite.colors);
    ctx.globalAlpha = 1;
  } else {
    drawLayers(ctx, px, py, frame, S, sprite.colors);
  }
}


// ---------------------------------------------------------------------------
// Player sprites — data-driven with dynamic shirt color
// ---------------------------------------------------------------------------
function makePlayerColorMap(colorIndex) {
  return { SHIRT: SHIRT_COLORS[colorIndex % SHIRT_COLORS.length] };
}

function drawPlayerDance(ctx, px, py, colorIndex, danceFrame, S) {
  const colors = makePlayerColorMap(colorIndex);
  drawLayers(ctx, px, py, DANCE_FRAMES[danceFrame % DANCE_FRAMES.length], S, colors);
}

function drawPlayer(ctx, px, py, direction, colorIndex, animFrame, S) {
  const colors = makePlayerColorMap(colorIndex);
  const frames = PLAYER_WALK_FRAMES[direction] || PLAYER_WALK_FRAMES.down;
  drawLayers(ctx, px, py, frames[animFrame % frames.length], S, colors);
}

function drawPlayerFallOver(ctx, px, py, colorIndex, frame, S) {
  const colors = makePlayerColorMap(colorIndex);
  if (frame >= 2) {
    ctx.globalAlpha = Math.max(0, 1 - (frame - 2) * 0.3);
    drawLayers(ctx, px, py, PLAYER_FALL_FRAMES[2], S, colors);
    ctx.globalAlpha = 1;
  } else {
    drawLayers(ctx, px, py, PLAYER_FALL_FRAMES[frame], S, colors);
  }
}

// ---------------------------------------------------------------------------
// Attack animation — kept as code (dynamic thrust offsets)
// ---------------------------------------------------------------------------
function drawPlayerAttack(ctx, px, py, direction, colorIndex, attackFrame, S) {
  const sx = px, sy = py;
  const shirt = SHIRT_COLORS[colorIndex % SHIRT_COLORS.length];
  const thrust = attackFrame === 1;

  if (direction === "down") {
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+5*S, sy+0*S, 6*S, 2*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+5*S, sy+2*S, 6*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+6*S, sy+3*S, S, S);
    ctx.fillRect(sx+9*S, sy+3*S, S, S);
    const tOff = thrust ? S : 0;
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+4*S, sy+6*S+tOff, 8*S, 5*S);
    ctx.fillRect(sx+3*S, sy+6*S+tOff, S, 4*S);
    ctx.fillRect(sx+12*S, sy+6*S+tOff, S, 4*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+3*S, sy+10*S+tOff, S, S);
    ctx.fillRect(sx+12*S, sy+10*S+tOff, S, S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+5*S, sy+11*S+tOff, 6*S, 2*S);
    ctx.fillStyle = BOOTS;
    ctx.fillRect(sx+5*S, sy+13*S+tOff, 2*S, 2*S);
    ctx.fillRect(sx+9*S, sy+13*S+tOff, 2*S, 2*S);
  } else if (direction === "up") {
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+5*S, sy+0*S, 6*S, 5*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+4*S, sy+3*S, S, 2*S);
    ctx.fillRect(sx+11*S, sy+3*S, S, 2*S);
    const tOff = thrust ? -S : 0;
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+4*S, sy+6*S+tOff, 8*S, 5*S);
    ctx.fillRect(sx+3*S, sy+6*S+tOff, S, 4*S);
    ctx.fillRect(sx+12*S, sy+6*S+tOff, S, 4*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+3*S, sy+10*S+tOff, S, S);
    ctx.fillRect(sx+12*S, sy+10*S+tOff, S, S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+5*S, sy+11*S, 6*S, 2*S);
    ctx.fillStyle = BOOTS;
    ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
    ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
  } else if (direction === "left") {
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+4*S, sy+0*S, 6*S, 2*S);
    ctx.fillRect(sx+8*S, sy+2*S, 2*S, 4*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+4*S, sy+2*S, 4*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+4*S, sy+3*S, S, S);
    const tOff = thrust ? -S : 0;
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+5*S+tOff, sy+6*S, 6*S, 5*S);
    ctx.fillRect(sx+3*S+tOff, sy+7*S, 2*S, 3*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+2*S+tOff, sy+8*S, S, S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+5*S, sy+11*S, 5*S, 2*S);
    ctx.fillStyle = BOOTS;
    ctx.fillRect(sx+5*S, sy+13*S, 3*S, 2*S);
  } else {
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+6*S, sy+0*S, 6*S, 2*S);
    ctx.fillRect(sx+6*S, sy+2*S, 2*S, 4*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+8*S, sy+2*S, 4*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+11*S, sy+3*S, S, S);
    const tOff = thrust ? S : 0;
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+5*S+tOff, sy+6*S, 6*S, 5*S);
    ctx.fillRect(sx+11*S+tOff, sy+7*S, 2*S, 3*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+13*S+tOff, sy+8*S, S, S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+6*S, sy+11*S, 5*S, 2*S);
    ctx.fillStyle = BOOTS;
    ctx.fillRect(sx+8*S, sy+13*S, 3*S, 2*S);
  }
}

// ---------------------------------------------------------------------------
// Sword sprite — drawn on the tile in front of the attacking player
// ---------------------------------------------------------------------------
function drawSwordAttack(ctx, px, py, direction, attackFrame, S) {
  const BLADE = "#C0C0C0";
  const HILT = "#8B4513";
  const GUARD = "#DAA520";
  const thrust = attackFrame === 1;
  const ext = thrust ? 4*S : 2*S;

  if (direction === "down") {
    const sx = px + 7*S, sy = py + 16*S;
    ctx.fillStyle = HILT;  ctx.fillRect(sx - S, sy, 2*S, 3*S);
    ctx.fillStyle = GUARD; ctx.fillRect(sx - 2*S, sy + 3*S, 4*S, S);
    ctx.fillStyle = BLADE; ctx.fillRect(sx - S, sy + 4*S, 2*S, ext);
    ctx.fillRect(sx, sy + 4*S + ext, S, S);
  } else if (direction === "up") {
    const sx = px + 7*S, sy = py - S;
    ctx.fillStyle = HILT;  ctx.fillRect(sx - S, sy - 2*S, 2*S, 3*S);
    ctx.fillStyle = GUARD; ctx.fillRect(sx - 2*S, sy - 3*S, 4*S, S);
    ctx.fillStyle = BLADE; ctx.fillRect(sx - S, sy - 3*S - ext, 2*S, ext);
    ctx.fillRect(sx, sy - 4*S - ext, S, S);
  } else if (direction === "left") {
    const sx = px - S, sy = py + 7*S;
    ctx.fillStyle = HILT;  ctx.fillRect(sx - 2*S, sy - S, 3*S, 2*S);
    ctx.fillStyle = GUARD; ctx.fillRect(sx - 3*S, sy - 2*S, S, 4*S);
    ctx.fillStyle = BLADE; ctx.fillRect(sx - 3*S - ext, sy - S, ext, 2*S);
    ctx.fillRect(sx - 4*S - ext, sy, S, S);
  } else {
    const sx = px + 16*S, sy = py + 7*S;
    ctx.fillStyle = HILT;  ctx.fillRect(sx, sy - S, 3*S, 2*S);
    ctx.fillStyle = GUARD; ctx.fillRect(sx + 3*S, sy - 2*S, S, 4*S);
    ctx.fillStyle = BLADE; ctx.fillRect(sx + 4*S, sy - S, ext, 2*S);
    ctx.fillRect(sx + 4*S + ext, sy, S, S);
  }
}

// ---------------------------------------------------------------------------
// Sword pickup animation
// ---------------------------------------------------------------------------
function drawSwordPickup(ctx, px, py, frame, S) {
  const BLADE = "#C0C0C0", HILT = "#8B4513", GUARD = "#DAA520";
  const riseY = frame * 4 * S;
  const sx = px + 6*S, sy = py - 4*S - riseY;
  const alpha = Math.max(0, 1 - frame * 0.2);
  ctx.globalAlpha = alpha;
  ctx.fillStyle = "rgba(230, 180, 34, 0.4)";
  ctx.fillRect(sx - 2*S, sy - S, 6*S, 14*S);
  ctx.fillStyle = BLADE; ctx.fillRect(sx, sy, 2*S, 6*S);
  ctx.fillRect(sx + S*0.5, sy - S, S, S);
  ctx.fillStyle = GUARD; ctx.fillRect(sx - S, sy + 6*S, 4*S, S);
  ctx.fillStyle = HILT;  ctx.fillRect(sx, sy + 7*S, 2*S, 3*S);
  ctx.globalAlpha = 1;
}

// ---------------------------------------------------------------------------
// Heart sprites
// ---------------------------------------------------------------------------
function drawHeart(ctx, px, py, state, S) {
  const RED = "#e03030", DARK_RED = "#a02020", GREY = "#555", DARK_GREY = "#333";
  const full = state === "full", half = state === "half";
  const leftColor = (full || half) ? RED : GREY;
  const leftDark = (full || half) ? DARK_RED : DARK_GREY;
  const rightColor = full ? RED : GREY;
  const rightDark = full ? DARK_RED : DARK_GREY;

  ctx.fillStyle = leftColor;
  ctx.fillRect(px+1*S, py+0*S, 4*S, S);
  ctx.fillRect(px+0*S, py+1*S, 6*S, 2*S);
  ctx.fillRect(px+0*S, py+3*S, 6*S, 2*S);
  ctx.fillRect(px+1*S, py+5*S, 5*S, 2*S);
  ctx.fillRect(px+2*S, py+7*S, 4*S, S);
  ctx.fillRect(px+3*S, py+8*S, 3*S, S);
  ctx.fillRect(px+4*S, py+9*S, 2*S, S);
  ctx.fillRect(px+5*S, py+10*S, S, S);
  ctx.fillStyle = "#ff6060";
  if (full || half) ctx.fillRect(px+1*S, py+1*S, 2*S, S);
  ctx.fillStyle = leftDark;
  ctx.fillRect(px+0*S, py+4*S, S, S);
  ctx.fillRect(px+1*S, py+6*S, S, S);

  ctx.fillStyle = rightColor;
  ctx.fillRect(px+7*S, py+0*S, 4*S, S);
  ctx.fillRect(px+6*S, py+1*S, 6*S, 2*S);
  ctx.fillRect(px+6*S, py+3*S, 6*S, 2*S);
  ctx.fillRect(px+6*S, py+5*S, 5*S, 2*S);
  ctx.fillRect(px+6*S, py+7*S, 4*S, S);
  ctx.fillRect(px+6*S, py+8*S, 3*S, S);
  ctx.fillStyle = rightDark;
  ctx.fillRect(px+11*S, py+4*S, S, S);
  ctx.fillRect(px+10*S, py+6*S, S, S);
}

// ---------------------------------------------------------------------------
// Player hold-item pose
// ---------------------------------------------------------------------------
function drawPlayerHoldItem(ctx, px, py, colorIndex, S) {
  const colors = makePlayerColorMap(colorIndex);
  drawLayers(ctx, px, py, ITEM_HOLD_FRAME, S, colors);
}

// ---------------------------------------------------------------------------
// Dungeon item sprites
// ---------------------------------------------------------------------------
function drawItemSword(ctx, px, py, S) {
  const BLADE = "#C0C0C0", HILT = "#8B4513", GUARD = "#DAA520";
  ctx.fillStyle = BLADE; ctx.fillRect(px + 3*S, py, 2*S, 6*S);
  ctx.fillRect(px + 4*S, py - S, S, S);
  ctx.fillStyle = GUARD; ctx.fillRect(px + 2*S, py + 6*S, 4*S, S);
  ctx.fillStyle = HILT;  ctx.fillRect(px + 3*S, py + 7*S, 2*S, 3*S);
}

function drawItemMap(ctx, px, py, S) {
  ctx.fillStyle = "#d4b483"; ctx.fillRect(px + S, py + S, 6*S, 8*S);
  ctx.fillStyle = "#c4a473"; ctx.fillRect(px + S, py + S, 6*S, S);
  ctx.fillStyle = "#c4a473"; ctx.fillRect(px + S, py + 8*S, 6*S, S);
  ctx.fillStyle = "#8b6914"; ctx.fillRect(px + 2*S, py + 3*S, 4*S, S);
  ctx.fillStyle = "#8b6914"; ctx.fillRect(px + 2*S, py + 5*S, 3*S, S);
  ctx.fillStyle = "#8b6914"; ctx.fillRect(px + 2*S, py + 7*S, 4*S, S);
}

function drawItemCompass(ctx, px, py, S) {
  const cx = px + 4*S, cy = py + 4*S, r = 3.5*S;
  ctx.fillStyle = "#d4a44c";
  ctx.beginPath(); ctx.arc(cx, cy, r + S, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = "#f5e6c8";
  ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.fill();
  // Needle — red north, white south
  ctx.fillStyle = "#cc2222";
  ctx.fillRect(cx - 0.5*S, cy - 3*S, S, 3*S);
  ctx.fillStyle = "#888888";
  ctx.fillRect(cx - 0.5*S, cy, S, 3*S);
  // Center dot
  ctx.fillStyle = "#333";
  ctx.fillRect(cx - 0.5*S, cy - 0.5*S, S, S);
}

function drawBigHeartSolid(ctx, px, py, color, S) {
  // 18x13 heart shape — bigger than HUD heart for item pickup/ground display
  ctx.fillStyle = color;
  // Left half
  ctx.fillRect(px+2*S, py, 5*S, S);
  ctx.fillRect(px+S, py+S, 7*S, S);
  ctx.fillRect(px, py+2*S, 9*S, 3*S);
  ctx.fillRect(px+S, py+5*S, 8*S, S);
  ctx.fillRect(px+2*S, py+6*S, 7*S, S);
  ctx.fillRect(px+3*S, py+7*S, 6*S, S);
  ctx.fillRect(px+4*S, py+8*S, 5*S, S);
  ctx.fillRect(px+5*S, py+9*S, 4*S, S);
  ctx.fillRect(px+6*S, py+10*S, 3*S, S);
  ctx.fillRect(px+7*S, py+11*S, 2*S, S);
  ctx.fillRect(px+8*S, py+12*S, S, S);
  // Right half
  ctx.fillRect(px+11*S, py, 5*S, S);
  ctx.fillRect(px+10*S, py+S, 7*S, S);
  ctx.fillRect(px+9*S, py+2*S, 9*S, 3*S);
  ctx.fillRect(px+9*S, py+5*S, 8*S, S);
  ctx.fillRect(px+9*S, py+6*S, 7*S, S);
  ctx.fillRect(px+9*S, py+7*S, 6*S, S);
  ctx.fillRect(px+9*S, py+8*S, 5*S, S);
  ctx.fillRect(px+9*S, py+9*S, 4*S, S);
  ctx.fillRect(px+9*S, py+10*S, 3*S, S);
  ctx.fillRect(px+9*S, py+11*S, 2*S, S);
  ctx.fillRect(px+9*S, py+12*S, S, S);
}

function drawItemHeart(ctx, px, py, S) {
  const ox = px - 4*S, oy = py - S;
  // Gold container border (1px dilation of big heart shape)
  for (let dx = -1; dx <= 1; dx++) {
    for (let dy = -1; dy <= 1; dy++) {
      drawBigHeartSolid(ctx, ox + dx*S, oy + dy*S, "#DAA520", S);
    }
  }
  // Red heart fill
  drawBigHeartSolid(ctx, ox, oy, "#e03030", S);
  // Highlight (top-left lobe)
  ctx.fillStyle = "#ff6060";
  ctx.fillRect(ox+2*S, oy+S, 3*S, S);
  ctx.fillRect(ox+S, oy+2*S, 2*S, S);
  // Subtle highlight (right lobe)
  ctx.fillStyle = "#f04848";
  ctx.fillRect(ox+12*S, oy+S, 2*S, S);
  // Shadow (lower edges)
  ctx.fillStyle = "#a02020";
  ctx.fillRect(ox, oy+4*S, S, S);
  ctx.fillRect(ox+S, oy+5*S, S, S);
  ctx.fillRect(ox+2*S, oy+6*S, S, S);
  ctx.fillRect(ox+3*S, oy+7*S, S, S);
  ctx.fillRect(ox+17*S, oy+4*S, S, S);
  ctx.fillRect(ox+16*S, oy+5*S, S, S);
  ctx.fillRect(ox+15*S, oy+6*S, S, S);
  ctx.fillRect(ox+14*S, oy+7*S, S, S);
}

function drawItemKey(ctx, px, py, S) {
  // Classic gold small key — circular bow at top, shaft, two teeth
  const gold = "#d4a830";
  const dark = "#8a6e10";
  const bright = "#f0d060";
  ctx.fillStyle = gold;
  // Bow (circular ring at top)
  ctx.fillRect(px+2*S, py, 4*S, S);
  ctx.fillRect(px+S, py+S, 6*S, S);
  ctx.fillRect(px+S, py+2*S, 2*S, S);
  ctx.fillRect(px+5*S, py+2*S, 2*S, S);
  ctx.fillRect(px+S, py+3*S, 6*S, S);
  ctx.fillRect(px+2*S, py+4*S, 4*S, S);
  // Shaft
  ctx.fillRect(px+3*S, py+5*S, 2*S, 5*S);
  // Teeth
  ctx.fillRect(px+5*S, py+8*S, 2*S, S);
  ctx.fillRect(px+5*S, py+10*S, 2*S, S);
  // Highlight
  ctx.fillStyle = bright;
  ctx.fillRect(px+3*S, py+S, 2*S, S);
  ctx.fillRect(px+2*S, py+2*S, S, S);
  // Shadow
  ctx.fillStyle = dark;
  ctx.fillRect(px+4*S, py+5*S, S, 5*S);
  ctx.fillRect(px+6*S, py+8*S, S, S);
  ctx.fillRect(px+6*S, py+10*S, S, S);
}

const ITEM_DRAW_FNS = {
  sword: drawItemSword,
  map: drawItemMap,
  compass: drawItemCompass,
  heart: drawItemHeart,
  key: drawItemKey,
};

function drawGroundItem(ctx, px, py, itemType, S) {
  const bounce = Math.sin(Date.now() / 300) * 2 * S;
  const drawFn = ITEM_DRAW_FNS[itemType];
  if (!drawFn) return;
  // Golden glow
  ctx.globalAlpha = 0.3 + 0.1 * Math.sin(Date.now() / 400);
  ctx.fillStyle = "#e6b422";
  ctx.fillRect(px + S, py + S + bounce, 14*S, 14*S);
  ctx.globalAlpha = 1;
  drawFn(ctx, px + 4*S, py + 3*S + bounce, S);
}

function drawItemPickupOverlay(ctx, px, py, itemType, progress, S) {
  const drawFn = ITEM_DRAW_FNS[itemType];
  if (!drawFn) return;
  const riseY = progress * 8 * S;
  const itemX = px + 4*S;
  const itemY = py - 6*S - riseY;
  // Golden glow behind item
  ctx.globalAlpha = 0.4 + 0.2 * Math.sin(Date.now() / 150);
  ctx.fillStyle = "#e6b422";
  ctx.fillRect(itemX - S, itemY - S, 10*S, 12*S);
  ctx.globalAlpha = 1;
  drawFn(ctx, itemX, itemY, S);
  // Sparkles
  const t = Date.now() / 1000;
  for (let i = 0; i < 6; i++) {
    const angle = (i / 6) * Math.PI * 2 + t * 3;
    const dist = (4 + 2 * Math.sin(t * 2 + i)) * S;
    const sx = itemX + 4*S + Math.cos(angle) * dist;
    const sy = itemY + 4*S + Math.sin(angle) * dist;
    const sparkAlpha = 0.5 + 0.5 * Math.sin(t * 5 + i * 2);
    ctx.globalAlpha = sparkAlpha;
    ctx.fillStyle = "#fff";
    ctx.fillRect(sx, sy, S, S);
  }
  ctx.globalAlpha = 1;
}

function drawHeartPickup(ctx, px, py, bounceFrame, S) {
  const yOff = bounceFrame % 2 === 0 ? 0 : -2*S;
  drawHeart(ctx, px + 2*S, py + 2*S + yOff, "full", S * 0.7);
}
