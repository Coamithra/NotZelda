/* title.js — NES Zelda-style title screen for "Legends of Amara"
   Renders at 240×176 virtual pixels, scaled 3× to 720×528 for authentic pixel art.
   Inspired by Legend of Zelda (1986) and Zelda II: Adventure of Link. */

const TITLE = {
  off: null,       // offscreen canvas (240×176)
  oc: null,        // offscreen context
  phase: "title",  // "title" | "login" | "done"
  stars: [],
  cliffBlocksL: [],
  cliffBlocksR: [],
  t0: 0,
  animId: null,
  titleMusic: null,
  musicStarted: false,
  loginFadeStart: 0,
  W: 240,
  H: 176,
};

// ---------------------------------------------------------------------------
// Sword pixel art — each cell rendered at 2×2 for prominence
// ---------------------------------------------------------------------------
const SWORD_MAP = [
  "   W   ",  // blade tip
  "  WbW  ",
  "  WBW  ",
  "  WBW  ",
  "  WBW  ",
  "  WBW  ",
  "  WBW  ",
  "  WBW  ",
  "  WBW  ",
  "  WBW  ",
  "  WBW  ",
  " gGGGg ",  // crossguard
  "  gGg  ",
  "  HhH  ",  // handle
  "  HhH  ",
  "  HhH  ",
  "  gPg  ",  // pommel
  "   g   ",
];
const SWORD_COLORS = {
  W: "#f0f0ff", b: "#d8d8f0", B: "#b8b8d8",
  G: "#e6b422", g: "#c89e1c", P: "#d4a31c",
  H: "#7b4e2c", h: "#5b3e1c",
};
const SWORD_PX = 2; // each sword pixel = 2×2 virtual pixels

// ---------------------------------------------------------------------------
// Cliff edge profiles — wider range, more dramatic cave shape
// ---------------------------------------------------------------------------
function leftEdge(y) {
  const base = 68;
  // Stronger bulge for wider opening in middle; pull back at top too
  const topPull = y < 30 ? (30 - y) * 0.6 : 0;
  const bulge = -32 * Math.sin(y / 176 * Math.PI);
  const noise = Math.sin(y * 0.13) * 7 + Math.sin(y * 0.31 + 0.7) * 4;
  return Math.max(6, base + bulge + noise - topPull);
}
function rightEdge(y) {
  const base = 172;
  const topPull = y < 30 ? (30 - y) * 0.6 : 0;
  const bulge = 32 * Math.sin(y / 176 * Math.PI);
  const noise = Math.sin(y * 0.13 + 2.1) * 7 + Math.sin(y * 0.31 + 1.3) * 4;
  return Math.min(234, base + bulge + noise + topPull);
}

// Deterministic pseudo-random from seed
function seeded(n) {
  return ((Math.sin(n * 127.1 + 311.7) * 43758.5453) % 1 + 1) % 1;
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
TITLE.init = function () {
  const off = document.createElement("canvas");
  off.width = this.W;
  off.height = this.H;
  this.off = off;
  this.oc = off.getContext("2d");

  // Generate stars (only in open sky between cliffs)
  for (let i = 0; i < 60; i++) {
    const y = Math.floor(Math.random() * 115);
    const lx = leftEdge(y);
    const rx = rightEdge(y);
    if (rx - lx < 25) continue;
    this.stars.push({
      x: lx + 6 + Math.floor(Math.random() * (rx - lx - 12)),
      y: y,
      speed: 0.4 + Math.random() * 2.5,
      phase: Math.random() * Math.PI * 2,
      bright: Math.random() < 0.18,
    });
  }

  // Generate cliff blocks (brick pattern)
  this._generateCliffs();

  this.t0 = performance.now();
  this._tick();

  // Attempt autoplay immediately — falls back to first interaction if blocked
  this.startMusic();
};

// ---------------------------------------------------------------------------
// Cliff generation — brick-laying pattern with mortar gaps
// ---------------------------------------------------------------------------
TITLE._generateCliffs = function () {
  const BLOCK_H = 4;   // each stone row is 4px tall
  const MORTAR = 1;     // 1px mortar between rows

  // Left cliff
  for (let row = 0; row < Math.ceil(176 / (BLOCK_H + MORTAR)); row++) {
    const y = row * (BLOCK_H + MORTAR);
    if (y >= 176) break;
    const edge = leftEdge(y + BLOCK_H / 2);
    const rowOffset = (row % 2) * 4; // stagger every other row
    for (let x = rowOffset - 4; x < edge; x += 0) {
      const w = 6 + Math.floor(seeded(row * 240 + x + 1) * 5); // 6-10px wide
      const blockRight = Math.min(x + w, Math.ceil(edge));
      if (blockRight <= x) { x += w + 1; continue; }
      const distFromEdge = edge - (x + w / 2);
      const baseShade = 32 + Math.floor(seeded(row * 100 + x * 7) * 22);
      const edgeLight = distFromEdge < 6 ? 18 : (distFromEdge < 12 ? 8 : 0);
      this.cliffBlocksL.push({
        x: Math.max(0, x), y, w: blockRight - Math.max(0, x), h: BLOCK_H,
        r: baseShade + edgeLight + 10,
        g: baseShade + edgeLight + 4,
        b: baseShade,
      });
      x += w + 1; // 1px mortar gap
    }
  }

  // Right cliff
  for (let row = 0; row < Math.ceil(176 / (BLOCK_H + MORTAR)); row++) {
    const y = row * (BLOCK_H + MORTAR);
    if (y >= 176) break;
    const edge = rightEdge(y + BLOCK_H / 2);
    const rowOffset = (row % 2) * 4;
    for (let x = Math.floor(edge) + rowOffset % 3; x < 240; x += 0) {
      const w = 6 + Math.floor(seeded(row * 250 + x * 3 + 1) * 5);
      const blockEnd = Math.min(x + w, 240);
      const distFromEdge = (x + w / 2) - edge;
      const baseShade = 32 + Math.floor(seeded(row * 200 + x * 7) * 22);
      const edgeLight = distFromEdge < 6 ? 18 : (distFromEdge < 12 ? 8 : 0);
      this.cliffBlocksR.push({
        x, y, w: blockEnd - x, h: BLOCK_H,
        r: baseShade + edgeLight + 10,
        g: baseShade + edgeLight + 4,
        b: baseShade,
      });
      x += w + 1;
    }
  }
};

// ---------------------------------------------------------------------------
// Main render loop
// ---------------------------------------------------------------------------
TITLE._tick = function () {
  if (this.phase === "done") return;

  const t = performance.now() - this.t0;
  const c = this.oc;

  // --- Sky ---
  c.fillStyle = "#0a0a22";
  c.fillRect(0, 0, this.W, this.H);

  // Horizon glow — warm amber behind mountains
  const grad = c.createLinearGradient(0, 75, 0, 135);
  grad.addColorStop(0, "rgba(15, 12, 40, 0)");
  grad.addColorStop(0.4, "rgba(30, 18, 45, 0.35)");
  grad.addColorStop(0.7, "rgba(20, 14, 35, 0.6)");
  grad.addColorStop(1, "rgba(8, 6, 20, 0.9)");
  c.fillStyle = grad;
  c.fillRect(0, 75, this.W, 60);

  // Subtle warm glow at horizon center
  const warmGrad = c.createRadialGradient(this.W / 2, 128, 5, this.W / 2, 128, 50);
  warmGrad.addColorStop(0, "rgba(60, 35, 20, 0.25)");
  warmGrad.addColorStop(1, "rgba(60, 35, 20, 0)");
  c.fillStyle = warmGrad;
  c.fillRect(60, 95, 120, 45);

  // --- Stars ---
  for (const s of this.stars) {
    const alpha = 0.3 + 0.7 * (0.5 + 0.5 * Math.sin(t * 0.001 * s.speed + s.phase));
    if (s.bright) {
      c.fillStyle = "rgba(200, 220, 255, " + alpha + ")";
      c.fillRect(s.x, s.y, 1, 1);
      c.fillStyle = "rgba(180, 200, 255, " + (alpha * 0.35) + ")";
      c.fillRect(s.x + 1, s.y, 1, 1);
      c.fillRect(s.x - 1, s.y, 1, 1);
      c.fillRect(s.x, s.y + 1, 1, 1);
      c.fillRect(s.x, s.y - 1, 1, 1);
    } else {
      c.fillStyle = "rgba(255, 255, 255, " + (alpha * 0.65) + ")";
      c.fillRect(s.x, s.y, 1, 1);
    }
  }

  // --- Distant mountains ---
  this._drawMountains(c);

  // --- Landscape (trees, hills) ---
  this._drawLandscape(c);

  // --- Cliffs (mortar bg first, then blocks) ---
  // Mortar fill behind cliff areas
  c.fillStyle = "#0e0e0c";
  for (let y = 0; y < 176; y++) {
    const le = leftEdge(y);
    c.fillRect(0, y, Math.ceil(le), 1);
    const re = rightEdge(y);
    c.fillRect(Math.floor(re), y, 240 - Math.floor(re), 1);
  }
  // Stone blocks
  for (const b of this.cliffBlocksL) {
    c.fillStyle = "rgb(" + b.r + "," + b.g + "," + b.b + ")";
    c.fillRect(b.x, b.y, b.w, b.h);
  }
  for (const b of this.cliffBlocksR) {
    c.fillStyle = "rgb(" + b.r + "," + b.g + "," + b.b + ")";
    c.fillRect(b.x, b.y, b.w, b.h);
  }

  // --- Bright edge stones (highlight along cliff boundary) ---
  for (let y = 5; y < 170; y += 5) {
    const le = Math.floor(leftEdge(y));
    const re = Math.floor(rightEdge(y));
    if (seeded(y * 17) > 0.5) {
      c.fillStyle = "#4a4a40";
      c.fillRect(le - 3, y, 3, 3);
    }
    if (seeded(y * 23) > 0.5) {
      c.fillStyle = "#4a4a40";
      c.fillRect(re, y, 3, 3);
    }
  }

  // --- Stalactites hanging from upper cliff edges into cave opening ---
  // Draw pointed rock formations at the cliff/sky boundary near the top
  for (let sy = 2; sy < 20; sy += 4) {
    const le = Math.floor(leftEdge(sy));
    const re = Math.floor(rightEdge(sy));
    // Left side stalactites — hanging from cliff edge into open sky
    if (seeded(sy * 37) > 0.4) {
      const sh = 4 + Math.floor(seeded(sy * 41) * 6);
      c.fillStyle = "#38362e";
      c.fillRect(le - 1, sy, 2, sh);
      c.fillRect(le, sy + sh, 1, 2);
      c.fillStyle = "#42403a";
      c.fillRect(le - 1, sy, 1, sh);
    }
    // Right side stalactites
    if (seeded(sy * 53) > 0.4) {
      const sh = 4 + Math.floor(seeded(sy * 59) * 6);
      c.fillStyle = "#38362e";
      c.fillRect(re, sy, 2, sh);
      c.fillRect(re, sy + sh, 1, 2);
      c.fillStyle = "#42403a";
      c.fillRect(re + 1, sy, 1, sh);
    }
  }

  // --- Moss on cliff edges ---
  for (let y = 40; y < 140; y += 3) {
    if (seeded(y * 77 + 3) > 0.45) {
      c.fillStyle = "#1a3e1a";
      const le = Math.floor(leftEdge(y));
      c.fillRect(le - 2, y, 4, 2);
      c.fillStyle = "#0e2e0e";
      c.fillRect(le - 1, y - 1, 2, 1);
    }
    if (seeded(y * 88 + 5) > 0.45) {
      c.fillStyle = "#1a3e1a";
      const re = Math.floor(rightEdge(y));
      c.fillRect(re - 1, y, 4, 2);
      c.fillStyle = "#0e2e0e";
      c.fillRect(re, y - 1, 2, 1);
    }
  }

  // --- Waterfall ---
  this._drawWaterfall(c, t);

  // --- Torch on right cliff (Zelda 1 homage) ---
  this._drawTorch(c, t);

  // --- Ground ---
  this._drawGround(c);

  // --- Sword ---
  this._drawSword(c, t);

  // --- Title frame ---
  this._drawTitle(c, t);

  // --- Scale up to display canvas ---
  const dst = document.getElementById("title-canvas");
  if (!dst) return;
  const dc = dst.getContext("2d");
  dc.imageSmoothingEnabled = false;
  dc.drawImage(this.off, 0, 0, dst.width, dst.height);

  // --- Edge vignette ---
  var vGrad = dc.createRadialGradient(dst.width / 2, dst.height / 2, dst.height * 0.4,
                                       dst.width / 2, dst.height / 2, dst.height * 0.85);
  vGrad.addColorStop(0, "rgba(0,0,0,0)");
  vGrad.addColorStop(1, "rgba(0,0,0,0.25)");
  dc.fillStyle = vGrad;
  dc.fillRect(0, 0, dst.width, dst.height);

  // --- Floating particles (fireflies) on full canvas ---
  for (var i = 0; i < 6; i++) {
    var px = 150 + Math.sin(t * 0.0003 * (i + 1) + i * 1.7) * 180;
    var py = 180 + Math.sin(t * 0.0005 * (i + 1) + i * 2.3) * 100;
    var pa = 0.15 + 0.25 * (0.5 + 0.5 * Math.sin(t * 0.0025 * (i + 1) + i));
    dc.globalAlpha = pa;
    dc.fillStyle = "#ccdd88";
    dc.fillRect(px, py, 3, 3);
    dc.globalAlpha = pa * 0.25;
    dc.fillRect(px - 3, py - 3, 9, 9);
    dc.globalAlpha = 1;
  }

  // --- Crisp text on full-size canvas ---
  this._drawText(dc, t);

  // --- Dim overlay when login form is shown ---
  if (this.phase === "login" && this.loginFadeStart) {
    const elapsed = performance.now() - this.loginFadeStart;
    const alpha = Math.min(0.55, elapsed / 600 * 0.55);
    dc.fillStyle = "rgba(0, 0, 0, " + alpha + ")";
    dc.fillRect(0, 0, dst.width, dst.height);
  }

  this.animId = requestAnimationFrame(() => this._tick());
};

// ---------------------------------------------------------------------------
// Scene elements
// ---------------------------------------------------------------------------
TITLE._drawMountains = function (c) {
  // Mountain range — taller, more contrast
  c.fillStyle = "#1c1c42";
  c.beginPath();
  c.moveTo(55, 132); c.lineTo(82, 88); c.lineTo(110, 132);
  c.closePath(); c.fill();

  c.fillStyle = "#18183e";
  c.beginPath();
  c.moveTo(90, 132); c.lineTo(120, 75); c.lineTo(155, 132);
  c.closePath(); c.fill();

  c.fillStyle = "#1e1e44";
  c.beginPath();
  c.moveTo(135, 132); c.lineTo(160, 92); c.lineTo(185, 132);
  c.closePath(); c.fill();

  // Snow caps
  c.fillStyle = "#3a3a60";
  c.beginPath(); c.moveTo(82, 88); c.lineTo(78, 95); c.lineTo(86, 95); c.closePath(); c.fill();
  c.fillStyle = "#38385c";
  c.beginPath(); c.moveTo(120, 75); c.lineTo(115, 84); c.lineTo(125, 84); c.closePath(); c.fill();
  c.fillStyle = "#363658";
  c.beginPath(); c.moveTo(160, 92); c.lineTo(157, 98); c.lineTo(163, 98); c.closePath(); c.fill();
};

TITLE._drawLandscape = function (c) {
  // Far hills (behind trees)
  c.fillStyle = "#0a1806";
  c.beginPath();
  c.moveTo(35, 135);
  for (let x = 35; x <= 205; x++) {
    const h = Math.sin(x * 0.03) * 5 + Math.sin(x * 0.08 + 1) * 3 + 2;
    c.lineTo(x, 132 - h);
  }
  c.lineTo(205, 135); c.closePath(); c.fill();

  // Near hills (slightly brighter)
  c.fillStyle = "#0e2208";
  c.beginPath();
  c.moveTo(40, 135);
  for (let x = 40; x <= 200; x++) {
    const h = Math.sin(x * 0.05 + 0.5) * 3.5 + Math.sin(x * 0.11) * 2;
    c.lineTo(x, 133 - h);
  }
  c.lineTo(200, 135); c.closePath(); c.fill();

  // Pine tree silhouettes — varied sizes and colors
  const trees = [
    { x: 60, h: 18, w: 8, dark: true },
    { x: 73, h: 14, w: 7, dark: false },
    { x: 85, h: 11, w: 6, dark: true },
    { x: 96, h: 8, w: 5, dark: false },
    { x: 148, h: 10, w: 5, dark: true },
    { x: 158, h: 16, w: 7, dark: false },
    { x: 170, h: 22, w: 10, dark: true },
    { x: 184, h: 14, w: 7, dark: false },
    { x: 194, h: 10, w: 6, dark: true },
  ];
  for (const tr of trees) {
    const base = 133;
    c.fillStyle = "#081408";
    c.fillRect(tr.x, base - 3, 2, 4);
    c.fillStyle = tr.dark ? "#0e2e0a" : "#14380e";
    for (let layer = 0; layer < 3; layer++) {
      const ly = base - 3 - layer * (tr.h / 3);
      const lw = tr.w - layer * 2;
      c.beginPath();
      c.moveTo(tr.x + 1 - lw / 2, ly);
      c.lineTo(tr.x + 1, ly - tr.h / 3 - 2);
      c.lineTo(tr.x + 1 + lw / 2, ly);
      c.closePath();
      c.fill();
    }
  }
};

TITLE._drawWaterfall = function (c, t) {
  const baseX = Math.floor(leftEdge(80)) - 3;
  const startY = 55;
  const endY = 130;
  const offset = Math.floor(t * 0.008) % 4;
  const WIDTH = 5;

  // Water stream — muted blues
  for (let y = startY; y < endY; y++) {
    for (let dx = 0; dx < WIDTH; dx++) {
      const stripe = (y + dx + offset) % 4;
      const edge = dx === 0 || dx === WIDTH - 1;
      if (edge) {
        c.fillStyle = "#1e5588";
      } else if (stripe === 0) c.fillStyle = "#6eaad8";
      else if (stripe === 1) c.fillStyle = "#4488bb";
      else if (stripe === 2) c.fillStyle = "#2a6699";
      else c.fillStyle = "#5588aa";
      c.fillRect(baseX + dx, y, 1, 1);
    }
  }

  // White highlight streaks
  const hlOffset = Math.floor(t * 0.012) % 6;
  c.fillStyle = "#99bbdd";
  for (let y = startY; y < endY; y += 7) {
    const hy = y + hlOffset;
    if (hy < endY) c.fillRect(baseX + 2, hy, 2, 1);
  }

  // Splash at bottom
  const splash = Math.floor(t * 0.005) % 3;
  c.fillStyle = "rgba(110, 170, 216, 0.6)";
  c.fillRect(baseX - 1 - splash, endY, WIDTH + 2 + splash * 2, 1);
  c.fillStyle = "rgba(80, 140, 200, 0.35)";
  c.fillRect(baseX - 2 - splash, endY + 1, WIDTH + 4 + splash * 2, 1);
};

TITLE._drawTorch = function (c, t) {
  // Torch mounted on right cliff wall — flickering fire
  const re = Math.floor(rightEdge(85));
  const tx = re + 2;  // on the cliff face
  const ty = 80;

  // Bracket/mount
  c.fillStyle = "#5a4a2a";
  c.fillRect(tx, ty + 6, 3, 8);
  c.fillRect(tx - 1, ty + 6, 1, 2);

  // Flame (flickering)
  const flicker = Math.sin(t * 0.012) * 1.5 + Math.sin(t * 0.019) * 1;
  const flicker2 = Math.sin(t * 0.015 + 1) * 1;

  // Outer flame (orange)
  c.fillStyle = "#cc6622";
  c.fillRect(tx, ty + 2 + flicker2, 3, 4);
  c.fillRect(tx + 1, ty + flicker, 1, 3);

  // Inner flame (yellow)
  c.fillStyle = "#eebb33";
  c.fillRect(tx + 1, ty + 3 + flicker2, 1, 3);

  // Core (white-hot)
  c.fillStyle = "#ffee88";
  c.fillRect(tx + 1, ty + 4 + flicker2, 1, 1);

  // Glow around torch
  c.globalAlpha = 0.06 + 0.03 * Math.sin(t * 0.008);
  c.fillStyle = "#ff8844";
  c.fillRect(tx - 6, ty - 4, 16, 20);
  c.globalAlpha = 0.03 + 0.015 * Math.sin(t * 0.008);
  c.fillRect(tx - 10, ty - 8, 24, 28);
  c.globalAlpha = 1;
};

TITLE._drawGround = function (c) {
  // Earth base — varied with patches
  c.fillStyle = "#0e1e06";
  c.fillRect(0, 133, this.W, 43);

  // Darker subsoil
  c.fillStyle = "#0a1604";
  c.fillRect(0, 150, this.W, 26);

  // Slightly lighter top-soil
  c.fillStyle = "#122408";
  c.fillRect(0, 133, this.W, 8);

  // Earth texture — random patches
  for (let i = 0; i < 30; i++) {
    const px = Math.floor(seeded(i * 37) * this.W);
    const py = 135 + Math.floor(seeded(i * 53) * 35);
    const pw = 4 + Math.floor(seeded(i * 71) * 8);
    c.fillStyle = seeded(i * 19) > 0.5 ? "#0c1a05" : "#101e08";
    c.fillRect(px, py, pw, 2);
  }

  // Grass fringe — taller, varied, with highlights
  const le = leftEdge(133);
  const re = rightEdge(133);
  for (let x = Math.floor(le) - 5; x < Math.ceil(re) + 5; x++) {
    const h = 3 + Math.floor(Math.sin(x * 0.5) * 2 + Math.sin(x * 1.7) * 1.5);
    const shade = seeded(x * 31);
    c.fillStyle = shade > 0.6 ? "#246a18" : shade > 0.3 ? "#1a5212" : "#165010";
    c.fillRect(x, 132 - h, 1, h + 2);
    if (h > 3) {
      c.fillStyle = "#2e7a1e";
      c.fillRect(x, 132 - h, 1, 1);
    }
  }

  // Small stones/pebbles on ground
  c.fillStyle = "#1a2a10";
  c.fillRect(85, 137, 3, 2);
  c.fillRect(150, 139, 2, 2);
  c.fillRect(98, 142, 2, 1);
  c.fillRect(140, 136, 3, 2);
  c.fillStyle = "#222e18";
  c.fillRect(170, 141, 2, 2);
  c.fillRect(72, 140, 3, 1);

  // Dirt path — narrow, tapering down
  for (let y = 135; y < 176; y++) {
    const dist = y - 135;
    const pw = 6 + Math.min(6, dist * 0.3);
    const px = this.W / 2 - pw / 2;
    c.fillStyle = "#161008";
    c.fillRect(px, y, pw, 1);
  }
};

TITLE._drawSword = function (c, t) {
  const sw = SWORD_MAP[0].length * SWORD_PX;
  const sh = SWORD_MAP.length * SWORD_PX;
  const sx = Math.floor(this.W / 2 - sw / 2);
  const sy = 96;

  // Light beam BEHIND sword — draw first
  var glowAlpha = 0.035 + 0.02 * Math.sin(t * 0.002);
  var cx = sx + sw / 2;
  for (let gy = sy - 6; gy < sy + sh + 2; gy++) {
    var dist = Math.abs(gy - (sy + sh / 2)) / (sh / 2 + 6);
    var halfW = 2 + (1 - dist) * 5;
    c.globalAlpha = glowAlpha * (1 - dist * 0.7);
    c.fillStyle = "#9999dd";
    c.fillRect(cx - halfW, gy, halfW * 2, 1);
  }
  c.globalAlpha = 1;

  // Sword pixels on top of glow
  for (let row = 0; row < SWORD_MAP.length; row++) {
    const line = SWORD_MAP[row];
    for (let col = 0; col < line.length; col++) {
      const ch = line[col];
      if (ch === " ") continue;
      const color = SWORD_COLORS[ch];
      if (!color) continue;
      c.fillStyle = color;
      c.fillRect(sx + col * SWORD_PX, sy + row * SWORD_PX, SWORD_PX, SWORD_PX);
    }
  }

  // Gleam — white highlight traveling down blade
  const cycle = 4000;
  const progress = (t % cycle) / cycle;
  if (progress < 0.12) {
    const bladeRows = 11;
    const gleamRow = Math.floor(progress / 0.12 * bladeRows);
    c.fillStyle = "#ffffff";
    c.fillRect(sx + 3 * SWORD_PX, sy + gleamRow * SWORD_PX, SWORD_PX, SWORD_PX);
    if (gleamRow > 0) {
      c.fillStyle = "rgba(255, 255, 255, 0.5)";
      c.fillRect(sx + 3 * SWORD_PX, sy + (gleamRow - 1) * SWORD_PX, SWORD_PX, SWORD_PX);
    }
  }

  // Grass tufts around sword base
  c.fillStyle = "#14480e";
  c.fillRect(sx - 4, sy + sh - 2, sw + 8, 4);
  c.fillStyle = "#1e5a14";
  c.fillRect(sx - 2, sy + sh - 4, 3, 3);
  c.fillRect(sx + sw - 1, sy + sh - 4, 3, 3);
  c.fillStyle = "#16500e";
  c.fillRect(sx - 6, sy + sh, sw + 12, 3);
};

TITLE._drawTitle = function (c, t) {
  const fx = 62, fy = 12;
  const fw = 116, fh = 48;

  // Outer border (dark gold)
  c.fillStyle = "#7a5a10";
  c.fillRect(fx, fy, fw, fh);

  // Inner dark fill
  c.fillStyle = "#08081a";
  c.fillRect(fx + 2, fy + 2, fw - 4, fh - 4);

  // Gold border
  c.fillStyle = "#e6b422";
  c.fillRect(fx + 2, fy + 2, fw - 4, 1);
  c.fillRect(fx + 2, fy + fh - 3, fw - 4, 1);
  c.fillRect(fx + 2, fy + 3, 1, fh - 6);
  c.fillRect(fx + fw - 3, fy + 3, 1, fh - 6);

  // Second inner border
  c.fillStyle = "#c89e1c";
  c.fillRect(fx + 4, fy + 4, fw - 8, 1);
  c.fillRect(fx + 4, fy + fh - 5, fw - 8, 1);
  c.fillRect(fx + 4, fy + 5, 1, fh - 10);
  c.fillRect(fx + fw - 5, fy + 5, 1, fh - 10);

  // Green vine decorations
  c.fillStyle = "#2a8a2a";
  for (let x = fx + 7; x < fx + fw - 7; x += 4) {
    c.fillRect(x, fy, 2, 1);
    if ((x - fx) % 8 < 4) c.fillRect(x + 1, fy - 1, 1, 1);
    c.fillRect(x, fy + fh - 1, 2, 1);
    if ((x - fx) % 8 >= 4) c.fillRect(x, fy + fh, 1, 1);
  }
  c.fillStyle = "#1e7a1e";
  for (let y = fy + 6; y < fy + fh - 6; y += 5) {
    c.fillRect(fx, y, 1, 2);
    c.fillRect(fx + fw - 1, y, 1, 2);
  }

  // Corner diamonds
  c.fillStyle = "#ffd700";
  const corners = [
    [fx + 4, fy + 4], [fx + fw - 7, fy + 4],
    [fx + 4, fy + fh - 7], [fx + fw - 7, fy + fh - 7],
  ];
  for (const [cx, cy] of corners) {
    c.fillRect(cx + 1, cy, 1, 1);
    c.fillRect(cx, cy + 1, 3, 1);
    c.fillRect(cx + 1, cy + 2, 1, 1);
  }

  // Golden glow around frame — pulsing aura
  var glowAlpha = 0.12 + 0.06 * Math.sin(t * 0.0015);
  c.globalAlpha = glowAlpha;
  c.fillStyle = "#e6b422";
  c.fillRect(fx - 4, fy - 4, fw + 8, fh + 8);
  c.globalAlpha = glowAlpha * 0.5;
  c.fillRect(fx - 6, fy - 6, fw + 12, fh + 12);
  c.globalAlpha = 1;

  // Text is rendered later on the full-size canvas for crisp rendering
  // (see _drawTitleText)
};

// Title text + subtitle + PRESS ENTER — rendered on full-size canvas for crispness
TITLE._drawText = function (dc, t) {
  // Scale factor from virtual to display
  const S = 3;
  const fx = 62, fy = 12, fw = 116, fh = 48;

  dc.textAlign = "center";
  dc.textBaseline = "middle";

  // "LEGENDS OF" — shadow then gold
  dc.fillStyle = "#6b4a0e";
  dc.font = "bold 24px monospace";
  dc.fillText("LEGENDS OF", (fx + fw / 2) * S + S, (fy + 17) * S + S);
  dc.fillStyle = "#d4a31c";
  dc.fillText("LEGENDS OF", (fx + fw / 2) * S, (fy + 17) * S);

  // "AMARA" — large, shimmering gold
  var shimmer = 0.5 + 0.5 * Math.sin(t * 0.002);
  var gold = Math.floor(215 + shimmer * 40);
  dc.fillStyle = "#5a3a08";
  dc.font = "bold 54px monospace";
  dc.fillText("AMARA", (fx + fw / 2) * S + S, (fy + 31) * S + S);
  dc.fillStyle = "rgb(" + gold + "," + Math.floor(gold * 0.72) + "," + Math.floor(30 + shimmer * 10) + ")";
  dc.fillText("AMARA", (fx + fw / 2) * S, (fy + 31) * S);

  // Subtitle
  dc.fillStyle = "#9098a8";
  dc.font = "18px monospace";
  dc.fillText("A Multiplayer Adventure", this.W / 2 * S, (fy + fh + 9) * S);

  // "PRESS ENTER" / "TAP TO START"
  if (this.phase === "title") {
    var pulse = 0.45 + 0.55 * (0.5 + 0.5 * Math.sin(t * 0.005));
    dc.globalAlpha = pulse;
    dc.fillStyle = "#ffffff";
    dc.font = "bold 24px monospace";
    var isMobile = typeof G !== "undefined" && G.ui.isMobile;
    dc.fillText(isMobile ? "- TAP TO START -" : "- PRESS ENTER -", this.W / 2 * S, 166 * S);
    dc.globalAlpha = 1;
  }
};

// ---------------------------------------------------------------------------
// Title music (chapel track)
// ---------------------------------------------------------------------------
TITLE.startMusic = function () {
  if (this.musicStarted) return;
  this.musicStarted = true;
  this.titleMusic = new Audio("music_chapel.mp3");
  this.titleMusic.loop = true;
  this.titleMusic.volume = 0;
  var self = this;

  function beginFade() {
    var startTime = performance.now();
    var TARGET = 0.3;
    var FADE = 2500;
    function fadeStep() {
      if (!self.titleMusic) return;
      var elapsed = performance.now() - startTime;
      var prog = Math.min(1, elapsed / FADE);
      self.titleMusic.volume = prog * TARGET;
      if (prog < 1) requestAnimationFrame(fadeStep);
    }
    requestAnimationFrame(fadeStep);
  }

  var p = this.titleMusic.play();
  if (p) {
    p.then(function () {
      beginFade();
    }).catch(function () {
      // Autoplay blocked — retry on first user interaction
      function unlock() {
        if (self.titleMusic) {
          var r = self.titleMusic.play();
          if (r) r.catch(function () {});
          beginFade();
        }
        document.removeEventListener("keydown", unlock);
        document.removeEventListener("click", unlock);
        document.removeEventListener("touchstart", unlock);
      }
      document.addEventListener("keydown", unlock);
      document.addEventListener("click", unlock);
      document.addEventListener("touchstart", unlock);
    });
  } else {
    beginFade();
  }
};

TITLE.stopMusic = function () {
  if (!this.titleMusic) return;
  var audio = this.titleMusic;
  var startVol = audio.volume;
  var startTime = performance.now();
  var FADE = 800;
  function fadeStep() {
    var elapsed = performance.now() - startTime;
    var prog = Math.min(1, elapsed / FADE);
    audio.volume = startVol * (1 - prog);
    if (prog < 1) {
      requestAnimationFrame(fadeStep);
    } else {
      audio.pause();
      audio.src = "";
    }
  }
  requestAnimationFrame(fadeStep);
  this.titleMusic = null;
};

// ---------------------------------------------------------------------------
// Phase transitions
// ---------------------------------------------------------------------------
TITLE.showLogin = function () {
  if (this.phase !== "title") return;
  this.phase = "login";
  this.loginFadeStart = performance.now();
  this.startMusic();

  var card = document.getElementById("login-card");
  if (card) {
    card.classList.remove("hidden");
    setTimeout(function () {
      card.classList.add("visible");
      G.ui.nameInput.focus();
    }, 50);
  }
};

TITLE.hide = function () {
  this.phase = "done";
  if (this.animId) {
    cancelAnimationFrame(this.animId);
    this.animId = null;
  }
  this.stopMusic();
};
