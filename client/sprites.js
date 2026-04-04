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
  const eS = sprite.resolution ? S / sprite.resolution : S;
  const frame = hopFrame % sprite.frames.length;
  const yOffset = sprite.yOff ? sprite.yOff[frame] * eS : 0;
  drawLayers(ctx, px, py + yOffset, sprite.frames[frame], eS, sprite.colors);
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
  const mainSprite = customMonsterSprites[kind];
  const eS = mainSprite?.resolution ? S / mainSprite.resolution : S;
  const frame = sprite.frames[Math.min(deathFrame, sprite.frames.length - 1)];
  if (frame.alpha != null) {
    ctx.globalAlpha = frame.alpha;
    drawLayers(ctx, px, py, frame.layers, eS, sprite.colors);
    ctx.globalAlpha = 1;
  } else {
    drawLayers(ctx, px, py, frame, eS, sprite.colors);
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

function drawItemSpiritJar(ctx, px, py, S) {
  // Glass jar with ghostly wisp inside
  const glass = "#88cccc", glassDark = "#5a9999", glassBright = "#aaeedd";
  const lid = "#8a7060", lidDark = "#6a5040";
  const wisp = "#aaffcc", wispGlow = "#66ffaa";
  // Jar body
  ctx.fillStyle = glass;
  ctx.fillRect(px+2*S, py+3*S, 4*S, 6*S);
  ctx.fillRect(px+S, py+4*S, 6*S, 4*S);
  // Jar highlight (left edge)
  ctx.fillStyle = glassBright;
  ctx.fillRect(px+S, py+4*S, S, 4*S);
  ctx.fillRect(px+2*S, py+3*S, S, S);
  // Jar shadow (right edge)
  ctx.fillStyle = glassDark;
  ctx.fillRect(px+6*S, py+4*S, S, 4*S);
  ctx.fillRect(px+5*S, py+3*S, S, S);
  // Lid / cork
  ctx.fillStyle = lid;
  ctx.fillRect(px+2*S, py+S, 4*S, 2*S);
  ctx.fillStyle = lidDark;
  ctx.fillRect(px+3*S, py, 2*S, S);
  // Ghostly wisp inside
  ctx.fillStyle = wispGlow;
  ctx.fillRect(px+3*S, py+5*S, 2*S, S);
  ctx.fillRect(px+4*S, py+4*S, S, 2*S);
  ctx.fillStyle = wisp;
  ctx.fillRect(px+3*S, py+6*S, S, S);
  ctx.fillRect(px+4*S, py+7*S, S, S);
  // Jar bottom
  ctx.fillStyle = glassDark;
  ctx.fillRect(px+S, py+8*S, 6*S, S);
  ctx.fillRect(px+2*S, py+9*S, 4*S, S);
}

function drawItemLantern(ctx, px, py, S) {
  // Brass lantern with amber flame inside
  const brass = "#c8a832", brassDark = "#8a7020", brassBright = "#e8d060";
  const flame = "#ff9922", flameCore = "#ffdd44", flameTip = "#ff6600";
  const glass = "rgba(255,200,100,0.3)";
  // Handle (top)
  ctx.fillStyle = brassDark;
  ctx.fillRect(px+3*S, py, 2*S, S);
  ctx.fillRect(px+2*S, py+S, S, S);
  ctx.fillRect(px+5*S, py+S, S, S);
  // Top cap
  ctx.fillStyle = brass;
  ctx.fillRect(px+S, py+2*S, 6*S, S);
  ctx.fillStyle = brassBright;
  ctx.fillRect(px+2*S, py+2*S, 3*S, S);
  // Glass body
  ctx.fillStyle = glass;
  ctx.fillRect(px+S, py+3*S, 6*S, 5*S);
  // Flame
  ctx.fillStyle = flame;
  ctx.fillRect(px+3*S, py+4*S, 2*S, 3*S);
  ctx.fillStyle = flameCore;
  ctx.fillRect(px+3*S, py+5*S, 2*S, S);
  ctx.fillRect(px+4*S, py+4*S, S, S);
  ctx.fillStyle = flameTip;
  ctx.fillRect(px+4*S, py+3*S, S, S);
  // Side frame
  ctx.fillStyle = brass;
  ctx.fillRect(px, py+3*S, S, 5*S);
  ctx.fillRect(px+7*S, py+3*S, S, 5*S);
  // Bottom base
  ctx.fillStyle = brass;
  ctx.fillRect(px, py+8*S, 8*S, S);
  ctx.fillRect(px+S, py+9*S, 6*S, S);
  ctx.fillStyle = brassDark;
  ctx.fillRect(px+S, py+9*S, 2*S, S);
}

function drawItemSealFragment(ctx, px, py, S) {
  // Glowing crystal fragment — purple/blue with golden edge
  const crystal = "#7744cc", crystalBright = "#aa77ff", crystalDark = "#442288";
  const gold = "#d4a830", goldBright = "#f0d060";
  const glow = "rgba(120,80,220,0.4)";
  // Glow aura
  ctx.fillStyle = glow;
  ctx.fillRect(px, py+2*S, 8*S, 7*S);
  ctx.fillRect(px+S, py+S, 6*S, 9*S);
  // Crystal body (shield/triangle shape)
  ctx.fillStyle = crystal;
  ctx.fillRect(px+3*S, py+S, 2*S, S);
  ctx.fillRect(px+2*S, py+2*S, 4*S, S);
  ctx.fillRect(px+2*S, py+3*S, 5*S, S);
  ctx.fillRect(px+S, py+4*S, 6*S, S);
  ctx.fillRect(px+S, py+5*S, 6*S, S);
  ctx.fillRect(px+2*S, py+6*S, 5*S, S);
  ctx.fillRect(px+2*S, py+7*S, 4*S, S);
  ctx.fillRect(px+3*S, py+8*S, 3*S, S);
  ctx.fillRect(px+3*S, py+9*S, 2*S, S);
  // Bright edge (left)
  ctx.fillStyle = crystalBright;
  ctx.fillRect(px+2*S, py+2*S, S, S);
  ctx.fillRect(px+S, py+4*S, S, 2*S);
  ctx.fillRect(px+2*S, py+3*S, S, S);
  ctx.fillRect(px+3*S, py+S, S, S);
  // Dark edge (right)
  ctx.fillStyle = crystalDark;
  ctx.fillRect(px+6*S, py+4*S, S, 2*S);
  ctx.fillRect(px+6*S, py+6*S, S, S);
  ctx.fillRect(px+5*S, py+7*S, S, S);
  ctx.fillRect(px+4*S, py+9*S, S, S);
  // Golden border highlight
  ctx.fillStyle = gold;
  ctx.fillRect(px+3*S, py, 2*S, S);
  ctx.fillRect(px+S, py+3*S, S, S);
  ctx.fillRect(px+7*S, py+3*S, S, S);
  ctx.fillStyle = goldBright;
  ctx.fillRect(px+4*S, py, S, S);
  // Center shine
  ctx.fillStyle = "#ccaaff";
  ctx.fillRect(px+3*S, py+4*S, S, 2*S);
  ctx.fillRect(px+4*S, py+5*S, S, S);
}

function drawItemTideMedallion(ctx, px, py, S) {
  // Blue-teal circular medallion with wave motif
  const outer = "#1a5c8a", inner = "#2a8cba", bright = "#44bbdd";
  const gold = "#d4a830", goldBright = "#f0d060";
  const wave = "#88ddff", waveDark = "#2277aa";
  const glow = "rgba(40,140,200,0.35)";
  // Glow aura
  ctx.fillStyle = glow;
  ctx.fillRect(px, py+S, 8*S, 8*S);
  ctx.fillRect(px+S, py, 6*S, 10*S);
  // Gold border ring
  ctx.fillStyle = gold;
  ctx.fillRect(px+2*S, py, 4*S, S);
  ctx.fillRect(px+S, py+S, S, S);   ctx.fillRect(px+6*S, py+S, S, S);
  ctx.fillRect(px, py+2*S, S, 6*S); ctx.fillRect(px+7*S, py+2*S, S, 6*S);
  ctx.fillRect(px+S, py+8*S, S, S); ctx.fillRect(px+6*S, py+8*S, S, S);
  ctx.fillRect(px+2*S, py+9*S, 4*S, S);
  ctx.fillStyle = goldBright;
  ctx.fillRect(px+3*S, py, 2*S, S);
  ctx.fillRect(px, py+3*S, S, 2*S);
  // Inner disc
  ctx.fillStyle = outer;
  ctx.fillRect(px+2*S, py+S, 4*S, S);
  ctx.fillRect(px+S, py+2*S, 6*S, 6*S);
  ctx.fillRect(px+2*S, py+8*S, 4*S, S);
  ctx.fillStyle = inner;
  ctx.fillRect(px+2*S, py+2*S, 4*S, 6*S);
  ctx.fillRect(px+3*S, py+S, 2*S, S);
  ctx.fillRect(px+3*S, py+8*S, 2*S, S);
  // Wave pattern (3 horizontal waves)
  ctx.fillStyle = wave;
  ctx.fillRect(px+2*S, py+3*S, 2*S, S); ctx.fillRect(px+5*S, py+3*S, S, S);
  ctx.fillRect(px+2*S, py+5*S, S, S);   ctx.fillRect(px+4*S, py+5*S, 2*S, S);
  ctx.fillRect(px+3*S, py+7*S, 2*S, S);
  ctx.fillStyle = waveDark;
  ctx.fillRect(px+4*S, py+4*S, 2*S, S);
  ctx.fillRect(px+2*S, py+6*S, 2*S, S);
  // Center bright spot
  ctx.fillStyle = bright;
  ctx.fillRect(px+3*S, py+4*S, S, S);
  ctx.fillRect(px+4*S, py+3*S, S, S);
}

const ITEM_DRAW_FNS = {
  sword: drawItemSword,
  map: drawItemMap,
  compass: drawItemCompass,
  heart: drawItemHeart,
  key: drawItemKey,
  spirit_jar: drawItemSpiritJar,
  lantern: drawItemLantern,
  tide_medallion: drawItemTideMedallion,
  seal_fragment: drawItemSealFragment,
  heart_container: function(ctx, px, py, S) {
    drawItemHeart(ctx, px + 2*S, py + 2*S, S * 0.6);
  },
};

// ── Treasure Chest (large, two states) ──────────────────────────────
// 14 wide × 12 tall pixel grid, drawn at scale S per pixel.

function drawChestClosed(ctx, px, py, S) {
  const wood = "#7a4420", woodLt = "#9b6030", woodDk = "#4e2a10";
  const metal = "#5a5a62", metalLt = "#787880";
  const gold = "#d4a830", goldLt = "#f0d060";
  // --- Lid (curved top) ---
  ctx.fillStyle = woodLt;
  ctx.fillRect(px+3*S, py,     8*S, S);   // top curve
  ctx.fillRect(px+2*S, py+S,  10*S, S);
  ctx.fillStyle = wood;
  ctx.fillRect(px+S,   py+2*S, 12*S, S);
  ctx.fillRect(px+S,   py+3*S, 12*S, S);
  // Metal band across lid
  ctx.fillStyle = metal;
  ctx.fillRect(px+S,   py+4*S, 12*S, S);
  ctx.fillStyle = metalLt;
  ctx.fillRect(px+2*S, py+4*S, 4*S, S);
  // --- Seam / clasp row ---
  ctx.fillStyle = wood;
  ctx.fillRect(px,     py+5*S, 14*S, S);
  ctx.fillStyle = gold;
  ctx.fillRect(px+6*S, py+5*S, 2*S, S);   // clasp
  // --- Body ---
  ctx.fillStyle = wood;
  ctx.fillRect(px,     py+6*S, 14*S, S);
  ctx.fillRect(px,     py+7*S, 14*S, S);
  // Metal band across body
  ctx.fillStyle = metal;
  ctx.fillRect(px,     py+8*S, 14*S, S);
  ctx.fillStyle = metalLt;
  ctx.fillRect(px+S,   py+8*S, 4*S, S);
  // Lower body
  ctx.fillStyle = woodDk;
  ctx.fillRect(px,     py+9*S, 14*S, S);
  ctx.fillRect(px,     py+10*S,14*S, S);
  // Base band
  ctx.fillStyle = metal;
  ctx.fillRect(px+S,   py+11*S,12*S, S);
  // --- Lock plate ---
  ctx.fillStyle = gold;
  ctx.fillRect(px+5*S, py+6*S, 4*S, 4*S);
  ctx.fillStyle = goldLt;
  ctx.fillRect(px+6*S, py+6*S, 2*S, S);
  // Keyhole
  ctx.fillStyle = woodDk;
  ctx.fillRect(px+6*S, py+8*S, 2*S, S);
  ctx.fillRect(px+7*S, py+9*S, S, S);
  // --- Side edges ---
  ctx.fillStyle = metalLt;
  ctx.fillRect(px,     py+5*S, S, 7*S);   // left edge
  ctx.fillRect(px+13*S,py+5*S, S, 7*S);   // right edge
  // --- Lid highlight ---
  ctx.fillStyle = "#b07838";
  ctx.fillRect(px+3*S, py+S, 6*S, S);
}

function drawChestOpened(ctx, px, py, S) {
  const wood = "#7a4420", woodLt = "#9b6030", woodDk = "#4e2a10";
  const metal = "#5a5a62", metalLt = "#787880";
  const gold = "#d4a830", goldLt = "#f0d060";
  const glow = "#fff4b0", glowMid = "#ffe060";
  // --- Open lid (tilted back, shown above body) ---
  ctx.fillStyle = woodDk;
  ctx.fillRect(px+S,   py,     12*S, S);  // lid interior (dark)
  ctx.fillRect(px+S,   py+S,   12*S, S);
  ctx.fillStyle = metal;
  ctx.fillRect(px+S,   py+2*S, 12*S, S);  // metal band on lid
  ctx.fillStyle = woodLt;
  ctx.fillRect(px+2*S, py+3*S, 10*S, S);  // lid top edge (visible rim)
  // --- Inner glow from open chest ---
  ctx.fillStyle = "rgba(255,230,80,0.35)";
  ctx.fillRect(px+S,   py+4*S, 12*S, 3*S);
  ctx.fillStyle = glow;
  ctx.fillRect(px+4*S, py+4*S, 6*S, S);
  ctx.fillStyle = glowMid;
  ctx.fillRect(px+3*S, py+5*S, 8*S, S);
  ctx.fillRect(px+2*S, py+6*S, 10*S, S);
  // --- Body (same as closed) ---
  ctx.fillStyle = wood;
  ctx.fillRect(px,     py+7*S, 14*S, S);
  ctx.fillRect(px,     py+8*S, 14*S, S);
  // Metal band
  ctx.fillStyle = metal;
  ctx.fillRect(px,     py+9*S, 14*S, S);
  ctx.fillStyle = metalLt;
  ctx.fillRect(px+S,   py+9*S, 4*S, S);
  // Lower body
  ctx.fillStyle = woodDk;
  ctx.fillRect(px,     py+10*S,14*S, S);
  // Base band
  ctx.fillStyle = metal;
  ctx.fillRect(px+S,   py+11*S,12*S, S);
  // --- Lock plate (open / unlatched) ---
  ctx.fillStyle = gold;
  ctx.fillRect(px+5*S, py+7*S, 4*S, 3*S);
  ctx.fillStyle = goldLt;
  ctx.fillRect(px+6*S, py+7*S, 2*S, S);
  // --- Side edges ---
  ctx.fillStyle = metalLt;
  ctx.fillRect(px,     py+7*S, S, 5*S);
  ctx.fillRect(px+13*S,py+7*S, S, 5*S);
}

function drawGroundChest(ctx, px, py, opened, S) {
  // Chest sits still on the ground — no bounce, subtle ambient glow
  const t = performance.now() / 1000;
  const cx = px + 7*S, cy = py + 6*S;
  if (!opened) {
    // Faint golden shimmer for closed chest
    const flicker = 0.15 + 0.08 * Math.sin(t * 3.0);
    const radius = 12*S;
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
    grad.addColorStop(0, `rgba(255, 200, 50, ${flicker})`);
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = grad;
    ctx.fillRect(cx - radius, cy - radius, radius * 2, radius * 2);
    drawChestClosed(ctx, px, py, S);
  } else {
    // Bright glow for opened chest
    const flicker = 0.35 + 0.1 * Math.sin(t * 5.0);
    const radius = 14*S;
    const grad = ctx.createRadialGradient(cx, cy - 2*S, 0, cx, cy, radius);
    grad.addColorStop(0, `rgba(255, 230, 80, ${flicker})`);
    grad.addColorStop(0.5, `rgba(230, 150, 30, ${flicker * 0.3})`);
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = grad;
    ctx.fillRect(cx - radius, cy - radius, radius * 2, radius * 2);
    drawChestOpened(ctx, px, py, S);
  }
}

function drawTombstone(ctx, px, py, S) {
  for (const [color, x, y, w, h] of TOMBSTONE_SPRITE) {
    ctx.fillStyle = color;
    ctx.fillRect(px + x*S, py + y*S, w*S, h*S);
  }
}

function drawGroundItem(ctx, px, py, itemType, S) {
  const bounce = Math.sin(Date.now() / 300) * 2 * S;
  const drawFn = ITEM_DRAW_FNS[itemType];
  if (!drawFn) return;
  // Golden radial glow
  const t = performance.now() / 1000;
  const flicker = 0.4 + 0.15 * Math.sin(t * 6.2) + 0.1 * Math.sin(t * 11.4);
  const cx = px + 8*S;
  const cy = py + 8*S + bounce;
  const radius = 10*S + S * Math.sin(t * 4.3);
  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
  grad.addColorStop(0, `rgba(255, 200, 50, ${flicker})`);
  grad.addColorStop(0.5, `rgba(230, 150, 30, ${flicker * 0.4})`);
  grad.addColorStop(1, "rgba(0, 0, 0, 0)");
  ctx.fillStyle = grad;
  ctx.fillRect(cx - radius, cy - radius, radius * 2, radius * 2);
  drawFn(ctx, px + 4*S, py + 3*S + bounce, S);
}

function drawItemPickupOverlay(ctx, px, py, itemType, progress, S) {
  const drawFn = ITEM_DRAW_FNS[itemType];
  if (!drawFn) return;
  const riseY = progress * 8 * S;
  const itemX = px + 4*S;
  const itemY = py - 6*S - riseY;
  // Golden radial glow behind item
  const t = performance.now() / 1000;
  const flicker = 0.5 + 0.2 * Math.sin(t * 8.5);
  const gcx = itemX + 4*S;
  const gcy = itemY + 5*S;
  const gr = 9*S;
  const grad = ctx.createRadialGradient(gcx, gcy, 0, gcx, gcy, gr);
  grad.addColorStop(0, `rgba(255, 200, 50, ${flicker})`);
  grad.addColorStop(0.5, `rgba(230, 150, 30, ${flicker * 0.4})`);
  grad.addColorStop(1, "rgba(0, 0, 0, 0)");
  ctx.fillStyle = grad;
  ctx.fillRect(gcx - gr, gcy - gr, gr * 2, gr * 2);
  drawFn(ctx, itemX, itemY, S);
  // Sparkles
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
