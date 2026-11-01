#!/usr/bin/python3
"""Small HTTPS management panel; no third-party Python packages required."""

import http.cookies
import json
import os
import secrets
import select
import socket
import ssl
import threading
import time
import urllib.parse
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import auth
import system

FRONTEND = os.environ.get("CFL_FRONTEND", "/opt/cloud-firefox-lite/frontend")
NOVNC = "/usr/share/novnc"
CERT = os.environ.get("CFL_TLS_CERT", "/etc/cloud-firefox-lite/tls.crt")
KEY = os.environ.get("CFL_TLS_KEY", "/etc/cloud-firefox-lite/tls.key")
SESSION_TTL = 8 * 60 * 60
sessions = {}
failures = {}
state_lock = threading.Lock()


def _clean_expired(now):
    for token in [key for key, value in sessions.items() if value["expires"] <= now]:
        sessions.pop(token, None)


class PanelHandler(BaseHTTPRequestHandler):
    server_version = "CloudFirefoxLite/1"
    sys_version = ""

    def log_message(self, _format, *_args):
        return

    def _json(self, status, data, headers=None):
        body = json.dumps(data, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self' wss:; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 4096:
                return None
            data = json.loads(self.rfile.read(size))
            return data if isinstance(data, dict) else None
        except (ValueError, json.JSONDecodeError):
            return None

    def _origin_ok(self):
        origin = self.headers.get("Origin", "")
        host = self.headers.get("Host", "")
        return bool(host and origin == f"https://{host}")

    def _cookies(self):
        cookies = http.cookies.SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return {}
        return cookies

    def _session(self):
        morsel = self._cookies().get("cfl_session")
        if morsel is None:
            return None, None
        token = morsel.value
        now = time.time()
        with state_lock:
            _clean_expired(now)
            record = sessions.get(token)
            if record and record["expires"] > now:
                return token, record
        return None, None

    def _authorized(self, require_csrf=False):
        token, record = self._session()
        if record is None:
            self._json(401, {"error": "Vui long dang nhap"})
            return None
        if require_csrf:
            csrf = self.headers.get("X-CSRF-Token", "")
            if not self._origin_ok() or not secrets.compare_digest(csrf, record["csrf"]):
                self._json(403, {"error": "Yeu cau khong hop le"})
                return None
        return record

    def do_GET(self):
        if self.path == "/api/session":
            _, record = self._session()
            if record is None:
                self._json(401, {"authenticated": False})
            else:
                self._json(200, {"authenticated": True, "csrf": record["csrf"]})
            return
        if self.path == "/api/status":
            if self._authorized() is None:
                return
            self._json(200, system.status())
            return
        if self.path == "/api/logs":
            if self._authorized() is None:
                return
            try:
                self._json(200, {"logs": system.logs()})
            except RuntimeError as error:
                self._json(503, {"error": str(error)})
            return
        if self.path == "/control" or self.path.startswith("/control/"):
            if self._authorized() is None:
                return
            if self.path == "/control" or self.path == "/control/":
                self.send_response(302)
                self.send_header("Location", "/control/vnc.html?autoconnect=true&resize=scale&path=control/ws")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if self.path == "/control/ws":
                self._websocket_proxy()
                return
            self._novnc_file()
            return
        if self.path in ("/", "/index.html"):
            self._static_file(FRONTEND, "index.html")
            return
        if self.path in ("/style.css", "/app.js"):
            self._static_file(FRONTEND, self.path.lstrip("/"))
            return
        self._json(404, {"error": "Khong tim thay"})

    def do_POST(self):
        if self.path == "/api/login":
            self._login()
            return
        if self.path == "/api/logout":
            if self._authorized(require_csrf=True) is None:
                return
            token, _ = self._session()
            with state_lock:
                sessions.pop(token, None)
            self._json(200, {"ok": True}, {"Set-Cookie": "cfl_session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Strict"})
            return
        if self.path == "/api/action":
            if self._authorized(require_csrf=True) is None:
                return
            payload = self._read_json()
            if payload is None or not isinstance(payload.get("action"), str):
                self._json(400, {"error": "Du lieu khong hop le"})
                return
            try:
                system.action(payload["action"])
                self._json(200, {"ok": True})
            except ValueError:
                self._json(400, {"error": "Tac vu khong hop le"})
            except RuntimeError as error:
                self._json(503, {"error": str(error)})
            return
        if self.path == "/api/password":
            self._change_password()
            return
        self._json(404, {"error": "Khong tim thay"})

    def _login(self):
        if not self._origin_ok():
            self._json(403, {"error": "Yeu cau khong hop le"})
            return
        address = self.client_address[0]
        now = time.time()
        blocked = False
        with state_lock:
            attempts = failures.get(address, [])
            attempts = [attempt for attempt in attempts if now - attempt < 900]
            failures[address] = attempts
            if len(attempts) >= 5:
                blocked = True
        if blocked:
            self._json(429, {"error": "Qua nhieu lan dang nhap, thu lai sau 15 phut"})
            return
        payload = self._read_json()
        password = payload.get("password") if payload else None
        if not isinstance(password, str) or not auth.verify_password(password):
            with state_lock:
                failures.setdefault(address, []).append(now)
            self._json(401, {"error": "Mat khau khong dung"})
            return
        with state_lock:
            failures.pop(address, None)
            _clean_expired(now)
            token = secrets.token_urlsafe(32)
            csrf = secrets.token_urlsafe(32)
            sessions[token] = {"csrf": csrf, "expires": now + SESSION_TTL}
        cookie = f"cfl_session={token}; Path=/; Max-Age={SESSION_TTL}; Secure; HttpOnly; SameSite=Strict"
        self._json(200, {"ok": True, "csrf": csrf}, {"Set-Cookie": cookie})

    def _change_password(self):
        record = self._authorized(require_csrf=True)
        if record is None:
            return
        payload = self._read_json()
        if not payload or not isinstance(payload.get("current"), str) or not isinstance(payload.get("new"), str):
            self._json(400, {"error": "Du lieu khong hop le"})
            return
        if not auth.verify_password(payload["current"]):
            self._json(401, {"error": "Mat khau hien tai khong dung"})
            return
        if len(payload["new"]) < 12:
            self._json(400, {"error": "Mat khau moi can it nhat 12 ky tu"})
            return
        auth.set_password(payload["new"])
        with state_lock:
            sessions.clear()
        self._json(200, {"ok": True}, {"Set-Cookie": "cfl_session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Strict"})

    def _static_file(self, root, name):
        self._serve_file(root, name)

    def _novnc_file(self):
        parsed = urllib.parse.urlsplit(self.path)
        name = urllib.parse.unquote(parsed.path[len("/control/"):])
        if not name or ".." in name.split("/"):
            self._json(404, {"error": "Khong tim thay"})
            return
        self._serve_file(NOVNC, name)

    def _serve_file(self, root, name):
        target = os.path.realpath(os.path.join(root, name))
        if not target.startswith(os.path.realpath(root) + os.sep):
            self._json(404, {"error": "Khong tim thay"})
            return
        try:
            with open(target, "rb") as source:
                body = source.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                self._json(413, {"error": "Tep qua lon"})
                return
        except OSError:
            self._json(404, {"error": "Khong tim thay"})
            return
        content_type = mimetypes.guess_type(target)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Strict-Transport-Security", "max-age=31536000")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self' wss:; img-src 'self' data:; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _websocket_proxy(self):
        _, record = self._session()
        origin = self.headers.get("Origin", "")
        if (record is None or not self._origin_ok() or origin != f"https://{self.headers.get('Host', '')}"
                or self.headers.get("Upgrade", "").lower() != "websocket"):
            self.send_error(403)
            return
        try:
            upstream = socket.create_connection(("127.0.0.1", 6080), timeout=5)
            request = ["GET /websockify HTTP/1.1\r\n", "Host: 127.0.0.1:6080\r\n"]
            request.append(f"Origin: {origin}\r\n")
            for header in ("Sec-WebSocket-Key", "Sec-WebSocket-Version", "Sec-WebSocket-Protocol",
                           "Sec-WebSocket-Extensions"):
                value = self.headers.get(header)
                if value:
                    request.append(f"{header}: {value}\r\n")
            request.extend(["Connection: Upgrade\r\n", "Upgrade: websocket\r\n", "\r\n"])
            upstream.sendall("".join(request).encode("ascii"))
            response = bytearray()
            while not response.endswith(b"\r\n\r\n") and len(response) < 16384:
                chunk = upstream.recv(1)
                if not chunk:
                    raise OSError("Websocket proxy handshake failed")
                response.extend(chunk)
            self.wfile.write(response)
            self.wfile.flush()
            if not response.startswith(b"HTTP/1.1 101"):
                upstream.close()
                return
            self.close_connection = True
            upstream.settimeout(None)
            client = self.connection
            while True:
                readable, _, _ = select.select([client, upstream], [], [], 60)
                if not readable:
                    break
                for source in readable:
                    data = source.recv(65536)
                    if not data:
                        return
                    destination = upstream if source is client else client
                    destination.sendall(data)
        except (OSError, ValueError):
            if not self.wfile.closed:
                try:
                    self.send_error(502)
                except OSError:
                    pass
        finally:
            try:
                upstream.close()
            except (UnboundLocalError, OSError):
                pass


class PanelHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(30)
        return request, address


def main():
    server = PanelHTTPServer(("0.0.0.0", int(os.environ.get("CFL_PORT", "8443"))), PanelHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(CERT, KEY)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()


if __name__ == "__main__":
    main()