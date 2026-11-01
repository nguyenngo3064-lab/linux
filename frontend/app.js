(() => {
  const loginView = document.querySelector('#login-view');
  const dashboard = document.querySelector('#dashboard');
  const loginForm = document.querySelector('#login-form');
  const loginMessage = document.querySelector('#login-message');
  const logoutButton = document.querySelector('#logout');
  const actionMessage = document.querySelector('#action-message');
  const csrfToken = { value: '' };
  let pollTimer = null;

  async function request(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
    if (csrfToken.value && options.method === 'POST') headers['X-CSRF-Token'] = csrfToken.value;
    const response = await fetch(path, { ...options, headers, credentials: 'same-origin', cache: 'no-store' });
    let payload = {};
    try { payload = await response.json(); } catch { /* handled as an empty response */ }
    if (!response.ok) throw new Error(payload.error || `Yêu cầu thất bại (${response.status})`);
    return payload;
  }

  function showDashboard(csrf) {
    csrfToken.value = csrf;
    loginView.classList.add('hidden');
    dashboard.classList.remove('hidden');
    logoutButton.classList.remove('hidden');
    refreshStatus();
    clearInterval(pollTimer);
    pollTimer = setInterval(() => {
      if (!document.hidden) refreshStatus();
    }, 15000);
  }

  function showLogin() {
    clearInterval(pollTimer);
    csrfToken.value = '';
    dashboard.classList.add('hidden');
    logoutButton.classList.add('hidden');
    loginView.classList.remove('hidden');
  }

  function formatBytes(value) {
    if (typeof value !== 'number') return 'Không rõ';
    const units = ['B', 'MiB', 'GiB', 'TiB'];
    let size = value;
    let index = 0;
    while (size >= 1024 && index < units.length - 1) {
      size /= 1024;
      index += 1;
    }
    return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
  }

  function formatUptime(value) {
    if (typeof value !== 'number') return 'Không rõ';
    const days = Math.floor(value / 86400);
    const hours = Math.floor((value % 86400) / 3600);
    const minutes = Math.floor((value % 3600) / 60);
    return days ? `${days} ngày ${hours} giờ` : `${hours} giờ ${minutes} phút`;
  }

  async function refreshStatus() {
    try {
      const state = await request('/api/status');
      const status = document.querySelector('#firefox-status');
      status.classList.toggle('online', state.firefox);
      status.classList.toggle('offline', !state.firefox);
      status.querySelector('b').textContent = state.firefox ? 'Đang chạy' : 'Đã dừng';
      document.querySelector('#ram-value').textContent = formatBytes(state.memory.used_bytes);
      document.querySelector('#ram-detail').textContent = `Khả dụng ${formatBytes(state.memory.available_bytes)} / ${formatBytes(state.memory.total_bytes)}`;
      document.querySelector('#cpu-value').textContent = state.cpu_percent == null ? 'Không rõ' : `${state.cpu_percent.toFixed(1)}%`;
      document.querySelector('#uptime-value').textContent = formatUptime(state.uptime_seconds);
      document.querySelector('#disk-value').textContent = formatBytes(state.disk.used_bytes);
      document.querySelector('#disk-detail').textContent = `Còn ${formatBytes(state.disk.free_bytes)} / ${formatBytes(state.disk.total_bytes)}`;
      document.querySelector('#oom-status').textContent = `OOM kills: ${state.oom_kills ?? 'không rõ'}`;
      document.querySelector('#updated-at').textContent = `Cập nhật ${new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' })}`;
    } catch (error) {
      if (/401|đăng nhập/i.test(error.message)) showLogin();
      else actionMessage.textContent = error.message;
    }
  }

  loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    loginMessage.textContent = '';
    const password = new FormData(loginForm).get('password');
    const submit = loginForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    try {
      const result = await request('/api/login', { method: 'POST', body: JSON.stringify({ password }) });
      loginForm.reset();
      showDashboard(result.csrf);
    } catch (error) {
      loginMessage.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });

  logoutButton.addEventListener('click', async () => {
    try { await request('/api/logout', { method: 'POST', body: '{}' }); } catch { /* clear the local view either way */ }
    showLogin();
  });

  document.querySelectorAll('[data-action]').forEach((button) => {
    button.addEventListener('click', async () => {
      button.disabled = true;
      actionMessage.textContent = 'Đang gửi yêu cầu…';
      try {
        await request('/api/action', { method: 'POST', body: JSON.stringify({ action: button.dataset.action }) });
        actionMessage.textContent = 'Đã gửi yêu cầu tới systemd.';
        window.setTimeout(refreshStatus, 1200);
      } catch (error) {
        actionMessage.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });
  });

  document.querySelector('#open-control').addEventListener('click', async () => {
    const controlWindow = window.open('about:blank', '_blank');
    if (!controlWindow) {
      actionMessage.textContent = 'Trình duyệt đã chặn cửa sổ điều khiển.';
      return;
    }
    controlWindow.opener = null;
    actionMessage.textContent = 'Đang khởi chạy kết nối điều khiển…';
    try {
      await request('/api/action', { method: 'POST', body: JSON.stringify({ action: 'control-start' }) });
      controlWindow.location = '/control/';
      actionMessage.textContent = 'Đang mở Firefox trong thẻ mới.';
      window.setTimeout(refreshStatus, 1200);
    } catch (error) {
      controlWindow.close();
      actionMessage.textContent = error.message;
    }
  });

  document.querySelector('#show-logs').addEventListener('click', async () => {
    const dialog = document.querySelector('#logs-dialog');
    const output = document.querySelector('#log-output');
    output.textContent = 'Đang tải…';
    dialog.showModal();
    try { output.textContent = (await request('/api/logs')).logs || 'Chưa có log.'; }
    catch (error) { output.textContent = error.message; }
  });

  document.querySelector('#change-password').addEventListener('click', () => {
    document.querySelector('#password-message').textContent = '';
    document.querySelector('#password-dialog').showModal();
  });

  document.querySelector('#password-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const message = document.querySelector('#password-message');
    const submit = form.querySelector('button[type="submit"]');
    submit.disabled = true;
    message.textContent = '';
    try {
      await request('/api/password', { method: 'POST', body: JSON.stringify(Object.fromEntries(new FormData(form))) });
      form.reset();
      document.querySelector('#password-dialog').close();
      showLogin();
      loginMessage.textContent = 'Mật khẩu đã đổi. Hãy đăng nhập lại.';
    } catch (error) {
      message.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });

  document.querySelectorAll('[data-close]').forEach((button) => {
    button.addEventListener('click', () => document.querySelector(`#${button.dataset.close}`).close());
  });

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && !dashboard.classList.contains('hidden')) refreshStatus();
  });

  request('/api/session').then((result) => showDashboard(result.csrf)).catch(() => showLogin());
})();