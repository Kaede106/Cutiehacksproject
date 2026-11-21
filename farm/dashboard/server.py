"""A small read-only web server: one page, its two static files, /api/state and scan images.

Only GET and HEAD are answered. The only files served are the three fixed page assets and images
directly under <data folder>/scans/ (see state.scan_image_path). Nothing else on disk is reachable.
"""
from __future__ import annotations

import ipaddress
import json
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import state
from .settings import Settings

STATIC_DIR = Path(__file__).resolve().parent / "static"
ASSETS = {  # URL path -> (file, content type). A fixed list: no path is ever built from the request.
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
MAX_IMAGE_BYTES = 15_000_000
STATE_TTL = 1.0  # seconds: several screens polling at once share one read of the files
LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def host_allowed(header: str | None, bound_host: str) -> bool:
    """When bound to loopback, only answer requests addressed to localhost (blocks DNS rebinding)."""
    if not is_loopback(bound_host):
        return True
    if not header:
        return False
    name = header.strip()
    if name.startswith("["):
        name = name[1:].split("]", 1)[0]
    elif name.count(":") == 1:
        name = name.split(":", 1)[0]
    return name.lower() in LOOPBACK_NAMES


class StateCache:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._lock = threading.Lock()
        self._at = 0.0
        self._body = b""

    def get(self) -> bytes:
        with self._lock:
            if time.monotonic() - self._at > STATE_TTL or not self._body:
                body = json.dumps(state.build_state(self._settings), ensure_ascii=False).encode("utf-8")
                self._body, self._at = body, time.monotonic()
            return self._body


class Handler(BaseHTTPRequestHandler):
    server_version = "CutieFarmDashboard"
    sys_version = ""

    def log_request(self, code="-", size="-") -> None:  # a poll every 2 s would fill the log
        if str(code).isdigit() and int(code) >= 400:
            super().log_request(code, size)

    def _send(self, status: int, body: bytes, content_type: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _error(self, status: HTTPStatus) -> None:
        self._send(status, status.phrase.encode(), "text/plain; charset=utf-8")

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        if not host_allowed(self.headers.get("Host"), self.server.bound_host):
            return self._error(HTTPStatus.FORBIDDEN)
        path = urlsplit(self.path).path
        if path in ASSETS:
            name, content_type = ASSETS[path]
            try:
                body = (STATIC_DIR / name).read_bytes()
            except OSError:
                return self._error(HTTPStatus.NOT_FOUND)
            return self._send(200, body, content_type)
        if path == "/api/state":
            try:
                body = self.server.state_cache.get()
            except Exception:
                return self._error(HTTPStatus.INTERNAL_SERVER_ERROR)
            return self._send(200, body, "application/json; charset=utf-8")
        if path.startswith("/scans/"):
            return self._image(unquote(path[len("/scans/"):]))
        self._error(HTTPStatus.NOT_FOUND)

    def _image(self, name: str) -> None:
        image = state.scan_image_path(state.data_folder(), name)
        if image is None:
            return self._error(HTTPStatus.NOT_FOUND)
        try:
            if image.stat().st_size > MAX_IMAGE_BYTES:
                return self._error(HTTPStatus.NOT_FOUND)
            body = image.read_bytes()
        except OSError:
            return self._error(HTTPStatus.NOT_FOUND)
        self._send(200, body, state.IMAGE_SUFFIXES[image.suffix.lower()], cache="private, max-age=30")

    def _method_not_allowed(self) -> None:
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _method_not_allowed


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, host: str, port: int, settings: Settings) -> None:
        self.bound_host = host
        self.state_cache = StateCache(settings)
        super().__init__((host, port), Handler)
