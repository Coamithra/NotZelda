/* Service worker for the Legends of Amara OST site (/ost).
 *
 * Scope is "/" (it must be, because the audio + icons live at the root), but it
 * deliberately only ever *handles* a known set of OST assets. Every other
 * request — including the game at "/" and its files — passes straight through
 * untouched, so installing this SW from /ost has zero effect on the game.
 *
 * Two caches:
 *   SHELL_CACHE  — the page shell (HTML, manifest, icons). Versioned; wiped on
 *                  activate when the version bumps so updates roll out.
 *   AUDIO_CACHE  — the MP3 tracks. Stable name, NEVER auto-wiped: it is only
 *                  populated by the "Store locally" button and cleared by the
 *                  "Remove" button, so a deploy never throws away ~100 MB the
 *                  user already downloaded.
 *
 * NOTE: TRACK_URLS below must stay in sync with the TRACKS list in ost.html.
 */
const SHELL_CACHE = "amara-ost-shell-v1";
const AUDIO_CACHE = "amara-ost-audio";

const SHELL_ASSETS = [
  "/ost",
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
  "/apple-touch-icon.png",
];

const TRACK_URLS = [
  "/music.mp3",
  "/music_overworld.mp3",
  "/music_tavern.mp3",
  "/music_chapel.mp3",
  "/music_cave_marbles.mp3",
  "/music_castle_ruins.mp3",
  "/music_menu.mp3",
  "/music_dungeon2.mp3",
  "/music_dungeon4.mp3",
  "/music_dungeon5.mp3",
  "/music_dungeon6.mp3",
  "/music_boss1.mp3",
  "/music_boss2.mp3",
  "/music_boss3.mp3",
  "/music_watertemple1.mp3",
  "/music_watertemple2.mp3",
  "/music_watertemple3.mp3",
  "/music_watertemple_boss1.mp3",
  "/music_watertemple_boss2.mp3",
  "/music_desert_a.mp3",
  "/music_desert_b.mp3",
  "/music_desert_c.mp3",
  "/music_desert_d.mp3",
  "/music_desert_boss1.mp3",
  "/music_desert_boss2.mp3",
];

// Paths this SW is allowed to handle. Anything not in here is left to the
// browser's default networking (i.e. the game is never intercepted).
const MANAGED = new Set([...SHELL_ASSETS, ...TRACK_URLS]);

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE)
      .then((cache) => cache.addAll(SHELL_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names
          // Drop stale shell caches, but never touch the audio cache.
          .filter((n) => n.startsWith("amara-ost-shell-") && n !== SHELL_CACHE)
          .map((n) => caches.delete(n))
      )
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Navigations: only the OST page is ours (network-first so edits show up,
  // cached shell when offline). Any other navigation (e.g. the game) passes
  // through.
  if (req.mode === "navigate") {
    if (url.pathname === "/ost") {
      event.respondWith(networkFirst(req, "/ost"));
    }
    return;
  }

  if (MANAGED.has(url.pathname)) {
    event.respondWith(cacheFirst(req));
  }
  // else: not ours — default browser handling.
});

async function networkFirst(req, fallbackKey) {
  try {
    return await fetch(req);
  } catch (err) {
    const cached = await caches.match(fallbackKey);
    return cached || Response.error();
  }
}

async function cacheFirst(req) {
  const cached = await caches.match(req, { ignoreVary: true });
  if (cached) {
    // Media elements request byte ranges; the Cache API only stores full 200
    // responses, and iOS Safari refuses a 200 when it asked for a range. So
    // synthesize a 206 Partial Content from the cached body when needed.
    if (req.headers.has("range")) {
      return buildRangeResponse(req, cached);
    }
    return cached;
  }
  // Not stored offline yet — go to the network (don't auto-populate; the
  // "Store locally" button owns what lives in the audio cache).
  return fetch(req);
}

async function buildRangeResponse(req, cached) {
  const buf = await cached.arrayBuffer();
  const size = buf.byteLength;
  const match = /bytes=(\d*)-(\d*)/.exec(req.headers.get("range") || "");
  let start = match && match[1] ? parseInt(match[1], 10) : 0;
  let end = match && match[2] ? parseInt(match[2], 10) : size - 1;
  if (isNaN(start)) start = 0;
  if (isNaN(end) || end >= size) end = size - 1;
  if (start > end || start >= size) {
    return new Response(null, {
      status: 416,
      statusText: "Range Not Satisfiable",
      headers: { "Content-Range": `bytes */${size}` },
    });
  }
  const chunk = buf.slice(start, end + 1);
  return new Response(chunk, {
    status: 206,
    statusText: "Partial Content",
    headers: {
      "Content-Type": cached.headers.get("Content-Type") || "audio/mpeg",
      "Content-Range": `bytes ${start}-${end}/${size}`,
      "Content-Length": String(chunk.byteLength),
      "Accept-Ranges": "bytes",
    },
  });
}
