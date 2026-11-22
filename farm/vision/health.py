"""Fruit health: the ML team's CNN (healthy / citrus canker / melanose) run on each orange crop.

The architecture and preprocessing mirror `src/python/ml/image_classification/initial_prediction.py`
(OrangeCNN, 128x128, normalised to [-1, 1]) and the class order of its dataset (`dataset.py`
CONDITION). That module loads its weights from a hard-coded path at import, so it is not imported
here; the weights are looked up in the places the team keeps them. Without torch or the weights,
`load_health()` returns None and scans simply carry no health field.
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

HEALTH_LABELS = ("healthy", "citrus_canker", "melanose")
_ROOT = Path(__file__).resolve().parents[2]
WEIGHT_CANDIDATES = (
    _ROOT / "src" / "python" / "ml" / "notebooks" / "orange_cnn.pth",
    _ROOT / "src" / "python" / "ml" / "image_classification" / "orange_cnn.pth",
    _ROOT / "src" / "orange_cnn.pth",
)


def _build_model(torch):
    nn = torch.nn

    class OrangeCNN(nn.Module):
        def __init__(self):
            super().__init__()
            self.conv1 = nn.Conv2d(3, 32, kernel_size=3, stride=1, padding=1)
            self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
            self.relu = nn.ReLU()
            self.pool = nn.MaxPool2d(kernel_size=2, stride=2)
            self.adaptive_pool = nn.AdaptiveAvgPool2d((4, 4))
            self.flatten = nn.Flatten()
            self.fc1 = nn.Linear(64 * 4 * 4, 128)
            self.fc2 = nn.Linear(128, 3)

        def forward(self, x):
            x = self.pool(self.relu(self.conv1(x)))
            x = self.pool(self.relu(self.conv2(x)))
            x = self.flatten(self.adaptive_pool(x))
            return self.fc2(self.relu(self.fc1(x)))

    return OrangeCNN()


class HealthClassifier:
    """Callable: RGB uint8 crop -> {"label", "confidence" (high/medium/low), "probability"}."""

    def __init__(self, torch, model):
        self.torch = torch
        self.model = model

    def __call__(self, crop_rgb: np.ndarray) -> dict | None:
        if crop_rgb.size == 0 or min(crop_rgb.shape[:2]) < 8:
            return None
        import cv2
        # The team's own pipeline feeds the CNN OpenCV's BGR crops (YOLO's orig_img), and the model gives
        # sensible answers that way: on a photo of healthy tangerines, BGR input says healthy (~0.99) while
        # RGB input says citrus canker. So match their channel order.
        crop = cv2.cvtColor(crop_rgb, cv2.COLOR_RGB2BGR)
        resized = cv2.resize(crop, (128, 128), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255.0
        tensor = self.torch.from_numpy(((resized - 0.5) / 0.5).transpose(2, 0, 1)).unsqueeze(0)
        with self.torch.no_grad():
            probs = self.torch.softmax(self.model(tensor), dim=1)[0].tolist()
        index = int(np.argmax(probs))
        p = float(probs[index])
        confidence = "high" if p >= 0.8 else "medium" if p >= 0.6 else "low"
        return {"label": HEALTH_LABELS[index], "confidence": confidence, "probability": round(p, 3)}


def load_health(weights: Path | None = None) -> HealthClassifier | None:
    import os
    if os.environ.get("CUTIEFARM_HEALTH", "").strip() == "0":
        return None
    path = weights or next((p for p in WEIGHT_CANDIDATES if p.exists()), None)
    if path is None or not path.exists():
        print("Health check off: orange_cnn.pth not found.", file=sys.stderr)
        return None
    try:
        import torch
    except ImportError:
        print("Health check off: PyTorch is not installed.", file=sys.stderr)
        return None
    model = _build_model(torch)
    model.load_state_dict(torch.load(str(path), map_location="cpu", weights_only=True))
    model.eval()
    return HealthClassifier(torch, model)
