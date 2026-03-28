#!/usr/bin/env bash
# Run API so a physical phone on the same Wi‑Fi can reach it.
# 1) chmod +x dev_serve_mobile.sh && ./dev_serve_mobile.sh
# 2) On iPhone, build with YOUR Mac IP (not 127.0.0.1):
#    flutter run -d <device> --dart-define=API_BASE=http://192.168.x.x:8000

set -e
cd "$(dirname "$0")"

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || true)
if [[ -z "$LAN_IP" ]]; then
  LAN_IP=$(ipconfig getifaddr en1 2>/dev/null || true)
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  API will listen on ALL interfaces (0.0.0.0:8000)"
if [[ -n "$LAN_IP" ]]; then
  echo "  On your iPhone use:  http://${LAN_IP}:8000"
else
  echo "  Find your Mac Wi‑Fi IP in System Settings → Network"
fi
echo "  Flutter:  --dart-define=API_BASE=http://<that-ip>:8000"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
