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
