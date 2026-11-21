"""python -m farm.vision {scan,watch,live} --help"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
import sys
import time

import cv2
import numpy as np

from farm.bot.config import load_env_file
from farm.common import store
from farm.sensors.__main__ import duration
from .scan import MODEL, Classifier, classify_color, classify_frame, save_scan


class CaptureError(Exception):
    """The requested camera or file could not supply a frame."""


def read_camera(camera: cv2.VideoCapture, index: int) -> np.ndarray:
    try:
        ok, frame = camera.read()
        if ok and frame is not None and frame.size:
            return frame
    except cv2.error:
        pass
    raise CaptureError(f"Cannot read camera {index}. Check that it is connected and close other camera apps.")


@contextmanager
def open_camera(index: int):
    # Backends can emit several native log lines for a missing or busy camera.
    logging = cv2.utils.logging
    previous_log_level = logging.getLogLevel()
    logging.setLogLevel(logging.LOG_LEVEL_SILENT)
    camera = None
    try:
        try:
            camera = cv2.VideoCapture(index)
            opened = camera.isOpened()
        except cv2.error:
            opened = False
        if not opened:
            raise CaptureError(f"Cannot open camera {index}. Check that it is connected and close other camera apps.")

        # Keep the camera streaming so auto-exposure settles before the first scan.
        ready_at = time.monotonic() + 1.0
        while time.monotonic() < ready_at:
            read_camera(camera, index)
        yield camera
    finally:
        try:
            if camera is not None:
                camera.release()
        finally:
            logging.setLogLevel(previous_log_level)


def read_image(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if data:
        frame = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
        if frame is not None:
            return frame
    raise CaptureError(f"Cannot decode image {path}")


def load_classifier(spec: str | None) -> tuple[Classifier, str]:
    if spec is None:
        return classify_color, MODEL
    module, separator, name = spec.partition(":")
    if not separator or not module or not name:
        raise ValueError("--classifier must be module:function")
    try:
        classifier = getattr(import_module(module), name)
    except (ImportError, AttributeError) as error:
        raise ValueError(f"Cannot load classifier {spec}: {error}") from error
    if not callable(classifier):
        raise ValueError(f"Classifier {spec} is not callable")
    return classifier, spec


def report_scan(frame: np.ndarray, fruits: list[dict], *, source: str, model: str, taken_at: str) -> None:
    record = save_scan(frame, fruits, source=source, model=model, taken_at=taken_at)
    print(f"Saved scan {record['id']} ({len(fruits)} fruit)", flush=True)


def live(index: int, classifier: Classifier, model: str) -> None:
    window = "CutieFarm | S: save scan | Q: quit"
    with open_camera(index) as camera:
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        try:
            while True:
                frame = read_camera(camera, index)
                taken_at = store.now_iso()
                fruits = classify_frame(frame, classifier)
                preview = frame.copy()
                for fruit in fruits:
                    x, y, w, h = fruit["bbox"]
                    color = (50, 50, 255) if fruit["label"] == "mold" else (0, 220, 255)
                    cv2.rectangle(preview, (x, y), (x + w - 1, y + h - 1), color, 2)
                    cv2.putText(preview, f"{fruit['id']} {fruit['label']}", (x, max(16, y - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
                cv2.imshow(window, preview)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), ord("Q")):
                    break
                if key in (ord("s"), ord("S")):
                    report_scan(frame, fruits, source="webcam", model=model, taken_at=taken_at)
                if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    break
        finally:
            cv2.destroyAllWindows()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m farm.vision", description="Scan oranges with CutieFarm.")
    parser.add_argument("--classifier", metavar="MODULE:FUNCTION", help="classifier to use on each RGB crop")
    commands = parser.add_subparsers(dest="command", required=True)
    scan = commands.add_parser("scan", help="save one scan")
    source = scan.add_mutually_exclusive_group()
    source.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    source.add_argument("--image", type=Path, help="scan an image file instead of a camera")
    watch = commands.add_parser("watch", help="save scans periodically")
    watch.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    watch.add_argument("--every", type=duration, default="2m", help="interval (default 2m)")
    preview = commands.add_parser("live", help="preview detections, press S to save or Q to quit")
    preview.add_argument("--camera", type=int, default=0, help="camera index (default 0)")
    for command in (scan, watch, preview):
        command.add_argument("--classifier", metavar="MODULE:FUNCTION", default=argparse.SUPPRESS,
                             help="classifier to use on each RGB crop")
    args = parser.parse_args(argv)

    try:
        load_env_file()
        classifier, model = load_classifier(args.classifier)
        if args.command == "live":
            live(args.camera, classifier, model)
        elif args.command == "scan" and args.image is not None:
            frame = read_image(args.image)
            taken_at = store.now_iso()
            report_scan(frame, classify_frame(frame, classifier), source="file", model=model, taken_at=taken_at)
        else:
            while True:
                start = time.monotonic()
                with open_camera(args.camera) as camera:
                    frame = read_camera(camera, args.camera)
                    taken_at = store.now_iso()
                report_scan(frame, classify_frame(frame, classifier), source="webcam", model=model, taken_at=taken_at)
                if args.command == "scan":
                    break
                time.sleep(max(0, start + args.every - time.monotonic()))
    except CaptureError as error:
        print(f"CutieFarm vision: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, cv2.error) as error:
        print("CutieFarm vision:", " ".join(str(error).splitlines()), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
