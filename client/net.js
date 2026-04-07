/* WebSocket connection, message handling, and reconnection logic. */

function escHtml(s) {
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function appendChatLog(html) {
  if (!G.ui.chatLog) return;
  const div = document.createElement("div");
  div.className = "chat-line";
  div.innerHTML = html;
  G.ui.chatLog.appendChild(div);
  while (G.ui.chatLog.childElementCount > 100) G.ui.chatLog.removeChild(G.ui.chatLog.firstChild);
  G.ui.chatLog.scrollTop = G.ui.chatLog.scrollHeight;
}

function dbg(msg) {
  const ts = new Date().toLocaleTimeString();
  const line = `${ts} ${msg}`;
  console.log("[WS] " + msg);
  G.debug.debugLog.push(line);
  if (G.debug.debugLog.length > G.debug.MAX_DEBUG_LINES) G.debug.debugLog.shift();
}

function connect(name, description) {
  G.conn.lastLoginName = name;
  G.conn.lastLoginDesc = description;
  if (G.conn.reconnectTimer) { clearTimeout(G.conn.reconnectTimer); G.conn.reconnectTimer = null; }
  if (G.conn.pingInterval) { clearInterval(G.conn.pingInterval); G.conn.pingInterval = null; }

  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  // Use port 8443 for TLS WebSocket (bypasses nginx — fixes iOS Safari 30s disconnect)
  const wsHost = proto === "wss:" ? location.hostname + ":8443" : location.host;
  dbg(`Connecting...`);
  G.conn.ws = new WebSocket(`${proto}//${wsHost}/ws`);

  G.conn.ws.onopen = () => {
    dbg(`Connected, logging in`);
    G.conn.reconnectCount = 0;
    G.conn.ws.send(JSON.stringify({ type: "login", name, description }));
    G.conn.pingInterval = setInterval(() => {
      if (G.conn.ws && G.conn.ws.readyState === WebSocket.OPEN) {
        G.conn.ws.send(JSON.stringify({ type: "ping", ct: performance.now() }));
      }
    }, 15000);
  };

  G.conn.ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "pong") {
      // RTT measurement — ct is echoed back from our ping
      if (msg.ct) G.conn.rtt = performance.now() - msg.ct;
      return;
    }
    handleMessage(msg);
  };

  G.conn.ws.onclose = (ev) => {
    dbg(`Closed: code=${ev.code} reason='${ev.reason}' clean=${ev.wasClean}`);
    if (G.conn.pingInterval) { clearInterval(G.conn.pingInterval); G.conn.pingInterval = null; }
    if (!G.ui.loginScreen.classList.contains("hidden")) return;
    G.ui.infoMessages.push({ text: "Disconnected — reconnecting...", expires: Date.now() + 4000 });
    scheduleReconnect();
  };

  G.conn.ws.onerror = (ev) => {
    dbg(`Error event`);
    G.ui.loginError.textContent = "Could not connect to server.";
  };
}

function scheduleReconnect() {
  if (G.conn.reconnectTimer) return;
  G.conn.reconnectCount++;
  const delay = Math.min(G.conn.reconnectCount * 2000, 10000);
  dbg(`Reconnect #${G.conn.reconnectCount} in ${delay/1000}s`);
  G.conn.reconnectTimer = setTimeout(() => {
    G.conn.reconnectTimer = null;
    connect(G.conn.lastLoginName, G.conn.lastLoginDesc);
  }, delay);
}

function createOtherPlayer(x, y, direction, color_index) {
  const now = performance.now();
  return {
    x, y, displayX: x, displayY: y, direction, color_index,
    moving: false, walkState: null,
    // Interpolation snapshot buffer — [{x, y, dir, t}, ...]
    snapshots: [{ x, y, dir: direction, t: now }],
  };
}

function registerCustomContent(msg) {
  if (msg.custom_sprites) {
    for (const [kind, spriteData] of Object.entries(msg.custom_sprites)) {
      if (!customMonsterSprites[kind]) customMonsterSprites[kind] = spriteData;
    }
  }
  if (msg.custom_death_sprites) {
    for (const [kind, spriteData] of Object.entries(msg.custom_death_sprites)) {
      if (!customDeathSprites[kind]) customDeathSprites[kind] = spriteData;
    }
  }
  if (msg.npc_sprites) {
    for (const [key, spriteData] of Object.entries(msg.npc_sprites)) {
      if (!customNPCSprites[key]) customNPCSprites[key] = spriteData;
    }
  }
  if (msg.custom_tiles) {
    for (const [tileId, recipe] of Object.entries(msg.custom_tiles)) {
      if (!customTiles[tileId]) {
        customTiles[tileId] = recipe;
        delete tileCanvases[tileId];
      }
      // Register walkable custom tiles so client-side prediction works
      if (recipe.walkable) WALKABLE.add(tileId);
      if (recipe.water) WATER_TILES.add(tileId);
    }
  }
}

// Helper: get the active monster list — from spectateData when death-camera spectating, else G.room.monsters
function _getMonsters() {
  const sd = G.player.spectateData;
  return (sd && G.player.waitingForRevival) ? sd.monsters : G.room.monsters;
}

// Dead reckoning: shorten animation by RTT/2 to compensate for message travel time.
function computeEffectiveDuration(serverDurationMs) {
  const halfRtt = (G.conn.rtt || 0) / 2;
  return Math.max(serverDurationMs - halfRtt, 16);
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
      if (msg.name) { G.player.myName = msg.name; G.conn.lastLoginName = msg.name; }
      G.player.myColorIndex = msg.color_index;
      G.player.myHp = msg.hp;
      G.player.myMaxHp = msg.max_hp;
      G.debug.debugMode = !!msg.debug_mode;
      G.player.playerFlags = new Set();
      G.player.spiritJarCount = 0;
      G.room.dungeonState = null;
      G.room.dungeonGroundItems = [];
      G.player.itemPickupActive = null;
      G.player.itemPickupEffects = {};
      if (typeof TITLE !== "undefined") TITLE.hide();
      G.ui.loginScreen.classList.add("hidden");
      G.ui.gameScreen.classList.add("active");
      if (G.debug.debugMode && G.ui.serverLog) G.ui.serverLog.classList.add("active");
      MusicPlayer.start();
      SfxPlayer.preload();
      if (!G.ui.gameLoopStarted) {
        G.ui.gameLoopStarted = true;
        requestAnimationFrame(gameLoop);
      }
      break;

    case "room_generating": {
      // Entering dungeon — capture current frame for fade-out, then show conjuring
      const conjureCanvas = document.createElement("canvas");
      conjureCanvas.width = CW;
      conjureCanvas.height = CH;
      const conjureCtx = conjureCanvas.getContext("2d");
      const savedCtx2 = G.ui.ctx;
      G.ui.ctx = conjureCtx;
      try {
        renderRoom();
        renderPlayers();
        renderUI();
      } finally {
        G.ui.ctx = savedCtx2;
      }
      G.ui.conjuring = { startTime: Date.now(), progressSteps: [], oldCanvas: conjureCanvas };
      break;
    }

    case "room_generating_progress":
      // Debug mode: AI generation progress update
      if (G.ui.conjuring) {
        G.ui.conjuring.progressSteps.push({
          step: msg.step,
          detail: msg.detail,
          time: Date.now(),
        });
      }
      break;

    case "room_enter": {
      // Process immediately even during conjuring — the conjuring animation
      // is purely visual overlay. Room state updates in the background so
      // monsters, players etc. stay in sync with the server.
      const cameFromConjuring = !!G.ui.conjuring;
      if (G.ui.conjuring) {
        // Schedule end of conjuring overlay — fade into the already-live room
        const MIN_CONJURE_MS = 2500;
        const elapsed = Date.now() - G.ui.conjuring.startTime;
        const remaining = Math.max(0, MIN_CONJURE_MS - elapsed);
        setTimeout(() => {
          if (G.ui.conjuring) {
            G.ui.conjuring = null;
            G.ui.transition = {
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
          }
        }, remaining);
      }

      // Store dungeon debug info if present
      G.debug.dungeonDebug = msg.dungeon_debug || null;


      const isFirstRoom = !G.room.currentRoom;
      let oldCanvas = null;
      const prevRoom = G.room.currentRoom;
      if (prevRoom) {
        oldCanvas = document.createElement("canvas");
        oldCanvas.width = CW;
        oldCanvas.height = CH;
        const oldCtx = oldCanvas.getContext("2d");
        const savedCtx = G.ui.ctx;
        G.ui.ctx = oldCtx;
        renderRoom();
        renderAreaWarnings();
        renderHeartPickups();
        renderDungeonGroundItems();
        renderChargePreps();
        renderChargeTrails();
        renderPlayers();
        renderProjectiles();
        renderMonsterAttackFlashes();
        renderNpcThinking();
        renderSpeechBubbles();
        renderItemPickups();
        G.ui.ctx = savedCtx;
      }

      const prevExits = G.room.currentRoom ? G.room.currentRoom.exits : null;
      G.room.currentRoom = {
        name: msg.name,
        tilemap: msg.tilemap,
        room_id: msg.room_id,
        exits: msg.exits || {},
        biome: msg.biome || "town",
        dungeon_type: msg.dungeon_type || null,
      };
      G.player.myPlayer = {
        x: msg.your_pos.x,
        y: msg.your_pos.y,
        direction: G.player.myPlayer ? G.player.myPlayer.direction : "down",
        color_index: G.player.myColorIndex,
      };
      // Clear prediction state — server gave us authoritative position
      G.player.inputBuffer = [];
      G.player.pendingInputs = [];
      G.player.correctionOffset.x = 0;
      G.player.correctionOffset.y = 0;

      MusicPlayer.setRoom(msg.room_id, msg.biome, msg.music);

      registerCustomContent(msg);

      if (msg.hp !== undefined) { G.player.myHp = msg.hp; G.player.myMaxHp = msg.max_hp; }

      G.room.otherPlayers = {};
      G.room.dancingPlayers = {};
      G.room.attackingPlayers = {};
      G.room.speechBubbles = [];
      G.room.npcThinking = {};
      G.room.guards = msg.guards || [];
      G.room.dyingMonsters = [];
      G.room.heartPickups = [];
      // Juice: clear corpses, particles, effects on room change
      clearCorpses();
      G.fx.particles = [];
      G.fx.slashArcs = [];
      G.fx.floatingTexts = [];
      G.fx.screenShake = null;
      G.ui.canvas.style.transform = "";
      G.room.dungeonGroundItems = msg.dungeon_items || [];
      G.room.openedChests = msg.opened_chests || [];
      G.room.monsterFreeze = null;
      G.room.dark = msg.dark || false;
      G.room.lightSources = msg.light_sources || [];
      G.room.lanternHolders = new Set(msg.lantern_holders || []);
      G.room.medallionHolders = new Set(msg.medallion_holders || []);
      G.room.revealTilemap = msg.reveal_tilemap || null;
      // Re-apply water-walking tiles to WALKABLE on room enter / reconnect
      if (G.player.playerFlags.has("has_tide_medallion")) {
        for (const t of WATER_TILES) WALKABLE.add(t);
      }
      G.player.itemPickupActive = null;
      G.player.itemPickupEffects = {};
      G.player.dyingPlayerSelf = null;
      G.player.waitingForRevival = false;
      G.player.revivalProgress = null;
      G.player._revivalWaitStart = null;
      G.player.spectateData = null;
      G.room.dyingOtherPlayers = {};
      G.room.tombstones = {};
      G.room.activeRevival = null;
      G.fx.bossDeathEffect = null;
      G.fx.projectiles = [];
      G.fx.chargeTrails = [];
      G.fx.monsterAttackFlashes = [];
      G.room.monsters = (msg.monsters || []).map((m, idx) => {
        const mon = {
          id: m.id, kind: m.kind, x: m.x, y: m.y, displayX: m.x, displayY: m.y,
          width: m.width || 1, height: m.height || 1,
          action: null, stateSeq: m.seq || 0,
          correctionOffset: { x: 0, y: 0 },
          spawnTime: Date.now() + idx * 40,  // Juice: staggered spawn pop
        };
        if (m.walking) {
          // Room enter mid-walk: reconstruct walk action from server progress.
          // walk_time_step is the actual step duration (may differ from base walk_time).
          const walkTimeMs = (m.walk_time_step || m.walk_time || 2.0) * 1000;
          const alreadyElapsed = m.walk_progress * walkTimeMs;
          mon.action = {
            type: "walk",
            fromX: m.walk_from.x, fromY: m.walk_from.y,
            toX: m.walk_to.x, toY: m.walk_to.y,
            startTime: performance.now() - alreadyElapsed,
            effectiveDuration: walkTimeMs,  // no RTT adjustment (progress already compensates)
            duration: walkTimeMs,
            seq: mon.stateSeq,
          };
          mon.x = m.walk_to.x;
          mon.y = m.walk_to.y;
        }
        return mon;
      });
      for (const p of msg.players) {
        G.room.otherPlayers[p.name] = createOtherPlayer(p.x, p.y, p.direction, p.color_index);
        if (p.dancing) startDance(p.name);
        if (p.attacking) startAttack(p.name, p.attacking.direction);
      }
      // Populate tombstones from room data
      if (msg.tombstones) {
        for (const ts of msg.tombstones) {
          G.room.tombstones[ts.name] = { x: ts.x, y: ts.y, color_index: ts.color_index };
        }
      }
      G.player.displayX = G.player.myPlayer.x;
      G.player.displayY = G.player.myPlayer.y;
      G.player.knockbackOffsetX = 0;
      G.player.knockbackOffsetY = 0;
      G.player.knockbackSlide = null;
      setState("idle", {});

      // Dungeon state — track collected items and visited cells
      if (msg.dungeon_collected !== undefined) {
        // In a dungeon room — initialize or update dungeon state
        const mm = msg.dungeon_debug && msg.dungeon_debug.minimap;
        const currentCell = mm && mm.player;
        const otherPlayers = mm ? (mm.other_players || []) : [];
        const treasureCell = mm && mm.treasure_cell;
        if (!G.room.dungeonState) {
          G.room.dungeonState = {
            collected: new Set(msg.dungeon_collected),
            cells: mm ? mm.cells : [],
            bossCell: msg.dungeon_boss_cell,
            currentCell: currentCell,
            lockedEdges: msg.locked_edges || [],
            otherPlayers: otherPlayers,
            treasureCell: treasureCell || null,
          };
        } else {
          G.room.dungeonState.collected = new Set(msg.dungeon_collected);
          G.room.dungeonState.cells = mm ? mm.cells : G.room.dungeonState.cells;
          G.room.dungeonState.currentCell = currentCell;
          G.room.dungeonState.bossCell = msg.dungeon_boss_cell || G.room.dungeonState.bossCell;
          G.room.dungeonState.lockedEdges = msg.locked_edges || G.room.dungeonState.lockedEdges || [];
          G.room.dungeonState.otherPlayers = otherPlayers;
          // treasureCell is null once collected — don't overwrite with stale value
          if (treasureCell) G.room.dungeonState.treasureCell = treasureCell;
          else G.room.dungeonState.treasureCell = null;
        }
        if (msg.keys !== undefined) G.player.keyCount = msg.keys;
      } else {
        // Left the dungeon
        G.room.dungeonState = null;
        if (!msg.dungeon_items) G.room.dungeonGroundItems = [];
      }

      if (cameFromConjuring) {
        // Conjuring overlay is still active — the setTimeout in the conjuring
        // handler will create the fade transition when the animation ends.
        // Don't create a transition now.
      } else if (isFirstRoom) {
        // Fade in from black on first login
        G.ui.transition = {
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
      } else if (oldCanvas && prevRoom && prevRoom.room_id !== msg.room_id) {
        const transDir = guessTransitionDir(prevRoom.room_id, msg.room_id, msg.exit_direction, prevExits);
        const isFade = transDir === "up" || transDir === "down";
        if (transDir === "up") SfxPlayer.play("stairs_up");
        if (transDir === "down") SfxPlayer.play("stairs_down");
        G.ui.transition = {
          type: isFade ? "fade" : "slide",
          direction: transDir,
          oldCanvas: oldCanvas,
          startTime: Date.now(),
          duration: isFade ? 500 : 300,
        };
      }
      break;
    }

    case "state_correction": {
      // Server-authoritative position reconciliation
      const buf = G.player.inputBuffer;
      const ackSeq = msg.ack_seq;

      // Discard acknowledged inputs
      while (buf.length > 0 && buf[0].seq <= ackSeq) buf.shift();

      // Replay unacknowledged inputs from server position
      let serverX = msg.x, serverY = msg.y;
      for (const input of buf) {
        if (input.dir && input.dt > 0) {
          const result = simulateMove(serverX, serverY, input.dir, input.dt);
          serverX = result.x;
          serverY = result.y;
        }
      }

      // Compare replayed position with current prediction
      const dx = serverX - G.player.myPlayer.x;
      const dy = serverY - G.player.myPlayer.y;
      const drift = Math.abs(dx) + Math.abs(dy);

      if (drift > 2.0) {
        // Major desync — snap
        G.player.myPlayer.x = serverX;
        G.player.myPlayer.y = serverY;
        G.player.correctionOffset.x = 0;
        G.player.correctionOffset.y = 0;
      } else if (drift > 0.01) {
        // Small drift — smooth correction (offset absorbs the visual jump)
        G.player.correctionOffset.x -= dx;
        G.player.correctionOffset.y -= dy;
        G.player.myPlayer.x = serverX;
        G.player.myPlayer.y = serverY;
      }
      break;
    }

    case "reconcile": {
      if (G.conn.networkLog) {
        const t = performance.now().toFixed(1);
        console.log(`[NET IN  t=${t}] reconcile pos=(${msg.x},${msg.y}) [${G.player.state}]`);
      }
      G.player.myPlayer.x = msg.x;
      G.player.myPlayer.y = msg.y;
      G.player.displayX = msg.x;
      G.player.displayY = msg.y;
      G.player.knockbackOffsetX = 0;
      G.player.knockbackOffsetY = 0;
      G.player.knockbackSlide = null;
      G.player.myPlayer.direction = msg.direction;
      delete G.room.attackingPlayers[G.player.myName];
      // Clear prediction state — server forcibly corrected us
      G.player.inputBuffer = [];
      G.player.pendingInputs = [];
      G.player.correctionOffset.x = 0;
      G.player.correctionOffset.y = 0;
      setState("idle");
      break;
    }

    case "player_state_update": {
      // Own state echoed back — only handle dance (position is authoritative locally)
      if (msg.name === G.player.myName) {
        if (msg.dancing && !G.room.dancingPlayers[G.player.myName]) {
          startDance(G.player.myName);
        } else if (!msg.dancing && G.room.dancingPlayers[G.player.myName]) {
          stopDance(G.player.myName);
        }
        break;
      }

      // Unified state update for another player (position, direction, dancing, attacking)
      // When spectating another room, route to spectateData.players
      const _sd = G.player.spectateData;
      const op = (_sd && _sd.players[msg.name]) || G.room.otherPlayers[msg.name];
      if (!op) break;

      // Position update — push to interpolation buffer
      op.x = msg.x;
      op.y = msg.y;
      op.snapshots.push({ x: msg.x, y: msg.y, dir: msg.direction, t: performance.now() });
      if (op.snapshots.length > INTERP_BUFFER_SIZE) op.snapshots.shift();

      op.direction = msg.direction;

      // Dance state sync
      if (msg.dancing && !G.room.dancingPlayers[msg.name]) {
        startDance(msg.name);
      } else if (!msg.dancing && G.room.dancingPlayers[msg.name]) {
        stopDance(msg.name);
      }

      // Attack state sync — fire-and-forget animation, only trigger on rising edge
      if (msg.attacking && !G.room.attackingPlayers[msg.name]) {
        startAttack(msg.name, msg.attacking.direction);
      }

      break;
    }

    case "player_entered":
      if (msg.name !== G.player.myName) {
        const _peSD = G.player.spectateData;
        if (_peSD && G.player.waitingForRevival) {
          // Route to spectate data — player entered the spectated room
          _peSD.players[msg.name] = createOtherPlayer(msg.x, msg.y, msg.direction, msg.color_index);
        } else {
          G.room.otherPlayers[msg.name] = createOtherPlayer(msg.x, msg.y, msg.direction, msg.color_index);
        }
        if (msg.dancing) startDance(msg.name);
        if (msg.attacking) startAttack(msg.name, msg.attacking.direction);
        if (msg.has_lantern) G.room.lanternHolders.add(msg.name);
        if (msg.has_tide_medallion) G.room.medallionHolders.add(msg.name);
        appendChatLog(`<span class="chat-system">${escHtml(msg.name)} entered the room</span>`);
      }
      break;

    case "player_left": {
      const _plSD = G.player.spectateData;
      if (_plSD && _plSD.players[msg.name]) {
        delete _plSD.players[msg.name];
      } else {
        delete G.room.otherPlayers[msg.name];
      }
      G.room.lanternHolders.delete(msg.name);
      G.room.medallionHolders.delete(msg.name);
      stopDance(msg.name);
      appendChatLog(`<span class="chat-system">${escHtml(msg.name)} left the room</span>`);
      break;
    }

    case "npc_thinking": {
      // Show animated "..." thinking bubble above the NPC
      G.room.npcThinking[msg.name] = Date.now();
      SfxPlayer.play("npc_chat_open");
      break;
    }

    case "chat": {
      // NPC responses get longer display time and more lines
      const isNpc = G.room.guards && G.room.guards.some(g => g.name === msg.from);
      // Clear thinking bubble when the NPC responds
      if (isNpc) delete G.room.npcThinking[msg.from];
      G.room.speechBubbles.push({
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
      if (msg.name === G.player.myName) {
        // Knockback dust trail (before position overwrite)
        if (msg.knockback) {
          const oldX = G.player.myPlayer.x, oldY = G.player.myPlayer.y;
          for (let t = 0.33; t <= 0.66; t += 0.33) {
            const dustX = tileCenterX(oldX + (msg.x - oldX) * t);
            const dustY = (oldY + (msg.y - oldY) * t + 0.5) * TS;
            spawnBurst(dustX, dustY, 2, 1.0, 250, ["#c8b898", "#a09068"], [2 * SCALE, 3 * SCALE], { shrink: true });
          }
          // Knockback offset — visual position decays from old to new over 200ms
          G.player.knockbackSlide = {
            initialOffsetX: G.player.displayX - msg.x,
            initialOffsetY: G.player.displayY - msg.y,
            startTime: performance.now(), duration: 200,
          };
          G.player.knockbackOffsetX = G.player.displayX - msg.x;
          G.player.knockbackOffsetY = G.player.displayY - msg.y;
        }
        G.player.myHp = msg.hp;
        G.player.myPlayer.x = msg.x;
        G.player.myPlayer.y = msg.y;
        // Server forcibly moved us — clear prediction state
        G.player.inputBuffer = [];
        G.player.pendingInputs = [];
        G.player.correctionOffset.x = 0;
        G.player.correctionOffset.y = 0;
        if (!msg.knockback) {
          G.player.displayX = msg.x;
          G.player.displayY = msg.y;
          G.player.knockbackOffsetX = 0;
          G.player.knockbackOffsetY = 0;
          G.player.knockbackSlide = null;
        }
        setState("idle", {});
        G.player.hurtFlash = Date.now() + 300;
        G.player.invincibleUntil = Date.now() + 1500;
        G.player.stunUntil = performance.now() + 200;
        SfxPlayer.play("player_hurt");
        // Juice: screen shake + damage vignette
        triggerShake(4, 200);
        G.fx.damageVignette = Date.now() + VIGNETTE_DURATION;
        if (G.debug.debugCollision && msg.debug_source_x != null) {
          G.debug.debugGhosts.push({
            playerX: msg.debug_pre_x, playerY: msg.debug_pre_y,
            sourceX: msg.debug_source_x, sourceY: msg.debug_source_y,
            prevPlayerX: msg.debug_prev_player_x, prevPlayerY: msg.debug_prev_player_y,
            prevSourceX: msg.debug_prev_source_x, prevSourceY: msg.debug_prev_source_y,
            sourceW: msg.debug_source_w || 1, sourceH: msg.debug_source_h || 1,
            knockX: msg.x, knockY: msg.y,
            time: Date.now(),
          });
        }
      } else if (G.room.otherPlayers[msg.name]) {
        const op = G.room.otherPlayers[msg.name];
        if (msg.knockback) {
          op.knockbackSlide = {
            fromX: op.displayX, fromY: op.displayY,
            toX: msg.x, toY: msg.y,
            startTime: performance.now(), duration: 200,
          };
        }
        op.x = msg.x;
        op.y = msg.y;
        // Reset interpolation buffer to knockback destination so it resumes cleanly
        op.snapshots = [{ x: msg.x, y: msg.y, dir: op.direction, t: performance.now() + 200 }];
        op.hurtFlash = Date.now() + 300;
      }
      break;
    }

    case "you_died":
      SfxPlayer.play("player_death");
      G.player.dyingPlayerSelf = { x: msg.x, y: msg.y, frame: 0, startTime: Date.now() };
      G.player.myHp = 0;
      setState("dying", {});
      G.player.myPlayer.x = msg.x;
      G.player.myPlayer.y = msg.y;
      G.player.displayX = msg.x;
      G.player.displayY = msg.y;
      G.player.knockbackOffsetX = 0;
      G.player.knockbackOffsetY = 0;
      G.player.knockbackSlide = null;
      appendChatLog(`<span class="chat-system">You died!</span>`);
      break;

    case "player_died":
      delete G.room.otherPlayers[msg.name];
      stopDance(msg.name);
      G.room.dyingOtherPlayers[msg.name] = {
        x: msg.x, y: msg.y,
        color_index: msg.color_index,
        frame: 0,
        nextTime: Date.now() + DYING_PLAYER_FRAME_MS,
      };
      appendChatLog(`<span class="chat-system">${escHtml(msg.name)} died!</span>`);
      break;

    case "hp_update":
      G.player.myHp = msg.hp;
      G.player.myMaxHp = msg.max_hp;
      break;

    case "heart_spawned":
      G.room.heartPickups.push({ id: msg.id, x: msg.x, y: msg.y });
      break;

    case "heart_collected": {
      // Juice: sparkle particles at pickup point
      const collectedHeart = G.room.heartPickups.find(h => h.id === msg.id);
      if (collectedHeart) {
        const hx = tileCenterX(collectedHeart.x);
        const hy = tileCenterY(collectedHeart.y);
        spawnBurst(hx, hy, 4, 2, 300, ["#ff6060", "#fff", "#ffaaaa"], [2 * SCALE, 4 * SCALE]);
      }
      G.room.heartPickups = G.room.heartPickups.filter(h => h.id !== msg.id);
      break;
    }

    case "monster_walk_started": {
      const walkMon = _getMonsters().find(m => m.id === msg.id);
      if (walkMon && (msg.seq == null || msg.seq >= walkMon.stateSeq)) {
        walkMon.stateSeq = msg.seq || (walkMon.stateSeq + 1);
        const durationMs = msg.walk_time * 1000;
        // Capture old display position for correction offset
        const oldDX = walkMon.displayX;
        const oldDY = walkMon.displayY;
        walkMon.action = {
          type: "walk",
          fromX: msg.from_x, fromY: msg.from_y,
          toX: msg.to_x, toY: msg.to_y,
          startTime: performance.now(),
          effectiveDuration: computeEffectiveDuration(durationMs),
          duration: durationMs,
          seq: walkMon.stateSeq,
        };
        // Correction offset: smooth visual transition from old position
        const ffProgress = Math.min((G.conn.rtt || 0) / 2 / durationMs, 1.0);
        const newDX = msg.from_x + (msg.to_x - msg.from_x) * ffProgress;
        const newDY = msg.from_y + (msg.to_y - msg.from_y) * ffProgress;
        walkMon.correctionOffset = { x: oldDX - newDX, y: oldDY - newDY };
        // Set logical position to target
        walkMon.x = msg.to_x;
        walkMon.y = msg.to_y;
      }
      break;
    }

    case "monster_walk_complete": {
      const wcMon = _getMonsters().find(m => m.id === msg.id);
      if (wcMon) {
        // Only commit if this completion matches the walk we're currently
        // animating.  A charge, knockback, or newer walk will have bumped
        // stateSeq, making this message stale.
        if (wcMon.action && wcMon.action.type === "walk" &&
            wcMon.action.seq === (msg.seq != null ? msg.seq : wcMon.stateSeq)) {
          wcMon.displayX = wcMon.action.toX;
          wcMon.displayY = wcMon.action.toY;
          wcMon.action = null;
          wcMon.correctionOffset = { x: 0, y: 0 };
        }
      }
      break;
    }

    case "monster_moved": {
      const mon = _getMonsters().find(m => m.id === msg.id);
      if (mon) {
        mon.x = msg.x; mon.y = msg.y;
        mon.displayX = msg.x; mon.displayY = msg.y;
        mon.stateSeq = msg.seq || (mon.stateSeq + 1);
        mon.action = null;
        mon.correctionOffset = { x: 0, y: 0 };
      }
      break;
    }

    case "monster_killed": {
      const _mkList = _getMonsters();
      const idx = _mkList.findIndex(m => m.id === msg.id);
      if (idx !== -1) {
        const mon = _mkList[idx];
        mon.action = null;
        const isBoss = (mon.width || 1) > 1 || (mon.height || 1) > 1;
        G.room.dyingMonsters.push({ kind: mon.kind, x: msg.x, y: msg.y, frame: 0, nextTime: Date.now() + (isBoss ? 400 : DYING_MONSTER_FRAME_MS), width: mon.width || 1, height: mon.height || 1 });
        _mkList.splice(idx, 1);
        // Juice: corpse persistence
        addCorpse(mon.kind, msg.x, msg.y, mon.width, mon.height);
        // Juice: death particles in monster's sprite colors
        const monSprite = customMonsterSprites[mon.kind];
        const deathColors = monSprite && monSprite.colors
          ? Object.values(monSprite.colors).slice(0, 4)
          : ["#888", "#666", "#aaa"];
        const cx = msg.x * TS + (mon.width || 1) * TS / 2;
        const cy = msg.y * TS + (mon.height || 1) * TS / 2;
        spawnBurst(cx, cy, 10, 2.5, 500, deathColors, [3 * SCALE, 6 * SCALE], { gravity: 0.05, shrink: true });
        // Juice: hit pause + screen shake
        G.fx.hitPause = Date.now() + 60;
        triggerShake(2, 120);
        SfxPlayer.play("monster_death");
        // Boss death: dramatic screen flash + shake
        if (isBoss) {
          G.fx.bossDeathEffect = { startTime: Date.now(), duration: 2000 };
          triggerShake(6, 1000);
          SfxPlayer.play("boss_roar");
        }
      }
      break;
    }

    case "doors_unlocked": {
      // Restore doorway tiles (trap room cleared OR key-locked door opened)
      if (G.room.currentRoom && G.room.currentRoom.tilemap && msg.tile_changes) {
        for (const [r, c, tile] of msg.tile_changes) {
          G.room.currentRoom.tilemap[r][c] = tile;
        }
      }
      // Reveal dungeon items that were hidden during the trap
      if (msg.dungeon_items) {
        G.room.dungeonGroundItems = msg.dungeon_items;
      }
      // Remove unlocked edge from minimap
      if (msg.unlocked_edge && G.room.dungeonState && G.room.dungeonState.lockedEdges) {
        const [a, b] = msg.unlocked_edge;
        G.room.dungeonState.lockedEdges = G.room.dungeonState.lockedEdges.filter(e => {
          const match1 = e[0][0]===a[0] && e[0][1]===a[1] && e[1][0]===b[0] && e[1][1]===b[1];
          const match2 = e[0][0]===b[0] && e[0][1]===b[1] && e[1][0]===a[0] && e[1][1]===a[1];
          return !match1 && !match2;
        });
      }
      SfxPlayer.play("door_open");
      G.ui.infoMessages.push({ text: "The doors have opened!", expires: Date.now() + 3000 });
      break;
    }

    case "tile_change": {
      // Dynamic tile updates (e.g., exit stairwell spawning)
      if (G.room.currentRoom && G.room.currentRoom.tilemap && msg.changes) {
        for (const [r, c, tile] of msg.changes) {
          G.room.currentRoom.tilemap[r][c] = tile;
        }
      }
      break;
    }

    case "monster_hit": {
      const hitMon = _getMonsters().find(m => m.id === msg.id);
      if (hitMon) {
        const isBossHit = (hitMon.width || 1) > 1 || (hitMon.height || 1) > 1;
        SfxPlayer.play(isBossHit ? "sword_hit" : "sword_hit_flesh");
        hitMon.hitFlash = Date.now() + 200;
        hitMon.stateSeq = msg.seq || (hitMon.stateSeq + 1);
        // Only sync position and cancel walk if monster was knocked back
        // (bosses are non-knockbackable — they continue walking through hits)
        if (msg.knock_x != null) {
          hitMon.x = msg.knock_x;
          hitMon.y = msg.knock_y;
          const durationMs = (msg.knock_duration || 0.2) * 1000;
          hitMon.action = {
            type: "knockback",
            fromX: hitMon.displayX,
            fromY: hitMon.displayY,
            toX: msg.knock_x, toY: msg.knock_y,
            startTime: performance.now(),
            effectiveDuration: computeEffectiveDuration(durationMs),
            duration: durationMs,
            seq: hitMon.stateSeq,
          };
          hitMon.correctionOffset = { x: 0, y: 0 };
        }
        // Juice: hit sparks
        const cx = hitMon.displayX * TS + (hitMon.width || 1) * TS / 2;
        const cy = hitMon.displayY * TS + (hitMon.height || 1) * TS / 2;
        spawnBurst(cx, cy, 5, 3, 300, ["#fff", "#ffee88", "#ffcc44"], [2 * SCALE, 4 * SCALE], { shrink: true });
        // Juice: floating damage number
        spawnFloatingText(cx, hitMon.displayY * TS, "1", "#fff");
        // Juice: hit pause + tiny shake
        G.fx.hitPause = Date.now() + 40;
        triggerShake(1, 60);
      }
      break;
    }

    case "monster_spawned":
      registerCustomContent(msg);
      _getMonsters().push({ id: msg.id, kind: msg.kind, x: msg.x, y: msg.y, displayX: msg.x, displayY: msg.y, width: msg.width || 1, height: msg.height || 1, action: null, stateSeq: 0, correctionOffset: { x: 0, y: 0 }, spawnTime: Date.now() });
      break;

    // --- Stage 5: Monster attack messages ---
    case "projectile_spawned":
      G.fx.projectiles.push({
        id: msg.id, x: msg.x, y: msg.y,
        displayX: msg.x, displayY: msg.y,
        dx: msg.dx, dy: msg.dy, color: msg.color,
      });
      break;

    case "projectile_moved": {
      const proj = G.fx.projectiles.find(p => p.id === msg.id);
      if (proj) { proj.x = msg.x; proj.y = msg.y; }
      break;
    }

    case "projectile_hit":
      G.fx.projectiles = G.fx.projectiles.filter(p => p.id !== msg.id);
      if (msg.x !== undefined) {
        G.fx.monsterAttackFlashes.push({ x: msg.x, y: msg.y, startTime: Date.now() });
      }
      break;

    case "projectile_gone": {
      // Juice: dust particles at impact point (read position before removing)
      const deadProj = G.fx.projectiles.find(p => p.id === msg.id);
      if (deadProj) {
        const px = tileCenterX(deadProj.displayX);
        const py = tileCenterY(deadProj.displayY);
        spawnBurst(px, py, 4, 1.5, 250, ["#aaa", "#888", "#666"], [2 * SCALE, 3 * SCALE], { shrink: true });
      }
      G.fx.projectiles = G.fx.projectiles.filter(p => p.id !== msg.id);
      break;
    }

    case "monster_attack":
      G.fx.monsterAttackFlashes.push({ x: msg.target_x, y: msg.target_y, startTime: Date.now() });
      break;

    case "charge_prep": {
      const prepMon = _getMonsters().find(m => m.id === msg.id);
      if (prepMon) {
        if (msg.seq != null && msg.seq < prepMon.stateSeq) break; // stale
        const durationMs = (msg.duration || 2.0) * 1000;
        prepMon.action = {
          type: "charge_warmup",
          lane: msg.lane,
          startTime: performance.now(),
          effectiveDuration: computeEffectiveDuration(durationMs),
          duration: durationMs,
          seq: prepMon.stateSeq,
        };
      }
      break;
    }

    case "monster_charged": {
      const chargedMon = _getMonsters().find(m => m.id === msg.id);
      if (chargedMon) {
        if (msg.seq != null && msg.seq < chargedMon.stateSeq) break; // stale
        chargedMon.x = msg.x;
        chargedMon.y = msg.y;
        chargedMon.displayX = msg.x;
        chargedMon.displayY = msg.y;
        chargedMon.stateSeq = msg.seq || (chargedMon.stateSeq + 1);
        chargedMon.action = null;
        chargedMon.correctionOffset = { x: 0, y: 0 };
      }
      G.fx.chargeTrails.push({ path: msg.path, startTime: Date.now() });
      break;
    }

    case "teleport_start": {
      SfxPlayer.play("portal_enter");
      const tpMon = _getMonsters().find(m => m.id === msg.id);
      if (tpMon) {
        const durationMs = (msg.delay || 0.5) * 1000;
        tpMon.action = {
          type: "teleport_warmup",
          targetX: msg.target_x, targetY: msg.target_y,
          damageRadius: msg.damage_radius || 0,
          startTime: performance.now(),
          effectiveDuration: computeEffectiveDuration(durationMs),
          duration: durationMs,
          seq: tpMon.stateSeq,
        };
      }
      break;
    }

    case "teleport_end": {
      const tpEndMon = _getMonsters().find(m => m.id === msg.id);
      if (tpEndMon) {
        if (msg.seq != null && msg.seq < tpEndMon.stateSeq) break; // stale
        tpEndMon.x = msg.x;
        tpEndMon.y = msg.y;
        tpEndMon.displayX = msg.x;
        tpEndMon.displayY = msg.y;
        tpEndMon.stateSeq = msg.seq || (tpEndMon.stateSeq + 1);
        tpEndMon.action = null;
        tpEndMon.correctionOffset = { x: 0, y: 0 };
      }
      break;
    }

    case "area_warning": {
      const awMon = _getMonsters().find(m => m.id === msg.id);
      if (awMon) {
        const durationMs = (msg.duration || 0.75) * 1000;
        awMon.action = {
          type: "area_warmup",
          x: msg.x, y: msg.y,
          range: msg.range,
          areaWidth: msg.width || 1, areaHeight: msg.height || 1,
          startTime: performance.now(),
          effectiveDuration: computeEffectiveDuration(durationMs),
          duration: durationMs,
          seq: awMon.stateSeq,
        };
      }
      break;
    }

    case "area_attack":
      G.fx.monsterAttackFlashes.push({ x: msg.x, y: msg.y, width: msg.width || 1, height: msg.height || 1, range: msg.range, startTime: Date.now() });
      break;

    case "warmup_cancel": {
      const cancelMon = _getMonsters().find(m => m.id === msg.id);
      if (cancelMon && cancelMon.action &&
          (cancelMon.action.type === "charge_warmup" || cancelMon.action.type === "area_warmup")) {
        cancelMon.action = null;
      }
      break;
    }

    case "monster_fade_in": {
      const fadeMon = _getMonsters().find(m => m.id === msg.id);
      if (fadeMon && fadeMon.action && fadeMon.action.type === "teleport_warmup") {
        fadeMon.action = null;
      }
      break;
    }

    case "music_change":
      if (msg.music === null || msg.music === "silence") {
        MusicPlayer.silence();
      } else {
        MusicPlayer.setRoom(G.room.currentRoom ? G.room.currentRoom.room_id : "", G.room.currentRoom ? G.room.currentRoom.biome : "", msg.music);
      }
      break;

    case "boss_choir_start":
      MusicPlayer.startChoir(msg.distance, msg.choir_track);
      break;

    case "boss_choir_stop":
      MusicPlayer.stopChoir();
      break;

    case "quest_update":
      break;


    case "item_obtained": {
      if (msg.item_type) {
        // SFX: context-specific pickup sound
        if (msg.item_type === "key") SfxPlayer.play("key_pickup");
        else if (msg.item_type === "lantern" || msg.item_type === "tide_medallion") SfxPlayer.play("chest_open");
        else SfxPlayer.play("item_pickup");
        // Item pickup animation (dungeon items, sword, etc.)
        G.player.itemPickupActive = {
          item_type: msg.item_type,
          item_name: msg.item_name,
          startTime: Date.now(),
          x: G.player.displayX,
          y: G.player.displayY,
        };
        // Remove from ground items (dungeon items only)
        // Per-player items (lantern, seal_fragment) stay on ground for other players
        const perPlayerItems = new Set(["lantern", "tide_medallion", "seal_fragment", "heart_container"]);
        if (perPlayerItems.has(msg.item_type)) {
          // Remove for THIS player only (visual) — server keeps it for others
          const px = G.player.displayX, py = G.player.displayY;
          let removed = false;
          G.room.dungeonGroundItems = G.room.dungeonGroundItems.filter(it => {
            if (!removed && it.item_type === msg.item_type && Math.abs(it.x - px) < 1 && Math.abs(it.y - py) < 1) {
              removed = true;
              // Chest items: transition chest to opened state at this position
              if (msg.item_type === "lantern" || msg.item_type === "tide_medallion") {
                G.room.openedChests.push({x: it.x, y: it.y});
              }
              return false;
            }
            return true;
          });
        } else if (msg.item_type === "key") {
          // Keys: remove by position (multiple keys can exist)
          const kx = G.player.displayX, ky = G.player.displayY;
          let removed = false;
          G.room.dungeonGroundItems = G.room.dungeonGroundItems.filter(it => {
            if (!removed && it.item_type === "key" && Math.abs(it.x - kx) < 1 && Math.abs(it.y - ky) < 1) {
              removed = true;
              return false;
            }
            return true;
          });
          G.player.keyCount++;
        } else {
          G.room.dungeonGroundItems = G.room.dungeonGroundItems.filter(
            it => it.item_type !== msg.item_type
          );
        }
        // Grant gameplay flag after animation starts
        if (msg.item_type === "sword") {
          setTimeout(() => { G.player.playerFlags.add("has_sword"); }, 500);
        } else if (msg.item_type === "spirit_jar") {
          setTimeout(() => { G.player.spiritJarCount = (G.player.spiritJarCount || 0) + 1; }, 500);
        } else if (msg.item_type === "lantern") {
          setTimeout(() => {
            G.player.playerFlags.add("has_lantern");
            G.room.lanternHolders.add(G.player.myName);
          }, 500);
        } else if (msg.item_type === "tide_medallion") {
          setTimeout(() => {
            G.player.playerFlags.add("has_tide_medallion");
            G.room.medallionHolders.add(G.player.myName);
            for (const t of WATER_TILES) WALKABLE.add(t);
          }, 500);
        } else if (msg.item_type === "seal_fragment") {
          setTimeout(() => { G.player.playerFlags.add("has_seal_fragment"); }, 500);
        }
        setTimeout(() => {
          G.ui.infoMessages.push({ text: "You got the " + msg.item_name + "!", expires: Date.now() + 4000 });
        }, 500);
        appendChatLog(`<span class="chat-item">${escHtml(G.player.myName)} obtained ${escHtml(msg.item_name)}!</span>`);
      } else {
        // NPC gift item (legacy)
        G.player.playerFlags.add("has_" + msg.item);
        G.ui.infoMessages.push({ text: "You obtained: " + msg.name + "!", expires: Date.now() + 5000 });
        appendChatLog(`<span class="chat-item">${escHtml(G.player.myName)} obtained ${escHtml(msg.name)}!</span>`);
      }
      break;
    }

    case "item_effect": {
      // Another player picking up a dungeon item — show their animation
      const effPlayer = G.room.otherPlayers[msg.name];
      if (effPlayer) {
        G.player.itemPickupEffects[msg.name] = {
          item_type: msg.item_type,
          startTime: Date.now(),
          x: effPlayer.displayX,
          y: effPlayer.displayY,
        };
      }
      // Track lantern/medallion holders for rendering
      if (msg.item_type === "lantern") {
        G.room.lanternHolders.add(msg.name);
      } else if (msg.item_type === "tide_medallion") {
        G.room.medallionHolders.add(msg.name);
      }
      appendChatLog(`<span class="chat-item">${escHtml(msg.name)} obtained ${escHtml(msg.item_name)}!</span>`);
      break;
    }

    case "dungeon_item_collected": {
      // Any player collected a dungeon item — update minimap state
      if (G.room.dungeonState && msg.item_type !== "key") {
        G.room.dungeonState.collected.add(msg.item_type);
      }
      // Remove from ground items (in case we're in the same room)
      if (msg.x !== undefined && msg.y !== undefined) {
        // Position-based removal (keys — multiple can exist)
        let removed = false;
        G.room.dungeonGroundItems = G.room.dungeonGroundItems.filter(it => {
          if (!removed && it.item_type === msg.item_type &&
              Math.abs(it.x - msg.x) < 0.1 && Math.abs(it.y - msg.y) < 0.1) {
            removed = true;
            return false;
          }
          return true;
        });
      } else {
        G.room.dungeonGroundItems = G.room.dungeonGroundItems.filter(
          it => it.item_type !== msg.item_type
        );
      }
      break;
    }

    case "room_freeze":
      G.room.monsterFreeze = {
        start: performance.now(),
        duration: msg.duration * 1000,
      };
      break;

    case "key_update":
      G.player.keyCount = msg.keys;
      break;

    case "keylayout":
      // Store zone debug data for minimap overlay
      if (G.room.dungeonState) {
        G.room.dungeonState.keyLayout = msg.zones;
      }
      break;

    case "dungeon_player_positions":
      // Another player moved rooms in the dungeon — update compass dots
      if (G.room.dungeonState) {
        G.room.dungeonState.otherPlayers = msg.players || [];
      }
      break;

    case "debug_state":
      G.debug.serverState = msg;
      break;

    case "viewserver_toggle":
      G.debug.viewServer = msg.enabled;
      G.debug.serverState = null;
      G.ui.infoMessages.push({ text: msg.enabled ? "Server view ON" : "Server view OFF", expires: Date.now() + 3000 });
      break;

    case "debug_log":
      dbg(msg.text);
      break;

    case "server_log":
      if (G.ui.serverLog) {
        const line = document.createElement("div");
        line.className = "log-line";
        const t = msg.text;
        if (t.includes("[REGEN]")) line.classList.add("regen");
        else if (t.includes("[DEPRECATION]")) line.classList.add("deprecation");
        else if (t.includes("[DUNGEON]")) line.classList.add("highlight");
        else if (t.includes("ERROR") || t.includes("failed") || t.includes("Traceback")) line.classList.add("error");
        line.textContent = t;
        G.ui.serverLog.appendChild(line);
        // Cap at 200 lines
        while (G.ui.serverLog.childElementCount > 200) G.ui.serverLog.removeChild(G.ui.serverLog.firstChild);
        G.ui.serverLog.scrollTop = G.ui.serverLog.scrollHeight;
      }
      break;

    case "info": {
      const lines = msg.text.split("\n");
      for (const line of lines) {
        G.ui.infoMessages.push({ text: line, expires: Date.now() + 5000 });
        appendChatLog(`<span class="chat-system">${escHtml(line)}</span>`);
      }
      break;
    }

    case "flag_removed": {
      G.player.playerFlags.delete(msg.flag);
      break;
    }

    case "lantern_removed": {
      G.room.lanternHolders.delete(msg.name);
      break;
    }

    case "log": {
      // Chat log only, no popup overlay
      const cls = msg.boss ? "chat-boss" : "chat-system";
      appendChatLog(`<span class="${cls}">${escHtml(msg.text)}</span>`);
      break;
    }

    // ----- Revival system -----

    case "waiting_for_revival":
      G.player.waitingForRevival = true;
      appendChatLog(`<span class="chat-system">Waiting for revival... Press Respawn to give up.</span>`);
      break;

    case "tombstone_placed": {
      const _tpSD = G.player.spectateData;
      if (_tpSD && G.player.waitingForRevival) {
        _tpSD.tombstones[msg.name] = { x: msg.x, y: msg.y, color_index: msg.color_index };
      } else {
        G.room.tombstones[msg.name] = { x: msg.x, y: msg.y, color_index: msg.color_index };
      }
      break;
    }

    case "tombstone_removed": {
      const _trSD = G.player.spectateData;
      if (_trSD && _trSD.tombstones[msg.name]) {
        delete _trSD.tombstones[msg.name];
      } else {
        delete G.room.tombstones[msg.name];
      }
      delete G.room.dyingOtherPlayers[msg.name];
      if (G.room.activeRevival && G.room.activeRevival.targetName === msg.name) {
        G.room.activeRevival = null;
      }
      break;

    case "revival_started": {
      const revDuration = (msg.duration || 10) * 1000;  // server sends seconds
      if (msg.target === G.player.myName) {
        // Someone is reviving us
        G.player.revivalProgress = {
          reviverName: msg.reviver,
          startTime: Date.now(),
          duration: revDuration,
        };
      }
      if (msg.reviver === G.player.myName) {
        // We are reviving someone
        G.room.activeRevival = {
          targetName: msg.target,
          startTime: Date.now(),
          duration: revDuration,
        };
      }
      break;
    }

    case "revival_cancelled":
      if (G.player.revivalProgress) G.player.revivalProgress = null;
      if (G.room.activeRevival && (!msg.target || G.room.activeRevival.targetName === msg.target)) {
        G.room.activeRevival = null;
      }
      break;

    case "revival_complete": {
      // Sparkle burst at revival position
      const rcx = msg.x * TS + TS / 2;
      const rcy = msg.y * TS + TS / 2;
      spawnBurst(rcx, rcy, 12, 3, 600,
        ["#ffe066", "#ffffff", "#ffcc00", "#ffd700"],
        [3 * SCALE, 6 * SCALE]);
      G.room.activeRevival = null;
      if (msg.target === G.player.myName) {
        G.player.revivalProgress = null;
      }
      appendChatLog(`<span class="chat-system">${escHtml(msg.reviver)} revived ${escHtml(msg.target)}!</span>`);
      break;
    }

    case "you_revived":
      SfxPlayer.play("revival_success");
      G.player.waitingForRevival = false;
      G.player.revivalProgress = null;
      G.player.dyingPlayerSelf = null;
      G.player._revivalWaitStart = null;
      G.player.spectateData = null;
      appendChatLog(`<span class="chat-system">${escHtml(msg.reviver)} revived you!</span>`);
      break;

    case "spirit_jar_revive":
      G.player.spiritJarRevive = { startTime: Date.now() };
      G.player.myHp = msg.hp;
      G.player.myMaxHp = msg.max_hp;
      G.player.dyingPlayerSelf = null;
      G.player.waitingForRevival = false;
      G.player.revivalProgress = null;
      G.player._revivalWaitStart = null;
      G.player.spectateData = null;
      G.player.spiritJarCount = Math.max(0, (G.player.spiritJarCount || 0) - 1);
      appendChatLog(`<span class="chat-system">The Spirit Jar saved you!</span>`);
      break;

    // ----- Death camera (spectate) -----

    case "spectate_room": {
      registerCustomContent(msg);
      const sd = {
        room_id: msg.room_id,
        tilemap: msg.tilemap,
        exits: msg.exits || {},
        biome: msg.biome || "overworld",
        players: {},
        tombstones: {},
        monsters: (msg.monsters || []).map((m, idx) => ({
          id: m.id ?? idx, kind: m.kind, x: m.x, y: m.y,
          displayX: m.x, displayY: m.y,
          walk_time: m.walk_time || 0.25, seq: m.seq || 0, stateSeq: m.seq || 0,
          width: m.width || 1, height: m.height || 1,
          alive: true, action: null,
          walking: m.walking ? {
            from: m.walk_from, to: m.walk_to,
            progress: m.walk_progress || 0,
            walk_time: m.walk_time_step || 0.25,
            startTime: performance.now() - (m.walk_progress || 0) * (m.walk_time_step || 0.25) * 1000,
          } : null,
        })),
        target_name: msg.target_name,
        dark: msg.dark || false,
        light_sources: msg.light_sources || [],
        lantern_holders: new Set(msg.lantern_holders || []),
      };
      for (const p of (msg.players || [])) {
        sd.players[p.name] = createOtherPlayer(p.x, p.y, p.direction, p.color_index);
      }
      for (const ts of (msg.tombstones || [])) {
        sd.tombstones[ts.name] = { x: ts.x, y: ts.y, color_index: ts.color_index };
      }
      G.player.spectateData = sd;
      break;
    }

    case "spectate_stop":
      G.player.spectateData = null;
      break;

    case "error":
      G.ui.loginError.textContent = msg.text;
      break;
  }
}
