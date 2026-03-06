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
// NPC sprites — data-driven
// ---------------------------------------------------------------------------
function drawNPCSprite(ctx, px, py, spriteKey, S) {
  const sprite = NPC_SPRITE_DATA[spriteKey];
  if (!sprite) { drawNPCSprite(ctx, px, py, "guard", S); return; }

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

const NPC_SPRITES = {
  guard: "guard", smith: "smith", priest: "priest", barmaid: "barmaid",
  amara: "amara", witch: "witch", ghost: "ghost", ghost_knight: "ghost_knight",
  ranger: "ranger", farmer: "farmer", nomad: "nomad", merchant: "merchant",
  elder: "elder", fisher: "fisher",
};

function drawNPC(ctx, px, py, sprite, S) {
  drawNPCSprite(ctx, px, py, NPC_SPRITES[sprite] || "guard", S);
}

// Backward-compatible named exports for direct calls
function drawGuard(ctx, px, py, S)       { drawNPCSprite(ctx, px, py, "guard", S); }
function drawSmith(ctx, px, py, S)       { drawNPCSprite(ctx, px, py, "smith", S); }
function drawPriest(ctx, px, py, S)      { drawNPCSprite(ctx, px, py, "priest", S); }
function drawBarmaid(ctx, px, py, S)     { drawNPCSprite(ctx, px, py, "barmaid", S); }
function drawWitch(ctx, px, py, S)       { drawNPCSprite(ctx, px, py, "witch", S); }
function drawGhost(ctx, px, py, S)       { drawNPCSprite(ctx, px, py, "ghost", S); }
function drawGhostKnight(ctx, px, py, S) { drawNPCSprite(ctx, px, py, "ghost_knight", S); }
function drawRanger(ctx, px, py, S)      { drawNPCSprite(ctx, px, py, "ranger", S); }
function drawFarmer(ctx, px, py, S)      { drawNPCSprite(ctx, px, py, "farmer", S); }
function drawNomad(ctx, px, py, S)       { drawNPCSprite(ctx, px, py, "nomad", S); }
function drawMerchant(ctx, px, py, S)    { drawNPCSprite(ctx, px, py, "merchant", S); }
function drawElder(ctx, px, py, S)       { drawNPCSprite(ctx, px, py, "elder", S); }
function drawFisher(ctx, px, py, S)      { drawNPCSprite(ctx, px, py, "fisher", S); }
function drawAmara(ctx, px, py, S)       { drawNPCSprite(ctx, px, py, "amara", S); }

// ---------------------------------------------------------------------------
// Monster sprites — data-driven
// ---------------------------------------------------------------------------
function drawMonsterSprite(ctx, px, py, kind, hopFrame, S) {
  const sprite = MONSTER_SPRITE_DATA[kind];
  if (!sprite) return;
  const frame = hopFrame % sprite.frames.length;
  const yOffset = sprite.yOff ? sprite.yOff[frame] * S : 0;
  drawLayers(ctx, px, py + yOffset, sprite.frames[frame], S, sprite.colors);
}

function drawMonsterDeath(ctx, px, py, kind, deathFrame, S) {
  const sprite = DEATH_SPRITE_DATA[kind];
  if (!sprite) return;
  const frame = sprite.frames[Math.min(deathFrame, sprite.frames.length - 1)];
  if (frame.alpha != null) {
    ctx.globalAlpha = frame.alpha;
    drawLayers(ctx, px, py, frame.layers, S, sprite.colors);
    ctx.globalAlpha = 1;
  } else {
    drawLayers(ctx, px, py, frame, S, sprite.colors);
  }
}

// Named exports for backward compatibility
function drawSlime(ctx, px, py, hopFrame, S)      { drawMonsterSprite(ctx, px, py, "slime", hopFrame, S); }
function drawBat(ctx, px, py, hopFrame, S)        { drawMonsterSprite(ctx, px, py, "bat", hopFrame, S); }
function drawScorpion(ctx, px, py, hopFrame, S)   { drawMonsterSprite(ctx, px, py, "scorpion", hopFrame, S); }
function drawSkeleton(ctx, px, py, hopFrame, S)   { drawMonsterSprite(ctx, px, py, "skeleton", hopFrame, S); }
function drawSwampBlob(ctx, px, py, hopFrame, S)  { drawMonsterSprite(ctx, px, py, "swamp_blob", hopFrame, S); }

function drawSlimeDeath(ctx, px, py, deathFrame, S)      { drawMonsterDeath(ctx, px, py, "slime", deathFrame, S); }
function drawBatDeath(ctx, px, py, deathFrame, S)        { drawMonsterDeath(ctx, px, py, "bat", deathFrame, S); }
function drawScorpionDeath(ctx, px, py, deathFrame, S)   { drawMonsterDeath(ctx, px, py, "scorpion", deathFrame, S); }
function drawSkeletonDeath(ctx, px, py, deathFrame, S)   { drawMonsterDeath(ctx, px, py, "skeleton", deathFrame, S); }
function drawSwampBlobDeath(ctx, px, py, deathFrame, S)  { drawMonsterDeath(ctx, px, py, "swamp_blob", deathFrame, S); }

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

function drawHeartPickup(ctx, px, py, bounceFrame, S) {
  const yOff = bounceFrame % 2 === 0 ? 0 : -2*S;
  drawHeart(ctx, px + 2*S, py + 2*S + yOff, "full", S * 0.7);
}
