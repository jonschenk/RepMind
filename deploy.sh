#!/usr/bin/env bash
# One-command deploy of repMind to pi4host over the tailnet.
#
# Flow: build the frontend locally (the Pi has no Node) -> push main ->
#       Pi pulls the backend -> rsync the built UI -> restart the service.
#
# Prereqs: Tailscale up on this Mac; you've committed backend changes (the Pi
# deploys backend from pushed `main`; the frontend ships from your local build).
set -euo pipefail

PI="pi4host@pi4host"
URL="http://pi4host:8000"
cd "$(dirname "$0")"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "!!  Uncommitted changes present. Backend deploys from pushed 'main', so commit"
  echo "    backend edits first or they won't ship (frontend ships from your local build)."
fi

echo "==> Building frontend"
( cd frontend && npm run build )

echo "==> Pushing main"
git push origin main

echo "==> Updating backend on the Pi"
ssh "$PI" 'cd ~/repMind && git pull --ff-only'

echo "==> Syncing built frontend to the Pi"
rsync -az --delete frontend/dist/ "$PI:repMind/frontend/dist/"

echo "==> Installing any new deps + restarting service"
ssh "$PI" 'cd ~/repMind/backend && .venv/bin/pip install -q -r requirements.txt && sudo systemctl restart repmind'

echo "==> Waiting for health"
for _ in $(seq 1 15); do
  if curl -fsS -m 5 "$URL/api/health" >/dev/null 2>&1; then
    echo "OK - live at $URL"
    curl -s "$URL/api/health"; echo
    exit 0
  fi
  sleep 2
done
echo "FAILED health check. Inspect: ssh $PI 'journalctl -u repmind -n 50 --no-pager'"
exit 1
