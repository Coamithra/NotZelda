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
  // Use port 8443 for TLS WebSocket (bypasses nginx — fixes iOS Safari 30s disconnect)
  const wsHost = proto === "wss:" ? location.hostname + ":8443" : location.host;
  dbg(`Connecting...`);
  G.ws = new WebSocket(`${proto}//${wsHost}/ws`);

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
      G.dungeonState = null;
      G.dungeonGroundItems = [];
      G.itemPickupActive = null;
      G.itemPickupEffects = {};
      if (typeof TITLE !== "undefined") TITLE.hide();
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
      G.conjuring = { startTime: Date.now(), progressSteps: [], oldCanvas: conjureCanvas };
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
      // Process immediately even during conjuring — the conjuring animation
      // is purely visual overlay. Room state updates in the background so
      // monsters, players etc. stay in sync with the server.
      const cameFromConjuring = !!G.conjuring;
      if (G.conjuring) {
        // Schedule end of conjuring overlay — fade into the already-live room
        const MIN_CONJURE_MS = 2500;
        const elapsed = Date.now() - G.conjuring.startTime;
        const remaining = Math.max(0, MIN_CONJURE_MS - elapsed);
        setTimeout(() => {
          if (G.conjuring) {
            G.conjuring = null;
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
          }
        }, remaining);
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
        renderDungeonGroundItems();
        renderChargePreps();
        renderChargeTrails();
        renderPlayers();
        renderProjectiles();
        renderMonsterAttackFlashes();
        renderSpeechBubbles();
        renderSwordPickups();
        renderItemPickups();
        G.ctx = savedCtx;
      }

      const prevExits = G.currentRoom ? G.currentRoom.exits : null;
      G.currentRoom = {
        name: msg.name,
        tilemap: msg.tilemap,
        room_id: msg.room_id,
        exits: msg.exits || {},
        biome: msg.biome || "town",
        dungeon_type: msg.dungeon_type || null,
      };
      G.myPlayer = {
        x: msg.your_pos.x,
        y: msg.your_pos.y,
        direction: G.myPlayer ? G.myPlayer.direction : "down",
        color_index: G.myColorIndex,
      };

      MusicPlayer.setRoom(msg.room_id, msg.biome, msg.music);

      // Register any custom sprites/tiles/NPC data sent with this room
      if (msg.custom_sprites) {
        for (const [kind, spriteData] of Object.entries(msg.custom_sprites)) {
          if (!customMonsterSprites[kind]) {
            customMonsterSprites[kind] = spriteData;
          }
        }
      }
      if (msg.custom_death_sprites) {
        for (const [kind, spriteData] of Object.entries(msg.custom_death_sprites)) {
          if (!customDeathSprites[kind]) {
            customDeathSprites[kind] = spriteData;
          }
        }
      }
      if (msg.npc_sprites) {
        for (const [key, spriteData] of Object.entries(msg.npc_sprites)) {
          if (!customNPCSprites[key]) {
            customNPCSprites[key] = spriteData;
          }
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
      // Juice: clear corpses, particles, effects on room change
      clearCorpses();
      G.particles = [];
      G.slashArcs = [];
      G.floatingTexts = [];
      G.screenShake = null;
      G.canvas.style.transform = "";
      G.dungeonGroundItems = msg.dungeon_items || [];
      G.itemPickupActive = null;
      G.itemPickupEffects = {};
      G.dyingPlayerSelf = null;
      G.dyingOtherPlayers = {};
      G.bossDeathEffect = null;
      G.projectiles = [];
      G.areaWarnings = [];
      G.chargeTrails = [];
      G.chargePreps = [];
      G.monsterAttackFlashes = [];
      G.monsters = (msg.monsters || []).map((m, idx) => {
        const mon = {
          id: m.id, kind: m.kind, x: m.x, y: m.y, displayX: m.x, displayY: m.y,
          width: m.width || 1, height: m.height || 1,
          walkTime: (m.walk_time || 2.0) * 1000,  // per-monster walk duration in ms
          walkState: null,
          spawnTime: Date.now() + idx * 40,  // Juice: staggered spawn pop
        };
        if (m.walking) {
          mon.walkState = {
            fromX: m.walk_from.x, fromY: m.walk_from.y,
            toX: m.walk_to.x, toY: m.walk_to.y,
            startTime: performance.now() - (m.walk_progress * mon.walkTime),
            walkTime: mon.walkTime,
          };
          mon.x = m.walk_to.x;
          mon.y = m.walk_to.y;
        }
        return mon;
      });
      for (const p of msg.players) {
        const op = {
          x: p.x, y: p.y,
          displayX: p.x, displayY: p.y,
          direction: p.direction,
          color_index: p.color_index,
          moving: false,
          walkState: null,
        };
        G.otherPlayers[p.name] = op;
        if (p.dancing) startDance(p.name);
      }
      G.preciseX = G.myPlayer.x;
      G.preciseY = G.myPlayer.y;
      G.lastReportedX = G.myPlayer.x;
      G.lastReportedY = G.myPlayer.y;
      G.displayX = G.myPlayer.x;
      G.displayY = G.myPlayer.y;
      setState("idle", {});

      // Dungeon state — track collected items and visited cells
      if (msg.dungeon_collected !== undefined) {
        // In a dungeon room — initialize or update dungeon state
        const mm = msg.dungeon_debug && msg.dungeon_debug.minimap;
        const currentCell = mm && mm.player;
        if (!G.dungeonState) {
          G.dungeonState = {
            collected: new Set(msg.dungeon_collected),
            cells: mm ? mm.cells : [],
            bossCell: msg.dungeon_boss_cell,
            currentCell: currentCell,
          };
        } else {
          G.dungeonState.collected = new Set(msg.dungeon_collected);
          G.dungeonState.cells = mm ? mm.cells : G.dungeonState.cells;
          G.dungeonState.currentCell = currentCell;
          G.dungeonState.bossCell = msg.dungeon_boss_cell || G.dungeonState.bossCell;
        }
      } else {
        // Left the dungeon
        G.dungeonState = null;
        G.dungeonGroundItems = [];
      }

      if (cameFromConjuring) {
        // Conjuring overlay is still active — the setTimeout in the conjuring
        // handler will create the fade transition when the animation ends.
        // Don't create a transition now.
      } else if (isFirstRoom) {
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

    case "reconcile": {
      if (G.networkLog) {
        const t = performance.now().toFixed(1);
        console.log(`[NET IN  t=${t}] reconcile pos=(${msg.x},${msg.y}) [${G.state}]`);
      }
      G.preciseX = G.displayX = G.myPlayer.x = msg.x;
      G.preciseY = G.displayY = G.myPlayer.y = msg.y;
      G.lastReportedX = msg.x;
      G.lastReportedY = msg.y;
      G.myPlayer.direction = msg.direction;
      delete G.attackingPlayers[G.myName];
      setState("idle");
      break;
    }

    case "player_walk_half": {
      // Another player moved half a tile — smooth interpolation
      const op = G.otherPlayers[msg.name];
      if (op) {
        stopDance(msg.name);
        delete G.attackingPlayers[msg.name];
        op.direction = msg.direction;
        op.x = msg.x;
        op.y = msg.y;
        op.walkState = {
          fromX: op.displayX, fromY: op.displayY,
          toX: msg.x, toY: msg.y,
          startTime: performance.now(),
        };
      }
      break;
    }

    case "player_faced":
      if (msg.name !== G.myName && G.otherPlayers[msg.name]) {
        stopDance(msg.name);
        G.otherPlayers[msg.name].direction = msg.direction;
      }
      break;

    case "player_entered":
      if (msg.name !== G.myName) {
        const ep = {
          x: msg.x, y: msg.y,
          displayX: msg.x, displayY: msg.y,
          direction: msg.direction,
          color_index: msg.color_index,
          moving: false,
          walkState: null,
        };
        G.otherPlayers[msg.name] = ep;
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
      if (msg.name !== G.myName) {
        startAttack(msg.name, msg.direction);
      }
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
        // Knockback dust trail (before position overwrite)
        if (msg.knockback) {
          const oldX = G.preciseX, oldY = G.preciseY;
          for (let t = 0.33; t <= 0.66; t += 0.33) {
            const dustX = (oldX + (msg.x - oldX) * t) * TS + TS / 2;
            const dustY = (oldY + (msg.y - oldY) * t + 0.5) * TS;
            spawnBurst(dustX, dustY, 2, 1.0, 250, ["#c8b898", "#a09068"], [2 * SCALE, 3 * SCALE], { shrink: true });
          }
          // Smooth knockback slide — keep displayX/Y at old position, animate to new
          G.knockbackSlide = {
            fromX: G.displayX, fromY: G.displayY,
            toX: msg.x, toY: msg.y,
            startTime: performance.now(), duration: 200,
          };
        }
        G.myHp = msg.hp;
        G.myPlayer.x = msg.x;
        G.myPlayer.y = msg.y;
        G.preciseX = msg.x;
        G.preciseY = msg.y;
        G.lastReportedX = msg.x;
        G.lastReportedY = msg.y;
        if (!msg.knockback) {
          G.displayX = msg.x;
          G.displayY = msg.y;
        }
        setState("idle", {});
        G.hurtFlash = Date.now() + 300;
        G.invincibleUntil = Date.now() + 1500;
        G.stunUntil = performance.now() + 200;
        // Juice: screen shake + damage vignette
        triggerShake(4, 200);
        G.damageVignette = Date.now() + VIGNETTE_DURATION;
        if (G.debugCollision && msg.debug_source_x != null) {
          G.debugGhosts.push({
            playerX: msg.debug_pre_x, playerY: msg.debug_pre_y,
            sourceX: msg.debug_source_x, sourceY: msg.debug_source_y,
            prevPlayerX: msg.debug_prev_player_x, prevPlayerY: msg.debug_prev_player_y,
            prevSourceX: msg.debug_prev_source_x, prevSourceY: msg.debug_prev_source_y,
            sourceW: msg.debug_source_w || 1, sourceH: msg.debug_source_h || 1,
            knockX: msg.x, knockY: msg.y,
            time: Date.now(),
          });
        }
      } else if (G.otherPlayers[msg.name]) {
        const op = G.otherPlayers[msg.name];
        if (msg.knockback) {
          op.knockbackSlide = {
            fromX: op.displayX, fromY: op.displayY,
            toX: msg.x, toY: msg.y,
            startTime: performance.now(), duration: 200,
          };
        }
        op.x = msg.x;
        op.y = msg.y;
        op.hurtFlash = Date.now() + 300;
      }
      break;
    }

    case "you_died":
      G.dyingPlayerSelf = { x: msg.x, y: msg.y, frame: 0, startTime: Date.now() };
      G.myHp = 0;
      setState("dying", {});
      G.preciseX = msg.x;
      G.preciseY = msg.y;
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

    case "heart_collected": {
      // Juice: sparkle particles at pickup point
      const collectedHeart = G.heartPickups.find(h => h.id === msg.id);
      if (collectedHeart) {
        const hx = collectedHeart.x * TS + TS / 2;
        const hy = collectedHeart.y * TS + TS / 2;
        spawnBurst(hx, hy, 4, 2, 300, ["#ff6060", "#fff", "#ffaaaa"], [2 * SCALE, 4 * SCALE]);
      }
      G.heartPickups = G.heartPickups.filter(h => h.id !== msg.id);
      break;
    }

    case "monster_walk_started": {
      const walkMon = G.monsters.find(m => m.id === msg.id);
      if (walkMon) {
        walkMon.walkState = {
          fromX: msg.from_x, fromY: msg.from_y,
          toX: msg.to_x, toY: msg.to_y,
          startTime: performance.now(),
          walkTime: msg.walk_time * 1000,
        };
        // Set logical position to target (walk will commit midway)
        walkMon.x = msg.to_x;
        walkMon.y = msg.to_y;
      }
      break;
    }

    case "monster_walk_complete": {
      const wcMon = G.monsters.find(m => m.id === msg.id);
      if (wcMon) {
        wcMon.walkState = null;
        wcMon.displayX = wcMon.x;
        wcMon.displayY = wcMon.y;
      }
      break;
    }

    case "monster_moved": {
      const mon = G.monsters.find(m => m.id === msg.id);
      if (mon) {
        mon.x = msg.x; mon.y = msg.y;
        mon.displayX = msg.x; mon.displayY = msg.y;
        mon.walkState = null;  // instant move — clear any walk
      }
      break;
    }

    case "monster_killed": {
      const idx = G.monsters.findIndex(m => m.id === msg.id);
      if (idx !== -1) {
        const mon = G.monsters[idx];
        mon.walkState = null;
        const isBoss = (mon.width || 1) > 1 || (mon.height || 1) > 1;
        G.dyingMonsters.push({ kind: mon.kind, x: msg.x, y: msg.y, frame: 0, nextTime: Date.now() + (isBoss ? 400 : DYING_MONSTER_FRAME_MS), width: mon.width || 1, height: mon.height || 1 });
        G.monsters.splice(idx, 1);
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
        G.hitPause = Date.now() + 60;
        triggerShake(2, 120);
        // Boss death: dramatic screen flash + shake
        if (isBoss) {
          G.bossDeathEffect = { startTime: Date.now(), duration: 2000 };
          triggerShake(6, 1000);
        }
      }
      break;
    }

    case "doors_unlocked": {
      // Trap room cleared — restore doorway tiles
      if (G.currentRoom && G.currentRoom.tilemap && msg.tile_changes) {
        for (const [r, c, tile] of msg.tile_changes) {
          G.currentRoom.tilemap[r][c] = tile;
        }
      }
      // Reveal dungeon items that were hidden during the trap
      if (msg.dungeon_items) {
        G.dungeonGroundItems = msg.dungeon_items;
      }
      G.infoMessages.push({ text: "The doors have opened!", expires: Date.now() + 3000 });
      break;
    }

    case "monster_hit": {
      const hitMon = G.monsters.find(m => m.id === msg.id);
      if (hitMon) {
        hitMon.hitFlash = Date.now() + 200;
        // Knockback slide (separate from walkState so no hop animation)
        if (msg.knock_x != null) {
          hitMon.knockbackSlide = {
            fromX: hitMon.displayX, fromY: hitMon.displayY,
            toX: msg.knock_x, toY: msg.knock_y,
            startTime: performance.now(), duration: 200,
          };
          hitMon.x = msg.knock_x;
          hitMon.y = msg.knock_y;
          hitMon.walkState = null;  // cancel any in-progress walk
        }
        // Juice: hit sparks
        const cx = hitMon.displayX * TS + (hitMon.width || 1) * TS / 2;
        const cy = hitMon.displayY * TS + (hitMon.height || 1) * TS / 2;
        spawnBurst(cx, cy, 5, 3, 300, ["#fff", "#ffee88", "#ffcc44"], [2 * SCALE, 4 * SCALE], { shrink: true });
        // Juice: floating damage number
        spawnFloatingText(cx, hitMon.displayY * TS, "1", "#fff");
        // Juice: hit pause + tiny shake
        G.hitPause = Date.now() + 40;
        triggerShake(1, 60);
      }
      break;
    }

    case "monster_spawned":
      if (msg.custom_sprites) {
        for (const [kind, spriteData] of Object.entries(msg.custom_sprites)) {
          if (!customMonsterSprites[kind]) {
            customMonsterSprites[kind] = spriteData;
          }
        }
      }
      if (msg.custom_death_sprites) {
        for (const [kind, spriteData] of Object.entries(msg.custom_death_sprites)) {
          if (!customDeathSprites[kind]) {
            customDeathSprites[kind] = spriteData;
          }
        }
      }
      G.monsters.push({ id: msg.id, kind: msg.kind, x: msg.x, y: msg.y, displayX: msg.x, displayY: msg.y, width: msg.width || 1, height: msg.height || 1, walkTime: (msg.walk_time || 2.0) * 1000, walkState: null, spawnTime: Date.now() });
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

    case "projectile_gone": {
      // Juice: dust particles at impact point (read position before removing)
      const deadProj = G.projectiles.find(p => p.id === msg.id);
      if (deadProj) {
        const px = deadProj.displayX * TS + TS / 2;
        const py = deadProj.displayY * TS + TS / 2;
        spawnBurst(px, py, 4, 1.5, 250, ["#aaa", "#888", "#666"], [2 * SCALE, 3 * SCALE], { shrink: true });
      }
      G.projectiles = G.projectiles.filter(p => p.id !== msg.id);
      break;
    }

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
        chargedMon.walkState = null;
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
        tpEndMon.walkState = null;
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

    case "boss_choir_start":
      MusicPlayer.startChoir(msg.distance, msg.choir_track);
      break;

    case "boss_choir_stop":
      MusicPlayer.stopChoir();
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

    case "item_obtained": {
      if (msg.item_type) {
        // Dungeon item (map/compass) — trigger pickup animation
        G.itemPickupActive = {
          item_type: msg.item_type,
          item_name: msg.item_name,
          startTime: Date.now(),
          x: G.displayX,
          y: G.displayY,
        };
        // Remove from ground items
        G.dungeonGroundItems = G.dungeonGroundItems.filter(
          it => it.item_type !== msg.item_type
        );
        setTimeout(() => {
          G.infoMessages.push({ text: "You got the " + msg.item_name + "!", expires: Date.now() + 4000 });
        }, 500);
      } else {
        // NPC gift item (legacy)
        G.playerFlags.add("has_" + msg.item);
        G.infoMessages.push({ text: "You obtained: " + msg.name + "!", expires: Date.now() + 5000 });
      }
      break;
    }

    case "item_effect": {
      // Another player picking up a dungeon item — show their animation
      const effPlayer = G.otherPlayers[msg.name];
      if (effPlayer) {
        G.itemPickupEffects[msg.name] = {
          item_type: msg.item_type,
          startTime: Date.now(),
          x: effPlayer.displayX,
          y: effPlayer.displayY,
        };
      }
      break;
    }

    case "dungeon_item_collected": {
      // Any player collected a dungeon item — update minimap state
      if (G.dungeonState) {
        G.dungeonState.collected.add(msg.item_type);
      }
      // Remove from ground items (in case we're in the same room)
      G.dungeonGroundItems = G.dungeonGroundItems.filter(
        it => it.item_type !== msg.item_type
      );
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
