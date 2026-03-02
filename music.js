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

  // Map room IDs to music tracks
  const ROOM_MUSIC = {
    "town_square":      "music.mp3",
    "tavern":           "music_tavern.mp3",
    "tavern_upstairs":  "music_tavern.mp3",
    "blacksmith":       "music.mp3",
    "old_chapel":       "music.mp3",
    "forest_path":      "music_forest.mp3",
    "clearing":         "music_forest.mp3",
  };

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

  function setRoom(roomId) {
    const url = ROOM_MUSIC[roomId] || "music.mp3";
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

  return { start, stop, toggle, isPlaying, setRoom };
})();
