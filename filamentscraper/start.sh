#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-8095}"
if [[ ! -f data/prices_cache.json ]]; then
  echo "First run: fetching prices (may take 1–2 minutes)…"
  python3 scrape.py || true
fi
exec python3 server.py "$PORT"
