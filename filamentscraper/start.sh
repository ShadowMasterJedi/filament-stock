#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-8095}"

LAN_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
LAN_IP="${LAN_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"

if command -v lsof >/dev/null 2>&1 && lsof -ti :"${PORT}" >/dev/null 2>&1; then
  echo "Port ${PORT} er optaget – stopper gammel server…"
  lsof -ti :"${PORT}" | xargs -r kill 2>/dev/null || true
  sleep 1
fi

if [[ ! -f data/prices_cache.json ]]; then
  echo "First run: fetching prices (may take 1–2 minutes)…"
  python3 scrape.py || true
fi

echo "FilamentScraper starter på port ${PORT}"
echo ""
echo "  Lokalt:    http://localhost:${PORT}"
if [ -n "$LAN_IP" ]; then
  echo "  Netværk:   http://${LAN_IP}:${PORT}"
fi
echo ""
echo "Tryk Ctrl+C for at stoppe"
exec python3 server.py "$PORT"
