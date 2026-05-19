#!/usr/bin/env bash
# One-shot setup for a fresh clone. Idempotent — safe to re-run.
#
#   - installs the tailwind toolchain into node_modules/
#   - points git at .githooks/ so the pre-commit hook fires
#   - builds styles.css from input.css for the first time
#
# Run once after cloning; the hook handles every commit after that.
set -euo pipefail

repo_root="$(cd "$(dirname "$0")" && pwd)"
cd "$repo_root"

log()  { printf '==> %s\n' "$*"; }
warn() { printf 'WARN: %s\n' "$*" >&2; }

command -v node >/dev/null || { warn "node not found — install a recent LTS"; exit 1; }
command -v npm  >/dev/null || { warn "npm not found"; exit 1; }

log "pointing git at .githooks/"
git config core.hooksPath .githooks
chmod +x .githooks/* 2>/dev/null || true

log "installing tailwind toolchain"
if [ -f package-lock.json ]; then npm ci --silent; else npm install --silent; fi

log "building tailwind"
npm run --silent build:css

cat <<EOF

setup complete.

deploy:
  the repo is pure-static — styles.css is committed, so any host that serves
  the directory works (no build step at deploy time).

stripe sync (only when prices or descriptions change):
  python3 stripe_sync.py

re-build css manually (the pre-commit hook does this automatically on
commits that touch *.html or input.css):
  npm run build:css
EOF
