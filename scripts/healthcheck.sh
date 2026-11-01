#!/bin/bash
set -Eeuo pipefail

failed=0
for service in cloud-firefox.service cloud-panel.service; do
  if /usr/bin/systemctl is-active --quiet "$service"; then
    printf 'OK  %s is active\n' "$service"
  else
    printf 'ERR %s is not active\n' "$service"
    failed=1
  fi
done

firefox_ready=0
for _ in $(/usr/bin/seq 1 30); do
  if /usr/bin/pgrep -u cloudfirefox -f 'firefox-esr' >/dev/null && [[ -S /tmp/.X11-unix/X99 ]]; then
    firefox_ready=1
    break
  fi
  /usr/bin/sleep 1
done
if (( firefox_ready )); then
  printf 'OK  Firefox process and Xvfb display are ready\n'
else
  printf 'ERR Firefox process or Xvfb display is not ready\n'
  failed=1
fi

if /usr/bin/grep -q '^MemAvailable:' /proc/meminfo; then
  printf 'OK  memory metrics are available\n'
else
  printf 'ERR memory metrics are unavailable\n'
  failed=1
fi

oom_kills=$(/usr/bin/awk '$1 == "oom_kill" { print $2 }' /proc/vmstat)
printf 'INFO kernel OOM kill count: %s\n' "${oom_kills:-unknown}"
/usr/bin/df -h / | /usr/bin/tail -n 1
exit "$failed"