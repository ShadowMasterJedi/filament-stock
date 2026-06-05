#!/usr/bin/env bash
cd "$(dirname "$0")"
PORT="${1:-8090}"

LAN_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
LAN_IP="${LAN_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"

if command -v lsof >/dev/null 2>&1 && lsof -ti :"${PORT}" >/dev/null 2>&1; then
  echo "Port ${PORT} er optaget – stopper gammel server…"
  lsof -ti :"${PORT}" | xargs -r kill 2>/dev/null || true
  sleep 1
fi

echo "Filament Stock starter på port ${PORT}"
echo ""
echo "  Lokalt:    http://localhost:${PORT}"
if [ -n "$LAN_IP" ]; then
  echo "  Netværk:   http://${LAN_IP}:${PORT}"
  echo ""
  echo "  Åbn på iPhone og tilføj til hjemmeskærm for app-oplevelse"
fi
echo ""
echo "Tryk Ctrl+C for at stoppe"
python3 server.py "$PORT"
