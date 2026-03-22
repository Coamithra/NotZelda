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
  if (e.target === G.nameInput || e.target === G.descInput) return;
  if (typeof TITLE !== "undefined" && TITLE.phase !== "done") return;

  G.keysDown[e.code] = true;

  // Track direction key press order so most-recent direction wins
  const dir = DIR_KEY_MAP[e.code];
  if (dir && !G.chatFocused && !e.repeat) {
    G.dirStack = G.dirStack.filter(d => d !== dir);
    G.dirStack.push(dir);
  }

  if (e.key === "Enter" && !G.chatFocused) {
    e.preventDefault();
    G.chatInput.focus();
    G.chatFocused = true;
    G.chatBar.classList.add("focused");
    return;
  }

  if (e.key === "Escape" && G.chatFocused) {
    e.preventDefault();
    G.chatInput.blur();
    G.chatFocused = false;
    G.chatBar.classList.remove("focused");
    return;
  }

  if (e.key === "m" && !G.chatFocused) {
    const on = MusicPlayer.toggle();
    G.infoMessages.push({ text: on ? "Music on" : "Music off", expires: Date.now() + 2000 });
    return;
  }

  if (e.key === "`" && !G.chatFocused && G.debugMode) {
    G.showDebug = !G.showDebug;
    G.debugCollision = !G.debugCollision;
    return;
  }

  if (e.code === "Space" && !e.repeat && !G.chatFocused && G.state !== "attacking" && G.state !== "dying") {
    e.preventDefault();
    if (!G.playerFlags.has("has_sword")) {
      G.infoMessages.push({ text: "You don't have a weapon.", expires: Date.now() + 2000 });
      return;
    }
    if (G.state === "idle") {
      sendToServer({ type: "attack" });
      startAttack(G.myName, G.myPlayer.direction);
      spawnSlashArc(G.myPlayer.direction);
      setState("attacking", { startTime: performance.now() });
    }
    return;
  }

  if (["ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].includes(e.key) && !G.chatFocused) {
    e.preventDefault();
  }
});

document.addEventListener("keyup", (e) => {
  delete G.keysDown[e.code];

  // Remove direction from stack if no other key for the same direction is held
  const dir = DIR_KEY_MAP[e.code];
  if (dir) {
    const stillHeld = Object.entries(DIR_KEY_MAP).some(
      ([k, d]) => d === dir && k !== e.code && G.keysDown[k]
    );
    if (!stillHeld) {
      G.dirStack = G.dirStack.filter(d => d !== dir);
    }
  }
});

// ---------------------------------------------------------------------------
// Chat input
// ---------------------------------------------------------------------------
G.chatInput.addEventListener("focus", () => {
  G.chatFocused = true;
  G.chatBar.classList.add("focused");
});

G.chatInput.addEventListener("blur", () => {
  G.chatFocused = false;
  G.chatBar.classList.remove("focused");
});

G.chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const text = G.chatInput.value.trim();
    // Client-side commands
    if (text === "/networklog") {
      G.networkLog = !G.networkLog;
      G.infoMessages.push({ text: `Network log: ${G.networkLog ? "ON" : "OFF"}`, expires: Date.now() + 2000 });
      G.chatInput.value = "";
      G.chatInput.blur();
      G.chatFocused = false;
      G.chatBar.classList.remove("focused");
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    if (text && G.ws && G.ws.readyState === WebSocket.OPEN) {
      G.ws.send(JSON.stringify({ type: "chat", text }));
    }
    G.chatInput.value = "";
    G.chatInput.blur();
    G.chatFocused = false;
    G.chatBar.classList.remove("focused");
    e.preventDefault();
  }
  if (e.key === "Escape") {
    G.chatInput.blur();
    G.chatFocused = false;
    G.chatBar.classList.remove("focused");
    e.preventDefault();
  }
  e.stopPropagation();
});

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------
G.connectBtn.addEventListener("click", () => {
  const name = G.nameInput.value.trim();
  if (!name) {
    G.loginError.textContent = "Please enter a name.";
    return;
  }
  G.myName = name;
  G.loginError.textContent = "";
  MusicPlayer.start();
  connect(name, G.descInput.value.trim());
});

[G.nameInput, G.descInput].forEach(el => {
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter") G.connectBtn.click();
    e.stopPropagation();
  });
});

// ---------------------------------------------------------------------------
// Visibility change (reconnect on tab resume)
// ---------------------------------------------------------------------------
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && G.loginScreen.classList.contains("hidden")) {
    G.keysDown = {};
    G.dirStack = [];
    dbg(`Tab visible, ws.readyState=${G.ws ? G.ws.readyState : 'null'}`);
    if (!G.ws || G.ws.readyState !== WebSocket.OPEN) {
      dbg(`Connection dead on resume, reconnecting`);
      G.infoMessages.push({ text: "Reconnecting...", expires: Date.now() + 3000 });
      connect(G.lastLoginName, G.lastLoginDesc);
    }
  }
});

// ---------------------------------------------------------------------------
// Mobile D-pad controls
// ---------------------------------------------------------------------------
if (G.isMobile) {
  let activeDir = null;
  const DPAD_KEY_MAP = { up: "ArrowUp", down: "ArrowDown", left: "ArrowLeft", right: "ArrowRight" };

  function startDpad(dir) {
    if (activeDir === dir) return;
    stopDpad();
    stopDance(G.myName);
    activeDir = dir;
    G.keysDown[DPAD_KEY_MAP[dir]] = true;
    G.dirStack = [dir];
  }

  function stopDpad() {
    if (activeDir) {
      delete G.keysDown[DPAD_KEY_MAP[activeDir]];
      G.dirStack = [];
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
    G.chatInput.focus();
    G.chatFocused = true;
    G.chatBar.classList.add("focused");
  });

  document.getElementById("mobile-sword-btn").addEventListener("touchstart", (e) => {
    e.preventDefault();
    if (!G.ws || !G.myName || G.attackingPlayers[G.myName]) return;
    if (!G.playerFlags.has("has_sword")) return;
    if (G.state !== "idle" && G.state !== "attacking") return;
    sendToServer({ type: "attack" });
    startAttack(G.myName, G.myPlayer.direction);
    spawnSlashArc(G.myPlayer.direction);
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
  if (G.debugMode) G.showDebug = !G.showDebug;
});
