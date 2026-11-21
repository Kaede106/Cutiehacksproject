import sys
import time

from farm.__main__ import CONFIG_ERROR, MAX_RESTARTS, Part, data_lines


def wait(part):
    part.process.wait(timeout=10)


def test_crashing_part_is_restarted_then_marked_failed(tmp_path):
    part = Part("x", [sys.executable, "-c", "raise SystemExit(1)"], tmp_path / "x.log")
    part.start()
    for _ in range(MAX_RESTARTS):
        wait(part)
        part.check()
        assert part.state == "running" and "restarted" in part.note
    wait(part)
    part.check()
    assert part.state == "failed"
    assert "started" in (tmp_path / "x.log").read_text(encoding="utf-8")


def test_settings_error_is_not_restarted(tmp_path):
    part = Part("x", [sys.executable, "-c", f"raise SystemExit({CONFIG_ERROR})"], tmp_path / "x.log")
    part.start()
    wait(part)
    part.check()
    assert part.state == "failed" and "settings" in part.note


def test_stop_ends_a_running_part(tmp_path):
    part = Part("x", [sys.executable, "-c", "import time; time.sleep(60)"], tmp_path / "x.log")
    part.start()
    part.stop()
    assert part.process.poll() is not None and part.state == "stopped"


def test_data_lines_on_an_empty_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    text = "\n".join(data_lines())
    assert "Last scan     none yet" in text and "Last sensors  none yet" in text
