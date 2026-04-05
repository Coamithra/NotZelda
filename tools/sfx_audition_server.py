"""Local web server for auditioning SFX variants and selecting favorites.

Opens a browser interface to listen to all generated variants side-by-side,
select your preferred version for each sound, and save the selection.

Usage:
    python tools/sfx_audition_server.py               # start on port 8090
    python tools/sfx_audition_server.py --port 9000    # custom port
"""

import json
import webbrowser
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "data" / "sfx_manifest.json"
SELECTION_PATH = ROOT / "data" / "sfx_selection.json"
VARIANTS_DIR = ROOT / "audio" / "sfx" / "_variants"

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>SFX Audition — Legends of Amara</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: #0f0f1a;
    color: #e0e0e0;
    line-height: 1.5;
    padding: 0 0 100px;
  }
  header {
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
    padding: 24px 32px;
    border-bottom: 2px solid #0f3460;
    position: sticky; top: 0; z-index: 100;
  }
  header h1 { font-size: 22px; color: #e94560; margin-bottom: 4px; }
  header .subtitle { font-size: 13px; color: #888; }
  .progress-bar {
    margin-top: 12px; height: 6px; background: #1a1a2e;
    border-radius: 3px; overflow: hidden;
  }
  .progress-fill {
    height: 100%; background: linear-gradient(90deg, #e94560, #0f3460);
    transition: width 0.3s ease; width: 0%;
  }
  .progress-text { font-size: 12px; color: #aaa; margin-top: 4px; }
  .category {
    margin: 24px 16px 0;
  }
  .category-header {
    font-size: 14px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 2px; padding: 8px 16px; border-radius: 6px 6px 0 0;
    margin-bottom: 0;
  }
  .cat-combat .category-header     { background: #3d1425; color: #e94560; }
  .cat-environment .category-header { background: #142e1a; color: #4ade80; }
  .cat-items .category-header       { background: #2e2a14; color: #facc15; }
  .cat-ui .category-header          { background: #14202e; color: #60a5fa; }
  .sfx-card {
    background: #16172a; border: 1px solid #252545;
    border-radius: 0 0 8px 8px; margin-bottom: 12px; overflow: hidden;
  }
  .sfx-card + .sfx-card { border-radius: 8px; }
  .sfx-header {
    display: flex; align-items: baseline; gap: 12px;
    padding: 12px 16px 4px; flex-wrap: wrap;
  }
  .sfx-name { font-size: 16px; font-weight: 700; color: #fff; }
  .sfx-prompt { font-size: 12px; color: #777; font-style: italic; }
  .sfx-duration { font-size: 12px; color: #555; }
  .variants { padding: 4px 8px 12px; }
  .variant-row {
    display: flex; align-items: center; gap: 10px;
    padding: 6px 8px; border-radius: 6px; cursor: pointer;
    transition: background 0.15s;
  }
  .variant-row:hover { background: #1e1f35; }
  .variant-row.selected { background: #1a2540; outline: 1px solid #0f3460; }
  .variant-row input[type="radio"] { accent-color: #e94560; cursor: pointer; }
  .variant-label {
    font-size: 13px; font-weight: 600; color: #aaa;
    min-width: 28px; text-align: center;
  }
  .variant-row.selected .variant-label { color: #e94560; }
  .variant-row audio {
    flex: 1; height: 32px; max-width: 500px;
  }
  /* Compact play button for quick comparison */
  .play-btn {
    width: 32px; height: 32px; border-radius: 50%;
    border: 1px solid #444; background: #222; color: #ccc;
    font-size: 14px; cursor: pointer; display: flex;
    align-items: center; justify-content: center;
    transition: all 0.15s; flex-shrink: 0;
  }
  .play-btn:hover { background: #333; border-color: #e94560; color: #e94560; }
  .play-btn.playing { background: #e94560; border-color: #e94560; color: #fff; }
  .footer {
    position: fixed; bottom: 0; left: 0; right: 0;
    background: #16213e; border-top: 2px solid #0f3460;
    padding: 12px 32px; display: flex; align-items: center; gap: 16px;
    z-index: 100;
  }
  .save-btn {
    padding: 10px 28px; background: #e94560; color: #fff;
    border: none; border-radius: 6px; font-size: 14px;
    font-weight: 700; cursor: pointer; transition: all 0.15s;
  }
  .save-btn:hover { background: #c23152; }
  .save-btn:disabled { background: #555; cursor: not-allowed; }
  .save-status { font-size: 13px; color: #4ade80; }
  .preview-btn {
    padding: 8px 20px; background: transparent; color: #60a5fa;
    border: 1px solid #60a5fa; border-radius: 6px; font-size: 13px;
    cursor: pointer; margin-left: auto;
  }
  .preview-btn:hover { background: #1a2540; }
  .keyboard-hint {
    font-size: 11px; color: #555; margin-left: 8px;
  }
  .missing-variants {
    padding: 12px 16px; color: #e94560; font-size: 13px;
    font-style: italic;
  }
</style>
</head>
<body>

<header>
  <h1>SFX Audition — Legends of Amara</h1>
  <div class="subtitle">Listen to variants, pick your favorites, save selection</div>
  <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
  <div class="progress-text" id="progressText">Loading...</div>
</header>

<div id="content"></div>

<div class="footer">
  <button class="save-btn" id="saveBtn" onclick="saveSelection()">Save Selection</button>
  <span class="save-status" id="saveStatus"></span>
  <span class="keyboard-hint">Space = play/pause &middot; 1-9 = select variant &middot; &uarr;&darr; = navigate sounds</span>
  <button class="preview-btn" onclick="previewAll()">Preview All Selected</button>
</div>

<script>
let manifest = {};
let available = {};
let mtimes = {};
let selection = {};
let currentAudio = null;
let focusedSfx = null;
const allAudios = [];

async function init() {
  const resp = await fetch('/api/manifest');
  const data = await resp.json();
  manifest = data.manifest;
  available = data.available;
  mtimes = data.mtimes || {};

  // Load existing selection
  try {
    const selResp = await fetch('/api/selection');
    if (selResp.ok) selection = await selResp.json();
  } catch(e) {}

  render();
  updateProgress();

  // Focus first sound
  const names = Object.keys(manifest);
  if (names.length) focusedSfx = names[0];
}

function render() {
  const content = document.getElementById('content');
  const categories = {};

  for (const [name, entry] of Object.entries(manifest)) {
    const cat = entry.category || 'misc';
    if (!categories[cat]) categories[cat] = [];
    categories[cat].push({ name, ...entry });
  }

  const catOrder = ['combat', 'environment', 'items', 'ui', 'misc'];
  let html = '';

  for (const cat of catOrder) {
    if (!categories[cat]) continue;
    html += `<div class="category cat-${cat}">`;
    html += `<div class="category-header">${cat} (${categories[cat].length})</div>`;

    for (const sfx of categories[cat]) {
      const variants = available[sfx.name] || [];
      const selected = selection[sfx.name];

      html += `<div class="sfx-card" data-sfx="${sfx.name}" id="card-${sfx.name}">`;
      html += `<div class="sfx-header">`;
      html += `<span class="sfx-name">${sfx.name}</span>`;
      html += `<span class="sfx-prompt">"${sfx.prompt}"</span>`;
      html += `<span class="sfx-duration">${sfx.duration}s</span>`;
      html += `</div>`;

      if (variants.length === 0) {
        html += `<div class="missing-variants">No variants generated yet. Run: python tools/generate_sfx_variants.py --only ${sfx.name}</div>`;
      } else {
        html += `<div class="variants">`;
        for (const v of variants) {
          const isSelected = selected === v;
          html += `<div class="variant-row${isSelected ? ' selected' : ''}"
                        data-sfx="${sfx.name}" data-variant="${v}"
                        onclick="selectVariant('${sfx.name}', ${v})">`;
          html += `<input type="radio" name="${sfx.name}" value="${v}"${isSelected ? ' checked' : ''}>`;
          html += `<span class="variant-label">V${v}</span>`;
          html += `<button class="play-btn" onclick="event.stopPropagation(); togglePlay('${sfx.name}', ${v}, this)">&#9654;</button>`;
          const mt = mtimes[sfx.name + '_v' + v] || Date.now();
          html += `<audio preload="none" src="/variants/${sfx.name}_v${v}.wav?t=${mt}"
                          data-sfx="${sfx.name}" data-variant="${v}"></audio>`;
          html += `</div>`;
        }
        html += `</div>`;
      }
      html += `</div>`;
    }
    html += `</div>`;
  }

  content.innerHTML = html;

  // Collect all audio elements
  allAudios.length = 0;
  document.querySelectorAll('audio').forEach(a => allAudios.push(a));

  // Add ended handlers
  allAudios.forEach(a => {
    a.addEventListener('ended', () => {
      const btn = a.parentElement.querySelector('.play-btn');
      if (btn) btn.classList.remove('playing');
      btn.innerHTML = '&#9654;';
    });
  });
}

function stopAll() {
  allAudios.forEach(a => {
    a.pause();
    a.currentTime = 0;
  });
  document.querySelectorAll('.play-btn.playing').forEach(b => {
    b.classList.remove('playing');
    b.innerHTML = '&#9654;';
  });
  currentAudio = null;
}

function togglePlay(name, variant, btn) {
  const audio = btn.parentElement.querySelector('audio');
  if (currentAudio === audio && !audio.paused) {
    audio.pause();
    audio.currentTime = 0;
    btn.classList.remove('playing');
    btn.innerHTML = '&#9654;';
    currentAudio = null;
  } else {
    stopAll();
    audio.play();
    btn.classList.add('playing');
    btn.innerHTML = '&#9646;&#9646;';
    currentAudio = audio;
    focusedSfx = name;
  }
}

function selectVariant(name, variant) {
  selection[name] = variant;

  // Update UI for this card
  const card = document.getElementById('card-' + name);
  card.querySelectorAll('.variant-row').forEach(row => {
    const v = parseInt(row.dataset.variant);
    const radio = row.querySelector('input[type="radio"]');
    if (v === variant) {
      row.classList.add('selected');
      radio.checked = true;
    } else {
      row.classList.remove('selected');
      radio.checked = false;
    }
  });

  focusedSfx = name;
  updateProgress();
}

function updateProgress() {
  const total = Object.keys(manifest).length;
  const done = Object.keys(selection).length;
  const pct = total > 0 ? (done / total * 100) : 0;

  document.getElementById('progressFill').style.width = pct + '%';
  document.getElementById('progressText').textContent =
    `${done} / ${total} selected` + (done === total ? ' — All done! Save your selection.' : '');
  document.getElementById('saveBtn').disabled = done === 0;
}

async function saveSelection() {
  const btn = document.getElementById('saveBtn');
  const status = document.getElementById('saveStatus');
  btn.disabled = true;
  btn.textContent = 'Saving...';

  try {
    const resp = await fetch('/api/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(selection)
    });
    const result = await resp.json();
    if (result.ok) {
      status.style.color = '#4ade80';
      status.textContent = `Saved ${Object.keys(selection).length} selections to ${result.path}`;
    } else {
      status.style.color = '#e94560';
      status.textContent = 'Error: ' + result.error;
    }
  } catch(e) {
    status.style.color = '#e94560';
    status.textContent = 'Network error: ' + e.message;
  }

  btn.disabled = false;
  btn.textContent = 'Save Selection';
}

async function previewAll() {
  stopAll();
  const names = Object.keys(selection);
  for (let i = 0; i < names.length; i++) {
    const name = names[i];
    const v = selection[name];
    const audio = document.querySelector(`audio[data-sfx="${name}"][data-variant="${v}"]`);
    if (!audio) continue;

    // Scroll card into view
    const card = document.getElementById('card-' + name);
    card.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Play and wait for it to finish
    const btn = audio.parentElement.querySelector('.play-btn');
    audio.play();
    if (btn) { btn.classList.add('playing'); btn.innerHTML = '&#9646;&#9646;'; }
    currentAudio = audio;

    await new Promise(resolve => {
      audio.onended = () => {
        if (btn) { btn.classList.remove('playing'); btn.innerHTML = '&#9654;'; }
        resolve();
      };
    });

    // Small gap between sounds
    await new Promise(r => setTimeout(r, 300));
  }
  currentAudio = null;
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if (!focusedSfx) return;
  const card = document.getElementById('card-' + focusedSfx);
  if (!card) return;

  // 1-9: select variant
  const num = parseInt(e.key);
  if (num >= 1 && num <= 9) {
    e.preventDefault();
    const variants = available[focusedSfx] || [];
    if (variants.includes(num)) {
      selectVariant(focusedSfx, num);
      // Also play it
      const btn = card.querySelector(`.variant-row[data-variant="${num}"] .play-btn`);
      if (btn) togglePlay(focusedSfx, num, btn);
    }
    return;
  }

  // Space: play/pause current
  if (e.key === ' ' && e.target.tagName !== 'BUTTON') {
    e.preventDefault();
    if (currentAudio && !currentAudio.paused) {
      stopAll();
    } else if (selection[focusedSfx]) {
      const v = selection[focusedSfx];
      const btn = card.querySelector(`.variant-row[data-variant="${v}"] .play-btn`);
      if (btn) togglePlay(focusedSfx, v, btn);
    }
    return;
  }

  // Up/Down: navigate between sounds
  const names = Object.keys(manifest);
  const idx = names.indexOf(focusedSfx);
  if (e.key === 'ArrowDown' && idx < names.length - 1) {
    e.preventDefault();
    stopAll();
    focusedSfx = names[idx + 1];
    document.getElementById('card-' + focusedSfx)
      .scrollIntoView({ behavior: 'smooth', block: 'center' });
  } else if (e.key === 'ArrowUp' && idx > 0) {
    e.preventDefault();
    stopAll();
    focusedSfx = names[idx - 1];
    document.getElementById('card-' + focusedSfx)
      .scrollIntoView({ behavior: 'smooth', block: 'center' });
  }
});

init();
</script>
</body>
</html>"""


class AuditionHandler(SimpleHTTPRequestHandler):
    """HTTP handler for the audition interface."""

    def log_message(self, format, *args):
        # Quieter logging
        if '/variants/' not in str(args[0]):
            super().log_message(format, *args)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/' or path == '':
            self._serve_html()
        elif path == '/api/manifest':
            self._serve_manifest()
        elif path == '/api/selection':
            self._serve_selection()
        elif path.startswith('/variants/'):
            self._serve_variant(path)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/api/save':
            self._save_selection()
        else:
            self.send_error(404)

    def _serve_html(self):
        data = HTML_PAGE.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_manifest(self):
        with open(MANIFEST_PATH) as f:
            raw = json.load(f)
        manifest = {k: v for k, v in raw.items() if not k.startswith("_")}

        # Scan which variants exist, include mtime for cache busting
        available = {}
        mtimes = {}
        for name in manifest:
            variants = []
            for v in range(1, 100):
                p = VARIANTS_DIR / f"{name}_v{v}.wav"
                if p.exists():
                    variants.append(v)
                    mtimes[f"{name}_v{v}"] = int(p.stat().st_mtime)
            if variants:
                available[name] = variants

        self._json_response({'manifest': manifest, 'available': available, 'mtimes': mtimes})

    def _serve_selection(self):
        if SELECTION_PATH.exists():
            with open(SELECTION_PATH) as f:
                data = json.load(f)
        else:
            data = {}
        self._json_response(data)

    def _serve_variant(self, path):
        filename = path.split('/')[-1].split('?')[0]
        filepath = VARIANTS_DIR / filename
        if not filepath.exists() or not filepath.suffix == '.wav':
            self.send_error(404)
            return
        data = filepath.read_bytes()
        self.send_response(200)
        self.send_header('Content-Type', 'audio/wav')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.end_headers()
        self.wfile.write(data)

    def _save_selection(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
            SELECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(SELECTION_PATH, 'w') as f:
                json.dump(data, f, indent=2)
            rel = SELECTION_PATH.relative_to(ROOT)
            self._json_response({'ok': True, 'path': str(rel)})
        except Exception as e:
            self._json_response({'ok': False, 'error': str(e)})

    def _json_response(self, data):
        body = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="SFX audition server")
    parser.add_argument('--port', type=int, default=8090, help='Port (default: 8090)')
    args = parser.parse_args()

    # Check for variants
    if not VARIANTS_DIR.exists():
        print(f"Warning: {VARIANTS_DIR.relative_to(ROOT)}/ doesn't exist yet.")
        print("Run: python tools/generate_sfx_variants.py\n")

    variant_count = len(list(VARIANTS_DIR.glob("*.wav"))) if VARIANTS_DIR.exists() else 0
    with open(MANIFEST_PATH) as f:
        manifest_count = sum(1 for k in json.load(f) if not k.startswith("_"))

    print(f"SFX Audition Server")
    print(f"  Manifest: {manifest_count} sounds")
    print(f"  Variants: {variant_count} WAV files in _variants/")
    print(f"  Server:   http://localhost:{args.port}\n")

    server = HTTPServer(('127.0.0.1', args.port), AuditionHandler)

    webbrowser.open(f'http://localhost:{args.port}')
    print(f"Opened browser. Press Ctrl+C to stop.\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == '__main__':
    main()
