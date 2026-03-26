#!/usr/bin/env bash
# copy_env.sh — Copy .env into a worktree under .trees/
# Usage: copy_env.sh <branch>
# Example: copy_env.sh fix/room-transition-race

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: copy_env.sh <branch>"
  echo "Copies .env from the repo root into .trees/<branch>/"
  exit 1
fi

BRANCH="$1"
# Use --git-common-dir to find the main repo root, not the worktree root
REPO_ROOT="$(cd "$(git rev-parse --git-common-dir)" && git rev-parse --show-toplevel)"
TARGET="$REPO_ROOT/.trees/$BRANCH/.env"

if [ ! -f "$REPO_ROOT/.env" ]; then
  echo "No .env found at repo root ($REPO_ROOT/.env)"
  exit 1
fi

if [ ! -d "$REPO_ROOT/.trees/$BRANCH" ]; then
  echo "Worktree not found: .trees/$BRANCH"
  exit 1
fi

cp "$REPO_ROOT/.env" "$TARGET"
echo "Copied .env -> .trees/$BRANCH/.env"
