import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from farm import __main__ as hub
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


@pytest.mark.parametrize("name", ["bot", "sensors", "vision", "dashboard"])
def test_child_environment_keeps_secrets_only_for_bot(tmp_path, monkeypatch, name):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path))
    popen = Mock()
    monkeypatch.setattr(hub.subprocess, "Popen", popen)
    Part(name, ["unused"], tmp_path / "child.log").start()
    env = popen.call_args.kwargs["env"]
    assert ("TELEGRAM_BOT_TOKEN" in env) == (name == "bot")
    assert ("OPENAI_API_KEY" in env) == (name == "bot")
    assert env["CUTIEFARM_DATA"] == str(tmp_path)


def test_bad_status_tick_does_not_stop_the_hub(monkeypatch, capsys):
    part = Mock(spec=Part)
    part.name, part.state, part.note, part.log_path = "bot", "running", "", None
    part.process = None
    monkeypatch.setattr(hub, "last_line", lambda path: "")
    monkeypatch.setattr(hub, "build_parts", lambda args: [part])
    monkeypatch.setattr(hub, "data_lines", Mock(side_effect=[TypeError("bad record"), ["Recovered data"]]))
    monkeypatch.setattr(hub.time, "sleep", Mock(side_effect=[None, KeyboardInterrupt]))
    assert hub.run(SimpleNamespace()) == 0
    assert part.check.call_count == 2
    part.stop.assert_called_once()
    output = capsys.readouterr().out
    assert "could not render status (TypeError)" in output and "Recovered data" in output


@pytest.mark.parametrize("value", [123, [], "broken", "2026-11-21T12:00:00"])
def test_bad_status_timestamp_does_not_raise(value):
    assert hub._age(value) in ("unknown", "never")
