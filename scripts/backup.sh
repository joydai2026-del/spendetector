#!/usr/bin/env bash
# Back up the Spendetector repo to GitHub. Safe to run anytime (and from a Claude Code
# SessionEnd hook): it commits any uncommitted changes, then pushes unpushed commits.
#
# Secrets stay safe: .env / .env.* / .vault / .venv are gitignored, so `git add -A` never
# stages them. Never fails loudly (always exits 0) so it cannot block a session from ending.
set -uo pipefail
cd "$(dirname "$0")/.." 2>/dev/null || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

branch="$(git branch --show-current 2>/dev/null)"
[ -z "$branch" ] && exit 0

# 1. Commit any uncommitted changes (gitignore protects .env/.vault/.venv).
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  git add -A
  git commit -q -m "backup: session changes $(date '+%Y-%m-%d %H:%M')" || true
fi

# 2. Push, but only if there is something to push.
if ! git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  git push -q -u origin "$branch" 2>/dev/null && echo "backup: pushed new branch $branch" || true
elif [ -n "$(git log '@{u}..HEAD' --oneline 2>/dev/null)" ]; then
  git push -q origin "$branch" 2>/dev/null && echo "backup: pushed $branch to GitHub" || true
else
  echo "backup: nothing to push (already up to date)"
fi
exit 0
