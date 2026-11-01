#!/bin/bash
set -Eeuo pipefail

if [[ "$EUID" -ne 0 ]]; then
  printf 'Hãy chạy bằng root: bash uninstall.sh\n' >&2
  exit 1
fi
printf 'Gỡ dịch vụ Cloud Firefox Lite? Profile Firefox và hash mật khẩu sẽ được giữ lại. [y/N] '
read -r answer
if [[ ! "$answer" =~ ^[Yy]$ ]]; then
  printf 'Đã hủy.\n'
  exit 0
fi

/usr/bin/systemctl disable --now cloud-firefox-control.service cloud-firefox.service cloud-panel.service 2>/dev/null || true
/usr/bin/rm -f /etc/systemd/system/cloud-firefox.service \
  /etc/systemd/system/cloud-firefox-control.service \
  /etc/systemd/system/cloud-panel.service /etc/sudoers.d/cloud-firefox-lite
/usr/bin/systemctl daemon-reload
/usr/bin/rm -rf /opt/cloud-firefox-lite
/usr/bin/rm -f /etc/cloud-firefox-lite/tls.crt /etc/cloud-firefox-lite/tls.key
/usr/bin/rmdir /etc/cloud-firefox-lite 2>/dev/null || true
printf 'Đã gỡ service và ứng dụng. Profile, mật khẩu admin và swap được giữ tại /var/lib/cloud-firefox, /var/lib/cloud-firefox-panel và /swapfile.\n'