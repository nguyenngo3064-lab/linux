#!/bin/bash
set -Eeuo pipefail

APP_DIR=/opt/cloud-firefox-lite
CONFIG_DIR=/etc/cloud-firefox-lite
DATA_DIR=/var/lib/cloud-firefox
PANEL_DATA_DIR=/var/lib/cloud-firefox-panel
PASSWORD_FILE="$PANEL_DATA_DIR/admin.json"
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

fail() {
  printf 'LỖI: %s\n' "$1" >&2
  exit 1
}

if [[ "$EUID" -ne 0 ]]; then
  fail "Hãy chạy bằng root: bash install.sh"
fi
if [[ ! -r /etc/os-release ]]; then
  fail "Không đọc được thông tin hệ điều hành."
fi
# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != debian || ! "${VERSION_ID:-}" =~ ^(12|13)(\.|$) ]]; then
  fail "Chỉ hỗ trợ Debian 12 hoặc Debian 13."
fi

read -r root_total root_available < <(/usr/bin/df -B1 --output=size,avail / | /usr/bin/tail -n 1)
if (( root_total < 5 * 1024 * 1024 * 1024 )); then
  fail "Phân vùng gốc cần tối thiểu 5 GiB dung lượng tổng."
fi
if (( root_available < 2 * 1024 * 1024 * 1024 )); then
  fail "Cần ít nhất 2 GiB trống để cài gói và tạo swap."
fi
total_memory_kib=$(/usr/bin/awk '/^MemTotal:/ { print $2 }' /proc/meminfo)
if (( total_memory_kib < 1024 * 1024 )); then
  printf 'CẢNH BÁO: RAM thấp hơn mục tiêu 1 GiB (%s MiB).\n' "$((total_memory_kib / 1024))"
fi

printf 'Đang cài dependencies tối thiểu cho Firefox ESR, Xvfb và panel…\n'
/usr/bin/apt-get update
DEBIAN_FRONTEND=noninteractive /usr/bin/apt-get install -y --no-install-recommends \
  ca-certificates firefox-esr novnc openssl procps python3 sudo websockify x11vnc \
  xauth xvfb
/usr/bin/apt-get clean

if ! /usr/bin/getent group cloudfirefox >/dev/null; then
  /usr/sbin/groupadd --system cloudfirefox
fi
if ! /usr/bin/getent passwd cloudfirefox >/dev/null; then
  /usr/sbin/useradd --system --gid cloudfirefox --home-dir "$DATA_DIR" \
    --no-create-home --shell /usr/sbin/nologin cloudfirefox
fi
if ! /usr/bin/getent group cloudpanel >/dev/null; then
  /usr/sbin/groupadd --system cloudpanel
fi
if ! /usr/bin/getent passwd cloudpanel >/dev/null; then
  /usr/sbin/useradd --system --gid cloudpanel --home-dir "$PANEL_DATA_DIR" \
    --no-create-home --shell /usr/sbin/nologin cloudpanel
fi

/usr/bin/install -d -o root -g root -m 0755 "$APP_DIR" "$APP_DIR/backend" \
  "$APP_DIR/frontend" "$APP_DIR/scripts" "$CONFIG_DIR"
/usr/bin/install -d -o cloudfirefox -g cloudfirefox -m 0750 "$DATA_DIR" "$DATA_DIR/profile"
/usr/bin/install -d -o cloudpanel -g cloudpanel -m 0700 "$PANEL_DATA_DIR"
/usr/bin/cp -R "$SCRIPT_DIR/backend/." "$APP_DIR/backend/"
/usr/bin/cp -R "$SCRIPT_DIR/frontend/." "$APP_DIR/frontend/"
/usr/bin/cp -R "$SCRIPT_DIR/scripts/." "$APP_DIR/scripts/"
/usr/bin/chown -R root:root "$APP_DIR"
/usr/bin/chmod 0755 "$APP_DIR/scripts/"*.sh
/usr/bin/chmod 0644 "$APP_DIR/backend/"*.py "$APP_DIR/frontend/"*

if [[ ! -s "$DATA_DIR/Xauthority" ]]; then
  cookie=$(/usr/bin/od -An -N16 -tx1 /dev/urandom | /usr/bin/tr -d ' \n')
  /usr/bin/xauth -f "$DATA_DIR/Xauthority" add :99 . "$cookie"
  /usr/bin/chown cloudfirefox:cloudfirefox "$DATA_DIR/Xauthority"
  /usr/bin/chmod 0600 "$DATA_DIR/Xauthority"
fi
if [[ ! -e "$DATA_DIR/profile/user.js" ]]; then
  cat > "$DATA_DIR/profile/user.js" <<'PREFS'
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.startup.page", 3);
user_pref("browser.sessionstore.resume_from_crash", true);
user_pref("browser.sessionstore.max_resumed_crashes", 1);
user_pref("browser.sessionstore.max_tabs_undo", 2);
user_pref("browser.sessionstore.max_windows_undo", 1);
user_pref("browser.sessionstore.interval", 60000);
user_pref("browser.cache.disk.capacity", 102400);
user_pref("browser.cache.memory.capacity", 32768);
user_pref("browser.safebrowsing.downloads.enabled", true);
user_pref("media.volume_scale", "0.0");
PREFS
  /usr/bin/chown cloudfirefox:cloudfirefox "$DATA_DIR/profile/user.js"
  /usr/bin/chmod 0640 "$DATA_DIR/profile/user.js"
fi

if [[ ! -s "$PASSWORD_FILE" ]]; then
  printf '\nThiết lập mật khẩu quản trị. Mật khẩu sẽ không hiển thị khi nhập.\n'
  CFL_PASSWORD_FILE="$PASSWORD_FILE" /usr/bin/python3 "$APP_DIR/backend/auth.py" set-password
  /usr/bin/chown cloudpanel:cloudpanel "$PASSWORD_FILE"
  /usr/bin/chmod 0600 "$PASSWORD_FILE"
else
  /usr/bin/chown cloudpanel:cloudpanel "$PASSWORD_FILE"
  /usr/bin/chmod 0600 "$PASSWORD_FILE"
  printf 'Giữ nguyên hash mật khẩu admin đã tồn tại.\n'
fi

if [[ ! -s "$CONFIG_DIR/tls.crt" || ! -s "$CONFIG_DIR/tls.key" ]]; then
  hostname_name=$(/usr/bin/hostname -f 2>/dev/null || /usr/bin/hostname)
  san_entries="DNS:localhost,DNS:$hostname_name,IP:127.0.0.1"
  for address in $(/usr/bin/hostname -I 2>/dev/null || true); do
    address=${address%%\%*}
    san_entries+=",IP:$address"
  done
  /usr/bin/openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 825 \
    -subj "/CN=$hostname_name" \
    -addext "subjectAltName=$san_entries" \
    -keyout "$CONFIG_DIR/tls.key" -out "$CONFIG_DIR/tls.crt"
  /usr/bin/chown root:cloudpanel "$CONFIG_DIR/tls.key"
  /usr/bin/chmod 0640 "$CONFIG_DIR/tls.key"
  /usr/bin/chown root:root "$CONFIG_DIR/tls.crt"
  /usr/bin/chmod 0644 "$CONFIG_DIR/tls.crt"
fi

sudoers_tmp=$(/usr/bin/mktemp)
cat > "$sudoers_tmp" <<'SUDOERS'
cloudpanel ALL=(root) NOPASSWD: /usr/bin/systemctl is-active cloud-firefox.service, /usr/bin/systemctl is-active cloud-firefox-control.service, /usr/bin/systemctl start cloud-firefox.service, /usr/bin/systemctl stop cloud-firefox.service, /usr/bin/systemctl restart cloud-firefox.service, /usr/bin/systemctl start cloud-firefox-control.service, /usr/bin/systemctl stop cloud-firefox-control.service, /usr/bin/journalctl --no-pager -n 100 -u cloud-firefox.service
SUDOERS
/usr/bin/visudo -cf "$sudoers_tmp"
/usr/bin/install -o root -g root -m 0440 "$sudoers_tmp" /etc/sudoers.d/cloud-firefox-lite
/usr/bin/rm -f "$sudoers_tmp"

for unit in cloud-firefox.service cloud-firefox-control.service cloud-panel.service; do
  /usr/bin/install -o root -g root -m 0644 "$SCRIPT_DIR/systemd/$unit" "/etc/systemd/system/$unit"
done
/usr/bin/systemctl daemon-reload

swap_active=0
if /usr/bin/awk 'NR > 1 { found = 1 } END { exit !found }' /proc/swaps; then
  swap_active=1
fi
if (( swap_active == 0 )); then
  if [[ ! -e /swapfile ]]; then
    if ! /usr/bin/fallocate -l 1G /swapfile; then
      /usr/bin/dd if=/dev/zero of=/swapfile bs=1M count=1024 status=none
    fi
    /usr/bin/chmod 0600 /swapfile
    /usr/sbin/mkswap /swapfile
    /usr/sbin/swapon /swapfile
    if ! /usr/bin/grep -qE '^[[:space:]]*/swapfile[[:space:]]' /etc/fstab; then
      printf '/swapfile none swap sw 0 0\n' >> /etc/fstab
    fi
  else
    printf 'CẢNH BÁO: /swapfile đã tồn tại nhưng chưa bật; installer không ghi đè file này.\n'
  fi
fi

/usr/bin/systemctl enable --now cloud-firefox.service cloud-panel.service
/usr/bin/chmod 0755 "$APP_DIR/scripts/healthcheck.sh"
if ! "$APP_DIR/scripts/healthcheck.sh"; then
  printf 'CẢNH BÁO: healthcheck chưa đạt; xem journalctl -u cloud-firefox.service -u cloud-panel.service.\n' >&2
fi

if ! /usr/bin/python3 - <<'PY'
import ssl
import urllib.error
import urllib.request

context = ssl._create_unverified_context()
request = urllib.request.Request("https://127.0.0.1:8443/api/session")
try:
    urllib.request.urlopen(request, context=context, timeout=5)
except urllib.error.HTTPError as error:
    raise SystemExit(0 if error.code == 401 else 1)
except Exception:
    raise SystemExit(1)
raise SystemExit(1)
PY
then
  printf 'CẢNH BÁO: panel HTTPS không phản hồi đúng tại cổng 8443.\n' >&2
fi

printf '\nCài đặt hoàn tất.\n'
printf 'Panel HTTPS: https://%s:8443/\n' "$(/usr/bin/hostname -I | /usr/bin/awk '{ print $1 }')"
printf 'Firefox service: %s\n' "$(/usr/bin/systemctl is-active cloud-firefox.service || true)"
printf 'Panel service: %s\n' "$(/usr/bin/systemctl is-active cloud-panel.service || true)"
printf 'Fingerprint chứng chỉ SHA-256: '
/usr/bin/openssl x509 -in "$CONFIG_DIR/tls.crt" -noout -fingerprint -sha256
printf 'Chứng chỉ tự ký; xác minh fingerprint qua kênh tin cậy và giới hạn firewall cổng TCP 8443.\n'
printf 'Đăng nhập Facebook thủ công trong Firefox; không nhập thông tin Facebook vào panel.\n'