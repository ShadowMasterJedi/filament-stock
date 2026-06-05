#!/usr/bin/env bash
PORT="${1:-8090}"

if ! command -v ufw >/dev/null 2>&1; then
  echo "ufw ikke fundet. Åbn port ${PORT}/tcp manuelt i firewall."
  exit 1
fi

echo "Åbner port ${PORT}/tcp i UFW…"
sudo ufw allow "${PORT}/tcp" comment "Filament Stock"
sudo ufw status | grep -E "${PORT}|Status"
