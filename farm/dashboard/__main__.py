"""CutieFarm control room: a live, read-only dashboard for the big screen.

    python -m farm.dashboard --port 8800            then open http://127.0.0.1:8800
    python -m farm.dashboard --host 0.0.0.0         also reachable from other devices on the LAN
    python -m farm.dashboard export --out <dir>     write a static snapshot for a public site

It only reads the shared data folder (farm/CONTRACT.md) and never writes to it.
"""
from __future__ import annotations

import argparse
import sys

from . import settings
from .server import DashboardServer, is_loopback


def export_main(argv: list[str]) -> int:
    from pathlib import Path

    from .export import ExportError, export

    parser = argparse.ArgumentParser(
        prog="python -m farm.dashboard export",
        description="Write a static, read-only copy of the control room (page, state.json, the scan image) "
                    "from the data folder ($CUTIEFARM_DATA). Use a demo data folder for a public site.")
    parser.add_argument("--out", required=True, type=Path, help="folder to write (created if missing)")
    parser.add_argument("--base-url", help="site path the folder is served from, e.g. /dashboard/")
    parser.add_argument("--home-url", help="site path the banner links back to, e.g. /")
    args = parser.parse_args(argv)
    settings.load_env_file()
    config = settings.load_settings()
    for warning in config.warnings:
        print(f"Dashboard: {warning}", flush=True)
    try:
        result = export(args.out, config, base_url=args.base_url, home_url=args.home_url)
    except ExportError as exc:
        print(f"Dashboard export: {exc}", flush=True)
        return 1
    print(f"Dashboard export: read {result['data_folder']}", flush=True)
    print(f"Dashboard export: wrote {', '.join(result['files'])} to {result['out']}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args_in = sys.argv[1:] if argv is None else argv
    if args_in[:1] == ["export"]:
        return export_main(args_in[1:])
    parser = argparse.ArgumentParser(prog="python -m farm.dashboard",
                                     description="CutieFarm control room: a live, read-only dashboard.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="address to listen on (default 127.0.0.1; 0.0.0.0 shows it on the LAN)")
    parser.add_argument("--port", type=int, default=8800, help="port (default 8800)")
    args = parser.parse_args(args_in)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be from 1 to 65535")

    settings.load_env_file()
    config = settings.load_settings()
    for warning in config.warnings:
        print(f"Dashboard: {warning}", flush=True)
    try:
        server = DashboardServer(args.host, args.port, config)
    except OSError as exc:
        print(f"Dashboard: cannot listen on {args.host}:{args.port} ({exc.strerror or exc}).", flush=True)
        return 1
    shown = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    print(f"Dashboard: http://{shown}:{args.port}  (read-only, Ctrl+C stops it)", flush=True)
    if not is_loopback(args.host):
        print("Dashboard: listening beyond this laptop. Anyone on the network can see the farm data.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
