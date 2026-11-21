"""Find and classify fruit, then publish a scan and its JPEGs."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from math import isfinite
from uuid import uuid4

import cv2
import numpy as np

from farm.bot import peel
from farm.common import store

MODEL = "color-heuristic-v1"
RIPENESS = ("unripe", "ripening", "ripe")
Classifier = Callable[[np.ndarray], tuple[str, str, Mapping[str, float]]]
Box = tuple[int, int, int, int]
Detector = Callable[[np.ndarray], list[Box]]


def classify_color(rgb: np.ndarray) -> tuple[str, str, dict[str, float]]:
    result = peel.classify_rgb(rgb)
    label = result["label"]
    scores = result["scores"]
    if label == "mold":
        # Compatibility with the older peel classifier while the shared contract changes.
        return max(RIPENESS, key=scores.__getitem__), "low", scores
    return label, peel.confidence_level(result["confidence"]), scores


def _split_component(component: np.ndarray, min_area: int) -> list[Box]:
    # The zero border ensures the distance transform sees the contour's edges.
    distance = cv2.distanceTransform(np.pad(component, 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
    cores = (distance >= 0.75 * distance.max()).astype(np.uint8)
    _, labels, stats, _ = cv2.connectedComponentsWithStats(cores)
    large_cores = stats[:, cv2.CC_STAT_AREA] >= 5
    large_cores[0] = False
    if np.count_nonzero(large_cores) < 2:
        return [cv2.boundingRect(component)]

    # Assign each silhouette pixel to its nearest core when the neck between
    # fruit is narrow enough to leave isolated cores.
    seeds = (~large_cores[labels]).astype(np.uint8)
    _, nearest = cv2.distanceTransformWithLabels(seeds, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_CCOMP)
    boxes = []
    for seed in np.unique(nearest[seeds == 0]):
        region = ((nearest == seed) & (component > 0)).astype(np.uint8)
        if cv2.countNonZero(region) >= min_area:
            boxes.append(cv2.boundingRect(region))
    return boxes if len(boxes) >= 2 else [cv2.boundingRect(component)]


def find_boxes(rgb: np.ndarray) -> list[Box]:
    classes, _ = peel.classify_pixels(rgb)
    mask = (classes == peel.FRUIT).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    min_area = max(120, round(mask.size * 0.001))

    boxes = []
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        if cv2.contourArea(contour) < min_area:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        silhouette = np.zeros((h, w), dtype=np.uint8)
        # Fill internal gaps before looking for touching fruit.
        cv2.drawContours(silhouette, [contour], -1, 1, cv2.FILLED, offset=(-x, -y))
        for dx, dy, width, height in _split_component(silhouette, min_area):
            boxes.append((x + dx, y + dy, width, height))
    return boxes


def classify_frame(frame: np.ndarray, classifier: Classifier, detector: Detector) -> list[dict]:
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    fruits = []
    for x, y, w, h in sorted(detector(frame)):
        crop = np.ascontiguousarray(rgb[y:y + h, x:x + w])
        label, confidence, raw_scores = classifier(crop)
        if label == "none":
            continue
        if label not in RIPENESS or confidence not in store.CONFIDENCE:
            raise ValueError("classifier returned an invalid label or confidence level")
        try:
            scores = {key: float(raw_scores[key]) for key in RIPENESS}
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError("classifier must supply a numeric score for each label") from None
        if not all(isfinite(score) for score in scores.values()):
            raise ValueError("classifier scores must be finite")
        fruits.append({"id": len(fruits) + 1, "label": label, "confidence": confidence,
                       "scores": scores, "bbox": [x, y, w, h], "crop": None})
    return fruits


def save_scan(frame: np.ndarray, fruits: list[dict], *, source: str, model: str, taken_at: str) -> dict:
    stamp = datetime.fromisoformat(taken_at).strftime("%Y%m%dT%H%M%S")
    scan_id = f"{stamp}-{uuid4().hex}"
    image = f"scans/{scan_id}.jpg"
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        raise OSError(f"could not encode {image}")
    folder = store.data_dir()
    (folder / "scans").mkdir(exist_ok=True)
    path = folder / image
    file = path.open("xb")
    try:
        with file:
            file.write(encoded.tobytes())
    except OSError:
        path.unlink(missing_ok=True)
        raise

    scan = {"id": scan_id, "taken_at": taken_at, "source": source, "model": model,
            "image": image, "fruits": fruits}
    store.append_scan(scan)
    return scan
