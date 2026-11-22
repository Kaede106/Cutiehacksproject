from pathlib import Path

import numpy as np
import pytest

from farm.vision import health
from farm.vision.scan import classify_frame


def test_health_off_by_env(monkeypatch):
    monkeypatch.setenv("CUTIEFARM_HEALTH", "0")
    assert health.load_health() is None


def test_classify_frame_adds_health_verdicts():
    frame = np.zeros((40, 40, 3), np.uint8)
    detector = lambda f: [(5, 5, 20, 20)]
    classifier = lambda crop: ("ripe", "high", {"unripe": 0.0, "ripening": 0.1, "ripe": 0.9})
    verdict = {"label": "healthy", "confidence": "high", "probability": 0.97}
    fruits = classify_frame(frame, classifier, detector, health=lambda crop: verdict)
    assert fruits[0]["health"] == verdict
    assert "health" not in classify_frame(frame, classifier, detector)[0]


@pytest.mark.skipif(not any(p.exists() for p in health.WEIGHT_CANDIDATES), reason="CNN weights not present")
def test_real_cnn_runs_on_a_crop(monkeypatch):
    pytest.importorskip("torch")
    monkeypatch.delenv("CUTIEFARM_HEALTH", raising=False)
    model = health.load_health()
    out = model(np.full((64, 64, 3), (230, 130, 30), np.uint8))
    assert out["label"] in health.HEALTH_LABELS and 0 <= out["probability"] <= 1
