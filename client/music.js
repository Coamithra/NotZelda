// ---------------------------------------------------------------------------
// Sound effects — one-shot WAV playback
// ---------------------------------------------------------------------------

const SfxPlayer = (function () {
  let enabled = true;
  let VOLUME = 0.5;
  const cache = {};  // name -> Audio (preloaded)

  const SFX_FILES = {
    sword_slash:    "sfx_sword_slash.wav",
    sword_hit:      "sfx_sword_hit.wav",
    sword_hit_flesh:"sfx_sword_hit_flesh.wav",
    player_hurt:    "sfx_player_hurt.wav",
    monster_death:  "sfx_monster_death.wav",
    boss_roar:      "sfx_boss_roar.wav",
    player_death:   "sfx_player_death.wav",
    revival_success:"sfx_revival_success.wav",
    door_open:      "sfx_door_open.wav",
    door_locked:    "sfx_door_locked.wav",
    footstep_grass: "sfx_footstep_grass.wav",
    footstep_stone: "sfx_footstep_stone.wav",
    water_splash:   "sfx_water_splash.wav",
    portal_enter:   "sfx_portal_enter.wav",
    chest_open:     "sfx_chest_open.wav",
    key_pickup:     "sfx_key_pickup.wav",
    item_pickup:    "sfx_item_pickup.wav",
    npc_chat_open:  "sfx_npc_chat_open.wav",
    stairs_up:      "sfx_stairs_up.wav",
    stairs_down:    "sfx_stairs_down.wav",
  };

  function play(name) {
    if (!enabled) return;
    const url = SFX_FILES[name];
    if (!url) return;
    // Clone from cache for overlapping playback, or create new
    if (cache[name]) {
      const sfx = cache[name].cloneNode();
      sfx.volume = VOLUME;
      sfx.play().catch(function () {});
    } else {
      const sfx = new Audio(url);
      sfx.volume = VOLUME;
      sfx.play().catch(function () {});
      cache[name] = sfx;
    }
  }

  function preload() {
    for (const [name, url] of Object.entries(SFX_FILES)) {
      const a = new Audio();
      a.preload = "auto";
      a.src = url;
      cache[name] = a;
    }
  }

  function toggle() { enabled = !enabled; return enabled; }
  function isEnabled() { return enabled; }

  function getVolume() { return VOLUME; }
  function setVolume(v) { VOLUME = v; }

  return { play, preload, toggle, isEnabled, getVolume, setVolume };
})();

// ---------------------------------------------------------------------------
// Background music — per-room MP3 playback with crossfade
// ---------------------------------------------------------------------------

const MusicPlayer = (function () {
  let playing = false;
  let currentTrack = null;
  const tracks = {};       // url -> Audio element
  const fadeIds = {};      // url -> requestAnimationFrame ID (for cancellation)
  let FADE_MS = 800;
  let VOLUME = 0.4;

  // Map music field values (from server) to track URLs
  const MUSIC_TRACKS = {
    "village":    "music.mp3",
    "tavern":     "music_tavern.mp3",
    "chapel":     "music_chapel.mp3",
    "overworld":  "music_overworld.mp3",
    "cave_marbles": "music_cave_marbles.mp3",
    "castle_ruins": "music_castle_ruins.mp3",
    "dungeon2":   "music_dungeon2.mp3",
    "dungeon4":   "music_dungeon4.mp3",
    "dungeon5":   "music_dungeon5.mp3",
    "dungeon6":   "music_dungeon6.mp3",
    "boss1":      "music_boss1.mp3",
    "boss2":      "music_boss2.mp3",
    "boss3":      "music_boss3.mp3",
    "watertemple1": "music_watertemple1.mp3",
    "watertemple2": "music_watertemple2.mp3",
    "watertemple3": "music_watertemple3.mp3",
    "watertemple_boss1": "music_watertemple_boss1.mp3",
    "watertemple_boss2": "music_watertemple_boss2.mp3",
    "desert_a":  "music_desert_a.mp3",
    "desert_b":  "music_desert_b.mp3",
    "desert_c":  "music_desert_c.mp3",
    "desert_boss1": "music_desert_boss1.mp3",
    "desert_boss2": "music_desert_boss2.mp3",
  };

  // Fallback: map biome names to music tracks (for rooms without explicit music field)
  const BIOME_MUSIC = {
    "forest":     "music_overworld.mp3",
    "mountain":   "music_overworld.mp3",
    "cave":       "music_cave_marbles.mp3",
    "graveyard":  "music_overworld.mp3",
    "castle":     "music_castle_ruins.mp3",
    "desert":     "music_overworld.mp3",
    "swamp":      "music_overworld.mp3",
    "plains":     "music_overworld.mp3",
    "lake":       "music_overworld.mp3",
    "river":      "music_overworld.mp3",
    "town":       "music.mp3",
    "dungeon":    "music_dungeon2.mp3",
  };

  let currentBiome = null;
  let silencedBiome = null;  // biome in which silence() was called — stays silent until biome changes

  // --- Boss choir overlay ---
  const CHOIR_DEFAULT_URL = "music_boss1_choir.mp3";
  let CHOIR_MAX_VOL = 0.70;
  let CHOIR_MIN_VOL = 0.10;
  let choirAudio = null;
  let choirFadeId = null;
  let choirActive = false;
  let choirDistance = 1;
  let choirUrl = CHOIR_DEFAULT_URL;

  function getOrCreateAudio(url) {
    if (!tracks[url]) {
      const a = new Audio(url);
      a.loop = true;
      a.volume = 0;
      tracks[url] = a;
    }
    return tracks[url];
  }

  // Cancel any in-progress fade on a given track URL
  function cancelFade(url) {
    if (fadeIds[url] != null) {
      cancelAnimationFrame(fadeIds[url]);
      fadeIds[url] = null;
    }
  }

  function fadeIn(url, duration) {
    cancelFade(url);
    const audio = getOrCreateAudio(url);
    audio.volume = 0;
    const playPromise = audio.play();
    if (playPromise) {
      playPromise.catch(function () {
        // Browser blocked autoplay — ignore silently
      });
    }
    const start = performance.now();
    function step(now) {
      const t = Math.max(0, Math.min(1, (now - start) / duration));
      audio.volume = t * VOLUME;
      if (t < 1) {
        fadeIds[url] = requestAnimationFrame(step);
      } else {
        fadeIds[url] = null;
      }
    }
    fadeIds[url] = requestAnimationFrame(step);
  }

  function fadeOut(url, duration) {
    cancelFade(url);
    const audio = tracks[url];
    if (!audio) return;
    const startVol = audio.volume;
    if (startVol <= 0) {
      audio.pause();
      return;
    }
    const start = performance.now();
    function step(now) {
      const t = Math.max(0, Math.min(1, (now - start) / duration));
      audio.volume = startVol * (1 - t);
      if (t < 1) {
        fadeIds[url] = requestAnimationFrame(step);
      } else {
        audio.pause();
        fadeIds[url] = null;
      }
    }
    fadeIds[url] = requestAnimationFrame(step);
  }

  function setRoom(roomId, biome, music) {
    // Use explicit music field first, then biome fallback, then overworld default
    let url;
    if (music && MUSIC_TRACKS[music]) {
      url = MUSIC_TRACKS[music];
    } else if (biome && BIOME_MUSIC[biome]) {
      url = BIOME_MUSIC[biome];
    } else {
      url = "music_overworld.mp3";
    }
    const newBiome = biome || null;
    // Clear silence when leaving the biome where silence was triggered
    if (silencedBiome && newBiome !== silencedBiome) {
      silencedBiome = null;
    }
    currentBiome = newBiome;
    // Stay silent while in the silenced biome
    if (silencedBiome) return;
    if (url === currentTrack) return;

    if (!playing) {
      currentTrack = url;
      return;
    }

    // Fade out old track
    if (currentTrack) {
      fadeOut(currentTrack, FADE_MS);
    }

    // Fade in new track
    currentTrack = url;
    const audio = getOrCreateAudio(url);
    if (audio.readyState >= 2) {
      // Buffered enough to start — play immediately
      fadeIn(url, FADE_MS);
    } else {
      // Wait for the file to buffer, then fade in
      audio.addEventListener("canplaythrough", function () {
        if (currentTrack === url && playing) {
          fadeIn(url, FADE_MS);
        }
      }, { once: true });
      // Guard against race: if it loaded between check and listener
      if (audio.readyState >= 2 && currentTrack === url && playing) {
        fadeIn(url, FADE_MS);
      }
    }
  }

  function start() {
    if (playing) return;
    playing = true;
    if (currentTrack) {
      fadeIn(currentTrack, FADE_MS);
    }
    // Resume choir if it was active
    if (choirActive && choirAudio) {
      var vol = choirVolumeForDistance(choirDistance);
      var p = choirAudio.play();
      if (p) p.catch(function () {});
      _fadeChoir(vol, FADE_MS);
    }
  }

  function stop() {
    if (!playing) return;
    playing = false;
    for (const url of Object.keys(tracks)) {
      fadeOut(url, FADE_MS);
    }
    // Pause choir audio (but keep choirActive so it resumes with start())
    if (choirAudio && !choirAudio.paused) {
      _fadeChoir(0, FADE_MS, function () { choirAudio.pause(); });
    }
  }

  function toggle() {
    if (playing) stop(); else start();
    return playing;
  }

  function isPlaying() {
    return playing;
  }

  function silence() {
    // Fade out and stay silent until the player leaves the current biome
    if (!playing) return;
    if (currentTrack) {
      fadeOut(currentTrack, FADE_MS);
    }
    currentTrack = null;
    silencedBiome = currentBiome;
  }

  // --- Choir overlay methods ---

  function choirVolumeForDistance(dist) {
    if (dist <= 1) return CHOIR_MAX_VOL;
    return Math.max(CHOIR_MIN_VOL, CHOIR_MAX_VOL / dist);
  }

  function _fadeChoir(targetVol, duration, onDone) {
    if (choirFadeId != null) {
      cancelAnimationFrame(choirFadeId);
      choirFadeId = null;
    }
    if (!choirAudio) { if (onDone) onDone(); return; }
    var startVol = choirAudio.volume;
    var startTime = performance.now();
    function step(now) {
      var t = Math.max(0, Math.min(1, (now - startTime) / duration));
      choirAudio.volume = startVol + (targetVol - startVol) * t;
      if (t < 1) {
        choirFadeId = requestAnimationFrame(step);
      } else {
        choirFadeId = null;
        if (onDone) onDone();
      }
    }
    choirFadeId = requestAnimationFrame(step);
  }

  function startChoir(distance, track) {
    choirActive = true;
    choirDistance = distance;
    var url = track || CHOIR_DEFAULT_URL;
    // If choir track changed, recreate the audio element
    if (url !== choirUrl && choirAudio) {
      choirAudio.pause();
      choirAudio = null;
    }
    choirUrl = url;
    if (!playing) return;
    if (!choirAudio) {
      choirAudio = new Audio(choirUrl);
      choirAudio.loop = true;
      choirAudio.volume = 0;
    }
    var vol = choirVolumeForDistance(distance);
    if (choirAudio.paused) {
      var p = choirAudio.play();
      if (p) p.catch(function () {});
    }
    _fadeChoir(vol, FADE_MS);
  }

  function stopChoir() {
    choirActive = false;
    if (!choirAudio) return;
    _fadeChoir(0, FADE_MS, function () { choirAudio.pause(); });
  }

  // Tweak accessors
  function getVolume() { return VOLUME; }
  function setVolume(v) { VOLUME = v; }
  function getFadeMs() { return FADE_MS; }
  function setFadeMs(v) { FADE_MS = v; }
  function getChoirMaxVol() { return CHOIR_MAX_VOL; }
  function setChoirMaxVol(v) { CHOIR_MAX_VOL = v; }
  function getChoirMinVol() { return CHOIR_MIN_VOL; }
  function setChoirMinVol(v) { CHOIR_MIN_VOL = v; }

  return {
    start, stop, toggle, isPlaying, setRoom, silence, startChoir, stopChoir,
    getVolume, setVolume, getFadeMs, setFadeMs,
    getChoirMaxVol, setChoirMaxVol, getChoirMinVol, setChoirMinVol,
  };
})();

// ---------------------------------------------------------------------------
// Tweak registrations
// ---------------------------------------------------------------------------

registerTweak("SFX_VOLUME", {
  get: () => SfxPlayer.getVolume(), set: v => SfxPlayer.setVolume(v),
  group: "Audio", label: "SFX Volume",
  min: 0, max: 1, step: 0.05,
});
registerTweak("MUSIC_VOLUME", {
  get: () => MusicPlayer.getVolume(), set: v => MusicPlayer.setVolume(v),
  group: "Audio", label: "Music Volume",
  min: 0, max: 1, step: 0.05,
});
registerTweak("MUSIC_FADE_MS", {
  get: () => MusicPlayer.getFadeMs(), set: v => MusicPlayer.setFadeMs(v),
  group: "Audio", label: "Music Crossfade (ms)",
  type: "int", min: 100, max: 3000, step: 100,
});
registerTweak("CHOIR_MAX_VOL", {
  get: () => MusicPlayer.getChoirMaxVol(), set: v => MusicPlayer.setChoirMaxVol(v),
  group: "Audio", label: "Choir Max Volume",
  min: 0, max: 1, step: 0.05,
});
registerTweak("CHOIR_MIN_VOL", {
  get: () => MusicPlayer.getChoirMinVol(), set: v => MusicPlayer.setChoirMinVol(v),
  group: "Audio", label: "Choir Min Volume",
  min: 0, max: 1, step: 0.05,
});
