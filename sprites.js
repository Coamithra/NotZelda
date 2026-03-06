// ---------------------------------------------------------------------------
// Player sprite — procedural drawing
// ---------------------------------------------------------------------------
const SHIRT_COLORS = ["#c8383c", "#3868c8", "#38a838", "#c8a838", "#a838c8", "#38c8c8"];
const SKIN = "#e8c898";
const HAIR = "#4a3020";
const PANTS = "#3a4a8a";
const BOOTS = "#3a2a1a";

// Dance animation — 4 frames of boogie, always facing down
function drawPlayerDance(ctx, px, py, colorIndex, danceFrame, S) {
  const sx = px;
  const sy = py;
  const shirt = SHIRT_COLORS[colorIndex % SHIRT_COLORS.length];
  const f = danceFrame % 4;

  if (f === 0) {
    // Lean left, right arm up, left arm out
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+4*S, sy+0*S, 6*S, 2*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+4*S, sy+2*S, 6*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+5*S, sy+3*S, S, S);  // left eye
    ctx.fillRect(sx+8*S, sy+3*S, S, S);  // right eye
    // Mouth — little smile
    ctx.fillRect(sx+6*S, sy+5*S, 2*S, S);
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+3*S, sy+6*S, 8*S, 5*S);  // torso shifted left
    // Left arm out to the side
    ctx.fillRect(sx+1*S, sy+7*S, 2*S, S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+0*S, sy+7*S, S, S);       // left hand
    // Right arm up!
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+11*S, sy+4*S, S, 3*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+11*S, sy+3*S, S, S);       // right hand up
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+3*S, sy+11*S, 3*S, 2*S);  // left leg
    ctx.fillRect(sx+8*S, sy+11*S, 3*S, 2*S);  // right leg apart
    ctx.fillStyle = BOOTS;
    ctx.fillRect(sx+2*S, sy+13*S, 3*S, 2*S);
    ctx.fillRect(sx+9*S, sy+13*S, 3*S, 2*S);
  } else if (f === 1) {
    // Lean right, left arm up, right arm out
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+6*S, sy+0*S, 6*S, 2*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+6*S, sy+2*S, 6*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+7*S, sy+3*S, S, S);
    ctx.fillRect(sx+10*S, sy+3*S, S, S);
    ctx.fillRect(sx+8*S, sy+5*S, 2*S, S);
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+5*S, sy+6*S, 8*S, 5*S);  // torso shifted right
    // Right arm out
    ctx.fillRect(sx+13*S, sy+7*S, 2*S, S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+15*S, sy+7*S, S, S);       // right hand
    // Left arm up!
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+4*S, sy+4*S, S, 3*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+4*S, sy+3*S, S, S);        // left hand up
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+5*S, sy+11*S, 3*S, 2*S);
    ctx.fillRect(sx+10*S, sy+11*S, 3*S, 2*S);
    ctx.fillStyle = BOOTS;
    ctx.fillRect(sx+4*S, sy+13*S, 3*S, 2*S);
    ctx.fillRect(sx+11*S, sy+13*S, 3*S, 2*S);
  } else if (f === 2) {
    // Both arms up, slight squat
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+5*S, sy+1*S, 6*S, 2*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+5*S, sy+3*S, 6*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+6*S, sy+4*S, S, S);
    ctx.fillRect(sx+9*S, sy+4*S, S, S);
    // Big smile
    ctx.fillRect(sx+7*S, sy+6*S, 2*S, S);
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+4*S, sy+7*S, 8*S, 5*S);
    // Both arms up!
    ctx.fillRect(sx+3*S, sy+5*S, S, 3*S);
    ctx.fillRect(sx+12*S, sy+5*S, S, 3*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+3*S, sy+4*S, S, S);
    ctx.fillRect(sx+12*S, sy+4*S, S, S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+4*S, sy+12*S, 3*S, 2*S);  // squat — legs wider & shorter
    ctx.fillRect(sx+9*S, sy+12*S, 3*S, 2*S);
    ctx.fillStyle = BOOTS;
    ctx.fillRect(sx+3*S, sy+14*S, 3*S, S);
    ctx.fillRect(sx+10*S, sy+14*S, 3*S, S);
  } else {
    // Arms crossed down, legs together — the "cool pause"
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+5*S, sy+0*S, 6*S, 2*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+5*S, sy+2*S, 6*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+6*S, sy+3*S, S, S);
    ctx.fillRect(sx+9*S, sy+3*S, S, S);
    ctx.fillRect(sx+7*S, sy+5*S, 2*S, S);
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+4*S, sy+6*S, 8*S, 5*S);
    // Arms crossed in front
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+4*S, sy+8*S, 2*S, S);
    ctx.fillRect(sx+10*S, sy+8*S, 2*S, S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+5*S, sy+11*S, 6*S, 2*S);
    ctx.fillStyle = BOOTS;
    ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
    ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
  }
}

function drawGuard(ctx, px, py, S) {
  const sx = px;
  const sy = py;
  const HELMET = "#8090a0";
  const HELMET_DARK = "#606e7a";
  const ARMOR = "#9aa8b8";
  // Helmet — wider and lower than hair, with visor band
  ctx.fillStyle = HELMET;
  ctx.fillRect(sx+4*S, sy+0*S, 8*S, 2*S);  // top of helmet (wider)
  ctx.fillRect(sx+4*S, sy+2*S, 8*S, 1*S);  // helmet extends down over forehead
  ctx.fillStyle = HELMET_DARK;
  ctx.fillRect(sx+4*S, sy+2*S, 8*S, S);     // visor band
  // Face
  ctx.fillStyle = SKIN;
  ctx.fillRect(sx+5*S, sy+3*S, 6*S, 3*S);
  // Eyes
  ctx.fillStyle = "#222";
  ctx.fillRect(sx+6*S, sy+3*S, S, S);
  ctx.fillRect(sx+9*S, sy+3*S, S, S);
  // Armor torso
  ctx.fillStyle = ARMOR;
  ctx.fillRect(sx+4*S, sy+6*S, 8*S, 5*S);
  ctx.fillRect(sx+3*S, sy+6*S, S, 4*S);
  ctx.fillRect(sx+12*S, sy+6*S, S, 4*S);
  // Hands
  ctx.fillStyle = SKIN;
  ctx.fillRect(sx+3*S, sy+10*S, S, S);
  ctx.fillRect(sx+12*S, sy+10*S, S, S);
  // Pants
  ctx.fillStyle = PANTS;
  ctx.fillRect(sx+5*S, sy+11*S, 6*S, 2*S);
  // Boots
  ctx.fillStyle = BOOTS;
  ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
  ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
}

// ---------------------------------------------------------------------------
// NPC sprite variants — unique looks per NPC type
// ---------------------------------------------------------------------------

function drawSmith(ctx, px, py, S) {
  const sx = px, sy = py;
  // Bald/short hair
  ctx.fillStyle = "#5a3a2a";
  ctx.fillRect(sx+5*S, sy+0*S, 6*S, 2*S);
  // Face
  ctx.fillStyle = SKIN;
  ctx.fillRect(sx+5*S, sy+2*S, 6*S, 4*S);
  // Eyes
  ctx.fillStyle = "#222";
  ctx.fillRect(sx+6*S, sy+3*S, S, S);
  ctx.fillRect(sx+9*S, sy+3*S, S, S);
  // Brown beard
  ctx.fillStyle = "#5a3a2a";
  ctx.fillRect(sx+6*S, sy+5*S, 4*S, S);
  // Leather apron over dark shirt
  ctx.fillStyle = "#4a4a4a";
  ctx.fillRect(sx+4*S, sy+6*S, 8*S, 5*S);
  ctx.fillStyle = "#8a5a2a";
  ctx.fillRect(sx+5*S, sy+6*S, 6*S, 5*S); // apron
  ctx.fillStyle = "#6a4010";
  ctx.fillRect(sx+6*S, sy+7*S, 4*S, S); // apron strap
  // Beefy arms
  ctx.fillStyle = SKIN;
  ctx.fillRect(sx+3*S, sy+7*S, S, 3*S);
  ctx.fillRect(sx+12*S, sy+7*S, S, 3*S);
  ctx.fillRect(sx+3*S, sy+10*S, S, S);
  ctx.fillRect(sx+12*S, sy+10*S, S, S);
  // Pants & boots
  ctx.fillStyle = PANTS;
  ctx.fillRect(sx+5*S, sy+11*S, 6*S, 2*S);
  ctx.fillStyle = BOOTS;
  ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
  ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
}

function drawPriest(ctx, px, py, S) {
  const sx = px, sy = py;
  // Bald head with tonsure
  ctx.fillStyle = SKIN;
  ctx.fillRect(sx+5*S, sy+0*S, 6*S, 6*S);
  ctx.fillStyle = "#6a5040";
  ctx.fillRect(sx+5*S, sy+0*S, 6*S, S); // ring of hair
  ctx.fillRect(sx+5*S, sy+0*S, S, 2*S);
  ctx.fillRect(sx+10*S, sy+0*S, S, 2*S);
  // Eyes
  ctx.fillStyle = "#222";
  ctx.fillRect(sx+6*S, sy+3*S, S, S);
  ctx.fillRect(sx+9*S, sy+3*S, S, S);
  // Kind smile
  ctx.fillStyle = "#a06060";
  ctx.fillRect(sx+7*S, sy+5*S, 2*S, S);
  // White robes
  ctx.fillStyle = "#e8e0d0";
  ctx.fillRect(sx+4*S, sy+6*S, 8*S, 5*S);
  ctx.fillRect(sx+3*S, sy+7*S, S, 3*S);
  ctx.fillRect(sx+12*S, sy+7*S, S, 3*S);
  // Gold cross on chest
  ctx.fillStyle = "#d4a840";
  ctx.fillRect(sx+7*S, sy+7*S, 2*S, S);
  ctx.fillRect(sx+7*S, sy+8*S, 2*S, 2*S);
  // Hands
  ctx.fillStyle = SKIN;
  ctx.fillRect(sx+3*S, sy+10*S, S, S);
  ctx.fillRect(sx+12*S, sy+10*S, S, S);
  // Robe skirt (no pants visible)
  ctx.fillStyle = "#d8d0c0";
  ctx.fillRect(sx+4*S, sy+11*S, 8*S, 2*S);
  // Sandals
  ctx.fillStyle = "#8a6a3a";
  ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
  ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
}

function drawBarmaid(ctx, px, py, S) {
  const sx = px, sy = py;
  // Red-brown hair, longer
  ctx.fillStyle = "#8a3020";
  ctx.fillRect(sx+4*S, sy+0*S, 8*S, 2*S);
  ctx.fillRect(sx+4*S, sy+2*S, 2*S, 4*S);
  ctx.fillRect(sx+10*S, sy+2*S, 2*S, 4*S);
  // Face
  ctx.fillStyle = SKIN;
  ctx.fillRect(sx+5*S, sy+2*S, 6*S, 4*S);
  // Eyes
  ctx.fillStyle = "#222";
  ctx.fillRect(sx+6*S, sy+3*S, S, S);
  ctx.fillRect(sx+9*S, sy+3*S, S, S);
  // Smile
  ctx.fillStyle = "#c06060";
  ctx.fillRect(sx+7*S, sy+5*S, 2*S, S);
  // Green dress with white apron
  ctx.fillStyle = "#3a8a3a";
  ctx.fillRect(sx+4*S, sy+6*S, 8*S, 5*S);
  ctx.fillStyle = "#e8e8e8";
  ctx.fillRect(sx+5*S, sy+7*S, 6*S, 4*S); // white apron
  // Arms
  ctx.fillStyle = "#3a8a3a";
  ctx.fillRect(sx+3*S, sy+7*S, S, 3*S);
  ctx.fillRect(sx+12*S, sy+7*S, S, 3*S);
  ctx.fillStyle = SKIN;
  ctx.fillRect(sx+3*S, sy+10*S, S, S);
  ctx.fillRect(sx+12*S, sy+10*S, S, S);
  // Skirt
  ctx.fillStyle = "#3a8a3a";
  ctx.fillRect(sx+4*S, sy+11*S, 8*S, 2*S);
  // Shoes
  ctx.fillStyle = "#4a2a1a";
  ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
  ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
}

function drawWitch(ctx, px, py, S) {
  const sx = px, sy = py;
  // Tall pointy hat
  ctx.fillStyle = "#2a1a3a";
  ctx.fillRect(sx+7*S, sy+0*S, 2*S, S);
  ctx.fillRect(sx+6*S, sy+1*S, 4*S, S);
  ctx.fillRect(sx+5*S, sy+2*S, 6*S, 2*S);
  ctx.fillRect(sx+3*S, sy+4*S, 10*S, S); // hat brim
  // Face — pale green tint
  ctx.fillStyle = "#c8d898";
  ctx.fillRect(sx+5*S, sy+5*S, 6*S, 3*S);
  // Eyes — glowing
  ctx.fillStyle = "#aa44cc";
  ctx.fillRect(sx+6*S, sy+5*S, S, S);
  ctx.fillRect(sx+9*S, sy+5*S, S, S);
  // Dark purple robes
  ctx.fillStyle = "#3a1a4a";
  ctx.fillRect(sx+4*S, sy+8*S, 8*S, 5*S);
  ctx.fillRect(sx+3*S, sy+9*S, S, 3*S);
  ctx.fillRect(sx+12*S, sy+9*S, S, 3*S);
  // Hands — bony
  ctx.fillStyle = "#c8d898";
  ctx.fillRect(sx+3*S, sy+12*S, S, S);
  ctx.fillRect(sx+12*S, sy+12*S, S, S);
  // Robe skirt
  ctx.fillStyle = "#2a1040";
  ctx.fillRect(sx+3*S, sy+13*S, 10*S, 2*S);
}

function drawGhost(ctx, px, py, S) {
  const sx = px, sy = py;
  // Floating bobbing effect
  const bob = Math.sin(Date.now() / 600) * S;
  const by = sy + bob;
  ctx.globalAlpha = 0.55;
  // Ghostly white/blue body
  ctx.fillStyle = "#c0d0e8";
  ctx.fillRect(sx+5*S, by+1*S, 6*S, 4*S); // head
  ctx.fillRect(sx+4*S, by+5*S, 8*S, 6*S); // body
  // Tattered bottom edge
  ctx.fillRect(sx+4*S, by+11*S, 2*S, 2*S);
  ctx.fillRect(sx+7*S, by+11*S, 2*S, 3*S);
  ctx.fillRect(sx+10*S, by+11*S, 2*S, 2*S);
  // Dark hollow eyes
  ctx.fillStyle = "#223";
  ctx.fillRect(sx+6*S, by+3*S, 2*S, 2*S);
  ctx.fillRect(sx+9*S, by+3*S, 2*S, 2*S);
  // Mouth
  ctx.fillRect(sx+7*S, by+5*S, 2*S, S);
  ctx.globalAlpha = 1;
}

function drawRanger(ctx, px, py, S) {
  const sx = px, sy = py;
  // Green hood
  ctx.fillStyle = "#3a6a2a";
  ctx.fillRect(sx+4*S, sy+0*S, 8*S, 3*S);
  ctx.fillRect(sx+4*S, sy+0*S, S, 4*S);
  ctx.fillRect(sx+11*S, sy+0*S, S, 4*S);
  // Face
  ctx.fillStyle = SKIN;
  ctx.fillRect(sx+5*S, sy+2*S, 6*S, 4*S);
  // Eyes
  ctx.fillStyle = "#222";
  ctx.fillRect(sx+6*S, sy+3*S, S, S);
  ctx.fillRect(sx+9*S, sy+3*S, S, S);
  // Green cloak/tunic
  ctx.fillStyle = "#4a7a3a";
  ctx.fillRect(sx+4*S, sy+6*S, 8*S, 5*S);
  ctx.fillRect(sx+3*S, sy+6*S, S, 4*S);
  ctx.fillRect(sx+12*S, sy+6*S, S, 4*S);
  // Belt
  ctx.fillStyle = "#6a4a1a";
  ctx.fillRect(sx+4*S, sy+9*S, 8*S, S);
  // Belt buckle
  ctx.fillStyle = "#c8a838";
  ctx.fillRect(sx+7*S, sy+9*S, 2*S, S);
  // Hands
  ctx.fillStyle = SKIN;
  ctx.fillRect(sx+3*S, sy+10*S, S, S);
  ctx.fillRect(sx+12*S, sy+10*S, S, S);
  // Brown pants & boots
  ctx.fillStyle = "#6a5a3a";
  ctx.fillRect(sx+5*S, sy+11*S, 6*S, 2*S);
  ctx.fillStyle = "#4a3a1a";
  ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
  ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
}

function drawFarmer(ctx, px, py, S) {
  const sx = px, sy = py;
  // Straw hat
  ctx.fillStyle = "#c8a838";
  ctx.fillRect(sx+5*S, sy+0*S, 6*S, S);
  ctx.fillRect(sx+3*S, sy+1*S, 10*S, S); // wide brim
  ctx.fillStyle = "#b89828";
  ctx.fillRect(sx+5*S, sy+2*S, 6*S, S);
  // Face
  ctx.fillStyle = "#d8b880";
  ctx.fillRect(sx+5*S, sy+3*S, 6*S, 3*S);
  // Eyes
  ctx.fillStyle = "#222";
  ctx.fillRect(sx+6*S, sy+4*S, S, S);
  ctx.fillRect(sx+9*S, sy+4*S, S, S);
  // Brown tunic
  ctx.fillStyle = "#8a7a5a";
  ctx.fillRect(sx+4*S, sy+6*S, 8*S, 5*S);
  ctx.fillRect(sx+3*S, sy+7*S, S, 3*S);
  ctx.fillRect(sx+12*S, sy+7*S, S, 3*S);
  // Hands
  ctx.fillStyle = "#d8b880";
  ctx.fillRect(sx+3*S, sy+10*S, S, S);
  ctx.fillRect(sx+12*S, sy+10*S, S, S);
  // Pants
  ctx.fillStyle = "#5a5040";
  ctx.fillRect(sx+5*S, sy+11*S, 6*S, 2*S);
  // Boots
  ctx.fillStyle = BOOTS;
  ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
  ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
}

function drawNomad(ctx, px, py, S) {
  const sx = px, sy = py;
  // Head wrap / turban
  ctx.fillStyle = "#d8c8a0";
  ctx.fillRect(sx+5*S, sy+0*S, 6*S, 3*S);
  ctx.fillRect(sx+4*S, sy+1*S, S, 2*S);
  ctx.fillRect(sx+11*S, sy+1*S, S, 2*S);
  // Trailing cloth
  ctx.fillRect(sx+11*S, sy+3*S, S, 3*S);
  // Face — tanned
  ctx.fillStyle = "#c8a070";
  ctx.fillRect(sx+5*S, sy+3*S, 6*S, 3*S);
  // Eyes
  ctx.fillStyle = "#222";
  ctx.fillRect(sx+6*S, sy+4*S, S, S);
  ctx.fillRect(sx+9*S, sy+4*S, S, S);
  // Sandy robes
  ctx.fillStyle = "#c0a870";
  ctx.fillRect(sx+4*S, sy+6*S, 8*S, 5*S);
  ctx.fillRect(sx+3*S, sy+7*S, S, 3*S);
  ctx.fillRect(sx+12*S, sy+7*S, S, 3*S);
  // Sash
  ctx.fillStyle = "#8a3030";
  ctx.fillRect(sx+4*S, sy+8*S, 8*S, S);
  // Hands
  ctx.fillStyle = "#c8a070";
  ctx.fillRect(sx+3*S, sy+10*S, S, S);
  ctx.fillRect(sx+12*S, sy+10*S, S, S);
  // Loose pants
  ctx.fillStyle = "#a89868";
  ctx.fillRect(sx+5*S, sy+11*S, 6*S, 2*S);
  // Sandals
  ctx.fillStyle = "#8a6a3a";
  ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
  ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
}

function drawMerchant(ctx, px, py, S) {
  const sx = px, sy = py;
  // Hat — flat cap
  ctx.fillStyle = "#6a2a2a";
  ctx.fillRect(sx+4*S, sy+0*S, 8*S, 2*S);
  ctx.fillRect(sx+3*S, sy+2*S, 10*S, S);
  // Face
  ctx.fillStyle = SKIN;
  ctx.fillRect(sx+5*S, sy+3*S, 6*S, 3*S);
  // Eyes
  ctx.fillStyle = "#222";
  ctx.fillRect(sx+6*S, sy+3*S, S, S);
  ctx.fillRect(sx+9*S, sy+3*S, S, S);
  // Mustache
  ctx.fillStyle = "#5a3a20";
  ctx.fillRect(sx+6*S, sy+5*S, S, S);
  ctx.fillRect(sx+9*S, sy+5*S, S, S);
  // Rich red vest over white shirt
  ctx.fillStyle = "#e8e0d0";
  ctx.fillRect(sx+4*S, sy+6*S, 8*S, 5*S);
  ctx.fillStyle = "#8a2a2a";
  ctx.fillRect(sx+5*S, sy+6*S, 6*S, 5*S); // vest
  // Gold buttons
  ctx.fillStyle = "#d4a840";
  ctx.fillRect(sx+7*S, sy+7*S, 2*S, S);
  ctx.fillRect(sx+7*S, sy+9*S, 2*S, S);
  // Sleeves
  ctx.fillStyle = "#e8e0d0";
  ctx.fillRect(sx+3*S, sy+7*S, S, 3*S);
  ctx.fillRect(sx+12*S, sy+7*S, S, 3*S);
  // Hands
  ctx.fillStyle = SKIN;
  ctx.fillRect(sx+3*S, sy+10*S, S, S);
  ctx.fillRect(sx+12*S, sy+10*S, S, S);
  // Pants
  ctx.fillStyle = "#3a3a5a";
  ctx.fillRect(sx+5*S, sy+11*S, 6*S, 2*S);
  // Boots
  ctx.fillStyle = BOOTS;
  ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
  ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
}

function drawElder(ctx, px, py, S) {
  const sx = px, sy = py;
  // White/grey hair
  ctx.fillStyle = "#b0a8a0";
  ctx.fillRect(sx+5*S, sy+0*S, 6*S, 2*S);
  ctx.fillRect(sx+4*S, sy+1*S, S, 4*S);
  ctx.fillRect(sx+11*S, sy+1*S, S, 4*S);
  // Face — weathered
  ctx.fillStyle = "#d0b888";
  ctx.fillRect(sx+5*S, sy+2*S, 6*S, 4*S);
  // Eyes
  ctx.fillStyle = "#222";
  ctx.fillRect(sx+6*S, sy+3*S, S, S);
  ctx.fillRect(sx+9*S, sy+3*S, S, S);
  // Long white beard
  ctx.fillStyle = "#c0b8b0";
  ctx.fillRect(sx+6*S, sy+5*S, 4*S, S);
  ctx.fillRect(sx+6*S, sy+6*S, 4*S, 2*S);
  ctx.fillRect(sx+7*S, sy+8*S, 2*S, S);
  // Brown robe
  ctx.fillStyle = "#6a5a3a";
  ctx.fillRect(sx+4*S, sy+6*S, 2*S, 5*S);
  ctx.fillRect(sx+10*S, sy+6*S, 2*S, 5*S);
  ctx.fillRect(sx+4*S, sy+8*S, 8*S, 3*S);
  // Arms
  ctx.fillRect(sx+3*S, sy+8*S, S, 2*S);
  ctx.fillRect(sx+12*S, sy+8*S, S, 2*S);
  // Walking stick implied by hand
  ctx.fillStyle = "#d0b888";
  ctx.fillRect(sx+3*S, sy+10*S, S, S);
  ctx.fillRect(sx+12*S, sy+10*S, S, S);
  // Robe bottom
  ctx.fillStyle = "#5a4a2a";
  ctx.fillRect(sx+4*S, sy+11*S, 8*S, 2*S);
  // Sandals
  ctx.fillStyle = "#8a6a3a";
  ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
  ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
}

function drawFisher(ctx, px, py, S) {
  const sx = px, sy = py;
  // Bucket hat
  ctx.fillStyle = "#5a7a8a";
  ctx.fillRect(sx+5*S, sy+0*S, 6*S, 2*S);
  ctx.fillRect(sx+3*S, sy+2*S, 10*S, S); // brim
  // Face — weathered/tanned
  ctx.fillStyle = "#d0a870";
  ctx.fillRect(sx+5*S, sy+3*S, 6*S, 3*S);
  // Eyes
  ctx.fillStyle = "#222";
  ctx.fillRect(sx+6*S, sy+4*S, S, S);
  ctx.fillRect(sx+9*S, sy+4*S, S, S);
  // Stubble
  ctx.fillStyle = "#9a8a6a";
  ctx.fillRect(sx+6*S, sy+5*S, 4*S, S);
  // Blue-grey vest
  ctx.fillStyle = "#5a7080";
  ctx.fillRect(sx+4*S, sy+6*S, 8*S, 5*S);
  ctx.fillRect(sx+3*S, sy+7*S, S, 3*S);
  ctx.fillRect(sx+12*S, sy+7*S, S, 3*S);
  // Hands
  ctx.fillStyle = "#d0a870";
  ctx.fillRect(sx+3*S, sy+10*S, S, S);
  ctx.fillRect(sx+12*S, sy+10*S, S, S);
  // Waders / rolled up pants
  ctx.fillStyle = "#5a5040";
  ctx.fillRect(sx+5*S, sy+11*S, 6*S, 2*S);
  // Boots
  ctx.fillStyle = "#4a3a2a";
  ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
  ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
}

function drawGhostKnight(ctx, px, py, S) {
  const sx = px, sy = py;
  const bob = Math.sin(Date.now() / 700) * S;
  const by = sy + bob;
  ctx.globalAlpha = 0.5;
  // Ghostly helmet
  ctx.fillStyle = "#8898b0";
  ctx.fillRect(sx+4*S, by+0*S, 8*S, 3*S);
  ctx.fillStyle = "#607080";
  ctx.fillRect(sx+4*S, by+2*S, 8*S, S); // visor
  // Hollow eyes
  ctx.fillStyle = "#dd3333";
  ctx.fillRect(sx+6*S, by+2*S, S, S);
  ctx.fillRect(sx+9*S, by+2*S, S, S);
  // Ghostly face
  ctx.fillStyle = "#a0b0c8";
  ctx.fillRect(sx+5*S, by+3*S, 6*S, 3*S);
  // Spectral armor
  ctx.fillStyle = "#7888a0";
  ctx.fillRect(sx+4*S, by+6*S, 8*S, 5*S);
  ctx.fillRect(sx+3*S, by+6*S, S, 4*S);
  ctx.fillRect(sx+12*S, by+6*S, S, 4*S);
  // Tattered bottom
  ctx.fillStyle = "#6878a0";
  ctx.fillRect(sx+4*S, by+11*S, 2*S, 2*S);
  ctx.fillRect(sx+7*S, by+11*S, 2*S, 3*S);
  ctx.fillRect(sx+10*S, by+11*S, 2*S, 2*S);
  ctx.globalAlpha = 1;
}

// ---------------------------------------------------------------------------
// NPC name → draw function mapping
// ---------------------------------------------------------------------------
const NPC_SPRITES = {
  "guard": drawGuard,
  "smith": drawSmith,
  "priest": drawPriest,
  "barmaid": drawBarmaid,
  "amara": drawAmara,
  "witch": drawWitch,
  "ghost": drawGhost,
  "ghost_knight": drawGhostKnight,
  "ranger": drawRanger,
  "farmer": drawFarmer,
  "nomad": drawNomad,
  "merchant": drawMerchant,
  "elder": drawElder,
  "fisher": drawFisher,
};

function drawNPC(ctx, px, py, sprite, S) {
  const fn = NPC_SPRITES[sprite];
  if (fn) {
    fn(ctx, px, py, S);
  } else {
    drawGuard(ctx, px, py, S);
  }
}

// Attack animation — player thrust pose (2 frames)
function drawPlayerAttack(ctx, px, py, direction, colorIndex, attackFrame, S) {
  const sx = px;
  const sy = py;
  const shirt = SHIRT_COLORS[colorIndex % SHIRT_COLORS.length];
  const thrust = attackFrame === 1; // frame 0 = wind-up, frame 1 = full thrust

  if (direction === "down") {
    // Hair
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+5*S, sy+0*S, 6*S, 2*S);
    // Face
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+5*S, sy+2*S, 6*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+6*S, sy+3*S, S, S);
    ctx.fillRect(sx+9*S, sy+3*S, S, S);
    // Torso — shifted down slightly on thrust
    const tOff = thrust ? S : 0;
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+4*S, sy+6*S+tOff, 8*S, 5*S);
    // Left arm normal
    ctx.fillRect(sx+3*S, sy+6*S+tOff, S, 4*S);
    // Right arm — extends down (holding sword)
    ctx.fillRect(sx+12*S, sy+6*S+tOff, S, 4*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+3*S, sy+10*S+tOff, S, S);
    ctx.fillRect(sx+12*S, sy+10*S+tOff, S, S);
    // Pants & boots
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
    // Left arm extends out (holding sword)
    ctx.fillRect(sx+3*S+tOff, sy+7*S, 2*S, 3*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+2*S+tOff, sy+8*S, S, S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+5*S, sy+11*S, 5*S, 2*S);
    ctx.fillStyle = BOOTS;
    ctx.fillRect(sx+5*S, sy+13*S, 3*S, 2*S);
  } else {
    // Right
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
    // Right arm extends out (holding sword)
    ctx.fillRect(sx+11*S+tOff, sy+7*S, 2*S, 3*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+13*S+tOff, sy+8*S, S, S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+6*S, sy+11*S, 5*S, 2*S);
    ctx.fillStyle = BOOTS;
    ctx.fillRect(sx+8*S, sy+13*S, 3*S, 2*S);
  }
}

// Sword sprite — drawn on the tile in front of the attacking player
function drawSwordAttack(ctx, px, py, direction, attackFrame, S) {
  const BLADE = "#C0C0C0";
  const HILT = "#8B4513";
  const GUARD = "#DAA520";
  const thrust = attackFrame === 1;
  const ext = thrust ? 4*S : 2*S;  // extension distance

  if (direction === "down") {
    const sx = px + 7*S;   // center of tile
    const sy = py + 16*S;  // just below the player tile
    // Hilt
    ctx.fillStyle = HILT;
    ctx.fillRect(sx - S, sy, 2*S, 3*S);
    // Guard
    ctx.fillStyle = GUARD;
    ctx.fillRect(sx - 2*S, sy + 3*S, 4*S, S);
    // Blade
    ctx.fillStyle = BLADE;
    ctx.fillRect(sx - S, sy + 4*S, 2*S, ext);
    // Tip
    ctx.fillRect(sx, sy + 4*S + ext, S, S);
  } else if (direction === "up") {
    const sx = px + 7*S;
    const sy = py - S;     // just above the player tile
    // Hilt
    ctx.fillStyle = HILT;
    ctx.fillRect(sx - S, sy - 2*S, 2*S, 3*S);
    // Guard
    ctx.fillStyle = GUARD;
    ctx.fillRect(sx - 2*S, sy - 3*S, 4*S, S);
    // Blade
    ctx.fillStyle = BLADE;
    ctx.fillRect(sx - S, sy - 3*S - ext, 2*S, ext);
    // Tip
    ctx.fillRect(sx, sy - 4*S - ext, S, S);
  } else if (direction === "left") {
    const sx = px - S;     // just left of player tile
    const sy = py + 7*S;
    // Hilt
    ctx.fillStyle = HILT;
    ctx.fillRect(sx - 2*S, sy - S, 3*S, 2*S);
    // Guard
    ctx.fillStyle = GUARD;
    ctx.fillRect(sx - 3*S, sy - 2*S, S, 4*S);
    // Blade
    ctx.fillStyle = BLADE;
    ctx.fillRect(sx - 3*S - ext, sy - S, ext, 2*S);
    // Tip
    ctx.fillRect(sx - 4*S - ext, sy, S, S);
  } else {
    // Right
    const sx = px + 16*S;  // just right of player tile
    const sy = py + 7*S;
    // Hilt
    ctx.fillStyle = HILT;
    ctx.fillRect(sx, sy - S, 3*S, 2*S);
    // Guard
    ctx.fillStyle = GUARD;
    ctx.fillRect(sx + 3*S, sy - 2*S, S, 4*S);
    // Blade
    ctx.fillStyle = BLADE;
    ctx.fillRect(sx + 4*S, sy - S, ext, 2*S);
    // Tip
    ctx.fillRect(sx + 4*S + ext, sy, S, S);
  }
}

// ---------------------------------------------------------------------------
// Slime sprite — green blob with hop animation
// ---------------------------------------------------------------------------
function drawSlime(ctx, px, py, hopFrame, S) {
  const BODY = "#44cc44";
  const DARK = "#228822";
  const EYES = "#222";
  const HIGHLIGHT = "#88ee88";

  if (hopFrame === 0) {
    // Squished — wider, shorter, on ground
    // Dark outline/shadow
    ctx.fillStyle = DARK;
    ctx.fillRect(px+2*S, py+9*S, 12*S, 6*S);
    // Body
    ctx.fillStyle = BODY;
    ctx.fillRect(px+3*S, py+8*S, 10*S, 6*S);
    ctx.fillRect(px+4*S, py+7*S, 8*S, S);
    // Eyes
    ctx.fillStyle = EYES;
    ctx.fillRect(px+5*S, py+9*S, 2*S, 2*S);
    ctx.fillRect(px+9*S, py+9*S, 2*S, 2*S);
    // Highlight
    ctx.fillStyle = HIGHLIGHT;
    ctx.fillRect(px+5*S, py+8*S, 2*S, S);
  } else {
    // Stretched — taller, narrower, lifted up
    // Dark outline/shadow on ground
    ctx.fillStyle = DARK;
    ctx.fillRect(px+4*S, py+12*S, 8*S, 2*S);
    // Body
    ctx.fillStyle = BODY;
    ctx.fillRect(px+4*S, py+4*S, 8*S, 9*S);
    ctx.fillRect(px+5*S, py+3*S, 6*S, S);
    ctx.fillRect(px+5*S, py+13*S, 6*S, S);
    // Dark bottom edge
    ctx.fillStyle = DARK;
    ctx.fillRect(px+4*S, py+11*S, 8*S, 2*S);
    // Eyes
    ctx.fillStyle = EYES;
    ctx.fillRect(px+5*S, py+6*S, 2*S, 2*S);
    ctx.fillRect(px+9*S, py+6*S, 2*S, 2*S);
    // Highlight
    ctx.fillStyle = HIGHLIGHT;
    ctx.fillRect(px+5*S, py+4*S, 2*S, S);
  }
}

function drawSlimeDeath(ctx, px, py, deathFrame, S) {
  const SPLAT = "#44cc44";
  const DARK = "#228822";

  if (deathFrame === 0) {
    // Flat splat
    ctx.fillStyle = DARK;
    ctx.fillRect(px+2*S, py+12*S, 12*S, 2*S);
    ctx.fillStyle = SPLAT;
    ctx.fillRect(px+3*S, py+11*S, 10*S, 2*S);
    ctx.fillRect(px+1*S, py+12*S, 14*S, S);
  } else if (deathFrame === 1) {
    // Particles spreading
    ctx.fillStyle = SPLAT;
    ctx.fillRect(px+1*S, py+12*S, 3*S, 2*S);
    ctx.fillRect(px+6*S, py+11*S, 4*S, 2*S);
    ctx.fillRect(px+12*S, py+12*S, 3*S, 2*S);
    ctx.fillRect(px+3*S, py+9*S, 2*S, 2*S);
    ctx.fillRect(px+10*S, py+8*S, 2*S, 2*S);
    ctx.fillStyle = DARK;
    ctx.fillRect(px+5*S, py+13*S, 2*S, S);
    ctx.fillRect(px+9*S, py+13*S, 2*S, S);
  } else {
    // Fading particles
    ctx.globalAlpha = 0.4;
    ctx.fillStyle = SPLAT;
    ctx.fillRect(px+0*S, py+13*S, 2*S, S);
    ctx.fillRect(px+6*S, py+12*S, 3*S, S);
    ctx.fillRect(px+13*S, py+13*S, 2*S, S);
    ctx.fillRect(px+3*S, py+8*S, S, S);
    ctx.fillRect(px+11*S, py+7*S, S, S);
    ctx.globalAlpha = 1;
  }
}

// ---------------------------------------------------------------------------
// Bat sprite — dark flapping creature
// ---------------------------------------------------------------------------
function drawBat(ctx, px, py, hopFrame, S) {
  const BODY = "#3a2a4a";
  const WING = "#5a3a6a";
  const EYES = "#ff4444";

  if (hopFrame === 0) {
    // Wings up
    ctx.fillStyle = BODY;
    ctx.fillRect(px+6*S, py+6*S, 4*S, 4*S);
    ctx.fillStyle = WING;
    ctx.fillRect(px+1*S, py+3*S, 5*S, 4*S);
    ctx.fillRect(px+10*S, py+3*S, 5*S, 4*S);
    ctx.fillRect(px+2*S, py+2*S, 3*S, S);
    ctx.fillRect(px+11*S, py+2*S, 3*S, S);
    ctx.fillStyle = EYES;
    ctx.fillRect(px+6*S, py+7*S, S, S);
    ctx.fillRect(px+9*S, py+7*S, S, S);
  } else {
    // Wings down
    ctx.fillStyle = BODY;
    ctx.fillRect(px+6*S, py+5*S, 4*S, 4*S);
    ctx.fillStyle = WING;
    ctx.fillRect(px+1*S, py+7*S, 5*S, 4*S);
    ctx.fillRect(px+10*S, py+7*S, 5*S, 4*S);
    ctx.fillRect(px+2*S, py+11*S, 3*S, S);
    ctx.fillRect(px+11*S, py+11*S, 3*S, S);
    ctx.fillStyle = EYES;
    ctx.fillRect(px+6*S, py+6*S, S, S);
    ctx.fillRect(px+9*S, py+6*S, S, S);
  }
}

function drawBatDeath(ctx, px, py, deathFrame, S) {
  const CLR = "#3a2a4a";
  if (deathFrame === 0) {
    ctx.fillStyle = CLR;
    ctx.fillRect(px+3*S, py+11*S, 10*S, 2*S);
    ctx.fillRect(px+1*S, py+12*S, 14*S, S);
  } else if (deathFrame === 1) {
    ctx.fillStyle = CLR;
    ctx.fillRect(px+1*S, py+12*S, 3*S, 2*S);
    ctx.fillRect(px+6*S, py+11*S, 4*S, 2*S);
    ctx.fillRect(px+12*S, py+12*S, 3*S, 2*S);
  } else {
    ctx.globalAlpha = 0.4;
    ctx.fillStyle = CLR;
    ctx.fillRect(px+0*S, py+13*S, 2*S, S);
    ctx.fillRect(px+7*S, py+12*S, 2*S, S);
    ctx.fillRect(px+13*S, py+13*S, 2*S, S);
    ctx.globalAlpha = 1;
  }
}

// ---------------------------------------------------------------------------
// Scorpion sprite — desert creature
// ---------------------------------------------------------------------------
function drawScorpion(ctx, px, py, hopFrame, S) {
  const BODY = "#8a5a2a";
  const DARK = "#6a4a1a";
  const CLAW = "#aa7a3a";
  const TAIL = "#7a4a1a";

  const yOff = hopFrame === 0 ? 0 : -S;
  ctx.fillStyle = BODY;
  ctx.fillRect(px+5*S, py+8*S+yOff, 6*S, 4*S);
  ctx.fillStyle = DARK;
  ctx.fillRect(px+6*S, py+9*S+yOff, 4*S, 2*S);
  // Claws
  ctx.fillStyle = CLAW;
  ctx.fillRect(px+2*S, py+7*S+yOff, 3*S, 2*S);
  ctx.fillRect(px+11*S, py+7*S+yOff, 3*S, 2*S);
  ctx.fillRect(px+1*S, py+6*S+yOff, 2*S, S);
  ctx.fillRect(px+13*S, py+6*S+yOff, 2*S, S);
  // Tail curving up
  ctx.fillStyle = TAIL;
  ctx.fillRect(px+7*S, py+5*S+yOff, 2*S, 3*S);
  ctx.fillRect(px+7*S, py+3*S+yOff, 2*S, 2*S);
  ctx.fillRect(px+8*S, py+2*S+yOff, 2*S, 2*S);
  ctx.fillStyle = "#cc4444";
  ctx.fillRect(px+9*S, py+1*S+yOff, S, 2*S);
  // Legs
  ctx.fillStyle = DARK;
  ctx.fillRect(px+4*S, py+12*S+yOff, S, 2*S);
  ctx.fillRect(px+11*S, py+12*S+yOff, S, 2*S);
  ctx.fillRect(px+3*S, py+11*S+yOff, S, 2*S);
  ctx.fillRect(px+12*S, py+11*S+yOff, S, 2*S);
}

function drawScorpionDeath(ctx, px, py, deathFrame, S) {
  const CLR = "#8a5a2a";
  if (deathFrame === 0) {
    ctx.fillStyle = CLR;
    ctx.fillRect(px+3*S, py+11*S, 10*S, 3*S);
  } else if (deathFrame === 1) {
    ctx.fillStyle = CLR;
    ctx.fillRect(px+1*S, py+12*S, 3*S, 2*S);
    ctx.fillRect(px+7*S, py+11*S, 3*S, 2*S);
    ctx.fillRect(px+12*S, py+12*S, 2*S, 2*S);
  } else {
    ctx.globalAlpha = 0.4;
    ctx.fillStyle = CLR;
    ctx.fillRect(px+0*S, py+13*S, 2*S, S);
    ctx.fillRect(px+7*S, py+12*S, 2*S, S);
    ctx.fillRect(px+14*S, py+13*S, 2*S, S);
    ctx.globalAlpha = 1;
  }
}

// ---------------------------------------------------------------------------
// Skeleton sprite — bony undead
// ---------------------------------------------------------------------------
function drawSkeleton(ctx, px, py, hopFrame, S) {
  const BONE = "#ddd8cc";
  const DARK = "#aaa89a";
  const EYES = "#222";

  const yOff = hopFrame === 0 ? 0 : -S;
  // Skull
  ctx.fillStyle = BONE;
  ctx.fillRect(px+5*S, py+1*S+yOff, 6*S, 5*S);
  ctx.fillStyle = EYES;
  ctx.fillRect(px+6*S, py+3*S+yOff, 2*S, 2*S);
  ctx.fillRect(px+9*S, py+3*S+yOff, 2*S, 2*S);
  ctx.fillRect(px+7*S, py+5*S+yOff, 2*S, S);
  // Ribcage
  ctx.fillStyle = BONE;
  ctx.fillRect(px+6*S, py+6*S+yOff, 4*S, 5*S);
  ctx.fillStyle = DARK;
  ctx.fillRect(px+7*S, py+7*S+yOff, 2*S, S);
  ctx.fillRect(px+7*S, py+9*S+yOff, 2*S, S);
  // Arms
  ctx.fillStyle = BONE;
  ctx.fillRect(px+4*S, py+7*S+yOff, 2*S, S);
  ctx.fillRect(px+3*S, py+8*S+yOff, S, 3*S);
  ctx.fillRect(px+10*S, py+7*S+yOff, 2*S, S);
  ctx.fillRect(px+12*S, py+8*S+yOff, S, 3*S);
  // Legs
  ctx.fillStyle = BONE;
  ctx.fillRect(px+6*S, py+11*S+yOff, 2*S, 3*S);
  ctx.fillRect(px+9*S, py+11*S+yOff, 2*S, 3*S);
  ctx.fillStyle = DARK;
  ctx.fillRect(px+5*S, py+14*S+yOff, 3*S, S);
  ctx.fillRect(px+9*S, py+14*S+yOff, 3*S, S);
}

function drawSkeletonDeath(ctx, px, py, deathFrame, S) {
  const CLR = "#ddd8cc";
  if (deathFrame === 0) {
    ctx.fillStyle = CLR;
    ctx.fillRect(px+3*S, py+11*S, 10*S, 3*S);
    ctx.fillRect(px+5*S, py+10*S, 6*S, S);
  } else if (deathFrame === 1) {
    ctx.fillStyle = CLR;
    ctx.fillRect(px+1*S, py+12*S, 3*S, 2*S);
    ctx.fillRect(px+5*S, py+13*S, 2*S, S);
    ctx.fillRect(px+8*S, py+11*S, 3*S, 2*S);
    ctx.fillRect(px+12*S, py+13*S, 3*S, S);
  } else {
    ctx.globalAlpha = 0.4;
    ctx.fillStyle = CLR;
    ctx.fillRect(px+0*S, py+13*S, 2*S, S);
    ctx.fillRect(px+6*S, py+14*S, 2*S, S);
    ctx.fillRect(px+13*S, py+13*S, 2*S, S);
    ctx.globalAlpha = 1;
  }
}

// ---------------------------------------------------------------------------
// Swamp blob sprite — murky green ooze
// ---------------------------------------------------------------------------
function drawSwampBlob(ctx, px, py, hopFrame, S) {
  const BODY = "#5a7a3a";
  const DARK = "#3a5a2a";
  const EYES = "#cc2";
  const HIGHLIGHT = "#7a9a5a";

  if (hopFrame === 0) {
    ctx.fillStyle = DARK;
    ctx.fillRect(px+2*S, py+9*S, 12*S, 6*S);
    ctx.fillStyle = BODY;
    ctx.fillRect(px+3*S, py+8*S, 10*S, 6*S);
    ctx.fillRect(px+4*S, py+7*S, 8*S, S);
    ctx.fillStyle = EYES;
    ctx.fillRect(px+5*S, py+9*S, 2*S, 2*S);
    ctx.fillRect(px+9*S, py+9*S, 2*S, 2*S);
    ctx.fillStyle = HIGHLIGHT;
    ctx.fillRect(px+5*S, py+8*S, 2*S, S);
  } else {
    ctx.fillStyle = DARK;
    ctx.fillRect(px+4*S, py+12*S, 8*S, 2*S);
    ctx.fillStyle = BODY;
    ctx.fillRect(px+4*S, py+4*S, 8*S, 9*S);
    ctx.fillRect(px+5*S, py+3*S, 6*S, S);
    ctx.fillRect(px+5*S, py+13*S, 6*S, S);
    ctx.fillStyle = DARK;
    ctx.fillRect(px+4*S, py+11*S, 8*S, 2*S);
    ctx.fillStyle = EYES;
    ctx.fillRect(px+5*S, py+6*S, 2*S, 2*S);
    ctx.fillRect(px+9*S, py+6*S, 2*S, 2*S);
    ctx.fillStyle = HIGHLIGHT;
    ctx.fillRect(px+5*S, py+4*S, 2*S, S);
  }
}

function drawSwampBlobDeath(ctx, px, py, deathFrame, S) {
  const SPLAT = "#5a7a3a";
  const DARK = "#3a5a2a";
  if (deathFrame === 0) {
    ctx.fillStyle = DARK;
    ctx.fillRect(px+2*S, py+12*S, 12*S, 2*S);
    ctx.fillStyle = SPLAT;
    ctx.fillRect(px+3*S, py+11*S, 10*S, 2*S);
    ctx.fillRect(px+1*S, py+12*S, 14*S, S);
  } else if (deathFrame === 1) {
    ctx.fillStyle = SPLAT;
    ctx.fillRect(px+1*S, py+12*S, 3*S, 2*S);
    ctx.fillRect(px+6*S, py+11*S, 4*S, 2*S);
    ctx.fillRect(px+12*S, py+12*S, 3*S, 2*S);
  } else {
    ctx.globalAlpha = 0.4;
    ctx.fillStyle = SPLAT;
    ctx.fillRect(px+0*S, py+13*S, 2*S, S);
    ctx.fillRect(px+6*S, py+12*S, 3*S, S);
    ctx.fillRect(px+13*S, py+13*S, 2*S, S);
    ctx.globalAlpha = 1;
  }
}

// ---------------------------------------------------------------------------
// Princess Amara — sleeping figure on altar with pulsing glow
// ---------------------------------------------------------------------------
function drawAmara(ctx, px, py, S) {
  const DRESS = "#b8c8e8";
  const DRESS_DARK = "#8898b8";
  const HAIR_GOLD = "#d4a840";
  const CROWN = "#e6b422";

  // Faint pulsing glow
  const pulse = (Math.sin(Date.now() / 800) + 1) / 2; // 0..1
  const glowAlpha = 0.08 + pulse * 0.12;
  ctx.fillStyle = `rgba(180, 200, 255, ${glowAlpha})`;
  ctx.fillRect(px+2*S, py+0*S, 12*S, 10*S);

  // Altar / bed stone slab
  ctx.fillStyle = "#606870";
  ctx.fillRect(px+1*S, py+9*S, 14*S, 3*S);
  ctx.fillStyle = "#505860";
  ctx.fillRect(px+2*S, py+8*S, 12*S, S);

  // Body — horizontal, lying on her back (head on left side)
  // Hair flowing left
  ctx.fillStyle = HAIR_GOLD;
  ctx.fillRect(px+2*S, py+3*S, 3*S, 4*S);
  ctx.fillRect(px+1*S, py+4*S, S, 3*S);

  // Crown / tiara
  ctx.fillStyle = CROWN;
  ctx.fillRect(px+3*S, py+3*S, 2*S, S);
  ctx.fillRect(px+4*S, py+2*S, S, S);

  // Face
  ctx.fillStyle = SKIN;
  ctx.fillRect(px+5*S, py+3*S, 3*S, 4*S);

  // Closed eyes (horizontal lines)
  ctx.fillStyle = "#666";
  ctx.fillRect(px+5*S, py+5*S, 2*S, S);

  // Dress body — horizontal
  ctx.fillStyle = DRESS;
  ctx.fillRect(px+8*S, py+3*S, 5*S, 4*S);
  ctx.fillStyle = DRESS_DARK;
  ctx.fillRect(px+8*S, py+6*S, 5*S, S);

  // Hands folded on chest
  ctx.fillStyle = SKIN;
  ctx.fillRect(px+9*S, py+3*S, 2*S, S);

  // Dress skirt extending right
  ctx.fillStyle = DRESS;
  ctx.fillRect(px+13*S, py+4*S, S, 3*S);
}

// ---------------------------------------------------------------------------
// Sword pickup animation — sword icon rising above player
// ---------------------------------------------------------------------------
function drawSwordPickup(ctx, px, py, frame, S) {
  const BLADE = "#C0C0C0";
  const HILT = "#8B4513";
  const GUARD = "#DAA520";

  // Rise offset — sword floats upward over 4 frames
  const riseY = frame * 4 * S;
  const sx = px + 6*S;
  const sy = py - 4*S - riseY;

  // Glow behind sword
  const alpha = Math.max(0, 1 - frame * 0.2);
  ctx.globalAlpha = alpha;
  ctx.fillStyle = "rgba(230, 180, 34, 0.4)";
  ctx.fillRect(sx - 2*S, sy - S, 6*S, 14*S);

  // Blade pointing up
  ctx.fillStyle = BLADE;
  ctx.fillRect(sx, sy, 2*S, 6*S);
  // Tip
  ctx.fillRect(sx + S*0.5, sy - S, S, S);

  // Guard
  ctx.fillStyle = GUARD;
  ctx.fillRect(sx - S, sy + 6*S, 4*S, S);

  // Hilt
  ctx.fillStyle = HILT;
  ctx.fillRect(sx, sy + 7*S, 2*S, 3*S);

  ctx.globalAlpha = 1;
}

// ---------------------------------------------------------------------------
// Heart sprites — HUD and pickup
// ---------------------------------------------------------------------------
function drawHeart(ctx, px, py, state, S) {
  // 12x11 pixel-art heart at scale S
  // state: "full", "half", "empty"
  const RED = "#e03030";
  const DARK_RED = "#a02020";
  const GREY = "#555";
  const DARK_GREY = "#333";

  const full = state === "full";
  const half = state === "half";
  const leftColor = (full || half) ? RED : GREY;
  const leftDark = (full || half) ? DARK_RED : DARK_GREY;
  const rightColor = full ? RED : GREY;
  const rightDark = full ? DARK_RED : DARK_GREY;

  // Left half of heart
  ctx.fillStyle = leftColor;
  ctx.fillRect(px+1*S, py+0*S, 4*S, S);
  ctx.fillRect(px+0*S, py+1*S, 6*S, 2*S);
  ctx.fillRect(px+0*S, py+3*S, 6*S, 2*S);
  ctx.fillRect(px+1*S, py+5*S, 5*S, 2*S);
  ctx.fillRect(px+2*S, py+7*S, 4*S, S);
  ctx.fillRect(px+3*S, py+8*S, 3*S, S);
  ctx.fillRect(px+4*S, py+9*S, 2*S, S);
  ctx.fillRect(px+5*S, py+10*S, S, S);
  // Left highlight
  ctx.fillStyle = "#ff6060";
  if (full || half) {
    ctx.fillRect(px+1*S, py+1*S, 2*S, S);
  }
  // Left shadow
  ctx.fillStyle = leftDark;
  ctx.fillRect(px+0*S, py+4*S, S, S);
  ctx.fillRect(px+1*S, py+6*S, S, S);

  // Right half of heart
  ctx.fillStyle = rightColor;
  ctx.fillRect(px+7*S, py+0*S, 4*S, S);
  ctx.fillRect(px+6*S, py+1*S, 6*S, 2*S);
  ctx.fillRect(px+6*S, py+3*S, 6*S, 2*S);
  ctx.fillRect(px+6*S, py+5*S, 5*S, 2*S);
  ctx.fillRect(px+6*S, py+7*S, 4*S, S);
  ctx.fillRect(px+6*S, py+8*S, 3*S, S);
  // Right shadow
  ctx.fillStyle = rightDark;
  ctx.fillRect(px+11*S, py+4*S, S, S);
  ctx.fillRect(px+10*S, py+6*S, S, S);
}

function drawHeartPickup(ctx, px, py, bounceFrame, S) {
  // Small bouncing heart on the ground tile
  const yOff = bounceFrame % 2 === 0 ? 0 : -2*S;
  drawHeart(ctx, px + 2*S, py + 2*S + yOff, "full", S * 0.7);
}

// ---------------------------------------------------------------------------
// Player death animations
// ---------------------------------------------------------------------------
function drawPlayerFallOver(ctx, px, py, colorIndex, frame, S) {
  // 3-frame fall-over for other players seeing a death
  const shirt = SHIRT_COLORS[colorIndex % SHIRT_COLORS.length];

  if (frame === 0) {
    // Leaning — draw normal but tilted slightly (approximate by shifting)
    ctx.fillStyle = HAIR;
    ctx.fillRect(px+6*S, py+1*S, 6*S, 2*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(px+6*S, py+3*S, 6*S, 3*S);
    ctx.fillStyle = shirt;
    ctx.fillRect(px+5*S, py+6*S, 8*S, 5*S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(px+5*S, py+11*S, 6*S, 2*S);
    ctx.fillStyle = BOOTS;
    ctx.fillRect(px+5*S, py+13*S, 2*S, 2*S);
    ctx.fillRect(px+9*S, py+13*S, 2*S, 2*S);
  } else if (frame === 1) {
    // Sideways — body drawn horizontally
    ctx.fillStyle = HAIR;
    ctx.fillRect(px+1*S, py+8*S, 2*S, 4*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(px+3*S, py+8*S, 3*S, 4*S);
    ctx.fillStyle = shirt;
    ctx.fillRect(px+6*S, py+7*S, 5*S, 5*S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(px+11*S, py+8*S, 2*S, 4*S);
    ctx.fillStyle = BOOTS;
    ctx.fillRect(px+13*S, py+8*S, 2*S, 2*S);
  } else {
    // Flat on ground + fading
    ctx.globalAlpha = Math.max(0, 1 - (frame - 2) * 0.3);
    ctx.fillStyle = HAIR;
    ctx.fillRect(px+1*S, py+10*S, 2*S, 3*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(px+3*S, py+10*S, 3*S, 3*S);
    ctx.fillStyle = shirt;
    ctx.fillRect(px+6*S, py+9*S, 5*S, 4*S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(px+11*S, py+10*S, 2*S, 3*S);
    ctx.fillStyle = BOOTS;
    ctx.fillRect(px+13*S, py+10*S, 2*S, 2*S);
    ctx.globalAlpha = 1;
  }
}

function drawPlayer(ctx, px, py, direction, colorIndex, animFrame, S) {
  const sx = px;
  const sy = py;
  const shirt = SHIRT_COLORS[colorIndex % SHIRT_COLORS.length];

  if (direction === "down") {
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+5*S, sy+0*S, 6*S, 2*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+5*S, sy+2*S, 6*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+6*S, sy+3*S, S, S);
    ctx.fillRect(sx+9*S, sy+3*S, S, S);
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+4*S, sy+6*S, 8*S, 5*S);
    ctx.fillRect(sx+3*S, sy+6*S, S, 4*S);
    ctx.fillRect(sx+12*S, sy+6*S, S, 4*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+3*S, sy+10*S, S, S);
    ctx.fillRect(sx+12*S, sy+10*S, S, S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+5*S, sy+11*S, 6*S, 2*S);
    ctx.fillStyle = BOOTS;
    if (animFrame % 2 === 0) {
      ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
      ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
    } else {
      ctx.fillRect(sx+4*S, sy+13*S, 2*S, 2*S);
      ctx.fillRect(sx+10*S, sy+13*S, 2*S, 2*S);
    }
  } else if (direction === "up") {
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+5*S, sy+0*S, 6*S, 5*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+4*S, sy+3*S, S, 2*S);
    ctx.fillRect(sx+11*S, sy+3*S, S, 2*S);
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+4*S, sy+6*S, 8*S, 5*S);
    ctx.fillRect(sx+3*S, sy+6*S, S, 4*S);
    ctx.fillRect(sx+12*S, sy+6*S, S, 4*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+3*S, sy+10*S, S, S);
    ctx.fillRect(sx+12*S, sy+10*S, S, S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+5*S, sy+11*S, 6*S, 2*S);
    ctx.fillStyle = BOOTS;
    if (animFrame % 2 === 0) {
      ctx.fillRect(sx+5*S, sy+13*S, 2*S, 2*S);
      ctx.fillRect(sx+9*S, sy+13*S, 2*S, 2*S);
    } else {
      ctx.fillRect(sx+4*S, sy+13*S, 2*S, 2*S);
      ctx.fillRect(sx+10*S, sy+13*S, 2*S, 2*S);
    }
  } else if (direction === "left") {
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+4*S, sy+0*S, 6*S, 2*S);
    ctx.fillRect(sx+8*S, sy+2*S, 2*S, 4*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+4*S, sy+2*S, 4*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+4*S, sy+3*S, S, S);
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+5*S, sy+6*S, 6*S, 5*S);
    ctx.fillRect(sx+4*S, sy+7*S, S, 3*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+4*S, sy+10*S, S, S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+5*S, sy+11*S, 5*S, 2*S);
    ctx.fillStyle = BOOTS;
    if (animFrame % 2 === 0) {
      ctx.fillRect(sx+5*S, sy+13*S, 3*S, 2*S);
    } else {
      ctx.fillRect(sx+4*S, sy+13*S, 3*S, 2*S);
    }
  } else {
    // Right — mirror of left
    ctx.fillStyle = HAIR;
    ctx.fillRect(sx+6*S, sy+0*S, 6*S, 2*S);
    ctx.fillRect(sx+6*S, sy+2*S, 2*S, 4*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+8*S, sy+2*S, 4*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+11*S, sy+3*S, S, S);
    ctx.fillStyle = shirt;
    ctx.fillRect(sx+5*S, sy+6*S, 6*S, 5*S);
    ctx.fillRect(sx+11*S, sy+7*S, S, 3*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+11*S, sy+10*S, S, S);
    ctx.fillStyle = PANTS;
    ctx.fillRect(sx+6*S, sy+11*S, 5*S, 2*S);
    ctx.fillStyle = BOOTS;
    if (animFrame % 2 === 0) {
      ctx.fillRect(sx+8*S, sy+13*S, 3*S, 2*S);
    } else {
      ctx.fillRect(sx+9*S, sy+13*S, 3*S, 2*S);
    }
  }
}
