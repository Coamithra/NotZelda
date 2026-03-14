// ---------------------------------------------------------------------------
// Background music — per-room MP3 playback with crossfade
// ---------------------------------------------------------------------------

const MusicPlayer = (function () {
  let playing = false;
  let currentTrack = null;
  const tracks = {};       // url -> Audio element
  const fadeIds = {};      // url -> requestAnimationFrame ID (for cancellation)
  const FADE_MS = 800;
  const VOLUME = 0.4;

  // Map music field values (from server) to track URLs
  const MUSIC_TRACKS = {
    "village":    "music.mp3",
    "tavern":     "music_tavern.mp3",
    "chapel":     "music_chapel.mp3",
    "overworld":  "music_overworld.mp3",
    "dungeon1":   "music_dungeon1.mp3",
    "dungeon2":   "music_dungeon2.mp3",
    "dungeon3":   "music_dungeon3.mp3",
    "dungeon4":   "music_dungeon4.mp3",
    "dungeon5":   "music_dungeon5.mp3",
    "dungeon6":   "music_dungeon6.mp3",
    "boss1":      "music_boss1.mp3",
  };

  // Fallback: map biome names to music tracks (for rooms without explicit music field)
  const BIOME_MUSIC = {
    "forest":     "music_overworld.mp3",
    "mountain":   "music_chapel.mp3",
    "cave":       "music_chapel.mp3",
    "graveyard":  "music_chapel.mp3",
    "castle":     "music_tavern.mp3",
    "desert":     "music_overworld.mp3",
    "swamp":      "music_overworld.mp3",
    "plains":     "music_overworld.mp3",
    "lake":       "music_overworld.mp3",
    "river":      "music_overworld.mp3",
    "town":       "music.mp3",
    "dungeon":    "music_dungeon1.mp3",
  };

  let currentBiome = null;
  let silencedBiome = null;  // biome in which silence() was called — stays silent until biome changes

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
      const t = Math.min(1, (now - start) / duration);
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
      const t = Math.min(1, (now - start) / duration);
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
    if (audio.readyState >= 4) {
      // Already buffered enough — play immediately
      fadeIn(url, FADE_MS);
    } else {
      // Wait for the file to buffer, then fade in
      audio.addEventListener("canplaythrough", function () {
        // Only play if this is still the current track
        if (currentTrack === url && playing) {
          fadeIn(url, FADE_MS);
        }
      }, { once: true });
    }
  }

  function start() {
    if (playing) return;
    playing = true;
    if (currentTrack) {
      fadeIn(currentTrack, FADE_MS);
    }
  }

  function stop() {
    if (!playing) return;
    playing = false;
    for (const url of Object.keys(tracks)) {
      fadeOut(url, FADE_MS);
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

  return { start, stop, toggle, isPlaying, setRoom, silence };
})();
