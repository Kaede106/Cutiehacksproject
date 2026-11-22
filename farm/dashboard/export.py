"""Write a self-contained, static copy of the control room: `python -m farm.dashboard export --out <dir>`.

The copy is for a public site, where there is no server and no data folder. It holds the page's three
assets, `state.json` (the same JSON `/api/state` serves, built by `state.build_state`) and the one scan
image that state refers to. Nothing else is copied: the image goes through `state.scan_image_path`, the
guard the live server uses, so only a plain image file directly under `<data>/scans/` can be exported.

The page learns it is a snapshot from `<meta name="cutiefarm-mode" content="static">`, written here.
"""
from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from . import state
from .server import CSP, MAX_IMAGE_BYTES, STATIC_DIR
from .settings import Settings

PAGE_FILES = ("index.html", "app.js", "app.css")
_URL_PATH = re.compile(r"/[A-Za-z0-9._~/-]*")  # a site path such as /dashboard/: no quotes, no scheme
# <base> needs base-uri 'self', and a <meta> CSP cannot carry frame-ancestors.
STATIC_CSP = CSP.replace("base-uri 'none'", "base-uri 'self'").replace("; frame-ancestors 'none'", "")


class ExportError(Exception):
    """The export cannot be done; the message says why."""


def _site_path(value: str | None, option: str) -> str | None:
    if value is None:
        return None
    if not _URL_PATH.fullmatch(value) or value.startswith("//") or ".." in value.split("/"):
        raise ExportError(f"{option} must be a site path like /dashboard/ (letters, digits, . _ ~ - and /).")
    return value


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:  # the live page changed: fail loudly rather than publish a half-static page
        raise ExportError(f"the dashboard page no longer contains exactly one {old!r}; update export.py.")
    return text.replace(old, new)


def static_index(page: str, date_label: str, base_url: str | None = None, home_url: str | None = None) -> str:
    """The live index.html turned into the snapshot page: mode meta, CSP, relative assets, a banner."""
    head = ('<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            '  <meta name="cutiefarm-mode" content="static">\n'
            f'  <meta http-equiv="Content-Security-Policy" content="{html.escape(STATIC_CSP)}">')
    if base_url:
        head += f'\n  <base href="{html.escape(base_url)}">'
    banner = ('<p class="demo-banner" id="demo-banner" role="note">'
              f"Demo snapshot of the CutieFarm control room, made from demo data on {html.escape(date_label)}. "
              "The live version runs on the farm laptop."
              + (f' <a href="{html.escape(home_url)}">Back to the CutieFarm page</a>' if home_url else "")
              + "</p>")
    page = _replace_once(page, '<meta name="viewport" content="width=device-width, initial-scale=1">', head)
    page = _replace_once(page, "<title>CutieFarm control room</title>",
                         "<title>CutieFarm control room (demo snapshot)</title>")
    page = _replace_once(page, 'href="/app.css"', 'href="app.css"')
    page = _replace_once(page, 'src="/app.js"', 'src="app.js"')
    return _replace_once(page, "<body>", f'<body class="static">\n  {banner}')


def _copy_scan_image(folder: Path, out: Path, scan: dict | None) -> None:
    """Copy the scan image the state refers to into <out>/scans/ and point the state at the copy.

    Anything the guard refuses (or that is too big) is dropped from the state: the page then draws the
    boxes on a plain background instead of linking to a file that is not there.
    """
    if not scan or not scan.get("image"):
        return
    name = Path(urlsplit(scan["image"]).path).name
    source = state.scan_image_path(folder, name)
    if source is None or source.stat().st_size > MAX_IMAGE_BYTES:
        scan["image"] = None
        return
    target = out / "scans"
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target / source.name)
    scan["image"] = f"scans/{source.name}"


def _clear_old_scans(out: Path) -> None:
    """Remove images left by an earlier export (flat image files in <out>/scans/ only)."""
    scans = out / "scans"
    if scans.is_dir() and not scans.is_symlink():
        for old in scans.iterdir():
            if old.is_file() and not old.is_symlink() and old.suffix.lower() in state.IMAGE_SUFFIXES:
                old.unlink()


def export(out: Path, settings: Settings, *, now: datetime | None = None, base_url: str | None = None,
           home_url: str | None = None) -> dict:
    """Write the snapshot to `out`. Returns what was written, for the command to print."""
    base_url = _site_path(base_url, "--base-url")
    home_url = _site_path(home_url, "--home-url")
    folder = state.data_folder()
    if not folder.is_dir():
        raise ExportError(f"the data folder {folder} does not exist: nothing to export. Set CUTIEFARM_DATA.")
    out = out.resolve()
    folder = folder.resolve()
    if out == folder or folder in out.parents or out in folder.parents:
        raise ExportError("--out must be a different folder from the data folder, and not inside it or above it.")

    now = (now or datetime.now(settings.timezone)).astimezone(settings.timezone)
    snapshot = state.build_state(settings, now)
    date_label = f"{now:%B} {now.day}, {now.year}"
    snapshot["snapshot"] = {"date": date_label, "timezone": getattr(settings.timezone, "key", "UTC")}

    out.mkdir(parents=True, exist_ok=True)
    _clear_old_scans(out)
    _copy_scan_image(folder, out, snapshot["scan"])
    for name in ("app.js", "app.css"):
        shutil.copyfile(STATIC_DIR / name, out / name)
    index = static_index((STATIC_DIR / "index.html").read_text(encoding="utf-8"), date_label, base_url, home_url)
    (out / "index.html").write_text(index, encoding="utf-8", newline="\n")
    (out / "state.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=1) + "\n",
                                    encoding="utf-8", newline="\n")
    written = [*PAGE_FILES, "state.json"]
    if snapshot["scan"] and snapshot["scan"]["image"]:
        written.append(snapshot["scan"]["image"])
    return {"out": out, "files": written, "data_folder": folder, "date": date_label}
