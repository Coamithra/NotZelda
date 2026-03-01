// ---------------------------------------------------------------------------
// Player sprite — procedural drawing
// ---------------------------------------------------------------------------
const SHIRT_COLORS = ["#c8383c", "#3868c8", "#38a838", "#c8a838", "#a838c8", "#38c8c8"];
const SKIN = "#e8c898";
const HAIR = "#4a3020";
const PANTS = "#3a4a8a";
const BOOTS = "#3a2a1a";

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
    ctx.fillRect(sx+5*S, sy+0*S, 5*S, 2*S);
    ctx.fillRect(sx+4*S, sy+2*S, 2*S, 4*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+6*S, sy+2*S, 4*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+6*S, sy+3*S, S, S);
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
    ctx.fillRect(sx+6*S, sy+0*S, 5*S, 2*S);
    ctx.fillRect(sx+10*S, sy+2*S, 2*S, 4*S);
    ctx.fillStyle = SKIN;
    ctx.fillRect(sx+6*S, sy+2*S, 4*S, 4*S);
    ctx.fillStyle = "#222";
    ctx.fillRect(sx+9*S, sy+3*S, S, S);
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
