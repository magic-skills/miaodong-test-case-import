#!/usr/bin/env bash
# Install this skill for Claude Code / Codex / the cross-runtime ~/.agents alias by symlinking
# this directory into each agent's skills root. Idempotent (ln -sfn) and path-relative, so it
# works no matter where you move this folder. Re-run after moving.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
NAME="$(basename "$SKILL_DIR")"

link() {
  local root="$1"
  mkdir -p "$root"
  local target="$root/$NAME"

  # The repo may already BE the directory inside this skills root (e.g. you cloned straight into
  # ~/.claude/skills/). Deleting it here would nuke the repo — including .git — and leave a
  # dangling link. Detect and skip.
  if [ -e "$target" ] && [ ! -L "$target" ]; then
    if [ "$(cd "$target" && pwd -P)" = "$SKILL_DIR" ]; then
      echo "  keep  $target  (已是本仓库真实目录，无需链接)"
      return
    fi
    echo "  replace stale copy at $target"
    rm -rf "$target"
  fi
  ln -sfn "$SKILL_DIR" "$target"
  echo "  link  $target -> $(readlink "$target")"
}

echo "Installing skill '$NAME' from $SKILL_DIR"
link "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills"          # Claude Code
link "${CODEX_HOME:-$HOME/.codex}/skills"                  # Codex
link "${AGENTS_SKILLS_DIR:-$HOME/.agents/skills}"          # 跨 runtime 通用位置

echo
echo "Done."
echo "  Claude Code : /$NAME  或按 description 自动触发"
echo "  Codex       : \$$NAME 或 /skills"
echo "  Python deps : pip3 install requests"
