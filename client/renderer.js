/* Rendering — all render* and update* functions for the game loop. */

const DANCE_FRAME_MS = 200;
const DYING_MONSTER_FRAME_MS = 150;
const SWORD_PICKUP_FRAME_MS = 200;
const SWORD_PICKUP_FRAMES = 4;
const ATTACK_FRAME_MS = 150;
const ATTACK_FRAMES = 2;
const DYING_PLAYER_FRAME_MS = 200;

// matches server WALKABLE_TILES (numeric IDs + string tile codes)
const WALKABLE = new Set([0, 1, 2, 7, 8, 9, 10, 15, 16, 19, 20, 22, 26, 27, 28, 30, 33,
  "GR", "ST", "WD", "FL", "DT", "SU", "SD", "DR", "SW", "DF", "MF", "CF", 37, 38]);

function renderRoom() {
  if (!G.currentRoom) return;
  const tm = G.currentRoom.tilemap;
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      G.ctx.drawImage(getTileCanvas(tm[r][c], TS, TILE, SCALE), c * TS, r * TS);
    }
  }
}

function startDance(name) {
  G.dancingPlayers[name] = { frame: 0, nextTime: Date.now() };
  G.speechBubbles.push({
    from: name,
    text: "* dances *",
    expires: Date.now() + 3000,
  });
}

function stopDance(name) {
  delete G.dancingPlayers[name];
}

function updateDances() {
  const now = Date.now();
  for (const [name, d] of Object.entries(G.dancingPlayers)) {
    if (now >= d.nextTime) {
      d.frame++;
      d.nextTime = now + DANCE_FRAME_MS;
    }
  }
}

function updateDyingMonsters() {
  const now = Date.now();
  G.dyingMonsters = G.dyingMonsters.filter(dm => {
    if (now >= dm.nextTime) {
      dm.frame++;
      dm.nextTime = now + DYING_MONSTER_FRAME_MS;
    }
    return dm.frame < 3;
  });
}

function updateSwordPickups() {
  const now = Date.now();
  G.swordPickups = G.swordPickups.filter(sp => {
    if (now >= sp.nextTime) {
      sp.frame++;
      sp.nextTime = now + SWORD_PICKUP_FRAME_MS;
    }
    return sp.frame < SWORD_PICKUP_FRAMES;
  });
}

function updateProjectiles() {
  for (const p of G.projectiles) {
    p.displayX += (p.x - p.displayX) * 0.4;
    p.displayY += (p.y - p.displayY) * 0.4;
    if (Math.abs(p.x - p.displayX) < 0.05) p.displayX = p.x;
    if (Math.abs(p.y - p.displayY) < 0.05) p.displayY = p.y;
  }
}

function updateAttackEffects() {
  const now = Date.now();
  G.areaWarnings = G.areaWarnings.filter(w => now - w.startTime < w.duration);
  G.chargeTrails = G.chargeTrails.filter(t => now - t.startTime < 400);
  G.chargePreps = G.chargePreps.filter(p => now - p.startTime < 2000);
  G.monsterAttackFlashes = G.monsterAttackFlashes.filter(f => now - f.startTime < 200);
}

function renderProjectiles() {
  for (const p of G.projectiles) {
    const px = p.displayX * TS + TS / 2;
    const py = p.displayY * TS + TS / 2;
    const r = 3 * SCALE;
    // Glow
    G.ctx.globalAlpha = 0.3;
    G.ctx.fillStyle = p.color;
    G.ctx.beginPath();
    G.ctx.arc(px, py, r * 2, 0, Math.PI * 2);
    G.ctx.fill();
    // Core
    G.ctx.globalAlpha = 1;
    G.ctx.fillStyle = p.color;
    G.ctx.beginPath();
    G.ctx.arc(px, py, r, 0, Math.PI * 2);
    G.ctx.fill();
  }
}

function renderAreaWarnings() {
  const now = Date.now();
  for (const w of G.areaWarnings) {
    const elapsed = now - w.startTime;
    const progress = elapsed / w.duration;
    const pulse = 0.15 + 0.15 * Math.sin(elapsed / 80);
    G.ctx.globalAlpha = pulse;
    G.ctx.fillStyle = progress > 0.85 ? "#ff4400" : "#ff8800";
    for (let dy = -w.range; dy <= w.range; dy++) {
      for (let dx = -w.range; dx <= w.range; dx++) {
        if (Math.abs(dx) + Math.abs(dy) <= w.range) {
          const tx = w.x + dx, ty = w.y + dy;
          if (tx >= 0 && tx < COLS && ty >= 0 && ty < ROWS) {
            G.ctx.fillRect(tx * TS, ty * TS, TS, TS);
          }
        }
      }
    }
    G.ctx.globalAlpha = 1;
  }
}

function renderChargePreps() {
  const now = Date.now();
  for (const p of G.chargePreps) {
    const age = now - p.startTime;
    const pulse = 0.25 + 0.15 * Math.sin(age / 80);
    G.ctx.globalAlpha = pulse;
    G.ctx.fillStyle = "#ff4422";
    for (const [tx, ty] of p.lane) {
      G.ctx.fillRect(tx * TS + 1*SCALE, ty * TS + 1*SCALE, TS - 2*SCALE, TS - 2*SCALE);
    }
    G.ctx.globalAlpha = 1;
  }
}

function renderChargeTrails() {
  const now = Date.now();
  for (const t of G.chargeTrails) {
    const age = now - t.startTime;
    const alpha = Math.max(0, 0.5 - age / 800);
    G.ctx.globalAlpha = alpha;
    G.ctx.fillStyle = "#ffcc44";
    for (const [tx, ty] of t.path) {
      G.ctx.fillRect(tx * TS + 2*SCALE, ty * TS + 2*SCALE, TS - 4*SCALE, TS - 4*SCALE);
    }
    G.ctx.globalAlpha = 1;
  }
}

function renderMonsterAttackFlashes() {
  const now = Date.now();
  for (const f of G.monsterAttackFlashes) {
    const age = now - f.startTime;
    const alpha = Math.max(0, 0.6 - age / 333);
    G.ctx.globalAlpha = alpha;
    G.ctx.fillStyle = "#ffffff";
    G.ctx.fillRect(f.x * TS, f.y * TS, TS, TS);
    G.ctx.globalAlpha = 1;
  }
}

function updateDyingOtherPlayers() {
  const now = Date.now();
  for (const [name, dp] of Object.entries(G.dyingOtherPlayers)) {
    if (now >= dp.nextTime) {
      dp.frame++;
      dp.nextTime = now + DYING_PLAYER_FRAME_MS;
    }
    if (dp.frame > 5) {
      delete G.dyingOtherPlayers[name];
    }
  }
}

function renderHeartPickups() {
  for (const h of G.heartPickups) {
    const bounceFrame = Math.floor(Date.now() / 400) % 2;
    drawHeartPickup(G.ctx, h.x * TS, h.y * TS, bounceFrame, SCALE);
  }
}

function renderDeathAnimation() {
  if (!G.dyingPlayerSelf) return;
  const elapsed = Date.now() - G.dyingPlayerSelf.startTime;
  const duration = 5000;

  if (elapsed >= duration) return;

  const px = G.dyingPlayerSelf.x * TS;
  const py = G.dyingPlayerSelf.y * TS;

  if (elapsed < 1000) {
    const dirs = ["down", "left", "up", "right"];
    const spinDir = dirs[Math.floor(elapsed / 80) % 4];
    const playerAlpha = Math.max(0, 1 - elapsed / 1000);
    G.ctx.globalAlpha = playerAlpha;
    drawPlayer(G.ctx, px, py, spinDir, G.myColorIndex, 0, SCALE);
    G.ctx.globalAlpha = 1;
    G.ctx.fillStyle = `rgba(0,0,0,${elapsed / 1000 * 0.7})`;
    G.ctx.fillRect(0, 0, CW, CH);
  } else if (elapsed < 1500) {
    const blackAlpha = 0.7 + 0.3 * ((elapsed - 1000) / 500);
    G.ctx.fillStyle = `rgba(0,0,0,${blackAlpha})`;
    G.ctx.fillRect(0, 0, CW, CH);
  } else {
    G.ctx.fillStyle = "rgba(0,0,0,1)";
    G.ctx.fillRect(0, 0, CW, CH);
  }

  if (elapsed > 800) {
    const textAlpha = Math.min(1, (elapsed - 800) / 500);
    G.ctx.globalAlpha = textAlpha;
    G.ctx.font = "bold 28px monospace";
    G.ctx.fillStyle = "#cc3333";
    const txt = "You died!";
    const tw = G.ctx.measureText(txt).width;
    G.ctx.fillText(txt, CW/2 - tw/2, CH/2);
    G.ctx.globalAlpha = 1;
  }
}

function startAttack(name, direction) {
  stopDance(name);
  G.attackingPlayers[name] = { direction, frame: 0, nextTime: Date.now() + ATTACK_FRAME_MS };
}

function updateAttacks() {
  const now = Date.now();
  for (const [name, a] of Object.entries(G.attackingPlayers)) {
    if (now >= a.nextTime) {
      a.frame++;
      if (a.frame >= ATTACK_FRAMES) {
        delete G.attackingPlayers[name];
      } else {
        a.nextTime = now + ATTACK_FRAME_MS;
      }
    }
  }
}

function renderPlayers() {
  if (!G.myPlayer) return;

  const all = [];
  if (!G.dyingPlayerSelf) {
    let skipSelf = false;
    if (Date.now() < G.invincibleUntil) {
      skipSelf = Math.floor(Date.now() / 100) % 2 === 1;
    }
    if (!skipSelf) {
      all.push({
        name: G.myName,
        x: G.displayX,
        y: G.displayY,
        direction: G.myPlayer.direction,
        color_index: G.myPlayer.color_index,
        hurtFlash: Date.now() < G.hurtFlash,
      });
    }
  }
  for (const [name, p] of Object.entries(G.otherPlayers)) {
    all.push({
      name: name,
      x: p.displayX,
      y: p.displayY,
      direction: p.direction,
      color_index: p.color_index,
      hurtFlash: p.hurtFlash && Date.now() < p.hurtFlash,
    });
  }

  for (const g of G.guards) {
    all.push({ name: g.name, x: g.x, y: g.y, isGuard: true, sprite: g.sprite || "guard" });
  }

  for (const m of G.monsters) {
    all.push({ x: m.displayX, y: m.displayY, isMonster: true, kind: m.kind, hitFlash: m.hitFlash, teleportAlpha: m.teleportAlpha, chargePrep: m.chargePrep });
  }

  all.sort((a, b) => a.y - b.y);

  for (const dm of G.dyingMonsters) {
    const dx = dm.x * TS, dy = dm.y * TS;
    drawMonsterDeath(G.ctx, dx, dy, dm.kind, dm.frame, SCALE);
  }

  for (const p of all) {
    const px = p.x * TS;
    const py = p.y * TS;
    if (p.isMonster) {
      let shakeX = 0;
      if (p.chargePrep) {
        shakeX = Math.round(Math.sin(Date.now() / 30) * 2) * SCALE;
      }
      if (p.teleportAlpha !== undefined && p.teleportAlpha < 1) {
        G.ctx.globalAlpha = Math.max(0, p.teleportAlpha);
      }
      drawMonsterSprite(G.ctx, px + shakeX, py, p.kind, G.monsterHopFrame, SCALE);
      G.ctx.globalAlpha = 1;
      if (p.hitFlash && Date.now() < p.hitFlash) {
        G.ctx.globalAlpha = 0.5;
        G.ctx.fillStyle = "#ffffff";
        G.ctx.fillRect(px, py, TS, TS);
        G.ctx.globalAlpha = 1;
      }
      continue;
    } else if (p.isGuard) {
      drawNPC(G.ctx, px, py, p.sprite, SCALE);
    } else if (G.attackingPlayers[p.name]) {
      const atk = G.attackingPlayers[p.name];
      drawPlayerAttack(G.ctx, px, py, atk.direction, p.color_index, atk.frame, SCALE);
      drawSwordAttack(G.ctx, px, py, atk.direction, atk.frame, SCALE);
    } else if (G.dancingPlayers[p.name]) {
      drawPlayerDance(G.ctx, px, py, p.color_index, G.dancingPlayers[p.name].frame, SCALE);
    } else {
      const moving = (p.name === G.myName) ? G.isMoving : (G.otherPlayers[p.name]?.moving || false);
      drawPlayer(G.ctx, px, py, p.direction, p.color_index, moving ? G.animFrame : 0, SCALE);
    }

    if (p.hurtFlash) {
      G.ctx.globalAlpha = 0.4;
      G.ctx.fillStyle = "#ff0000";
      G.ctx.fillRect(px + 3*SCALE, py, 10*SCALE, 15*SCALE);
      G.ctx.globalAlpha = 1;
    }

    G.ctx.font = "bold 11px monospace";
    const tw = G.ctx.measureText(p.name).width;
    const labelX = px + TS / 2 - tw / 2;
    const labelY = py - 6;
    G.ctx.fillStyle = "rgba(0,0,0,0.6)";
    G.ctx.fillRect(labelX - 3, labelY - 10, tw + 6, 14);
    G.ctx.fillStyle = "#fff";
    G.ctx.fillText(p.name, labelX, labelY);
  }

  for (const [name, dp] of Object.entries(G.dyingOtherPlayers)) {
    const dpx = dp.x * TS;
    const dpy = dp.y * TS;
    drawPlayerFallOver(G.ctx, dpx, dpy, dp.color_index, dp.frame, SCALE);
  }
}

function renderSpeechBubbles() {
  const now = Date.now();
  G.speechBubbles = G.speechBubbles.filter(b => now < b.expires);

  for (const bubble of G.speechBubbles) {
    let px, py;
    if (bubble.from === G.myName) {
      px = G.displayX * TS + TS / 2;
      py = G.displayY * TS - 16;
    } else if (G.otherPlayers[bubble.from]) {
      const p = G.otherPlayers[bubble.from];
      px = p.displayX * TS + TS / 2;
      py = p.displayY * TS - 16;
    } else {
      const guard = G.guards.find(g => g.name === bubble.from);
      if (guard) {
        px = guard.x * TS + TS / 2;
        py = guard.y * TS - 16;
      } else {
        continue;
      }
    }

    const timeLeft = bubble.expires - now;
    const alpha = timeLeft < 500 ? timeLeft / 500 : 1;
    G.ctx.globalAlpha = alpha;

    G.ctx.font = "11px monospace";
    const maxWidth = 200;
    const words = bubble.text.split(" ");
    const lines = [];
    let line = "";
    for (const word of words) {
      const test = line ? line + " " + word : word;
      if (G.ctx.measureText(test).width > maxWidth) {
        if (line) lines.push(line);
        line = word;
      } else {
        line = test;
      }
    }
    if (line) lines.push(line);
    if (lines.length > 3) lines.length = 3;

    const lineHeight = 14;
    const pad = 6;
    const bw = Math.min(maxWidth, Math.max(...lines.map(l => G.ctx.measureText(l).width))) + pad * 2;
    const bh = lines.length * lineHeight + pad * 2;
    const bx = px - bw / 2;
    const by = py - bh - 8;

    G.ctx.fillStyle = "rgba(255,255,255,0.95)";
    G.ctx.beginPath();
    roundRect(G.ctx, bx, by, bw, bh, 6);
    G.ctx.fill();

    G.ctx.beginPath();
    G.ctx.moveTo(px - 5, by + bh);
    G.ctx.lineTo(px, by + bh + 6);
    G.ctx.lineTo(px + 5, by + bh);
    G.ctx.fill();

    G.ctx.strokeStyle = "rgba(0,0,0,0.2)";
    G.ctx.lineWidth = 1;
    G.ctx.beginPath();
    roundRect(G.ctx, bx, by, bw, bh, 6);
    G.ctx.stroke();

    G.ctx.fillStyle = "#111";
    for (let i = 0; i < lines.length; i++) {
      G.ctx.fillText(lines[i], bx + pad, by + pad + 10 + i * lineHeight);
    }

    G.ctx.globalAlpha = 1;
  }
}

function renderSwordPickups() {
  for (const sp of G.swordPickups) {
    drawSwordPickup(G.ctx, sp.x * TS, sp.y * TS, sp.frame, SCALE);
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
  if (!G.currentRoom) return;

  G.ctx.font = "bold 13px monospace";
  const name = G.currentRoom.name;
  const tw = G.ctx.measureText(name).width;
  G.ctx.fillStyle = "rgba(0,0,0,0.6)";
  G.ctx.fillRect(8, 8, tw + 16, 22);
  G.ctx.fillStyle = "#e6b422";
  G.ctx.fillText(name, 16, 24);

  const version = "v0.6";
  G.ctx.font = "10px monospace";
  const vw = G.ctx.measureText(version).width;
  G.ctx.fillStyle = "rgba(255,255,255,0.3)";
  G.ctx.fillText(version, CW - vw - 10, 20);

  const exits = getExitDirs();
  G.ctx.font = "bold 20px monospace";
  G.ctx.fillStyle = "rgba(255,255,255,0.4)";
  if (exits.has("north")) G.ctx.fillText("\u25B2", CW/2 - 8, 20);
  if (exits.has("south")) G.ctx.fillText("\u25BC", CW/2 - 8, CH - 6);
  if (exits.has("west"))  G.ctx.fillText("\u25C0", 4, CH/2 + 6);
  if (exits.has("east"))  G.ctx.fillText("\u25B6", CW - 18, CH/2 + 6);

  const now = Date.now();
  G.infoMessages = G.infoMessages.filter(m => now < m.expires);
  G.ctx.font = "12px monospace";
  for (let i = 0; i < G.infoMessages.length; i++) {
    const msg = G.infoMessages[i];
    const alpha = Math.min(1, (msg.expires - now) / 1000);
    G.ctx.globalAlpha = alpha;
    G.ctx.fillStyle = "rgba(0,0,0,0.7)";
    const mw = G.ctx.measureText(msg.text).width;
    G.ctx.fillRect(CW/2 - mw/2 - 8, CH - 60 - i*20, mw + 16, 18);
    G.ctx.fillStyle = "#79c0ff";
    G.ctx.fillText(msg.text, CW/2 - mw/2, CH - 47 - i*20);
    G.ctx.globalAlpha = 1;
  }

  if (G.showDebug && G.debugLog.length > 0) {
    G.ctx.font = "9px monospace";
    const lineH = 12;
    const padding = 4;
    const boxH = G.debugLog.length * lineH + padding * 2;
    G.ctx.fillStyle = "rgba(0,0,0,0.75)";
    G.ctx.fillRect(4, CH - boxH - 4, CW - 8, boxH);
    G.ctx.fillStyle = "#0f0";
    for (let i = 0; i < G.debugLog.length; i++) {
      G.ctx.fillText(G.debugLog[i], 8, CH - boxH + padding + (i + 1) * lineH - 2);
    }
  }
}

function renderHeartsHUD() {
  const heartScale = SCALE * 0.45;
  const heartW = 12 * heartScale + 2;
  const heartStartX = CW - 3 * heartW - 14;
  for (let i = 0; i < 3; i++) {
    const hpForHeart = G.myHp - i * 2;
    let state = "empty";
    if (hpForHeart >= 2) state = "full";
    else if (hpForHeart === 1) state = "half";
    drawHeart(G.ctx, heartStartX + i * heartW, 8, state, heartScale);
  }
}

function getExitDirs() {
  if (!G.currentRoom || !G.currentRoom.room_id) return new Set();
  const tm = G.currentRoom.tilemap;
  const dirs = new Set();
  const w = (t) => WALKABLE.has(t);
  if (w(tm[0][6]) || w(tm[0][7]) || w(tm[0][8])) dirs.add("north");
  if (w(tm[10][6]) || w(tm[10][7]) || w(tm[10][8])) dirs.add("south");
  if (w(tm[4][0]) || w(tm[5][0]) || w(tm[6][0])) dirs.add("west");
  if (w(tm[4][14]) || w(tm[5][14]) || w(tm[6][14])) dirs.add("east");
  return dirs;
}

function renderTransition(now) {
  if (!G.transition) return;
  const elapsed = now - G.transition.startTime;
  const progress = Math.min(1, elapsed / G.transition.duration);

  if (G.transition.type === "fade") {
    if (progress < 0.5) {
      G.ctx.drawImage(G.transition.oldCanvas, 0, 0);
      G.ctx.fillStyle = `rgba(0,0,0,${progress * 2})`;
      G.ctx.fillRect(0, 0, CW, CH);
    } else {
      renderRoom();
      renderPlayers();
      renderUI();
      G.ctx.fillStyle = `rgba(0,0,0,${(1 - progress) * 2})`;
      G.ctx.fillRect(0, 0, CW, CH);
    }
  } else {
    const dir = G.transition.direction;
    let ox = 0, oy = 0;
    if (dir === "north") oy =  CH * progress;
    if (dir === "south") oy = -CH * progress;
    if (dir === "west")  ox =  CW * progress;
    if (dir === "east")  ox = -CW * progress;

    G.ctx.save();
    if (dir === "north") G.ctx.translate(0, oy - CH);
    if (dir === "south") G.ctx.translate(0, oy + CH);
    if (dir === "west")  G.ctx.translate(ox - CW, 0);
    if (dir === "east")  G.ctx.translate(ox + CW, 0);
    renderRoom();
    renderPlayers();
    renderUI();
    G.ctx.restore();

    G.ctx.drawImage(G.transition.oldCanvas, ox, oy);
  }

  if (progress >= 1) {
    G.transition = null;
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
  if (!G.conjuring) return false;
  const elapsed = now - G.conjuring.startTime;
  const t = elapsed / 1000; // seconds

  // Dark background
  G.ctx.fillStyle = "#0a0a12";
  G.ctx.fillRect(0, 0, CW, CH);

  // Flickering torchlight — two torch sources
  const torches = [
    { x: CW * 0.25, y: CH * 0.4 },
    { x: CW * 0.75, y: CH * 0.4 },
  ];
  for (const torch of torches) {
    const flicker = 0.3 + 0.15 * Math.sin(t * 8.3) + 0.1 * Math.sin(t * 13.7);
    const r = 80 + 30 * Math.sin(t * 5.1);
    const grad = G.ctx.createRadialGradient(torch.x, torch.y, 0, torch.x, torch.y, r);
    grad.addColorStop(0, `rgba(255, 170, 50, ${flicker * 0.4})`);
    grad.addColorStop(0.6, `rgba(200, 100, 20, ${flicker * 0.15})`);
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");
    G.ctx.fillStyle = grad;
    G.ctx.fillRect(0, 0, CW, CH);

    // Torch flame
    const fw = 6 + 2 * Math.sin(t * 9);
    const fh = 12 + 4 * Math.sin(t * 7);
    G.ctx.fillStyle = `rgba(255, 200, 60, ${0.6 + 0.3 * Math.sin(t * 11)})`;
    G.ctx.fillRect(torch.x - fw/2, torch.y - fh, fw, fh);
    G.ctx.fillStyle = `rgba(255, 100, 20, ${0.4 + 0.2 * Math.sin(t * 8)})`;
    G.ctx.fillRect(torch.x - fw/2 - 1, torch.y - fh * 0.6, fw + 2, fh * 0.6);
  }

  // Drifting particles
  const seed = G.conjuring.startTime;
  for (let i = 0; i < 12; i++) {
    const px = ((seed * 7 + i * 137) % CW);
    const py = CH - ((t * 30 + i * 50) % CH);
    const alpha = 0.2 + 0.3 * Math.sin(t * 2 + i);
    const size = 1 + (i % 3);
    G.ctx.fillStyle = `rgba(180, 160, 120, ${alpha})`;
    G.ctx.fillRect(px + Math.sin(t * 1.5 + i * 0.7) * 10, py, size, size);
  }

  // Atmospheric text
  const textIdx = Math.floor(t / 2) % CONJURE_TEXTS.length;
  const textAlpha = 0.5 + 0.3 * Math.sin(t * 2);
  G.ctx.font = "18px monospace";
  G.ctx.fillStyle = `rgba(180, 170, 140, ${textAlpha})`;
  G.ctx.textAlign = "center";
  G.ctx.fillText(CONJURE_TEXTS[textIdx], CW / 2, CH * 0.65);

  // Debug progress steps (sent when DEBUG_MODE is on)
  const steps = G.conjuring.progressSteps;
  if (steps && steps.length > 0) {
    // Backend/model header (from "init" step) — persistent dim text
    const initStep = steps.find(s => s.step === "init");
    if (initStep) {
      G.ctx.font = "10px monospace";
      G.ctx.fillStyle = "rgba(120, 120, 100, 0.5)";
      G.ctx.fillText(initStep.detail, CW / 2, CH * 0.73);
    }

    // Generation steps (skip "init")
    G.ctx.font = "12px monospace";
    const work = steps.filter(s => s.step !== "init");
    const visible = work.slice(-5);
    for (let i = 0; i < visible.length; i++) {
      const s = visible[i];
      const age = (Date.now() - s.time) / 1000;
      const isLatest = i === visible.length - 1;
      // Latest step pulses, older steps are dim
      const a = isLatest ? 0.5 + 0.3 * Math.sin(t * 3) : Math.max(0.15, 0.4 - age * 0.03);
      const prefix = isLatest ? "> " : "  ";
      G.ctx.fillStyle = isLatest
        ? `rgba(120, 220, 160, ${a})`
        : `rgba(140, 140, 120, ${a})`;
      G.ctx.fillText(prefix + s.detail, CW / 2, CH * 0.77 + i * 16);
    }
  }

  G.ctx.textAlign = "start";

  return true; // signal that conjuring is active
}

function renderDungeonDebug() {
  if (!G.showDebug || !G.dungeonDebug) return;
  const d = G.dungeonDebug;
  const lines = [];
  if (d.room_source) lines.push("src: " + d.room_source);
  if (d.lib_rooms) lines.push("rooms: " + d.lib_rooms);
  if (d.lib_monsters) lines.push("monsters: " + d.lib_monsters);
  if (d.lib_tiles) lines.push("tiles: " + d.lib_tiles);
  if (lines.length === 0) return;

  G.ctx.font = "9px monospace";
  const lineH = 12;
  const padding = 4;
  const boxW = 200;
  const boxH = lines.length * lineH + padding * 2;
  const boxX = CW - boxW - 4;
  const boxY = 24;

  G.ctx.fillStyle = "rgba(0,0,0,0.75)";
  G.ctx.fillRect(boxX, boxY, boxW, boxH);
  G.ctx.fillStyle = "#8af";
  for (let i = 0; i < lines.length; i++) {
    G.ctx.fillText(lines[i], boxX + padding, boxY + padding + (i + 1) * lineH - 2);
  }

  // Library icons with actual sprites/tiles (just below the room name)
  const libs = d.libraries;
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
      G.ctx.font = "8px monospace";
      G.ctx.fillStyle = "rgba(180, 180, 160, 0.7)";
      G.ctx.fillText(label, lx, nextY);
      nextY += 3;
      let idx = 0;
      for (let i = 0; i < items.length; i++, idx++) {
        const col = idx % perRow, row = Math.floor(idx / perRow);
        const ix = lx + (iconS + iconG) * col;
        const iy = nextY + (iconS + iconG) * row;
        G.ctx.fillStyle = "#0a0a12";
        G.ctx.fillRect(ix, iy, iconS, iconS);
        drawIcon(items[i], ix, iy);
        G.ctx.strokeStyle = statusBorder[items[i].s] || "#888";
        G.ctx.lineWidth = 1.5;
        G.ctx.strokeRect(ix + 0.5, iy + 0.5, iconS - 1, iconS - 1);
      }
      for (let i = 0; i < emptyCount; i++, idx++) {
        const col = idx % perRow, row = Math.floor(idx / perRow);
        const ix = lx + (iconS + iconG) * col;
        const iy = nextY + (iconS + iconG) * row;
        G.ctx.fillStyle = "#0a0a12";
        G.ctx.fillRect(ix, iy, iconS, iconS);
        G.ctx.strokeStyle = "#333";
        G.ctx.lineWidth = 1;
        G.ctx.setLineDash([2, 2]);
        G.ctx.strokeRect(ix + 0.5, iy + 0.5, iconS - 1, iconS - 1);
        G.ctx.setLineDash([]);
      }
      G.ctx.lineWidth = 1;
      const rows = Math.ceil((items.length + emptyCount) / perRow);
      nextY += rows * (iconS + iconG) + rowG - iconG;
    }

    // Monster icons
    drawIconGrid(libs.monsters || [], libs.monster_empty || 0, "monsters", (m, ix, iy) => {
      drawMonsterSprite(G.ctx, ix, iy, m.id, 0, 1);
    });

    // Tile icons
    drawIconGrid(libs.tiles || [], libs.tile_empty || 0, "tiles", (ti, ix, iy) => {
      const tc = getTileCanvas(ti.id, TS, TILE, SCALE);
      if (tc) {
        G.ctx.imageSmoothingEnabled = false;
        G.ctx.drawImage(tc, 0, 0, tc.width, tc.height, ix, iy, iconS, iconS);
        G.ctx.imageSmoothingEnabled = true;
      } else {
        G.ctx.fillStyle = ti.color;
        G.ctx.fillRect(ix, iy, iconS, iconS);
      }
    });
  }
}

function renderDungeonMinimap() {
  if (!G.showDebug) return;
  const mm = G.dungeonDebug && G.dungeonDebug.minimap;
  if (!mm || !mm.cells || mm.cells.length === 0) return;

  const cells = mm.cells;
  const pc = mm.player; // [col, row] of player's current cell

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
  G.ctx.fillStyle = "rgba(0, 0, 0, 0.55)";
  roundRect(G.ctx, mapX, mapY, mapW, mapH, 4);
  G.ctx.fill();

  // Draw each cell
  for (const cell of cells) {
    const cx = mapX + pad + (cell.c - minC) * step;
    const cy = mapY + pad + (cell.r - minR) * step;

    // Color based on state
    if (!cell.res && !cell.gen) {
      // Unresolved placeholder — dashed outline, no fill
      G.ctx.strokeStyle = "rgba(100, 100, 100, 0.6)";
      G.ctx.setLineDash([2, 2]);
      G.ctx.strokeRect(cx + 0.5, cy + 0.5, cellSize - 1, cellSize - 1);
      G.ctx.setLineDash([]);
    } else if (!cell.res) {
      // Unresolved but has content — dim outline
      G.ctx.strokeStyle = "rgba(140, 140, 100, 0.7)";
      G.ctx.strokeRect(cx + 0.5, cy + 0.5, cellSize - 1, cellSize - 1);
    } else if (cell.src === "precreated") {
      // Resolved precreated — blue
      G.ctx.fillStyle = "rgba(80, 140, 220, 0.7)";
      G.ctx.fillRect(cx, cy, cellSize, cellSize);
    } else {
      // Resolved custom — green
      G.ctx.fillStyle = "rgba(80, 200, 120, 0.7)";
      G.ctx.fillRect(cx, cy, cellSize, cellSize);
    }

    // Entrance marker — small diamond
    if (cell.ent) {
      G.ctx.fillStyle = "rgba(255, 220, 80, 0.9)";
      const mx = cx + cellSize / 2, my = cy + cellSize / 2;
      G.ctx.beginPath();
      G.ctx.moveTo(mx, my - 3);
      G.ctx.lineTo(mx + 3, my);
      G.ctx.lineTo(mx, my + 3);
      G.ctx.lineTo(mx - 3, my);
      G.ctx.closePath();
      G.ctx.fill();
    }
  }

  // Player position — pulsing white border
  if (pc) {
    const px = mapX + pad + (pc[0] - minC) * step;
    const py = mapY + pad + (pc[1] - minR) * step;
    const pulse = 0.6 + 0.4 * Math.sin(Date.now() / 200);
    G.ctx.strokeStyle = `rgba(255, 255, 255, ${pulse})`;
    G.ctx.lineWidth = 2;
    G.ctx.strokeRect(px - 1, py - 1, cellSize + 2, cellSize + 2);
    G.ctx.lineWidth = 1;
  }

  // Legend — tiny text below the map
  G.ctx.font = "7px monospace";
  G.ctx.fillStyle = "rgba(180, 180, 180, 0.6)";
  G.ctx.fillText(mm.layout, mapX + pad, mapY + mapH + 8);
}
