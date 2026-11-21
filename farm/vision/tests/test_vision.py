from contextlib import nullcontext
from datetime import datetime
import sys
from unittest.mock import Mock

import numpy as np
from PIL import Image, ImageDraw
import pytest

from farm import __main__ as hub
from farm.common import store
from farm.vision import __main__ as cli
from farm.vision.scan import find_boxes


@pytest.fixture(autouse=True)
def data_folder(tmp_path, monkeypatch):
    folder = tmp_path / "data"
    monkeypatch.setenv("CUTIEFARM_DATA", str(folder))
    monkeypatch.setattr(cli, "load_env_file", lambda: None)
    return folder


@pytest.fixture
def orchard():
    image = Image.new("RGB", (520, 140), (110, 110, 110))
    draw = ImageDraw.Draw(image)
    colors = [(85, 175, 35), (240, 216, 30), (246, 113, 20), (246, 113, 20)]
    for x, color in zip((65, 195, 325, 455), colors):
        draw.ellipse((x - 44, 26, x + 44, 114), fill=color)
    draw.ellipse((428, 52, 454, 81), fill=(221, 222, 219))
    draw.ellipse((454, 57, 483, 88), fill=(91, 167, 151))
    draw.rectangle((1, 1, 4, 4), fill=colors[0])  # stray pixels below the area cutoff
    return image


def test_file_scan_saves_a_contract_record(orchard, tmp_path, data_folder):
    path = tmp_path / "oranges.jpg"
    orchard.save(path, quality=98, subsampling=0)

    assert cli.main(["scan", "--image", str(path)]) == 0
    scan = store.latest_scan(max_age=None)
    assert set(scan) == {"id", "taken_at", "source", "model", "image", "fruits", "summary"}
    assert (scan["source"], scan["model"]) == ("file", "color-heuristic-v1")
    assert datetime.fromisoformat(scan["taken_at"]).utcoffset() is not None
    assert scan["summary"] == dict.fromkeys(store.LABELS, 1)
    assert scan["image"] == f"scans/{scan['id']}.jpg"
    with Image.open(data_folder / scan["image"]) as saved:
        assert saved.size == orchard.size
    assert len((data_folder / store.SCANS_FILE).read_text().splitlines()) == 1

    fruits = scan["fruits"]
    assert [fruit["id"] for fruit in fruits] == [1, 2, 3, 4]
    assert [fruit["label"] for fruit in fruits] == list(store.LABELS)
    for fruit, center in zip(fruits, (65, 195, 325, 455)):
        assert set(fruit) == {"id", "label", "confidence", "scores", "bbox", "crop"}
        assert fruit["confidence"] in store.CONFIDENCE
        assert set(fruit["scores"]) == set(store.LABELS)
        assert all(isinstance(score, float) for score in fruit["scores"].values())
        assert fruit["bbox"] == pytest.approx([center - 44, 26, 89, 89], abs=2)

    assert [fruit["crop"] for fruit in fruits[:3]] == [None] * 3
    mold = fruits[3]
    assert mold["crop"] == f"scans/{scan['id']}-4.jpg"
    with Image.open(data_folder / mold["crop"]) as saved:
        assert saved.size == tuple(mold["bbox"][2:])
        assert saved.format == "JPEG"


def test_empty_file_records_an_empty_scan(tmp_path):
    path = tmp_path / "empty.png"
    Image.new("RGB", (240, 140), (100, 100, 100)).save(path)
    assert cli.main(["scan", "--image", str(path)]) == 0
    scan = store.latest_scan(max_age=None)
    assert scan["fruits"] == []
    assert scan["summary"] == dict.fromkeys(store.LABELS, 0)


def test_touching_fruit_split_into_two_boxes():
    image = Image.new("RGB", (220, 130), (110, 110, 110))
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 20, 108, 108), fill=(246, 113, 20))
    draw.ellipse((101, 20, 189, 108), fill=(240, 216, 30))

    left, right = find_boxes(np.asarray(image))
    assert (left[0], right[0] + right[2]) == (20, 190)
    assert 95 < right[0] < 115
    assert 95 < left[0] + left[2] < 115


@pytest.mark.parametrize(("opened", "message"), [(False, "Cannot open camera"), (True, "Cannot read camera")])
def test_unavailable_camera_writes_nothing(opened, message, monkeypatch, capsys, data_folder):
    camera = Mock()
    camera.isOpened.return_value = opened
    camera.read.return_value = (False, None)
    capture = Mock(return_value=camera)
    monkeypatch.setattr(cli.cv2, "VideoCapture", capture)

    assert cli.main(["scan", "--camera", "3"]) == 2
    capture.assert_called_once_with(3)
    camera.release.assert_called_once()
    out, error = capsys.readouterr()
    assert not out
    assert len(error.splitlines()) == 1
    assert f"{message} 3" in error
    assert not data_folder.exists()


def test_invalid_image_writes_nothing(tmp_path, data_folder, capsys):
    path = tmp_path / "bad.jpg"
    path.write_bytes(b"invalid jpeg")
    assert cli.main(["scan", "--image", str(path)]) == 2
    assert "Cannot decode image" in capsys.readouterr().err
    assert not data_folder.exists()


def test_classifier_plugin_receives_rgb_and_sets_model(orchard, tmp_path, monkeypatch):
    path = tmp_path / "oranges.png"
    orchard.save(path)
    scores = dict.fromkeys(store.LABELS, np.float32(0.5))
    plugin = Mock(return_value=("ripening", "medium", scores))
    monkeypatch.setitem(sys.modules, "test_classifier", Mock(classify=plugin))

    assert cli.main(["scan", "--image", str(path), "--classifier", "test_classifier:classify"]) == 0
    assert plugin.call_count == 4
    crop = plugin.call_args_list[0].args[0]
    assert crop.dtype == np.uint8
    assert tuple(crop[44, 44]) == (85, 175, 35)
    scan = store.latest_scan(max_age=None)
    assert scan["model"] == "test_classifier:classify"
    assert [fruit["label"] for fruit in scan["fruits"]] == ["ripening"] * 4


def test_watch_scans_immediately_then_waits(orchard, monkeypatch):
    frame = np.asarray(orchard)[..., ::-1].copy()
    camera = Mock()
    camera.read.return_value = (True, frame)
    monkeypatch.setattr(cli, "open_camera", lambda index: nullcontext(camera))
    monkeypatch.setattr(cli.time, "monotonic", lambda: 0)
    sleep = Mock(side_effect=KeyboardInterrupt)
    monkeypatch.setattr(cli.time, "sleep", sleep)

    assert cli.main(["watch", "--every", "2m"]) == 130
    sleep.assert_called_once_with(120)
    assert store.latest_scan(max_age=None)["source"] == "webcam"


def test_live_s_saves_clean_frame_and_q_exits(orchard, monkeypatch, data_folder):
    frame = np.asarray(orchard)[..., ::-1].copy()
    camera = Mock()
    camera.read.return_value = (True, frame)
    show = Mock()
    destroy = Mock()
    monkeypatch.setattr(cli, "open_camera", lambda index: nullcontext(camera))
    monkeypatch.setattr(cli.cv2, "namedWindow", Mock())
    monkeypatch.setattr(cli.cv2, "getWindowProperty", lambda *args: 1)
    monkeypatch.setattr(cli.cv2, "imshow", show)
    monkeypatch.setattr(cli.cv2, "waitKey", Mock(side_effect=[ord("S"), ord("q")]))
    monkeypatch.setattr(cli.cv2, "destroyAllWindows", destroy)

    assert cli.main(["live"]) == 0
    destroy.assert_called_once()
    assert not np.array_equal(show.call_args.args[1], frame)
    scan = store.latest_scan(max_age=None)
    with Image.open(data_folder / scan["image"]) as saved:
        # The preview rectangle passes through this gray background pixel.
        assert saved.getpixel((21, 26)) == pytest.approx((110, 110, 110), abs=12)
    assert len((data_folder / store.SCANS_FILE).read_text().splitlines()) == 1


@pytest.mark.parametrize(("args", "override", "expected"), [
    ([], None, None),
    (["--vision"], None, [sys.executable, "-m", "farm.vision", "watch"]),
    (["--vision"], "custom-vision --every 30s", ["custom-vision", "--every", "30s"]),
    ([], "custom-vision", ["custom-vision"]),
])
def test_hub_vision_command(args, override, expected, monkeypatch):
    monkeypatch.delenv("VISION_COMMAND", raising=False)
    if override:
        monkeypatch.setenv("VISION_COMMAND", override)
    monkeypatch.setattr(hub, "_load_env", lambda: None)
    run = Mock(return_value=0)
    monkeypatch.setattr(hub, "run", run)

    assert hub.main(["--no-sensors", *args]) == 0
    parts = hub.build_parts(run.call_args.args[0])
    assert [part.command for part in parts if part.name == "vision"] == ([expected] if expected else [])
