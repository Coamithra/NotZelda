/* tweak.js - Runtime gamefeel tweaking console.
   Loaded AFTER game_state.js (needs G) but BEFORE other scripts so they
   can call registerTweak() at load time.

   Toggle with /tweak (debug mode only).
   Panel appears to the right of the game column, coexists with /draw. */

// ---------------------------------------------------------------------------
// Registry
// ---------------------------------------------------------------------------

const TWEAK_REGISTRY = {};   // name -> {get, set, group, label, min, max, step, type, default, server}
const TWEAK_GROUPS = {};     // groupName -> [name, name, ...]
const TWEAK_GROUP_ORDER = []; // ordered group names

function registerTweak(name, opts) {
  // opts: {get, set, group, label, min, max, step, type, server}
  // type: "float" | "int" | "bool" (default: "float")
  const def = opts.get();
  const entry = {
    get: opts.get,
    set: opts.set,
    group: opts.group || "Misc",
    label: opts.label || name,
    min: opts.min,
    max: opts.max,
    step: opts.step || (opts.type === "int" ? 1 : 0.01),
    // Infer "int" only for an integer default with no fractional step; an
    // explicit opts.type always wins. (A float param like MOVE_SPEED = 4.0 with
    // step 0.5 must stay "float" so applyTweakValue doesn't round it.)
    type: opts.type || (typeof def === "number" && Number.isInteger(def)
      && (opts.step == null || Number.isInteger(opts.step)) ? "int" : "float"),
    default: def,
    server: !!opts.server,
  };
  TWEAK_REGISTRY[name] = entry;
  if (!TWEAK_GROUPS[entry.group]) {
    TWEAK_GROUPS[entry.group] = [];
    TWEAK_GROUP_ORDER.push(entry.group);
  }
  TWEAK_GROUPS[entry.group].push(name);
}

// ---------------------------------------------------------------------------
// Monster tweaks (dynamic, populated from server data)
// ---------------------------------------------------------------------------

const MONSTER_TWEAK_DATA = {};  // kind -> {stats: {}, rules: [{params}]}

function registerMonsterTweaks(kind, stats, rules) {
  MONSTER_TWEAK_DATA[kind] = { stats: { ...stats }, rules: rules.map(r => ({ ...r })) };
  const group = "Monsters: " + kind;

  // Remove old entries for this kind (re-registration)
  if (TWEAK_GROUPS[group]) {
    for (const n of TWEAK_GROUPS[group]) delete TWEAK_REGISTRY[n];
    TWEAK_GROUPS[group] = [];
  }

  // Stats
  const statKeys = ["hp", "walk_time", "decision_time", "damage"];
  for (const key of statKeys) {
    if (stats[key] == null) continue;
    const tweakName = "monster." + kind + "." + key;
    registerTweak(tweakName, {
      get: () => MONSTER_TWEAK_DATA[kind].stats[key],
      set: (v) => {
        MONSTER_TWEAK_DATA[kind].stats[key] = v;
        _sendMonsterTweak(kind, "stat", key, v);
      },
      group: group,
      label: key,
      type: key === "hp" || key === "damage" ? "int" : "float",
      min: key === "hp" ? 1 : key === "damage" ? 0 : 0.01,
      max: key === "hp" ? 200 : key === "damage" ? 50 : 30,
      step: key === "hp" || key === "damage" ? 1 : 0.05,
      server: true,
    });
  }

  // Behavior rule params
  const ruleParams = ["range", "cooldown", "warmup", "damage", "drift", "speed",
                      "damage_radius", "count", "value"];
  for (let ri = 0; ri < rules.length; ri++) {
    const rule = rules[ri];
    const ruleLabel = (rule["do"] || "?") + (rule["if"] ? " (" + rule["if"] + ")" : "");
    for (const key of ruleParams) {
      if (rule[key] == null) continue;
      const tweakName = "monster." + kind + ".rule" + ri + "." + key;
      const rIdx = ri, rKey = key;
      registerTweak(tweakName, {
        get: () => MONSTER_TWEAK_DATA[kind].rules[rIdx][rKey],
        set: (v) => {
          MONSTER_TWEAK_DATA[kind].rules[rIdx][rKey] = v;
          _sendMonsterTweak(kind, "rule", rIdx + "." + rKey, v);
        },
        group: group,
        label: "rule" + ri + " " + ruleLabel + " - " + key,
        type: Number.isInteger(rule[key]) ? "int" : "float",
        min: 0,
        max: key === "range" ? 20 : key === "cooldown" || key === "warmup" ? 30 : 50,
        step: Number.isInteger(rule[key]) ? 1 : 0.1,
        server: true,
      });
    }
  }
}

function _sendMonsterTweak(kind, tweakType, key, value) {
  if (typeof sendToServer === "function") {
    sendToServer({ type: "tweak_monster", kind, tweak_type: tweakType, key, value });
  }
}

// ---------------------------------------------------------------------------
// Export
// ---------------------------------------------------------------------------

function exportTweaks() {
  const changed = {};
  for (const [name, entry] of Object.entries(TWEAK_REGISTRY)) {
    const val = entry.get();
    if (val !== entry.default) {
      changed[name] = { value: val, default: entry.default, group: entry.group, label: entry.label };
    }
  }

  if (Object.keys(changed).length === 0) {
    _flashExportBtn("No changes");
    return;
  }

  // Build readable output grouped by category
  let lines = ["// Tweak export - " + new Date().toISOString().slice(0, 19)];
  lines.push("// " + Object.keys(changed).length + " changed value(s)\n");

  const byGroup = {};
  for (const [name, info] of Object.entries(changed)) {
    if (!byGroup[info.group]) byGroup[info.group] = [];
    byGroup[info.group].push({ name, ...info });
  }

  for (const [group, entries] of Object.entries(byGroup)) {
    lines.push("// --- " + group + " ---");
    for (const e of entries) {
      lines.push(e.name + " = " + formatVal(e.value, TWEAK_REGISTRY[e.name].type)
        + "  // was " + formatVal(e.default, TWEAK_REGISTRY[e.name].type)
        + "  (" + e.label + ")");
    }
    lines.push("");
  }

  const text = lines.join("\n");
  navigator.clipboard.writeText(text).then(function () {
    _flashExportBtn("Copied!");
  }, function () {
    // Fallback: log to console
    console.log(text);
    _flashExportBtn("See console");
  });
}

function _flashExportBtn(msg) {
  const btn = _tweakPanelEl && _tweakPanelEl.querySelector(".tweak-export");
  if (!btn) return;
  const orig = btn.textContent;
  btn.textContent = msg;
  btn.style.color = "#3fb950";
  setTimeout(function () {
    btn.textContent = orig;
    btn.style.color = "";
  }, 1500);
}

// ---------------------------------------------------------------------------
// Panel UI
// ---------------------------------------------------------------------------

let _tweakPanelEl = null;
let _tweakCollapsedInit = false;
let _tweakCollapsed = {};   // group -> bool
let _tweakFilter = "";
let _tweakFocusedInput = null; // name of currently focused input (prevent overwrite)
let _tweakSliderActive = false; // true while a slider is being dragged

function toggleTweakPanel() {
  G.debug.tweakMode = !G.debug.tweakMode;
  if (_tweakPanelEl) {
    _tweakPanelEl.classList.toggle("active", G.debug.tweakMode);
  }
  if (G.debug.tweakMode) renderTweakPanel();
}

function renderTweakPanel() {
  if (!_tweakPanelEl || !G.debug.tweakMode) return;
  if (_tweakSliderActive || _tweakFocusedInput) return;
  // Start all groups collapsed on first render
  if (!_tweakCollapsedInit) {
    _tweakCollapsedInit = true;
    for (const group of TWEAK_GROUP_ORDER) _tweakCollapsed[group] = true;
  }
  const container = _tweakPanelEl.querySelector(".tweak-body");
  if (!container) return;

  const filter = _tweakFilter.toLowerCase();
  let html = "";

  for (const group of TWEAK_GROUP_ORDER) {
    const names = TWEAK_GROUPS[group];
    if (!names || names.length === 0) continue;

    // Filter check - does any param in this group match?
    const matching = filter
      ? names.filter(n => {
          const e = TWEAK_REGISTRY[n];
          return n.toLowerCase().includes(filter) ||
                 e.label.toLowerCase().includes(filter) ||
                 group.toLowerCase().includes(filter);
        })
      : names;
    if (matching.length === 0) continue;

    const collapsed = _tweakCollapsed[group];
    html += '<div class="tweak-group">';
    html += '<div class="tweak-group-header" data-group="' + escAttr(group) + '">';
    html += '<span class="tweak-arrow">' + (collapsed ? "\u25B6" : "\u25BC") + '</span> ';
    html += escHtmlTweak(group) + ' <span class="tweak-count">(' + matching.length + ')</span>';
    html += '</div>';

    if (!collapsed) {
      for (const name of matching) {
        const e = TWEAK_REGISTRY[name];
        const val = e.get();
        const isDefault = val === e.default;
        html += '<div class="tweak-row' + (e.server ? " tweak-server" : "") + '">';
        html += '<label class="tweak-label" title="' + escAttr(name) + '">' + escHtmlTweak(e.label) + '</label>';
        html += '<div class="tweak-controls">';

        // Input field
        html += '<input class="tweak-input" data-name="' + escAttr(name) + '" '
              + 'type="number" '
              + 'value="' + formatVal(val, e.type) + '" '
              + (e.step ? ' step="' + e.step + '"' : '')
              + (e.min != null ? ' min="' + e.min + '"' : '')
              + (e.max != null ? ' max="' + e.max + '"' : '')
              + '>';

        // +/- buttons
        html += '<button class="tweak-btn tweak-dec" data-name="' + escAttr(name) + '">-</button>';
        html += '<button class="tweak-btn tweak-inc" data-name="' + escAttr(name) + '">+</button>';

        // Slider (if min/max defined)
        if (e.min != null && e.max != null) {
          html += '<input class="tweak-slider" data-name="' + escAttr(name) + '" '
                + 'type="range" '
                + 'min="' + e.min + '" max="' + e.max + '" '
                + 'step="' + e.step + '" '
                + 'value="' + val + '">';
        }

        // Reset button
        html += '<button class="tweak-btn tweak-reset' + (isDefault ? " tweak-default" : "") + '" '
              + 'data-name="' + escAttr(name) + '" title="Reset to ' + e.default + '"'
              + (isDefault ? ' disabled' : '') + '>'
              + '\u21BA</button>';

        html += '</div></div>';
      }
    }
    html += '</div>';
  }

  if (!html) {
    html = '<div class="tweak-empty">No matching parameters</div>';
  }

  container.innerHTML = html;
  // Note: renderTweakPanel early-returns while an input is focused (see top), so
  // we never rebuild the DOM under an active edit and never need to restore focus
  // here. Committed values are re-formatted by the focusout handler's re-render.
}

function formatVal(v, type) {
  if (type === "int") return String(Math.round(v));
  if (type === "bool") return v ? "1" : "0";
  // Float: show up to 3 decimal places, trim trailing zeros
  return parseFloat(v.toFixed(3)).toString();
}

function escHtmlTweak(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escAttr(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function applyTweakValue(name, raw) {
  const e = TWEAK_REGISTRY[name];
  if (!e) return;
  let v = parseFloat(raw);
  if (isNaN(v)) return;
  if (e.type === "int") v = Math.round(v);
  if (e.min != null && v < e.min) v = e.min;
  if (e.max != null && v > e.max) v = e.max;
  e.set(v);
  renderTweakPanel();
}

// ---------------------------------------------------------------------------
// Event delegation
// ---------------------------------------------------------------------------

function initTweakPanel() {
  _tweakPanelEl = document.getElementById("tweak-panel");
  if (!_tweakPanelEl) return;

  // Filter input
  const filterInput = _tweakPanelEl.querySelector(".tweak-filter");
  if (filterInput) {
    filterInput.addEventListener("input", function (e) {
      _tweakFilter = e.target.value;
      renderTweakPanel();
    });
    // Prevent game input while typing in filter
    filterInput.addEventListener("keydown", function (e) { e.stopPropagation(); });
  }

  // Delegated click handling
  _tweakPanelEl.addEventListener("click", function (e) {
    // Group collapse toggle
    const header = e.target.closest(".tweak-group-header");
    if (header) {
      const group = header.dataset.group;
      _tweakCollapsed[group] = !_tweakCollapsed[group];
      renderTweakPanel();
      return;
    }

    // Decrement
    const dec = e.target.closest(".tweak-dec");
    if (dec) {
      const name = dec.dataset.name;
      const entry = TWEAK_REGISTRY[name];
      if (entry) applyTweakValue(name, entry.get() - entry.step);
      return;
    }

    // Increment
    const inc = e.target.closest(".tweak-inc");
    if (inc) {
      const name = inc.dataset.name;
      const entry = TWEAK_REGISTRY[name];
      if (entry) applyTweakValue(name, entry.get() + entry.step);
      return;
    }

    // Reset
    const reset = e.target.closest(".tweak-reset");
    if (reset && !reset.disabled) {
      const name = reset.dataset.name;
      const entry = TWEAK_REGISTRY[name];
      if (entry) applyTweakValue(name, entry.default);
      return;
    }
  });

  // Delegated input handling (number inputs)
  _tweakPanelEl.addEventListener("change", function (e) {
    if (e.target.classList.contains("tweak-input") || e.target.classList.contains("tweak-slider")) {
      applyTweakValue(e.target.dataset.name, e.target.value);
    }
  });

  // Slider live update (input event, not just change)
  _tweakPanelEl.addEventListener("input", function (e) {
    if (e.target.classList.contains("tweak-slider")) {
      const name = e.target.dataset.name;
      applyTweakValue(name, e.target.value);
      // Sync the number input while dragging (full re-render is suppressed)
      const inp = _tweakPanelEl.querySelector('.tweak-input[data-name="' + name + '"]');
      if (inp) {
        const entry = TWEAK_REGISTRY[name];
        inp.value = formatVal(entry.get(), entry.type);
      }
    }
  });

  // Track focus/blur on number inputs to prevent overwriting during edits
  _tweakPanelEl.addEventListener("focusin", function (e) {
    if (e.target.classList.contains("tweak-input")) {
      _tweakFocusedInput = e.target.dataset.name;
      e.target.select();
    }
  });
  _tweakPanelEl.addEventListener("focusout", function (e) {
    if (e.target.classList.contains("tweak-input")) {
      _tweakFocusedInput = null;
      renderTweakPanel();
    }
  });

  // Track slider drag to prevent re-renders mid-drag. Guard both mouse and touch:
  // on touch devices dragging fires `input`, which would rebuild container.innerHTML
  // (destroying the slider under the finger) unless _tweakSliderActive suppresses it.
  const _sliderDragStart = function (e) {
    if (e.target.classList.contains("tweak-slider")) _tweakSliderActive = true;
  };
  const _sliderDragEnd = function () {
    if (_tweakSliderActive) {
      _tweakSliderActive = false;
      renderTweakPanel();
    }
  };
  _tweakPanelEl.addEventListener("mousedown", _sliderDragStart);
  _tweakPanelEl.addEventListener("touchstart", _sliderDragStart);
  document.addEventListener("mouseup", _sliderDragEnd);
  document.addEventListener("touchend", _sliderDragEnd);
  document.addEventListener("touchcancel", _sliderDragEnd);

  // Prevent game input while typing in tweak inputs
  _tweakPanelEl.addEventListener("keydown", function (e) {
    if (e.target.classList.contains("tweak-input") || e.target.classList.contains("tweak-filter")) {
      e.stopPropagation();
    }
  });
}

// Auto-refresh panel every 500ms (picks up server-side changes)
setInterval(function () {
  if (G.debug.tweakMode) renderTweakPanel();
}, 500);

// ---------------------------------------------------------------------------
// game_state.js registrations (loaded before tweak.js, so register here)
// ---------------------------------------------------------------------------

registerTweak("MOVE_SPEED", {
  get: () => MOVE_SPEED, set: v => { MOVE_SPEED = v; },
  group: "Movement", label: "Player Speed (tiles/s)",
  min: 0.5, max: 20, step: 0.5,
});
registerTweak("MOVE_LERP", {
  get: () => MOVE_LERP, set: v => { MOVE_LERP = v; },
  group: "Movement", label: "Move Lerp (fallback)",
  min: 0.01, max: 1, step: 0.05,
});
registerTweak("HALF_WALK_TIME_MS", {
  get: () => HALF_WALK_TIME_MS, set: v => { HALF_WALK_TIME_MS = v; },
  group: "Movement", label: "Walk Anim Duration (ms)",
  type: "int", min: 50, max: 500, step: 25,
});
registerTweak("INTERP_DELAY", {
  get: () => INTERP_DELAY, set: v => { INTERP_DELAY = v; },
  group: "Network", label: "Interp Delay (ms)",
  type: "int", min: 0, max: 200, step: 11,
});
registerTweak("INTERP_BUFFER_SIZE", {
  get: () => INTERP_BUFFER_SIZE, set: v => { INTERP_BUFFER_SIZE = v; },
  group: "Network", label: "Interp Buffer Size",
  type: "int", min: 2, max: 20, step: 1,
});
registerTweak("CORRECTION_RATE", {
  get: () => CORRECTION_RATE, set: v => { CORRECTION_RATE = v; },
  group: "Network", label: "Correction Rate",
  min: 0.01, max: 1, step: 0.05,
});
registerTweak("MONSTER_CORRECTION_RATE", {
  get: () => MONSTER_CORRECTION_RATE, set: v => { MONSTER_CORRECTION_RATE = v; },
  group: "Network", label: "Monster Correction Rate",
  min: 0.01, max: 1, step: 0.05,
});
