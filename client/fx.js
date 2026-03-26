/* fx.js — Juice/game-feel effects system.
   Particle system, screen shake, slash arcs, floating texts,
   corpses, damage vignette, camera lead.
   Loaded between renderer.js and net.js. */

const PARTICLE_CAP = 100;
const SLASH_ARC_DURATION = 150;
const FLOATING_TEXT_DURATION = 600;
const FLOATING_TEXT_RISE = 30;
const VIGNETTE_DURATION = 300;
const CORPSE_CAP = 20;
const SPAWN_POP_DURATION = 300;

// Direction vectors for camera lead
const DIR_VECTORS = {
  up:    { x:  0, y: -1 },
  down:  { x:  0, y:  1 },
  left:  { x: -1, y:  0 },
  right: { x:  1, y:  0 },
};

// ── Particle System ──────────────────────────────────────────────

function spawnParticle(x, y, vx, vy, life, color, size, opts) {
  if (G.fx.particles.length >= PARTICLE_CAP) G.fx.particles.shift();
  G.fx.particles.push({
    x, y, vx, vy,
    life, maxLife: life,
    color, size,
    gravity: (opts && opts.gravity) || 0,
    shrink: (opts && opts.shrink) || false,
  });
}

function spawnBurst(cx, cy, count, speed, life, colors, sizeRange, opts) {
  for (let i = 0; i < count; i++) {
    const angle = (Math.PI * 2 * i / count) + (Math.random() - 0.5) * 0.8;
    const spd = speed * (0.5 + Math.random() * 0.5);
    const color = colors[Math.floor(Math.random() * colors.length)];
    const size = sizeRange[0] + Math.random() * (sizeRange[1] - sizeRange[0]);
    spawnParticle(cx, cy, Math.cos(angle) * spd, Math.sin(angle) * spd,
      life, color, size, opts);
  }
}

function updateParticles(dt) {
  for (let i = G.fx.particles.length - 1; i >= 0; i--) {
    const p = G.fx.particles[i];
    p.x += p.vx;
    p.y += p.vy;
    if (p.gravity) p.vy += p.gravity;
    p.life -= dt;
    if (p.life <= 0) {
      G.fx.particles.splice(i, 1);
    }
  }
}

function renderParticles() {
  const ctx = G.ui.ctx;
  for (const p of G.fx.particles) {
    const alpha = Math.max(0, p.life / p.maxLife);
    const size = p.shrink ? p.size * alpha : p.size;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = p.color;
    ctx.fillRect(p.x - size / 2, p.y - size / 2, size, size);
  }
  ctx.globalAlpha = 1;
}

// ── Screen Shake ─────────────────────────────────────────────────

function triggerShake(intensity, durationMs) {
  // Only override if new shake is stronger or current is done
  if (G.fx.screenShake) {
    const elapsed = Date.now() - G.fx.screenShake.startTime;
    const remaining = G.fx.screenShake.duration - elapsed;
    const currentIntensity = G.fx.screenShake.intensity * Math.max(0, 1 - elapsed / G.fx.screenShake.duration);
    if (remaining > 0 && currentIntensity >= intensity) return;
  }
  G.fx.screenShake = { startTime: Date.now(), duration: durationMs, intensity };
}

function applyScreenShake() {
  if (!G.fx.screenShake) {
    G.ui.canvas.style.transform = "";
    return;
  }
  const elapsed = Date.now() - G.fx.screenShake.startTime;
  if (elapsed > G.fx.screenShake.duration) {
    G.fx.screenShake = null;
    G.ui.canvas.style.transform = "";
    return;
  }
  const decay = 1 - elapsed / G.fx.screenShake.duration;
  const intensity = G.fx.screenShake.intensity * decay;
  const sx = Math.round(Math.sin(elapsed * 0.05) * intensity) * SCALE;
  const sy = Math.round(Math.cos(elapsed * 0.07) * intensity) * SCALE;
  G.ui.canvas.style.transform = `translate(${sx}px, ${sy}px)`;
}

// ── Sword Slash Arc ──────────────────────────────────────────────

function spawnSlashArc(direction) {
  if (!G.player.myPlayer) return;
  const dx = DIR_VECTORS[direction] ? DIR_VECTORS[direction].x : 0;
  const dy = DIR_VECTORS[direction] ? DIR_VECTORS[direction].y : 0;
  G.fx.slashArcs.push({
    x: G.player.displayX + dx,
    y: G.player.displayY + dy,
    direction,
    startTime: Date.now(),
  });
}

const ARC_ANGLES = {
  down:  { start: Math.PI * 0.2,   end: Math.PI * 0.8 },
  up:    { start: -Math.PI * 0.8,  end: -Math.PI * 0.2 },
  right: { start: -Math.PI * 0.3,  end: Math.PI * 0.3 },
  left:  { start: Math.PI * 0.7,   end: Math.PI * 1.3 },
};

function renderSlashArcs() {
  const now = Date.now();
  G.fx.slashArcs = G.fx.slashArcs.filter(s => now - s.startTime < SLASH_ARC_DURATION);
  const ctx = G.ui.ctx;
  for (const s of G.fx.slashArcs) {
    const progress = (now - s.startTime) / SLASH_ARC_DURATION;
    const alpha = (1 - progress) * 0.7;
    const cx = s.x * TS + TS / 2;
    const cy = s.y * TS + TS / 2;
    const angles = ARC_ANGLES[s.direction] || ARC_ANGLES.down;
    const radius = TS * 0.5;
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = (3 - progress * 2) * SCALE;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.arc(cx, cy, radius, angles.start, angles.end);
    ctx.stroke();
    // Inner glow
    ctx.globalAlpha = alpha * 0.4;
    ctx.strokeStyle = "#aaeeff";
    ctx.lineWidth = (5 - progress * 3) * SCALE;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, angles.start, angles.end);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
  ctx.lineCap = "butt";
}

// ── Floating Damage Numbers ──────────────────────────────────────

function spawnFloatingText(x, y, text, color) {
  if (G.fx.floatingTexts.length > 10) G.fx.floatingTexts.shift();
  G.fx.floatingTexts.push({ x, y, text, startTime: Date.now(), color: color || "#fff" });
}

function renderFloatingTexts() {
  const now = Date.now();
  G.fx.floatingTexts = G.fx.floatingTexts.filter(t => now - t.startTime < FLOATING_TEXT_DURATION);
  const ctx = G.ui.ctx;
  ctx.font = `bold ${10 * SCALE}px monospace`;
  ctx.textAlign = "center";
  for (const t of G.fx.floatingTexts) {
    const progress = (now - t.startTime) / FLOATING_TEXT_DURATION;
    const alpha = 1 - progress;
    const rise = progress * FLOATING_TEXT_RISE;
    const drawY = t.y - rise;
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = "#000";
    ctx.lineWidth = 3;
    ctx.strokeText(t.text, t.x, drawY);
    ctx.fillStyle = t.color;
    ctx.fillText(t.text, t.x, drawY);
  }
  ctx.globalAlpha = 1;
  ctx.textAlign = "start";
}

// ── Monster Death Persistence (Corpses) ──────────────────────────

function addCorpse(kind, x, y, width, height) {
  if (G.room.roomCorpses.length >= CORPSE_CAP) G.room.roomCorpses.shift();
  G.room.roomCorpses.push({ kind, x, y, width: width || 1, height: height || 1 });
}

function clearCorpses() {
  G.room.roomCorpses = [];
}

function renderCorpses() {
  if (G.room.roomCorpses.length === 0) return;
  const ctx = G.ui.ctx;
  for (const c of G.room.roomCorpses) {
    const dmScale = SCALE * Math.max(c.width, c.height);
    const deathSprite = customDeathSprites[c.kind];
    if (deathSprite && deathSprite.frames && deathSprite.frames.length > 0) {
      // Draw the last death frame as the corpse
      const mainSprite = customMonsterSprites[c.kind];
      const eS = mainSprite?.resolution ? dmScale / mainSprite.resolution : dmScale;
      const lastIdx = deathSprite.frames.length - 1;
      const frame = deathSprite.frames[lastIdx];
      if (frame.alpha != null) {
        ctx.globalAlpha = frame.alpha;
        drawLayers(ctx, c.x * TS, c.y * TS, frame.layers, eS, deathSprite.colors);
        ctx.globalAlpha = 1;
      } else {
        drawLayers(ctx, c.x * TS, c.y * TS, frame, eS, deathSprite.colors);
      }
    } else {
      // Fallback: simple colored splat for monsters without death sprites
      const sprite = customMonsterSprites[c.kind];
      const color = sprite && sprite.colors
        ? Object.values(sprite.colors)[0] || "#555" : "#555";
      const cx = c.x * TS + c.width * TS / 2;
      const cy = c.y * TS + c.height * TS / 2 + 4 * SCALE;
      ctx.globalAlpha = 0.3;
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.ellipse(cx, cy, 5 * SCALE, 3 * SCALE, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.beginPath();
      ctx.ellipse(cx - 2 * SCALE, cy + 1 * SCALE, 3 * SCALE, 2 * SCALE, 0.4, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;
    }
  }
}

// ── Damage Vignette ──────────────────────────────────────────────

function renderDamageVignette() {
  if (!G.fx.damageVignette || Date.now() > G.fx.damageVignette) return;
  const remaining = G.fx.damageVignette - Date.now();
  const alpha = (remaining / VIGNETTE_DURATION) * 0.35;
  const ctx = G.ui.ctx;
  const grad = ctx.createRadialGradient(CW / 2, CH / 2, CW * 0.25, CW / 2, CH / 2, CW * 0.65);
  grad.addColorStop(0, "rgba(200,0,0,0)");
  grad.addColorStop(1, `rgba(180,0,0,${alpha})`);
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, CW, CH);
}

// ── Monster Spawn Pop ────────────────────────────────────────────

function getSpawnPopScale(spawnTime) {
  if (!spawnTime) return 1;
  const age = Date.now() - spawnTime;
  if (age < 0) return 0; // not yet spawned (staggered delay)
  if (age >= SPAWN_POP_DURATION) return 1;
  const t = age / SPAWN_POP_DURATION;
  // Overshoot ease-out: rises to ~1.15 at 70%, settles to 1.0
  if (t < 0.7) {
    return 0.5 + (t / 0.7) * 0.65; // 0.5 → 1.15
  }
  return 1.15 - ((t - 0.7) / 0.3) * 0.15; // 1.15 → 1.0
}

// ── Dust Puffs ───────────────────────────────────────────────────

function spawnDustPuff(px, py, dir) {
  const vec = DIR_VECTORS[dir] || { x: 0, y: 0 };
  const cx = px * TS + TS / 2 - vec.x * TS * 0.3;
  const cy = (py + 0.5) * TS + TS / 2 - vec.y * TS * 0.3;
  const dustColors = ["#c8b898", "#a09068", "#d0c0a0"];
  spawnBurst(cx, cy, 2, 1.2, 200, dustColors, [2 * SCALE, 3 * SCALE], { shrink: true });
}
