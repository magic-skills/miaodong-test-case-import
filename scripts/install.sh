#!/usr/bin/env bash
# Install this skill for BOTH Claude Code and OpenAI Codex by symlinking this directory
# into each agent's skills root. Idempotent (ln -sfn) and path-relative, so it works no
# matter where you move this folder. Re-run after moving.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="$(basename "$SKILL_DIR")"

link() {
  local root="$1"
  mkdir -p "$root"
  if [ -e "$root/$NAME" ] && [ ! -L "$root/$NAME" ]; then rm -rf "$root/$NAME"; fi
  ln -sfn "$SKILL_DIR" "$root/$NAME"
  echo "  linked $root/$NAME -> $(readlink "$root/$NAME")"
}

echo "Installing skill '$NAME' from $SKILL_DIR"
link "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"
link "${CODEX_HOME:-$HOME/.codex}/skills"

echo "Done. Claude Code: /$NAME or auto-triggered. Codex: \$$NAME or /skills."
echo "Python deps: pip3 install requests"
