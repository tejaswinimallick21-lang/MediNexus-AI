#!/usr/bin/env bash
# One-time setup of MediNexus AI on an Ubuntu 22.04/24.04 server (e.g. an Azure VM).
# Run from the cloned repository as your normal user (it uses sudo where needed):
#
#   bash deploy/setup_server.sh --domain medinexus-demo.centralindia.cloudapp.azure.com \
#        --email you@example.com --data ~/medinexus_data.tar.gz --timezone Asia/Kolkata
#
#   --domain    public DNS name of the server (required for HTTPS)
#   --email     address Let's Encrypt uses for certificate expiry notices (required)
#   --data      archive from `python deploy/pack_data.py` (needed on the first run)
#   --timezone  server time zone; the 01:00 data feed and 07:00 sweep follow it (default UTC)
#   --no-https  skip the certificate (testing only: sign-in cookies then need plain HTTP)
#
# Safe to run again: steps that are already done are skipped or refreshed.
set -euo pipefail

DOMAIN="" EMAIL="" DATA="" TZONE="UTC" HTTPS=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --data) DATA="$2"; shift 2 ;;
    --timezone) TZONE="$2"; shift 2 ;;
    --no-https) HTTPS=0; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done
[[ -n "$DOMAIN" ]] || { echo "--domain is required"; exit 1; }
[[ $HTTPS -eq 0 || -n "$EMAIL" ]] || { echo "--email is required for HTTPS"; exit 1; }

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP_USER="$(id -un)"
cd "$APP_DIR"
step() { echo; echo "==> $*"; }

step "System packages"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip nginx git curl
if [[ $HTTPS -eq 1 ]]; then sudo apt-get install -y certbot python3-certbot-nginx; fi
if ! command -v node >/dev/null || [[ "$(node -v | cut -d. -f1 | tr -d v)" -lt 20 ]]; then
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
sudo timedatectl set-timezone "$TZONE"
# Swap as a safety net for the nightly Bronze -> Gold rebuild on small VMs
if [[ -z "$(swapon --show)" ]]; then
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

if [[ -n "$DATA" ]]; then
  step "Unpacking data from $DATA"
  sudo systemctl stop medinexus-api 2>/dev/null || true
  tar -xzf "$DATA" -C "$APP_DIR"
fi
[[ -f database/healthcare.duckdb ]] || { echo "No database yet: pass --data medinexus_data.tar.gz (see docs/DEPLOY_AZURE.md)"; exit 1; }
[[ -f backend/seed_users.json ]] || { echo "backend/seed_users.json is missing: it is inside the data archive"; exit 1; }

step "Python environment"
[[ -d .venv ]] || python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

step "Building the web app"
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build

step "Configuration (.env)"
if [[ ! -f .env ]]; then
  cp .env.example .env
  SECRET="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))')"
  sed -i "s|^MEDINEXUS_JWT_SECRET=.*|MEDINEXUS_JWT_SECRET=$SECRET|" .env
  {
    echo
    echo "# --- Server (written by deploy/setup_server.sh) ---"
    echo "MEDINEXUS_ENV=production"
    if [[ $HTTPS -eq 1 ]]; then echo "MEDINEXUS_COOKIE_SECURE=true"; fi
  } >> .env
  echo "Created .env with a new session key. Add OPENAI_API_KEY to it if you want AI answers."
else
  echo ".env already exists: left unchanged."
fi
chmod 600 .env backend/seed_users.json

step "API service"
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__USER__|$APP_USER|g" deploy/medinexus-api.service \
  | sudo tee /etc/systemd/system/medinexus-api.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable medinexus-api
sudo systemctl restart medinexus-api

step "Web server (nginx)"
# nginx (www-data) must be able to read the built web app
chmod o+x "$HOME" "$APP_DIR" "$APP_DIR/frontend"
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__SERVER_NAME__|$DOMAIN|g" deploy/nginx.conf \
  | sudo tee /etc/nginx/sites-available/medinexus >/dev/null
sudo ln -sf /etc/nginx/sites-available/medinexus /etc/nginx/sites-enabled/medinexus
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

if [[ $HTTPS -eq 1 ]]; then
  step "HTTPS certificate (Let's Encrypt)"
  sudo certbot --nginx -d "$DOMAIN" -m "$EMAIL" --agree-tos --no-eff-email --redirect --keep-until-expiring -n
fi

step "Checking the API"
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/system/status >/dev/null 2>&1; then
    SCHEME=$([[ $HTTPS -eq 1 ]] && echo https || echo http)
    echo "API is up. Open $SCHEME://$DOMAIN"
    exit 0
  fi
  sleep 2
done
echo "The API did not answer within a minute. See: sudo journalctl -u medinexus-api -n 100"
exit 1
