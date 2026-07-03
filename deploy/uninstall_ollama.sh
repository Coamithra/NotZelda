#!/usr/bin/env bash
# uninstall_ollama.sh — stop, disable, and purge Ollama after llama-server takes over.
#
# Run this AFTER setup_llamacpp.sh has been verified end-to-end (NPC chat
# actually working through llama-server). On a 4GB CX22, reclaiming Ollama's
# RAM matters; do not run this preemptively.
#
# Idempotent — safe to re-run.

set -euo pipefail

log()  { printf '\033[1;36m[uninstall_ollama]\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m[uninstall_ollama ERROR]\033[0m %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || fail "Run as root."

if systemctl list-unit-files ollama.service >/dev/null 2>&1; then
  log "Stopping/disabling ollama service..."
  systemctl stop ollama.service || true
  systemctl disable ollama.service 2>/dev/null || true
fi

if [ -f /etc/systemd/system/ollama.service ]; then
  rm -f /etc/systemd/system/ollama.service
  systemctl daemon-reload
fi

if command -v ollama >/dev/null 2>&1; then
  log "Removing /usr/local/bin/ollama and /usr/local/lib/ollama..."
  rm -f /usr/local/bin/ollama
  rm -rf /usr/local/lib/ollama
fi

if id ollama >/dev/null 2>&1; then
  log "Removing ollama user/group + /usr/share/ollama..."
  userdel ollama 2>/dev/null || true
  groupdel ollama 2>/dev/null || true
  rm -rf /usr/share/ollama
fi

log "Ollama removed. Confirming nothing still listens on :11434:"
ss -tlnp 2>/dev/null | grep ':11434' || log "  (nothing — good)"
log "Done."
