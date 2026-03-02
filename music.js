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
  let pendingPlay = null;  // audio element awaiting user gesture to unlock

  // Map room IDs to music tracks
  const ROOM_MUSIC = {
    "town_square":      "music.mp3",
    "tavern":           "music.mp3",
    "tavern_upstairs":  "music.mp3",
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

  // If play() was blocked by autoplay, retry on the next user interaction
  function unlockAudio() {
    if (!pendingPlay) return;
    const audio = pendingPlay;
    pendingPlay = null;
    audio.play().catch(function () {});
    document.removeEventListener("click", unlockAudio);
    document.removeEventListener("keydown", unlockAudio);
  }

  function fadeIn(url, duration) {
    cancelFade(url);
    const audio = getOrCreateAudio(url);
    audio.volume = 0;
    const playPromise = audio.play();
    if (playPromise) {
      playPromise.catch(function () {
        // Autoplay blocked — retry on the very next user interaction
        pendingPlay = audio;
        document.addEventListener("click", unlockAudio, { once: true });
        document.addEventListener("keydown", unlockAudio, { once: true });
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
    fadeIn(url, FADE_MS);
  }

  function start() {
    if (playing) return;
    playing = true;
    if (!currentTrack) currentTrack = "music.mp3";
    fadeIn(currentTrack, FADE_MS);
  }

  function stop() {
    if (!playing) return;
    playing = false;
    pendingPlay = null;
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
