from contextlib import nullcontext
from types import SimpleNamespace
import sys
from unittest.mock import Mock

import numpy as np
from PIL import Image, ImageDraw
import pytest

from farm.common import store
from farm.vision import __main__ as cli
from farm.vision.detector import DEFAULT_WEIGHTS, load_detector


@pytest.fixture(autouse=True)
def data_folder(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    monkeypatch.setenv("CUTIEFARM_DATA", str(folder))
    monkeypatch.setattr(cli, "load_env_file", lambda: None)
    return folder


def test_yolo_watch_loads_once_and_filters_orange_boxes(tmp_path, monkeypatch, data_folder):
    weights = tmp_path / "custom.pt"
    weights.touch()
    boxes = SimpleNamespace(
        xyxy=np.array([[116, 6, 173, 60], [-0.5, 4.1, 56, 60], [58, 5, 112, 62], [58, 5, 112, 62]]),
        cls=np.array([42, 42, 3, 42]),
        conf=np.array([0.99, 0.65, 0.98, 0.39]),
    )
    model = Mock(names={3: "person", 42: "orange"})
    model.predict.return_value = [SimpleNamespace(boxes=boxes)]
    yolo = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=yolo))

    image = Image.new("RGB", (170, 66), (100, 100, 100))
    draw = ImageDraw.Draw(image)
    for x, color in [(2, (85, 175, 35)), (60, (246, 113, 20)), (117, (246, 113, 20))]:
        draw.ellipse((x, 7, x + 49, 57), fill=color)
    frame = np.asarray(image)[..., ::-1].copy()
    camera = Mock()
    camera.read.return_value = (True, frame)
    monkeypatch.setattr(cli, "open_camera", lambda index: nullcontext(camera))
    monkeypatch.setattr(cli.time, "sleep", Mock(side_effect=[None, KeyboardInterrupt]))

    assert cli.main(["--yolo-weights", str(weights), "watch", "--min-conf", "0.4"]) == 130
    yolo.assert_called_once_with(str(weights))
    assert model.predict.call_count == 2
    for call in model.predict.call_args_list:
        assert call.kwargs["source"] is frame
        assert call.kwargs["classes"] == [42]
        assert call.kwargs["conf"] == 0.4
    scan = store.latest_scan(max_age=None)
    assert scan["model"] == "yolo-orange+color-heuristic-v1"
    assert [fruit["bbox"] for fruit in scan["fruits"]] == [[0, 4, 56, 56], [116, 6, 54, 54]]
    assert [fruit["label"] for fruit in scan["fruits"]] == ["unripe", "ripe"]
    assert len((data_folder / store.SCANS_FILE).read_text().splitlines()) == 2


@pytest.mark.parametrize("has_weights", [False, True])
def test_automatic_fallback_notices_once(tmp_path, monkeypatch, capsys, has_weights):
    weights = tmp_path / "yolo.pt"
    if has_weights:
        weights.touch()
    monkeypatch.setitem(sys.modules, "ultralytics", None)
    frame = np.full((32, 32, 3), 110, dtype=np.uint8)

    detector, prefix = load_detector(None, weights, 0.35)
    assert prefix == ""
    assert detector(frame) == []
    assert detector(frame) == []
    notice = capsys.readouterr().err.splitlines()
    assert len(notice) == 1
    assert "Using the colour detector" in notice[0]
    with pytest.raises(ValueError, match="Ultralytics" if has_weights else "weights not found"):
        load_detector("yolo", weights, 0.35)


def test_bundled_yolo_runs_on_synthetic_image():
    pytest.importorskip("ultralytics", exc_type=ImportError)
    if not DEFAULT_WEIGHTS.is_file():
        pytest.skip("bundled YOLO weights are missing")
    image = Image.new("RGB", (170, 100), (110, 110, 110))
    ImageDraw.Draw(image).ellipse((50, 15, 119, 84), fill=(246, 113, 20))
    detector, _ = load_detector("yolo", DEFAULT_WEIGHTS, 0.35)
    detector(np.asarray(image)[..., ::-1].copy())
