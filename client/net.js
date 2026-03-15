/* WebSocket connection, message handling, and reconnection logic. */

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function appendChatLog(html) {
  if (!G.chatLog) return;
  const div = document.createElement("div");
  div.className = "chat-line";
  div.innerHTML = html;
  G.chatLog.appendChild(div);
  while (G.chatLog.childElementCount > 100) G.chatLog.removeChild(G.chatLog.firstChild);
  G.chatLog.scrollTop = G.chatLog.scrollHeight;
}

function dbg(msg) {
  const ts = new Date().toLocaleTimeString();
  const line = `${ts} ${msg}`;
  console.log("[WS] " + msg);
  G.debugLog.push(line);
  if (G.debugLog.length > G.MAX_DEBUG_LINES) G.debugLog.shift();
}

function connect(name, description) {
  G.lastLoginName = name;
  G.lastLoginDesc = description;
  if (G.reconnectTimer) { clearTimeout(G.reconnectTimer); G.reconnectTimer = null; }
  if (G.pingInterval) { clearInterval(G.pingInterval); G.pingInterval = null; }

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  dbg(`Connecting...`);
  G.ws = new WebSocket(`${proto}//${location.host}/ws`);

  G.ws.onopen = () => {
    dbg(`Connected, logging in`);
    G.reconnectCount = 0;
    G.ws.send(JSON.stringify({ type: "login", name, description }));
    G.pingInterval = setInterval(() => {
      if (G.ws && G.ws.readyState === WebSocket.OPEN) {
        G.ws.send(JSON.stringify({ type: "ping" }));
      }
    }, 15000);
  };

  G.ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "pong") return;
    handleMessage(msg);
  };

  G.ws.onclose = (ev) => {
    dbg(`Closed: code=${ev.code} reason='${ev.reason}' clean=${ev.wasClean}`);
    if (G.pingInterval) { clearInterval(G.pingInterval); G.pingInterval = null; }
    if (!G.loginScreen.classList.contains("hidden")) return;
    G.infoMessages.push({ text: "Disconnected — reconnecting...", expires: Date.now() + 4000 });
    scheduleReconnect();
  };

  G.ws.onerror = (ev) => {
    dbg(`Error event`);
    G.loginError.textContent = "Could not connect to server.";
  };
}

function scheduleReconnect() {
  if (G.reconnectTimer) return;
  G.reconnectCount++;
  const delay = Math.min(G.reconnectCount * 2000, 10000);
  dbg(`Reconnect #${G.reconnectCount} in ${delay/1000}s`);
  G.reconnectTimer = setTimeout(() => {
    G.reconnectTimer = null;
    connect(G.lastLoginName, G.lastLoginDesc);
  }, delay);
}

function guessTransitionDir(fromId, toId, exitDir, fromExits) {
  if (exitDir) return exitDir;
  if (fromExits) {
    for (const [dir, target] of Object.entries(fromExits)) {
      if (target === toId) return dir;
    }
  }
  return "north";
}

function handleMessage(msg) {
  switch (msg.type) {
    case "login_ok":
      G.myColorIndex = msg.color_index;
      G.myHp = msg.hp;
      G.myMaxHp = msg.max_hp;
      G.debugMode = !!msg.debug_mode;
      G.playerFlags = new Set();
      G.loginScreen.classList.add("hidden");
      G.gameScreen.classList.add("active");
      if (G.debugMode && G.serverLog) G.serverLog.classList.add("active");
      MusicPlayer.start();
      if (!G.gameLoopStarted) {
        G.gameLoopStarted = true;
        requestAnimationFrame(gameLoop);
      }
      break;

    case "room_generating": {
      // Entering dungeon — capture current frame for fade-out, then show conjuring
      const conjureCanvas = document.createElement("canvas");
      conjureCanvas.width = CW;
      conjureCanvas.height = CH;
      const conjureCtx = conjureCanvas.getContext("2d");
      const savedCtx2 = G.ctx;
      G.ctx = conjureCtx;
      renderRoom();
      renderPlayers();
      renderUI();
      G.ctx = savedCtx2;
      G.conjuring = { startTime: Date.now(), pendingRoomEnter: null, progressSteps: [], oldCanvas: conjureCanvas };
      break;
    }

    case "room_generating_progress":
      // Debug mode: AI generation progress update
      if (G.conjuring) {
        G.conjuring.progressSteps.push({
          step: msg.step,
          detail: msg.detail,
          time: Date.now(),
        });
      }
      break;

    case "room_enter": {
      // If conjuring animation is active, check minimum duration
      let cameFromConjuring = !!msg._fromConjuring;
      if (G.conjuring) {
        const elapsed = Date.now() - G.conjuring.startTime;
        const MIN_CONJURE_MS = 2500;
        if (elapsed < MIN_CONJURE_MS) {
          // Queue this message until minimum time passes
          G.conjuring.pendingRoomEnter = msg;
          setTimeout(() => {
            if (G.conjuring && G.conjuring.pendingRoomEnter) {
              const pending = G.conjuring.pendingRoomEnter;
              pending._fromConjuring = true;
              G.conjuring = null;
              handleMessage(pending);
            }
          }, MIN_CONJURE_MS - elapsed);
          break;
        }
        G.conjuring = null;
        cameFromConjuring = true;
      }

      // Store dungeon debug info if present
      G.dungeonDebug = msg.dungeon_debug || null;


      const isFirstRoom = !G.currentRoom;
      let oldCanvas = null;
      const prevRoom = G.currentRoom;
      if (prevRoom) {
        oldCanvas = document.createElement("canvas");
        oldCanvas.width = CW;
        oldCanvas.height = CH;
        const oldCtx = oldCanvas.getContext("2d");
        const savedCtx = G.ctx;
        G.ctx = oldCtx;
        renderRoom();
        renderAreaWarnings();
        renderHeartPickups();
        renderChargePreps();
        renderChargeTrails();
        renderPlayers();
        renderProjectiles();
        renderMonsterAttackFlashes();
        renderSpeechBubbles();
        renderSwordPickups();
        G.ctx = savedCtx;
      }

      const prevExits = G.currentRoom ? G.currentRoom.exits : null;
      G.currentRoom = {
        name: msg.name,
        tilemap: msg.tilemap,
        room_id: msg.room_id,
        exits: msg.exits || {},
        biome: msg.biome || "town",
      };
      G.myPlayer = {
        x: msg.your_pos.x,
        y: msg.your_pos.y,
        direction: G.myPlayer ? G.myPlayer.direction : "down",
        color_index: G.myColorIndex,
      };

      MusicPlayer.setRoom(msg.room_id, msg.biome, msg.music);

      // Register any custom sprites/tiles sent with this room
      if (msg.custom_sprites) {
        for (const [kind, spriteData] of Object.entries(msg.custom_sprites)) {
          if (!MONSTER_SPRITE_DATA[kind] && !customMonsterSprites[kind]) {
            customMonsterSprites[kind] = spriteData;
          }
        }
      }
      if (msg.custom_death_sprites) {
        for (const [kind, spriteData] of Object.entries(msg.custom_death_sprites)) {
          if (!DEATH_SPRITE_DATA[kind] && !customDeathSprites[kind]) {
            customDeathSprites[kind] = spriteData;
          }
        }
      }
      if (msg.custom_tiles) {
        for (const [tileId, recipe] of Object.entries(msg.custom_tiles)) {
          if (!customTiles[tileId]) {
            customTiles[tileId] = recipe;
            delete tileCanvases[tileId];
          }
        }
      }

      if (msg.hp !== undefined) { G.myHp = msg.hp; G.myMaxHp = msg.max_hp; }

      G.otherPlayers = {};
      G.dancingPlayers = {};
      G.attackingPlayers = {};
      G.speechBubbles = [];
      G.guards = msg.guards || [];
      G.dyingMonsters = [];
      G.heartPickups = [];
      G.dyingPlayerSelf = null;
      G.dyingOtherPlayers = {};
      G.bossDeathEffect = null;
      G.canvas.style.transform = "";
      G.projectiles = [];
      G.areaWarnings = [];
      G.chargeTrails = [];
      G.chargePreps = [];
      G.monsterAttackFlashes = [];
      G.monsters = (msg.monsters || []).map(m => ({
        id: m.id, kind: m.kind, x: m.x, y: m.y, displayX: m.x, displayY: m.y,
        width: m.width || 1, height: m.height || 1,
      }));
      for (const p of msg.players) {
        G.otherPlayers[p.name] = {
          x: p.x, y: p.y,
          displayX: p.x, displayY: p.y,
          direction: p.direction,
          color_index: p.color_index,
          moving: false,
        };
        if (p.dancing) startDance(p.name);
      }

      G.displayX = G.myPlayer.x;
      G.displayY = G.myPlayer.y;
      G.moveState = null;
      G.inputBuffer = null;
      G.pendingMoves = [];

      if (cameFromConjuring || isFirstRoom) {
        // Fade in from black on first login
        G.transition = {
          type: "fade",
          direction: "north",
          oldCanvas: (() => {
            const c = document.createElement("canvas");
            c.width = CW; c.height = CH;
            c.getContext("2d").fillRect(0, 0, CW, CH);
            return c;
          })(),
          startTime: Date.now(),
          duration: 500,
        };
      } else if (oldCanvas && prevRoom) {
        const transDir = guessTransitionDir(prevRoom.room_id, msg.room_id, msg.exit_direction, prevExits);
        const isFade = transDir === "up" || transDir === "down";
        G.transition = {
          type: isFade ? "fade" : "slide",
          direction: transDir,
          oldCanvas: oldCanvas,
          startTime: Date.now(),
          duration: isFade ? 500 : 300,
        };
      }
      break;
    }

    case "player_moved":
      stopDance(msg.name);
      delete G.attackingPlayers[msg.name];
      if (msg.name === G.myName) {
        G.myPlayer.direction = msg.direction;
        // Check if server confirms a predicted move
        if (G.pendingMoves.length > 0 &&
            msg.x === G.pendingMoves[0].x && msg.y === G.pendingMoves[0].y) {
          G.pendingMoves.shift();
        } else {
          // Server position differs from prediction — snap to server
          G.myPlayer.x = msg.x;
          G.myPlayer.y = msg.y;
          G.displayX = msg.x;
          G.displayY = msg.y;
          G.moveState = null;
          G.inputBuffer = null;
          G.pendingMoves = [];
        }
      } else if (G.otherPlayers[msg.name]) {
        G.otherPlayers[msg.name].x = msg.x;
        G.otherPlayers[msg.name].y = msg.y;
        G.otherPlayers[msg.name].direction = msg.direction;
      }
      break;

    case "player_faced":
      if (msg.name !== G.myName && G.otherPlayers[msg.name]) {
        stopDance(msg.name);
        G.otherPlayers[msg.name].direction = msg.direction;
      }
      break;

    case "player_entered":
      if (msg.name !== G.myName) {
        G.otherPlayers[msg.name] = {
          x: msg.x, y: msg.y,
          displayX: msg.x, displayY: msg.y,
          direction: msg.direction,
          color_index: msg.color_index,
          moving: false,
        };
        if (msg.dancing) startDance(msg.name);
        appendChatLog(`<span class="chat-system">${escHtml(msg.name)} entered the room</span>`);
      }
      break;

    case "player_left":
      delete G.otherPlayers[msg.name];
      stopDance(msg.name);
      appendChatLog(`<span class="chat-system">${escHtml(msg.name)} left the room</span>`);
      break;

    case "attack":
      startAttack(msg.name, msg.direction);
      break;

    case "dance":
      startDance(msg.name);
      break;

    case "chat": {
      // NPC responses get longer display time and more lines
      const isNpc = G.guards && G.guards.some(g => g.name === msg.from);
      G.speechBubbles.push({
        from: msg.from,
        text: msg.text,
        npc: isNpc,
        expires: Date.now() + (isNpc ? 8000 : 4000),
      });
      const nameClass = isNpc ? "chat-name chat-npc" : "chat-name";
      appendChatLog(`<span class="${nameClass}">${escHtml(msg.from)}:</span> ${escHtml(msg.text)}`);
      break;
    }

    case "player_hurt": {
      if (msg.name === G.myName) {
        G.myHp = msg.hp;
        G.myPlayer.x = msg.x;
        G.myPlayer.y = msg.y;
        G.displayX = msg.x;
        G.displayY = msg.y;
        G.moveState = null;
        G.inputBuffer = null;
        G.pendingMoves = [];
        G.hurtFlash = Date.now() + 300;
        G.invincibleUntil = Date.now() + 1500;
      } else if (G.otherPlayers[msg.name]) {
        G.otherPlayers[msg.name].x = msg.x;
        G.otherPlayers[msg.name].y = msg.y;
        G.otherPlayers[msg.name].hurtFlash = Date.now() + 300;
      }
      break;
    }

    case "you_died":
      G.dyingPlayerSelf = { x: msg.x, y: msg.y, frame: 0, startTime: Date.now() };
      G.myHp = 0;
      G.moveState = null;
      G.inputBuffer = null;
      G.pendingMoves = [];
      G.displayX = msg.x;
      G.displayY = msg.y;
      appendChatLog(`<span class="chat-system">You died!</span>`);
      break;

    case "player_died":
      delete G.otherPlayers[msg.name];
      stopDance(msg.name);
      G.dyingOtherPlayers[msg.name] = {
        x: msg.x, y: msg.y,
        color_index: msg.color_index,
        frame: 0,
        nextTime: Date.now() + DYING_PLAYER_FRAME_MS,
      };
      appendChatLog(`<span class="chat-system">${escHtml(msg.name)} died!</span>`);
      break;

    case "hp_update":
      G.myHp = msg.hp;
      G.myMaxHp = msg.max_hp;
      break;

    case "heart_spawned":
      G.heartPickups.push({ id: msg.id, x: msg.x, y: msg.y });
      break;

    case "heart_collected":
      G.heartPickups = G.heartPickups.filter(h => h.id !== msg.id);
      break;

    case "monster_moved": {
      const mon = G.monsters.find(m => m.id === msg.id);
      if (mon) { mon.x = msg.x; mon.y = msg.y; }
      break;
    }

    case "monster_killed": {
      const idx = G.monsters.findIndex(m => m.id === msg.id);
      if (idx !== -1) {
        const mon = G.monsters[idx];
        const isBoss = (mon.width || 1) > 1 || (mon.height || 1) > 1;
        G.dyingMonsters.push({ kind: mon.kind, x: msg.x, y: msg.y, frame: 0, nextTime: Date.now() + (isBoss ? 400 : DYING_MONSTER_FRAME_MS), width: mon.width || 1, height: mon.height || 1 });
        G.monsters.splice(idx, 1);
        // Boss death: dramatic screen flash + shake
        if (isBoss) {
          G.bossDeathEffect = { startTime: Date.now(), duration: 2000 };
        }
      }
      break;
    }

    case "monster_hit": {
      const hitMon = G.monsters.find(m => m.id === msg.id);
      if (hitMon) {
        hitMon.hitFlash = Date.now() + 200;
      }
      break;
    }

    case "monster_spawned":
      if (msg.custom_sprites) {
        for (const [kind, spriteData] of Object.entries(msg.custom_sprites)) {
          if (!MONSTER_SPRITE_DATA[kind] && !customMonsterSprites[kind]) {
            customMonsterSprites[kind] = spriteData;
          }
        }
      }
      if (msg.custom_death_sprites) {
        for (const [kind, spriteData] of Object.entries(msg.custom_death_sprites)) {
          if (!DEATH_SPRITE_DATA[kind] && !customDeathSprites[kind]) {
            customDeathSprites[kind] = spriteData;
          }
        }
      }
      G.monsters.push({ id: msg.id, kind: msg.kind, x: msg.x, y: msg.y, displayX: msg.x, displayY: msg.y, width: msg.width || 1, height: msg.height || 1 });
      break;

    // --- Stage 5: Monster attack messages ---
    case "projectile_spawned":
      G.projectiles.push({
        id: msg.id, x: msg.x, y: msg.y,
        displayX: msg.x, displayY: msg.y,
        dx: msg.dx, dy: msg.dy, color: msg.color,
      });
      break;

    case "projectile_moved": {
      const proj = G.projectiles.find(p => p.id === msg.id);
      if (proj) { proj.x = msg.x; proj.y = msg.y; }
      break;
    }

    case "projectile_hit":
      G.projectiles = G.projectiles.filter(p => p.id !== msg.id);
      if (msg.x !== undefined) {
        G.monsterAttackFlashes.push({ x: msg.x, y: msg.y, startTime: Date.now() });
      }
      break;

    case "projectile_gone":
      G.projectiles = G.projectiles.filter(p => p.id !== msg.id);
      break;

    case "monster_attack":
      G.monsterAttackFlashes.push({ x: msg.target_x, y: msg.target_y, startTime: Date.now() });
      break;

    case "charge_prep": {
      const prepMon = G.monsters.find(m => m.id === msg.id);
      if (prepMon) prepMon.chargePrep = Date.now();
      G.chargePreps = G.chargePreps.filter(p => p.id !== msg.id);
      G.chargePreps.push({ id: msg.id, lane: msg.lane, startTime: Date.now() });
      break;
    }

    case "monster_charged": {
      const chargedMon = G.monsters.find(m => m.id === msg.id);
      if (chargedMon) {
        chargedMon.x = msg.x;
        chargedMon.y = msg.y;
        chargedMon.displayX = msg.x;
        chargedMon.displayY = msg.y;
        chargedMon.chargePrep = null;
      }
      G.chargePreps = G.chargePreps.filter(p => p.id !== msg.id);
      G.chargeTrails.push({ path: msg.path, startTime: Date.now() });
      break;
    }

    case "teleport_start": {
      const tpMon = G.monsters.find(m => m.id === msg.id);
      if (tpMon) {
        tpMon.teleportAlpha = 1;
        const fadeOut = () => {
          if (tpMon.teleportAlpha > 0) {
            tpMon.teleportAlpha -= 0.1;
            setTimeout(fadeOut, 30);
          } else {
            tpMon.teleportAlpha = 0;
          }
        };
        fadeOut();
      }
      if (msg.target_x !== undefined) {
        G.areaWarnings.push({ x: msg.target_x, y: msg.target_y, range: msg.damage_radius || 0, startTime: Date.now(), duration: (msg.delay || 0.5) * 1000 });
      }
      break;
    }

    case "teleport_end": {
      const tpEndMon = G.monsters.find(m => m.id === msg.id);
      if (tpEndMon) {
        tpEndMon.x = msg.x;
        tpEndMon.y = msg.y;
        tpEndMon.displayX = msg.x;
        tpEndMon.displayY = msg.y;
        tpEndMon.teleportAlpha = 0;
        const fadeIn = () => {
          if (tpEndMon.teleportAlpha < 1) {
            tpEndMon.teleportAlpha += 0.1;
            setTimeout(fadeIn, 30);
          } else {
            tpEndMon.teleportAlpha = 1;
          }
        };
        fadeIn();
      }
      break;
    }

    case "area_warning":
      G.areaWarnings.push({ x: msg.x, y: msg.y, range: msg.range, startTime: Date.now(), duration: (msg.duration || 0.75) * 1000 });
      break;

    case "area_attack":
      G.monsterAttackFlashes.push({ x: msg.x, y: msg.y, startTime: Date.now() });
      break;

    case "music_change":
      if (msg.music === null || msg.music === "silence") {
        MusicPlayer.silence();
      } else {
        MusicPlayer.setRoom(G.currentRoom ? G.currentRoom.room_id : "", G.currentRoom ? G.currentRoom.biome : "", msg.music);
      }
      break;

    case "quest_update":
      break;

    case "sword_obtained": {
      const now = Date.now();
      G.swordPickups.push({ x: G.displayX, y: G.displayY, frame: 0, nextTime: now + 200 });
      setTimeout(() => {
        G.playerFlags.add("has_sword");
        G.infoMessages.push({ text: "You obtained a sword!", expires: Date.now() + 4000 });
      }, 800);
      break;
    }

    case "sword_effect": {
      const other = G.otherPlayers[msg.name];
      if (other) {
        G.swordPickups.push({ x: other.displayX, y: other.displayY, frame: 0, nextTime: Date.now() + 200 });
      }
      break;
    }

    case "debug_log":
      dbg(msg.text);
      break;

    case "server_log":
      if (G.serverLog) {
        const line = document.createElement("div");
        line.className = "log-line";
        const t = msg.text;
        if (t.includes("[REGEN]")) line.classList.add("regen");
        else if (t.includes("[DEPRECATION]")) line.classList.add("deprecation");
        else if (t.includes("[DUNGEON]")) line.classList.add("highlight");
        else if (t.includes("ERROR") || t.includes("failed") || t.includes("Traceback")) line.classList.add("error");
        line.textContent = t;
        G.serverLog.appendChild(line);
        // Cap at 200 lines
        while (G.serverLog.childElementCount > 200) G.serverLog.removeChild(G.serverLog.firstChild);
        G.serverLog.scrollTop = G.serverLog.scrollHeight;
      }
      break;

    case "info": {
      const lines = msg.text.split("\n");
      for (const line of lines) {
        G.infoMessages.push({ text: line, expires: Date.now() + 5000 });
        appendChatLog(`<span class="chat-system">${escHtml(line)}</span>`);
      }
      break;
    }

    case "error":
      G.loginError.textContent = msg.text;
      break;
  }
}
