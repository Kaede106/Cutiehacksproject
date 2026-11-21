import json
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from farm.dashboard import state as dash
from farm.dashboard.server import DashboardServer, host_allowed

from .conftest import NOW, fruit, scan, write_jsonl

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82")


@pytest.fixture
def scans(data):
    folder = data / "scans"
    folder.mkdir()
    (folder / "a.png").write_bytes(PNG)
    (folder / "b.JPG").write_bytes(b"jpg")
    (folder / "notes.txt").write_text("not an image")
    (data / "secret.png").write_bytes(PNG)  # outside scans/
    return folder


# --- the image path guard ---------------------------------------------------------------------


@pytest.mark.parametrize("name", ["a.png", "b.JPG"])
def test_guard_accepts_plain_image_names(data, scans, name):
    assert dash.scan_image_path(data, name) == (scans / name).resolve()


@pytest.mark.parametrize("name", [
    "../secret.png", "..\\secret.png", "scans/a.png", "sub/a.png", "/etc/passwd", "\\windows\\win.ini",
    "C:\\Users\\x\\a.png", "C:/a.png", "/abs/path/a.png", "..", ".", "", ".hidden.png", "a.png\x00.txt",
    "a.png ", "%2e%2e/secret.png", "..%2fsecret.png", "notes.txt", "a", "a.png.exe", "missing.png", "a.png/",
    "a..png", None, 5,
])
def test_guard_rejects_traversal_absolute_and_odd_names(data, scans, name):
    assert dash.scan_image_path(data, name) is None


def test_guard_rejects_an_absolute_path_to_a_real_file(data, scans):
    assert dash.scan_image_path(data, str((data / "secret.png").resolve())) is None
    assert dash.scan_image_path(data, str((scans / "a.png").resolve())) is None


def test_guard_rejects_a_symlink_out_of_scans(data, scans):
    link = scans / "link.png"
    try:
        link.symlink_to(data / "secret.png")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    assert dash.scan_image_path(data, "link.png") is None


def test_guard_without_a_scans_folder(data):
    assert dash.scan_image_path(data, "a.png") is None


def test_state_only_links_images_under_scans(data, scans, settings):
    for image, ok in [("scans/a.png", True), ("secret.png", False), ("scans/../secret.png", False),
                      ("/etc/passwd", False), ("scans/nope.png", False), (str((data / "secret.png").resolve()), False)]:
        write_jsonl(data, "scans.jsonl", [scan("2026-11-21T14:59:00-08:00", fruit("ripe"), image=image)])
        url = dash.build_state(settings, NOW)["scan"]["image"]
        assert (url is not None and url.startswith("/scans/a.png?v=")) == ok, image


# --- the running server -------------------------------------------------------------------------


@pytest.fixture
def live(data, settings):
    srv = DashboardServer("127.0.0.1", 0, settings)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def get(url, method="GET", headers=None):
    request = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=5) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def raw_status(base, target):
    """Send the request line exactly as given, so nothing normalises the path first."""
    host, port = base[len("http://"):].split(":")
    with socket.create_connection((host, int(port)), timeout=5) as s:
        s.sendall(f"GET {target} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode())
        reply = b""
        while chunk := s.recv(4096):
            reply += chunk
    return int(reply.split(b" ", 2)[1]), reply


def test_serves_page_assets_state_and_images(live, scans):
    status, headers, body = get(live + "/")
    assert status == 200 and b"control room" in body and "script-src 'self'" in headers["Content-Security-Policy"]
    assert get(live + "/app.js")[0] == 200 and get(live + "/app.css")[0] == 200
    status, headers, body = get(live + "/api/state")
    assert status == 200 and headers["Cache-Control"] == "no-store"
    assert json.loads(body)["data_folder"] is True
    status, headers, body = get(live + "/scans/a.png")
    assert (status, headers["Content-Type"], body) == (200, "image/png", PNG)


@pytest.mark.parametrize("target", [
    "/scans/../secret.png", "/scans/%2e%2e/secret.png", "/scans/..%2fsecret.png", "/scans/%252e%252e%252fsecret.png",
    "/scans/..%5csecret.png", "/scans//etc/passwd", "/scans/C:%5Cwindows%5Cwin.ini", "/scans/notes.txt",
    "/scans/", "/secret.png", "/static/../server.py", "/server.py", "/index.html", "/app.js/../server.py",
    "/farm/bot/.env", "/.env", "/api/state/../../secret.png", "/scans/..\\secret.png",
])
def test_nothing_else_on_disk_is_reachable(live, scans, target):
    status, reply = raw_status(live, target)
    assert status in (403, 404) and PNG not in reply and b"CUTIEFARM" not in reply


def test_read_only_methods_and_rebinding_guard(live, data):
    for method in ("POST", "PUT", "DELETE"):
        request = urllib.request.Request(live + "/api/state", data=b"x", method=method)
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(request, timeout=5)
        assert err.value.code == 405
    assert get(live + "/api/state", headers={"Host": "evil.example"})[0] == 403
    assert get(live + "/api/state", headers={"Host": "localhost:8800"})[0] == 200
    assert get(live + "/", method="HEAD")[0] == 200


def test_state_endpoint_on_a_missing_folder(tmp_path, monkeypatch, settings):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path / "gone"))
    srv = DashboardServer("127.0.0.1", 0, settings)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        status, _, body = get(f"http://127.0.0.1:{srv.server_address[1]}/api/state")
    finally:
        srv.shutdown()
        srv.server_close()
    assert status == 200 and json.loads(body)["data_folder"] is False
    assert not (tmp_path / "gone").exists()


@pytest.mark.parametrize(("header", "bound", "ok"), [
    ("localhost:8800", "127.0.0.1", True), ("127.0.0.1", "127.0.0.1", True), ("[::1]:8800", "127.0.0.1", True),
    ("evil.example", "127.0.0.1", False), ("localhost.evil.example", "127.0.0.1", False), (None, "127.0.0.1", False),
    ("192.168.1.5:8800", "0.0.0.0", True), ("anything", "192.168.1.5", True),
])
def test_host_header_check(header, bound, ok):
    assert host_allowed(header, bound) is ok


def test_nothing_secret_in_state(data, settings, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:SECRETSECRETSECRETSECRETSECRETSECRET")
    write_jsonl(data, "scans.jsonl", [scan("2026-11-21T14:59:00-08:00", fruit("ripe"))])
    text = json.dumps(dash.build_state(settings, NOW))
    assert "SECRET" not in text and str(data) not in text
