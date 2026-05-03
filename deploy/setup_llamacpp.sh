#!/usr/bin/env bash
# setup_llamacpp.sh — install llama-server (llama.cpp HTTP server) + systemd unit.
#
# Idempotent: re-running is a no-op once everything is in place.
# Designed for Ubuntu 24.04 x86_64 CPU-only hosts (e.g. Hetzner CX22).
# Run as root.
#
# After this script succeeds, set in /opt/NotZelda/.env:
#     AI_BACKEND=llamacpp
#     LLAMACPP_BASE_URL=http://localhost:8081/v1
#     LLAMACPP_MODEL=<basename of GGUF without extension>
# then `systemctl restart notzelda`.

set -euo pipefail

# === Config (override via env) ===
LLAMACPP_VERSION="${LLAMACPP_VERSION:-latest}"             # GitHub release tag (e.g. b9010) or "latest"
LLAMACPP_DIR="${LLAMACPP_DIR:-/opt/llama.cpp}"             # extracted release lives here
MODELS_DIR="${MODELS_DIR:-/opt/NotZelda/models}"           # GGUF files live here
MODEL_FILE="${MODEL_FILE:-gemma-2-2b-it-Q4_K_M.gguf}"
MODEL_URL="${MODEL_URL:-https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf}"
MODEL_MIN_BYTES="${MODEL_MIN_BYTES:-1500000000}"           # ~1.5GB — gemma 2B Q4_K_M is ~1.6GB
LLAMA_PORT="${LLAMA_PORT:-8081}"                           # 8080 is taken by mud_server
LLAMA_CTX_SIZE="${LLAMA_CTX_SIZE:-1024}"
SERVICE_NAME="notzelda-llama"
NOTZELDA_UNIT="${NOTZELDA_UNIT:-notzelda.service}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UNIT_TEMPLATE="$SCRIPT_DIR/${SERVICE_NAME}.service"
UNIT_TARGET="/etc/systemd/system/${SERVICE_NAME}.service"
DROPIN_DIR="/etc/systemd/system/${NOTZELDA_UNIT}.d"
DROPIN_FILE="$DROPIN_DIR/llama.conf"

log()  { printf '\033[1;36m[setup_llamacpp]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[setup_llamacpp WARN]\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31m[setup_llamacpp ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || fail "Run as root."
[ -f "$UNIT_TEMPLATE" ] || fail "Missing unit template: $UNIT_TEMPLATE"

# Single tmpdir for the whole script — auto-cleanup on any exit.
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# === 1. Free RAM during the transition. ===
# Ollama (~1.5GB resident) + llama-server starting (~1.7GB peak load) on a 4GB
# CX22 + the running game can OOM. We stop Ollama for the duration of this run;
# permanent removal is `uninstall_ollama.sh` (manual, after verification).
if systemctl is-active --quiet ollama.service 2>/dev/null; then
  log "Stopping ollama.service to free RAM during install (uninstall_ollama.sh removes it permanently)..."
  systemctl stop ollama.service || true
fi

# === 2. Deps ===
need_install=()
command -v curl >/dev/null 2>&1 || need_install+=(curl)
command -v tar  >/dev/null 2>&1 || need_install+=(tar)
dpkg -s ca-certificates >/dev/null 2>&1 || need_install+=(ca-certificates)
if [ "${#need_install[@]}" -gt 0 ]; then
  log "apt-get install ${need_install[*]}"
  DEBIAN_FRONTEND=noninteractive apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${need_install[@]}" >/dev/null
fi

# === 3. llama.cpp release tarball ===
api_url="https://api.github.com/repos/ggml-org/llama.cpp/releases"
if [ "$LLAMACPP_VERSION" = "latest" ]; then
  api_url="$api_url/latest"
else
  api_url="$api_url/tags/$LLAMACPP_VERSION"
fi

# Pick the plain CPU Ubuntu x86_64 build — exclude CUDA/Vulkan/ROCm/SYCL/OpenVINO variants.
release_json=$(curl -fsSL "$api_url" 2>/dev/null || true)
if [ -z "$release_json" ]; then
  if [ -x /usr/local/bin/llama-server ] && [ -f "$LLAMACPP_DIR/INSTALLED_VERSION" ]; then
    warn "GitHub API unreachable (rate limit?). Keeping installed $(cat "$LLAMACPP_DIR/INSTALLED_VERSION")."
    tag=""
    asset_url=""
  else
    fail "Could not query GitHub API ($api_url) and no existing install to fall back on."
  fi
else
  # Single-process awk parsing so an early `exit` doesn't SIGPIPE upstream
  # producers (which `set -o pipefail` would surface as exit 141).
  tag=$(printf '%s' "$release_json" | awk -F'"' '/"tag_name"/ {print $4; exit}')
  asset_url=$(printf '%s' "$release_json" \
    | awk -F'"' '/"browser_download_url"/ && /bin-ubuntu-x64\.tar\.gz/ {print $4; exit}')
  [ -n "$tag" ]       || fail "Could not parse release tag from GitHub API"
  [ -n "$asset_url" ] || fail "Could not find ubuntu-x64 CPU asset in release $tag"
fi

stamp_file="$LLAMACPP_DIR/INSTALLED_VERSION"
if [ -n "$tag" ] && [ -x /usr/local/bin/llama-server ] && [ -f "$stamp_file" ] \
    && [ "$(cat "$stamp_file")" = "$tag" ]; then
  log "llama-server $tag already installed. Skipping download."
elif [ -n "$tag" ]; then
  log "Downloading llama.cpp $tag from $asset_url"
  curl -fL -C - --retry 3 -o "$tmp/llama.tgz" "$asset_url"
  rm -rf "$LLAMACPP_DIR"
  mkdir -p "$LLAMACPP_DIR"
  tar -xzf "$tmp/llama.tgz" -C "$LLAMACPP_DIR"
  bin_path=$(find "$LLAMACPP_DIR" -type f -name llama-server | head -1)
  [ -n "$bin_path" ] || fail "llama-server binary not found inside $asset_url"
  chmod +x "$bin_path"
  ln -sf "$bin_path" /usr/local/bin/llama-server
  # Smoke test: catches a bad tarball layout (missing .so deps) before systemd does.
  /usr/local/bin/llama-server --version >/dev/null 2>&1 \
    || fail "Installed llama-server fails to run. Check tarball layout under $LLAMACPP_DIR."
  printf '%s\n' "$tag" > "$stamp_file"
  log "Installed llama-server $tag -> /usr/local/bin/llama-server"
fi

# === 4. KV-cache slot directory (for --slot-save-path persistence) ===
mkdir -p /var/lib/llama-cache

# === 5. GGUF model ===
mkdir -p "$MODELS_DIR"
target_model="$MODELS_DIR/$MODEL_FILE"
if [ -f "$target_model" ] && [ "$(stat -c%s "$target_model")" -ge "$MODEL_MIN_BYTES" ]; then
  log "Model already present: $target_model ($(du -h "$target_model" | cut -f1))"
else
  log "Downloading $MODEL_FILE..."
  curl -fL -C - --retry 3 -o "$target_model.part" "$MODEL_URL"
  actual_size=$(stat -c%s "$target_model.part")
  if [ "$actual_size" -lt "$MODEL_MIN_BYTES" ]; then
    rm -f "$target_model.part"
    fail "Downloaded model is too small ($actual_size bytes < $MODEL_MIN_BYTES). Bad URL?"
  fi
  mv "$target_model.part" "$target_model"
  log "Downloaded -> $target_model"
fi

# === 6. systemd unit (only restart if changed) ===
sed -e "s|@MODEL_PATH@|$target_model|g" \
    -e "s|@PORT@|$LLAMA_PORT|g" \
    -e "s|@CTX_SIZE@|$LLAMA_CTX_SIZE|g" \
    "$UNIT_TEMPLATE" > "$tmp/${SERVICE_NAME}.service"

unit_changed=1
if cmp -s "$tmp/${SERVICE_NAME}.service" "$UNIT_TARGET"; then
  unit_changed=0
fi

if [ "$unit_changed" -eq 1 ]; then
  log "Writing $UNIT_TARGET"
  cp "$tmp/${SERVICE_NAME}.service" "$UNIT_TARGET"
  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME" >/dev/null
fi

# === 7. Drop-in: order notzelda after llama so reboots come up cleanly. ===
# `Before=` in the llama unit only orders units started in the same transaction;
# on boot, `multi-user.target` pulls both via `WantedBy=` and they race. The
# drop-in tells systemd to wait for llama-server before starting the game.
mkdir -p "$DROPIN_DIR"
cat > "$tmp/llama.conf" <<EOF
[Unit]
Wants=${SERVICE_NAME}.service
After=${SERVICE_NAME}.service
EOF
if ! cmp -s "$tmp/llama.conf" "$DROPIN_FILE"; then
  log "Writing $DROPIN_FILE (orders $NOTZELDA_UNIT after $SERVICE_NAME)"
  cp "$tmp/llama.conf" "$DROPIN_FILE"
  systemctl daemon-reload
fi

# Restart only when the unit actually changed, or when not running. Routine
# deploys with no infra change leave in-flight NPC chats alone.
if [ "$unit_changed" -eq 1 ] || ! systemctl is-active --quiet "$SERVICE_NAME"; then
  log "Restarting $SERVICE_NAME"
  systemctl restart "$SERVICE_NAME"
else
  log "$SERVICE_NAME unchanged and running — leaving it alone."
fi

# === 8. Wait for ready ===
log "Waiting for llama-server on :$LLAMA_PORT..."
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$LLAMA_PORT/health" >/dev/null 2>&1 \
      || curl -fsS "http://127.0.0.1:$LLAMA_PORT/v1/models" >/dev/null 2>&1; then
    log "llama-server is ready on http://127.0.0.1:$LLAMA_PORT"
    break
  fi
  sleep 1
  if [ "$i" -eq 60 ]; then
    fail "Timed out waiting for llama-server. Check: journalctl -u $SERVICE_NAME -n 50 --no-pager"
  fi
done

# === 9. Hint ===
model_id="${MODEL_FILE%.gguf}"
cat <<EOF

==============================================================================
llama-server is up. Next:

  1. Edit /opt/NotZelda/.env so the game talks to it:

       AI_BACKEND=llamacpp
       LLAMACPP_BASE_URL=http://localhost:$LLAMA_PORT/v1
       LLAMACPP_MODEL=$model_id

  2. Pull llmfacade into the venv (if requirements.txt changed):

       /opt/NotZelda/venv/bin/pip install -r /opt/NotZelda/requirements.txt

  3. Restart the game:

       systemctl restart notzelda
       journalctl -u notzelda -n 30 --no-pager

  4. Walk up to an NPC in-game and chat to verify.

  5. Once verified, retire Ollama:

       bash $SCRIPT_DIR/uninstall_ollama.sh
==============================================================================
EOF
