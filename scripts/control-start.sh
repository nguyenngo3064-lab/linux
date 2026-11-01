#!/bin/bash
set -Eeuo pipefail
export DISPLAY=:99
export XAUTHORITY=/var/lib/cloud-firefox/Xauthority
/usr/bin/x11vnc -display "$DISPLAY" -auth "$XAUTHORITY" -localhost \
  -rfbport 5900 -forever -shared -noxdamage -quiet &
x11vnc_pid=$!
cleanup() {
  kill "$x11vnc_pid" 2>/dev/null || true
  wait "$x11vnc_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
for _ in $(seq 1 50); do
  if ! kill -0 "$x11vnc_pid" 2>/dev/null; then
    echo "x11vnc exited before becoming ready" >&2
    exit 1
  fi
  if /usr/bin/bash -c '</dev/tcp/127.0.0.1/5900' 2>/dev/null; then break; fi
  sleep 0.1
done
/usr/bin/websockify --heartbeat 30 --web /usr/share/novnc \
  127.0.0.1:6080 127.0.0.1:5900 &
websockify_pid=$!
wait "$websockify_pid"