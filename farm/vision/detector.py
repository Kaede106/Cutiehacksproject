"""Optional Ultralytics detector for COCO oranges."""
from __future__ import annotations

from math import ceil, floor
from pathlib import Path
import sys

import numpy as np

from .scan import Box, Detector, find_boxes

_ROOT = Path(__file__).resolve().parents[2]
# The ML teammates have moved the weights before, so look in each place they have lived.
WEIGHT_CANDIDATES = (
    _ROOT / "src" / "python" / "ml" / "image_classification" / "yolo26n.pt",
    _ROOT / "src" / "yolo26n.pt",
    _ROOT / "ml" / "image-classification" / "yolo26n.pt",
)
DEFAULT_WEIGHTS = next((path for path in WEIGHT_CANDIDATES if path.exists()), WEIGHT_CANDIDATES[0])


class YoloOrangeDetector:
    def __init__(self, model, min_conf: float):
        self.model = model
        self.min_conf = min_conf
        names = model.names
        entries = names.items() if isinstance(names, dict) else enumerate(names)
        self.orange_class = next((int(index) for index, name in entries if name.strip().lower() == "orange"), None)
        if self.orange_class is None:
            raise ValueError("YOLO weights do not define an orange class")

    def __call__(self, frame: np.ndarray) -> list[Box]:
        height, width = frame.shape[:2]
        predictions = self.model.predict(
            source=frame, classes=[self.orange_class], conf=self.min_conf, save=False, verbose=False,
        )
        found = []
        for result in predictions:
            boxes = result.boxes
            for coords, class_id, confidence in zip(boxes.xyxy.tolist(), boxes.cls.tolist(), boxes.conf.tolist()):
                if int(class_id) != self.orange_class or confidence < self.min_conf:
                    continue
                left, top, right, bottom = coords
                x1, y1 = max(0, floor(left)), max(0, floor(top))
                x2, y2 = min(width, ceil(right)), min(height, ceil(bottom))
                if x2 > x1 and y2 > y1:
                    found.append((x1, y1, x2 - x1, y2 - y1))
        return found


def load_detector(mode: str | None, weights: Path, min_conf: float) -> tuple[Detector, str]:
    """Select one detector for the process. The automatic fallback announces itself once."""
    if mode == "color":
        return color_detector, ""

    if not weights.is_file():
        reason = f"YOLO weights not found at {weights}"
    else:
        try:
            from ultralytics import YOLO
        except (ImportError, OSError):
            reason = "Ultralytics could not be imported"
        else:
            return YoloOrangeDetector(YOLO(str(weights)), min_conf), "yolo-orange+"

    if mode == "yolo":
        raise ValueError(reason)

    def fallback(frame: np.ndarray) -> list[Box]:
        nonlocal reason
        if reason:
            print(f"CutieFarm vision: {reason}. Using the colour detector.", file=sys.stderr)
            reason = ""
        return color_detector(frame)

    return fallback, ""


def color_detector(frame: np.ndarray) -> list[Box]:
    return find_boxes(frame[..., ::-1])
