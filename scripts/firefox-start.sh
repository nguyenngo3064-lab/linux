#!/bin/bash
set -Eeuo pipefail

export HOME=/var/lib/cloud-firefox
export DISPLAY=:99
export XAUTHORITY=/var/lib/cloud-firefox/Xauthority
profile="$HOME/profile"
first_run="$HOME/.first-firefox-launch"

/usr/bin/Xvfb "$DISPLAY" -screen 0 1280x800x24 -nolisten tcp \
  -auth "$XAUTHORITY" -noreset &
xvfb_pid=$!
cleanup() {
  kill "$xvfb_pid" 2>/dev/null || true
  wait "$xvfb_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for _ in $(seq 1 50); do
  if [[ -S /tmp/.X11-unix/X99 ]]; then break; fi
  if ! kill -0 "$xvfb_pid" 2>/dev/null; then
    echo "Xvfb exited before its display became ready" >&2
    exit 1
  fi
  sleep 0.1
done
if [[ ! -S /tmp/.X11-unix/X99 ]]; then
  echo "Timed out waiting for Xvfb display :99" >&2
  exit 1
fi

args=(--no-remote --profile "$profile")
if [[ ! -e "$first_run" ]]; then
  args+=(--new-window https://www.facebook.com/)
  touch "$first_run"
fi
/usr/bin/firefox-esr "${args[@]}"