#!/usr/bin/env bash
# Install cron job: scrape Bambu + SUNLU EU prices twice daily (06:00 and 18:00).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(command -v python3)"
LOG="$ROOT/data/scrape.log"
MARKER="# filamentscraper-auto-scrape"
CRON_LINE="0 6,18 * * * cd $ROOT && $PYTHON scrape.py --quiet >> $LOG 2>&1 $MARKER"

mkdir -p "$ROOT/data"
touch "$LOG"

EXISTING="$(crontab -l 2>/dev/null || true)"
if echo "$EXISTING" | grep -qF "$MARKER"; then
  echo "Cron job already installed."
else
  (echo "$EXISTING"; echo "$CRON_LINE") | crontab -
  echo "Installed cron: twice daily at 06:00 and 18:00"
fi
echo "Log: $LOG"
crontab -l | grep -F "$MARKER" || true
