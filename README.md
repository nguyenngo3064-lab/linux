# Cloud Firefox Lite

Firefox ESR chạy nền trên Debian với Xvfb, một profile cố định và panel HTTPS tối giản. Dự án không cài desktop environment, audio server, database hay container runtime. Python panel chỉ dùng thư viện chuẩn; noVNC được cung cấp từ các gói Debian và chỉ dùng trong phiên điều khiển.

## Cài đặt

Trên Debian 12 hoặc Debian 13, chạy với quyền root:

```sh
bash install.sh
```

Installer kiểm tra Debian, RAM và dung lượng đĩa; cài Firefox ESR/Xvfb/noVNC; tạo tài khoản dịch vụ; hỏi mật khẩu admin mà không hiển thị ký tự; tạo swap 1 GiB nếu máy chưa có swap; rồi bật Firefox và panel. Mật khẩu admin được lưu bằng scrypt, không lưu dạng rõ. Chạy lại installer sẽ cập nhật ứng dụng nhưng giữ profile, mật khẩu và chứng chỉ hiện có.

Panel lắng nghe HTTPS tại `https://<địa-chỉ-máy-chủ>:8443/`. Chứng chỉ ban đầu là chứng chỉ tự ký để installer hoạt động không cần domain. Hãy xác minh fingerprint SHA-256 được in ở cuối cài đặt qua một kênh tin cậy; trình duyệt sẽ cảnh báo chứng chỉ chưa được CA tin cậy. Chỉ mở TCP 8443 từ các địa chỉ quản trị tin cậy trên firewall của VPS. Không có cổng VNC công khai: x11vnc và websockify chỉ bind loopback, còn panel xác thực session trước khi proxy WebSocket.

## Sử dụng

- Đăng nhập bằng mật khẩu admin đã tạo trong installer. Session hết hạn sau 8 giờ; cookie có `HttpOnly`, `Secure`, `SameSite=Strict`, và các thao tác thay đổi yêu cầu CSRF token.
- Panel hiển thị RAM hệ thống khả dụng/đã dùng, CPU toàn máy, uptime, dung lượng filesystem `/` và bộ đếm OOM từ kernel. CPU chưa có mẫu trước đó sẽ hiện là chưa rõ. Các số liệu này không phải mức sử dụng riêng của Firefox.
- Bắt đầu, dừng hoặc khởi động lại Firefox bằng systemd. Firefox tự phục hồi sau crash; profile ở `/var/lib/cloud-firefox/profile` không bị xóa khi restart hay cập nhật.
- Chọn **Mở Firefox** để bật dịch vụ noVNC theo yêu cầu. Dừng Firefox sẽ dừng dịch vụ điều khiển. Màn hình ảo cố định là 1280x800.
- Đăng nhập Facebook thủ công trong trình duyệt. Facebook không được tự đăng nhập và không có mật khẩu Facebook trong mã nguồn.
- Xem journal Firefox gần nhất trong panel. `scripts/healthcheck.sh` kiểm tra trạng thái service, khả năng đọc số liệu bộ nhớ và bộ đếm OOM.

Đổi mật khẩu trong panel; thao tác này làm hết hạn các session hiện tại. Firefox chạy bằng user `cloudfirefox`; panel chạy bằng user `cloudpanel` và chỉ được sudo các lệnh systemd/journal đã định danh. Không vô hiệu hóa sandbox Firefox, không đặt giới hạn `MemoryMax` và không tự refresh trang.

## Dịch vụ

- `cloud-firefox.service`: Xvfb và một Firefox ESR, tự restart sau lỗi.
- `cloud-firefox-control.service`: x11vnc/noVNC, chỉ khởi chạy khi được yêu cầu và bind localhost.
- `cloud-panel.service`: panel HTTPS trên cổng 8443.

Các lệnh vận hành hữu ích:

```sh
systemctl status cloud-firefox.service cloud-panel.service
journalctl -u cloud-firefox.service -n 100 --no-pager
bash /opt/cloud-firefox-lite/scripts/healthcheck.sh
```

Gỡ dịch vụ bằng `bash uninstall.sh`. Script yêu cầu xác nhận, gỡ service và ứng dụng nhưng giữ `/var/lib/cloud-firefox`, `/var/lib/cloud-firefox-panel` và swap để không phá profile hoặc hash admin.

## Giới hạn và kiểm thử

1 GiB RAM là mục tiêu cấu hình, không phải kết quả benchmark. Firefox/Facebook có thể dùng nhiều RAM tùy nội dung, tab và thời gian chạy; swap chỉ giúp giảm khả năng OOM, không thay thế RAM. Dashboard đọc số liệu hệ thống thật và bộ đếm OOM, không tự chạy nền khi chưa đăng nhập. Installer phải được chạy trên Debian 12/13; môi trường phát triển không thể xác nhận reboot, crash recovery hoặc tổng RAM của một VPS thực tế.

Firefox không có hard cap tab ổn định được cấu hình ở đây; hãy duy trì một tab Facebook khi máy chỉ có 1 GiB RAM. Cấu hình chỉ khởi chạy Facebook trong lần đầu, sau đó Firefox khôi phục session/profile. Không có audio server, microphone hoặc camera; cuộc gọi cần các thiết bị đó sẽ không hoạt động, và website có thể tự ngắt call khi tab nền hoặc server thiếu tài nguyên. Không thể cam kết giữ mọi call 24/7.

### Kiểm thử trên VPS

Sau cài đặt, xác nhận `healthcheck.sh`, đăng nhập/đăng xuất, thử sai mật khẩu nhiều lần, mở/đóng noVNC, đổi mật khẩu, và thử start/stop/restart Firefox. Sau đó reboot VPS, xác nhận Firefox và panel tự hoạt động, profile/cookie vẫn còn, rồi theo dõi RAM/OOM trong thời gian sử dụng thực tế. Chưa có kết quả kiểm thử Debian thực tế hoặc benchmark RAM được ghi nhận trong repository này.