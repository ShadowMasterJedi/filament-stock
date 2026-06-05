#!/usr/bin/env bash
# Opretter self-signed TLS-certifikat til LAN (iPhone live-kamera kræver HTTPS).
set -euo pipefail
cd "$(dirname "$0")"

CERT_DIR="certs"
CERT="${CERT_DIR}/cert.pem"
KEY="${CERT_DIR}/key.pem"
DAYS="${CERT_DAYS:-825}"

LAN_IP=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}')
LAN_IP="${LAN_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"

mkdir -p "$CERT_DIR"

if [ -f "$CERT" ] && [ -f "$KEY" ]; then
  echo "Certifikat findes allerede: ${CERT}"
  echo "Slet mappen certs/ og kør igen for at generere nyt certifikat."
  exit 0
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl mangler – installer med: sudo apt install openssl"
  exit 1
fi

SAN="DNS:localhost,DNS:filament-stock.local,IP:127.0.0.1"
if [ -n "$LAN_IP" ]; then
  SAN="${SAN},IP:${LAN_IP}"
fi

echo "Opretter self-signed certifikat (${DAYS} dage)…"
echo "  SAN: ${SAN}"

openssl req -x509 -newkey rsa:2048 \
  -keyout "$KEY" \
  -out "$CERT" \
  -days "$DAYS" \
  -nodes \
  -subj "/CN=filament-stock/O=Filament Stock/C=DK" \
  -addext "subjectAltName=${SAN}" 2>/dev/null || \
openssl req -x509 -newkey rsa:2048 \
  -keyout "$KEY" \
  -out "$CERT" \
  -days "$DAYS" \
  -nodes \
  -subj "/CN=filament-stock/O=Filament Stock/C=DK"

chmod 600 "$KEY"
chmod 644 "$CERT"

echo ""
echo "Certifikat oprettet:"
echo "  ${CERT}"
echo "  ${KEY}"
if [ -n "$LAN_IP" ]; then
  echo ""
  echo "Brug på iPhone: https://${LAN_IP}:8090"
  echo "Safari viser sikkerhedsadvarsel – tryk «Vis detaljer» → «Besøg websitet»."
fi
