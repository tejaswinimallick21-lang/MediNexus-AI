#!/usr/bin/env bash
# Deploy the latest code from GitHub to the server: pull, install, rebuild, restart.
#   bash deploy/update.sh
# Data, models, accounts and .env are not touched. data/metadata is tracked in git but rewritten by
# the nightly feed on the server, so the server's copy is kept.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_DIR"

KEEP="$(mktemp -d)"
cp -r data/metadata "$KEEP/"
git checkout -- data/metadata
git pull --ff-only
cp -r "$KEEP/metadata/." data/metadata/
rm -rf "$KEEP"

.venv/bin/pip install -r requirements.txt -q
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
sudo systemctl restart medinexus-api
echo "Updated to $(git log --oneline -1)"
