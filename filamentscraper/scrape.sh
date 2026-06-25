#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 scrape.py "$@"
echo "Open http://localhost:8095 after starting the server."
