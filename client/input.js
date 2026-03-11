/* Input handling — keyboard, chat, login, mobile d-pad. */

// ---------------------------------------------------------------------------
// Keyboard
// ---------------------------------------------------------------------------
document.addEventListener("keydown", (e) => {
  if (e.target === G.nameInput || e.target === G.descInput) return;

  G.keysDown[e.code] = true;

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
    return;
  }

  if (e.code === "Space" && !e.repeat && !G.chatFocused && !G.attackingPlayers[G.myName]) {
    e.preventDefault();
    if (!G.playerFlags.has("has_sword")) {
      G.infoMessages.push({ text: "You don't have a weapon.", expires: Date.now() + 2000 });
      return;
    }
    if (G.ws && G.ws.readyState === WebSocket.OPEN) {
      G.ws.send(JSON.stringify({ type: "attack" }));
    }
    return;
  }

  if (["ArrowUp","ArrowDown","ArrowLeft","ArrowRight"].includes(e.key) && !G.chatFocused) {
    e.preventDefault();
  }
});

document.addEventListener("keyup", (e) => {
  delete G.keysDown[e.code];
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
  let dpadInterval = null;
  let activeDir = null;

  function startDpad(dir) {
    if (activeDir === dir) return;
    stopDpad();
    stopDance(G.myName);
    activeDir = dir;
    if (G.ws && G.ws.readyState === WebSocket.OPEN) {
      G.ws.send(JSON.stringify({ type: "move", direction: dir }));
    }
    dpadInterval = setInterval(() => {
      if (G.ws && G.ws.readyState === WebSocket.OPEN) {
        G.ws.send(JSON.stringify({ type: "move", direction: dir }));
      }
    }, 150);
  }

  function stopDpad() {
    if (dpadInterval) {
      clearInterval(dpadInterval);
      dpadInterval = null;
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
    G.ws.send(JSON.stringify({ type: "attack" }));
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
