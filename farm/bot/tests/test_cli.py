import logging
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from farm.bot import __main__ as cli
from farm.bot.config import MISSING_TOKEN
from farm.bot.fixtures import FIXTURES
from farm.common import store


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    # Do not pick up a developer's real farm/bot/.env or data folder.
    monkeypatch.setattr(cli, "load_env_file", lambda: None)
    for name in ("TELEGRAM_BOT_TOKEN", "DAILY_AT", "TIMEZONE", "ALLOWED_CHAT_IDS", "SCAN_COMMAND",
                 "FARM_LAT", "FARM_LON", "WATER_BELOW_PCT", "CITRUS_KC"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path / "default-data"))


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_preview_every_fixture(name, capsys):
    assert cli.main(["preview", "--fixture", name]) == 0
    out = capsys.readouterr().out
    assert f"Fixture '{name}' (made-up data" in out
    assert "<b>" not in out


def test_preview_html(capsys):
    assert cli.main(["preview", "--fixture", "mold", "--html"]) == 0
    assert "<b>3 ready to pick, 5 ripening, 1 possible mold (photo attached): remove it today.</b>" in \
        capsys.readouterr().out


def test_preview_data_folder(tmp_path, monkeypatch, capsys):
    folder = tmp_path / "grove"
    folder.mkdir()
    monkeypatch.setenv("CUTIEFARM_DATA", str(folder))
    store.append_scan({"id": "a", "source": "webcam", "model": "color-heuristic-v1", "image": "scans/a.jpg",
                       "fruits": [{"id": 1, "label": "unripe", "confidence": "high", "bbox": [0, 0, 1, 1],
                                   "crop": None}]})
    monkeypatch.setenv("CUTIEFARM_DATA", str(tmp_path / "elsewhere"))
    assert cli.main(["preview", "--data", str(folder)]) == 0
    out = capsys.readouterr().out
    assert str(folder) in out and "Nothing to pick today." in out


def test_preview_missing_folder(tmp_path, capsys):
    assert cli.main(["preview", "--data", str(tmp_path / "nope")]) == 2
    assert "No such folder" in capsys.readouterr().err


def test_run_without_token_explains_botfather(capsys):
    assert cli.main([]) == 2
    err = capsys.readouterr().err
    assert err.strip() == MISSING_TOKEN


def test_run_with_bad_setting(monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "1234567890:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsawQ")
    monkeypatch.setenv("TIMEZONE", "Nowhere/Land")
    assert cli.main(["run"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("Config error: TIMEZONE") and "AAHdq" not in err


def test_polling_failure_exits_one_and_redacts_traceback(monkeypatch, capsys):
    token = "12345:" + "x" * 35
    key = "test-configured-key"
    secrets = [token, quote(token, safe=""), key, "bot99999:" + "a%2F" * 10, "sk-" + "b" * 25]
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", token)
    monkeypatch.setenv("OPENAI_API_KEY", key)
    root = logging.getLogger()
    monkeypatch.setattr(root, "handlers", root.handlers[:])
    for logger in (root, logging.getLogger("httpx"), logging.getLogger("httpcore")):
        original_level = logger.level
        monkeypatch.setattr(logger, "level", original_level)

    def fail(**kwargs):
        raise RuntimeError(" ".join(secrets))

    monkeypatch.setattr("farm.bot.app.build_application", lambda config: SimpleNamespace(run_polling=fail))
    assert cli.main(["run"]) == 1
    err = capsys.readouterr().err
    assert "Telegram bot failed" in err and "RuntimeError" in err and err.count("[redacted]") == len(secrets)
    assert all(secret not in err for secret in secrets)
