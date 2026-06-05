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

if [ ! -f certs/cert.pem ] || [ ! -f certs/key.pem ]; then
  echo "Opretter TLS-certifikat (self-signed)…"
  chmod +x gen-cert.sh
  ./gen-cert.sh
fi

echo "Filament Stock starter med HTTPS på port ${PORT}"
echo ""
echo "  Lokalt:    https://localhost:${PORT}"
if [ -n "$LAN_IP" ]; then
  echo "  Netværk:   https://${LAN_IP}:${PORT}"
  echo ""
  echo "  iPhone: Safari viser advarsel første gang – «Vis detaljer» → «Besøg websitet»"
  echo "  Derefter virker live kamera under Scan."
fi
echo ""
echo "Tryk Ctrl+C for at stoppe"
python3 server.py "$PORT" --https
