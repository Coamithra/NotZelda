/* Input handling — keyboard, chat, login, mobile d-pad. */

const DIR_KEY_MAP = {
  ArrowUp: "up", KeyW: "up",
  ArrowDown: "down", KeyS: "down",
  ArrowLeft: "left", KeyA: "left",
  ArrowRight: "right", KeyD: "right",
};

// ---------------------------------------------------------------------------
// Keyboard
// ---------------------------------------------------------------------------
document.addEventListener("keydown", (e) => {
  if (e.target === G.ui.nameInput || e.target === G.ui.descInput) return;
  if (typeof TITLE !== "undefined" && TITLE.phase !== "done") return;

  G.player.keysDown[e.code] = true;

  // Track direction key press order so most-recent direction wins
  const dir = DIR_KEY_MAP[e.code];
  if (dir && !G.ui.chatFocused && !e.repeat) {
    G.player.dirStack = G.player.dirStack.filter(d => d !== dir);
    G.player.dirStack.push(dir);
  }

  if (e.key === "Enter" && !G.ui.chatFocused) {
    e.preventDefault();
    G.ui.chatInput.focus();
    G.ui.chatFocused = true;
    G.ui.chatBar.classList.add("focused");
    return;
  }

  if (e.key === "Escape" && G.ui.chatFocused) {
    e.preventDefault();
    G.ui.chatInput.blur();
    G.ui.chatFocused = false;
    G.ui.chatBar.classList.remove("focused");
    return;
  }

  if (e.key === "m" && !G.ui.chatFocused) {
    const on = MusicPlayer.toggle();
    G.ui.infoMessages.push({ text: on ? "Music on" : "Music off", expires: Date.now() + 2000 });
    return;
  }

  if (e.key === "`" && !G.ui.chatFocused && G.debug.debugMode) {
    G.debug.showDebug = !G.debug.showDebug;
    G.debug.debugCollision = !G.debug.debugCollision;
    return;
  }

  if (e.code === "Space" && !e.repeat && !G.ui.chatFocused && !G.player.spiritJarRevive && G.player.state !== "attacking" && G.player.state !== "dying") {
    e.preventDefault();
    if (G.player.knockbackSlide) return;
    if (!G.player.playerFlags.has("has_sword")) {
      G.ui.infoMessages.push({ text: "You don't have a weapon.", expires: Date.now() + 2000 });
      return;
    }
    if (G.player.state === "idle") {
      sendToServer({ type: "attack", direction: G.player.myPlayer.direction, x: G.player.myPlayer.x, y: G.player.myPlayer.y });
      startAttack(G.player.myName, G.player.myPlayer.direction);
      spawnSlashArc(G.player.myPlayer.direction);
      setState("attacking", { startTime: performance.now() });
    }
    return;
  }

  if (["ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].includes(e.key) && !G.ui.chatFocused) {
    e.preventDefault();
  }
});

document.addEventListener("keyup", (e) => {
  delete G.player.keysDown[e.code];

  // Remove direction from stack if no other key for the same direction is held
  const dir = DIR_KEY_MAP[e.code];
  if (dir) {
    const stillHeld = Object.entries(DIR_KEY_MAP).some(
      ([k, d]) => d === dir && k !== e.code && G.player.keysDown[k]
    );
    if (!stillHeld) {
      G.player.dirStack = G.player.dirStack.filter(d => d !== dir);
    }
  }
});

// ---------------------------------------------------------------------------
// Chat input
// ---------------------------------------------------------------------------
G.ui.chatInput.addEventListener("focus", () => {
  G.ui.chatFocused = true;
  G.ui.chatBar.classList.add("focused");
});

G.ui.chatInput.addEventListener("blur", () => {
  G.ui.chatFocused = false;
  G.ui.chatBar.classList.remove("focused");
});

G.ui.chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const text = G.ui.chatInput.value.trim();
    // Client-side commands
    if (text === "/networklog") {
      G.conn.networkLog = !G.conn.networkLog;
      G.ui.infoMessages.push({ text: `Network log: ${G.conn.networkLog ? "ON" : "OFF"}`, expires: Date.now() + 2000 });
      G.ui.chatInput.value = "";
      G.ui.chatInput.blur();
      G.ui.chatFocused = false;
      G.ui.chatBar.classList.remove("focused");
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    if (text && G.conn.ws && G.conn.ws.readyState === WebSocket.OPEN) {
      G.conn.ws.send(JSON.stringify({ type: "chat", text }));
    }
    G.ui.chatInput.value = "";
    G.ui.chatInput.blur();
    G.ui.chatFocused = false;
    G.ui.chatBar.classList.remove("focused");
    e.preventDefault();
  }
  if (e.key === "Escape") {
    G.ui.chatInput.blur();
    G.ui.chatFocused = false;
    G.ui.chatBar.classList.remove("focused");
    e.preventDefault();
  }
  e.stopPropagation();
});

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------
G.ui.connectBtn.addEventListener("click", () => {
  const name = G.ui.nameInput.value.trim();
  if (!name) {
    G.ui.loginError.textContent = "Please enter a name.";
    return;
  }
  G.player.myName = name;
  G.ui.loginError.textContent = "";
  MusicPlayer.start();
  connect(name, G.ui.descInput.value.trim());
});

[G.ui.nameInput, G.ui.descInput].forEach(el => {
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter") G.ui.connectBtn.click();
    e.stopPropagation();
  });
});

// ---------------------------------------------------------------------------
// Debug auto-login: skip title screen, connect with empty name (server assigns debugN)
// ---------------------------------------------------------------------------
if (window.SERVER_DEBUG) {
  MusicPlayer.start();
  connect("", "");
}

// ---------------------------------------------------------------------------
// Visibility change (reconnect on tab resume)
// ---------------------------------------------------------------------------
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && G.ui.loginScreen.classList.contains("hidden")) {
    G.player.keysDown = {};
    G.player.dirStack = [];
    dbg(`Tab visible, ws.readyState=${G.conn.ws ? G.conn.ws.readyState : 'null'}`);
    if (!G.conn.ws || G.conn.ws.readyState !== WebSocket.OPEN) {
      dbg(`Connection dead on resume, reconnecting`);
      G.ui.infoMessages.push({ text: "Reconnecting...", expires: Date.now() + 3000 });
      connect(G.conn.lastLoginName, G.conn.lastLoginDesc);
    }
  }
});

// ---------------------------------------------------------------------------
// Mobile D-pad controls
// ---------------------------------------------------------------------------
if (G.ui.isMobile) {
  let activeDir = null;
  const DPAD_KEY_MAP = { up: "ArrowUp", down: "ArrowDown", left: "ArrowLeft", right: "ArrowRight" };

  function startDpad(dir) {
    if (activeDir === dir) return;
    stopDpad();
    stopDance(G.player.myName);
    activeDir = dir;
    G.player.keysDown[DPAD_KEY_MAP[dir]] = true;
    G.player.dirStack = [dir];
  }

  function stopDpad() {
    if (activeDir) {
      delete G.player.keysDown[DPAD_KEY_MAP[activeDir]];
      G.player.dirStack = [];
    }
    activeDir = null;
    document.querySelectorAll(".dpad-btn").forEach(b => b.classList.remove("active"));
  }

  document.querySelectorAll(".dpad-btn").forEach(btn => {
    const dir = btn.dataset.dir;

    btn.addEventListener("touchstart", (e) => {
      e.preventDefault();
      btn.classList.add("active");
      startDpad(dir);
    });

    btn.addEventListener("touchend", (e) => {
      e.preventDefault();
      stopDpad();
    });

    btn.addEventListener("touchcancel", (e) => {
      e.preventDefault();
      stopDpad();
    });
  });

  document.getElementById("mobile-chat-btn").addEventListener("click", () => {
    G.ui.chatInput.focus();
    G.ui.chatFocused = true;
    G.ui.chatBar.classList.add("focused");
  });

  document.getElementById("mobile-sword-btn").addEventListener("touchstart", (e) => {
    e.preventDefault();
    if (!G.conn.ws || !G.player.myName || G.room.attackingPlayers[G.player.myName]) return;
    if (G.player.knockbackSlide) return;
    if (!G.player.playerFlags.has("has_sword")) return;
    if (G.player.state !== "idle" && G.player.state !== "attacking") return;
    sendToServer({ type: "attack", direction: G.player.myPlayer.direction, x: G.player.myPlayer.x, y: G.player.myPlayer.y });
    startAttack(G.player.myName, G.player.myPlayer.direction);
    spawnSlashArc(G.player.myPlayer.direction);
    setState("attacking", { startTime: performance.now() });
  });

  // Re-scale when login completes and game screen appears
  const origHandleMsg = handleMessage;
  handleMessage = function(msg) {
    origHandleMsg(msg);
    if (msg.type === "login_ok") {
      setTimeout(scaleForMobile, 50);
    }
  };
}

// Debug overlay toggle (only works when server has DEBUG_MODE on)
document.getElementById("debug-btn").addEventListener("click", () => {
  if (G.debug.debugMode) G.debug.showDebug = !G.debug.showDebug;
});

// ---------------------------------------------------------------------------
// Revival — Respawn button click handling
// ---------------------------------------------------------------------------

function _canvasCoords(e) {
  const canvas = G.ui.canvas;
  const rect = canvas.getBoundingClientRect();
  return {
    x: (e.clientX - rect.left) * (canvas.width / rect.width),
    y: (e.clientY - rect.top) * (canvas.height / rect.height),
  };
}

function _isInRespawnBtn(cx, cy) {
  if (typeof RESPAWN_BTN === "undefined") return false;
  const btn = RESPAWN_BTN;
  return cx >= btn.x && cx <= btn.x + btn.w && cy >= btn.y && cy <= btn.y + btn.h;
}

G.ui.canvas.addEventListener("mousemove", (e) => {
  if (!G.player.waitingForRevival) { G.player._respawnBtnHover = false; return; }
  const { x, y } = _canvasCoords(e);
  G.player._respawnBtnHover = _isInRespawnBtn(x, y);
});

G.ui.canvas.addEventListener("click", (e) => {
  if (!G.player.waitingForRevival) return;
  const { x, y } = _canvasCoords(e);
  if (_isInRespawnBtn(x, y)) {
    sendToServer({ type: "respawn_request" });
  }
});

G.ui.canvas.addEventListener("touchstart", (e) => {
  if (!G.player.waitingForRevival) return;
  const touch = e.touches[0];
  const { x, y } = _canvasCoords(touch);
  if (_isInRespawnBtn(x, y)) {
    e.preventDefault();
    sendToServer({ type: "respawn_request" });
  }
}, { passive: false });
