import html
import json
import os
from pathlib import Path

import pytest

from farm.dashboard import __main__ as cli
from farm.dashboard import export as exp
from farm.dashboard import state as dash
from farm.dashboard.export import ExportError, export, static_index
from farm.dashboard.server import STATIC_DIR

from .conftest import NOW, fruit, reading, scan, write_jsonl
from .test_dashboard_server import PNG


@pytest.fixture
def data(tmp_path, monkeypatch):
    """The data folder, one level down so that tmp_path itself is free for an output folder."""
    folder = tmp_path / "data"
    folder.mkdir()
    monkeypatch.setenv("CUTIEFARM_DATA", str(folder))
    return folder


@pytest.fixture
def grove(data):
    """A data folder with one scan that has a photo, readings, and files that must never be exported."""
    (data / "scans").mkdir()
    (data / "scans" / "a.png").write_bytes(PNG)
    (data / "scans" / "other.png").write_bytes(PNG)  # a scan the page does not show
    (data / "scans" / "notes.txt").write_text("not an image")
    (data / "secret.png").write_bytes(PNG)
    (data / ".env").write_text("TELEGRAM_BOT_TOKEN=123:secret\n")
    (data / "bot_state.json").write_text('{"chats": [1234]}')
    write_jsonl(data, "scans.jsonl", [scan("2026-11-21T14:00:00-08:00", fruit("ripe"), fruit("unripe", x=90),
                                           image="scans/a.png", source="file")])
    write_jsonl(data, "sensors.jsonl", [reading("2026-11-21T14:50:00-08:00", 31, 22, 55, simulated=True)])
    return data


def tree(folder: Path) -> set[str]:
    return {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}


def run(grove, tmp_path, settings, **kwargs):
    out = tmp_path / "site"
    return out, export(out, settings, now=NOW, **kwargs)


def test_export_writes_the_page_the_state_and_the_scan_image(grove, tmp_path, settings):
    out, result = run(grove, tmp_path, settings)
    assert tree(out) == {"index.html", "app.js", "app.css", "state.json", "scans/a.png"}
    assert (out / "scans" / "a.png").read_bytes() == PNG
    assert (out / "app.js").read_bytes() == (STATIC_DIR / "app.js").read_bytes()
    assert (out / "app.css").read_bytes() == (STATIC_DIR / "app.css").read_bytes()
    assert result["files"] == ["index.html", "app.js", "app.css", "state.json", "scans/a.png"]


def test_state_json_is_valid_and_matches_the_live_builder(grove, tmp_path, settings):
    out, _ = run(grove, tmp_path, settings)
    snapshot = json.loads((out / "state.json").read_text(encoding="utf-8"))
    live = dash.build_state(settings, NOW)
    assert snapshot.pop("snapshot") == {"date": "November 21, 2026", "timezone": "America/Los_Angeles"}
    assert snapshot["scan"].pop("image") == "scans/a.png"
    live["scan"].pop("image")
    assert snapshot == live
    assert snapshot["scan"]["counts"] == {"ripe": 1, "ripening": 0, "unripe": 1}
    assert snapshot["sensors"]["any"] and "simulated" in [n["key"] for n in snapshot["notices"]]


def test_the_page_is_marked_static_with_the_demo_banner(grove, tmp_path, settings):
    out, _ = run(grove, tmp_path, settings)
    page = (out / "index.html").read_text(encoding="utf-8")
    assert '<meta name="cutiefarm-mode" content="static">' in page
    assert ("Demo snapshot of the CutieFarm control room, made from demo data on November 21, 2026. "
            "The live version runs on the farm laptop.") in page
    assert 'href="app.css"' in page and 'src="app.js"' in page and '"/app' not in page
    assert "<base" not in page and "Back to the CutieFarm page" not in page
    unescaped = html.unescape(page)
    assert "connect-src 'self'" in unescaped and "base-uri 'self'" in unescaped and "frame-ancestors" not in unescaped


def test_the_live_page_is_not_changed_and_is_not_static(grove):
    live = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "cutiefarm-mode" not in live and "demo-banner" not in live
    js = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert 'meta[name="cutiefarm-mode"]' in js and '"state.json"' in js and '"/api/state"' in js


def test_base_and_home_urls_are_written_for_a_site(grove, tmp_path, settings):
    out, _ = run(grove, tmp_path, settings, base_url="/dashboard/", home_url="/")
    page = (out / "index.html").read_text(encoding="utf-8")
    assert '<base href="/dashboard/">' in page
    assert '<a href="/">Back to the CutieFarm page</a>' in page


@pytest.mark.parametrize("bad", ['/x"><script>', "https://evil.example/", "//evil.example/", "dashboard/",
                                 "/a/../b/", "/a b/", "/a?b", "/a\n", ""])
def test_base_url_that_is_not_a_plain_site_path_is_refused(grove, tmp_path, settings, bad):
    with pytest.raises(ExportError):
        export(tmp_path / "site", settings, now=NOW, base_url=bad)
    with pytest.raises(ExportError):
        export(tmp_path / "site", settings, now=NOW, home_url=bad)
    assert not (tmp_path / "site").exists()


def test_the_date_is_escaped_in_the_banner():
    page = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    assert "<script>x" not in static_index(page, "<script>x</script>")
    assert "&lt;script&gt;x" in static_index(page, "<script>x</script>")


# --- nothing outside the data folder's scan images ---------------------------------------------------


def test_only_the_scan_image_the_page_shows_is_copied(grove, tmp_path, settings):
    out, _ = run(grove, tmp_path, settings)
    names = tree(out)
    assert not {"scans/other.png", "scans/notes.txt", "secret.png", ".env", "bot_state.json",
                "scans.jsonl", "sensors.jsonl"} & names
    assert "123:secret" not in "".join((out / n).read_text(encoding="utf-8") for n in names if not n.endswith(".png"))


@pytest.mark.parametrize("image", ["scans/../secret.png", "scans/..\\secret.png", "../secret.png", "/etc/passwd",
                                   "C:/secret.png", "scans/sub/a.png", "secret.png", "scans/notes.txt",
                                   "scans/missing.png", "scans/.hidden.png", "scans/a.png/../../secret.png"])
def test_a_path_traversal_in_a_scan_record_copies_nothing(grove, tmp_path, settings, image):
    write_jsonl(grove, "scans.jsonl", [scan("2026-11-21T14:00:00-08:00", fruit("ripe"), image=image)])
    out, _ = run(grove, tmp_path, settings)
    assert tree(out) == {"index.html", "app.js", "app.css", "state.json"}
    assert json.loads((out / "state.json").read_text(encoding="utf-8"))["scan"]["image"] is None


def test_a_symlink_out_of_scans_is_not_copied(grove, tmp_path, settings):
    link = grove / "scans" / "link.png"
    try:
        link.symlink_to(grove / "secret.png")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    write_jsonl(grove, "scans.jsonl", [scan("2026-11-21T14:00:00-08:00", fruit("ripe"), image="scans/link.png")])
    out, _ = run(grove, tmp_path, settings)
    assert "scans/link.png" not in tree(out)


def test_an_oversized_image_is_left_out(grove, tmp_path, settings, monkeypatch):
    monkeypatch.setattr(exp, "MAX_IMAGE_BYTES", 10)
    out, _ = run(grove, tmp_path, settings)
    assert "scans/a.png" not in tree(out)
    assert json.loads((out / "state.json").read_text(encoding="utf-8"))["scan"]["image"] is None


def test_the_data_folder_is_never_written(grove, tmp_path, settings):
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in grove.rglob("*") if p.is_file()}
    run(grove, tmp_path, settings)
    after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in grove.rglob("*") if p.is_file()}
    assert before == after and not any(p.suffix == ".json" and p.name == "state.json" for p in grove.rglob("*"))


@pytest.mark.parametrize("where", ["data", "inside", "above"])
def test_out_must_be_apart_from_the_data_folder(grove, tmp_path, settings, where):
    out = {"data": grove, "inside": grove / "site", "above": grove.parent}[where]
    with pytest.raises(ExportError):
        export(out, settings, now=NOW)
    assert not (grove / "site").exists() and not (grove / "state.json").exists()


def test_a_missing_data_folder_is_an_error_and_creates_nothing(tmp_path, settings, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path / "nope"))
    with pytest.raises(ExportError):
        export(tmp_path / "site", settings, now=NOW)
    assert not (tmp_path / "site").exists() and not (tmp_path / "nope").exists()


def test_re_exporting_replaces_old_images_and_keeps_other_files(grove, tmp_path, settings):
    out, _ = run(grove, tmp_path, settings)
    (out / "README.md").write_text("how to regenerate")
    (out / "scans" / "stale.png").write_bytes(PNG)
    (out / "scans" / "keep.txt").write_text("not an image")
    write_jsonl(grove, "scans.jsonl", [scan("2026-11-21T14:00:00-08:00", fruit("ripe"), image="scans/other.png")])
    export(out, settings, now=NOW)
    assert tree(out) == {"index.html", "app.js", "app.css", "state.json", "README.md",
                         "scans/other.png", "scans/keep.txt"}


def test_an_empty_data_folder_exports_an_empty_snapshot(data, tmp_path, settings):
    out, _ = run(data, tmp_path, settings)
    snapshot = json.loads((out / "state.json").read_text(encoding="utf-8"))
    assert snapshot["scan"] is None and snapshot["feed"] == [] and snapshot["data_folder"] is True
    assert tree(out) == {"index.html", "app.js", "app.css", "state.json"}


# --- the command ------------------------------------------------------------------------------------------


def test_command_writes_the_files_and_reports(grove, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli.settings, "load_env_file", lambda: None)
    out = tmp_path / "site"
    assert cli.main(["export", "--out", str(out), "--base-url", "/dashboard/", "--home-url", "/"]) == 0
    assert tree(out) == {"index.html", "app.js", "app.css", "state.json", "scans/a.png"}
    assert "wrote" in capsys.readouterr().out


def test_command_fails_cleanly_on_a_bad_option(grove, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli.settings, "load_env_file", lambda: None)
    assert cli.main(["export", "--out", str(tmp_path / "site"), "--base-url", "https://x/"]) == 1
    assert "--base-url" in capsys.readouterr().out
    assert not (tmp_path / "site").exists()


def test_command_needs_out(grove, capsys):
    with pytest.raises(SystemExit):
        cli.main(["export"])
