import os

from farm.dashboard import settings as cfg

SECRETS = "TELEGRAM_BOT_TOKEN=123456:SECRETSECRETSECRETSECRETSECRETSECRET\nOPENAI_API_KEY=sk-SECRETSECRETSECRETSECRET\n"


def test_only_allowed_keys_come_from_the_env_file(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        SECRETS + "FARM_LAT=34.5\nFARM_LON=-118.2\nWATER_BELOW_PCT=30\nTIMEZONE=Europe/Madrid\n", encoding="utf-8")
    for key in (*cfg.ALLOWED_KEYS, "TELEGRAM_BOT_TOKEN", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(cfg, "ENV_FILE", env_file)
    cfg.load_env_file()
    try:
        assert "TELEGRAM_BOT_TOKEN" not in os.environ and "OPENAI_API_KEY" not in os.environ
        settings = cfg.load_settings()
        assert settings.irrigation.latitude == 34.5 and settings.irrigation.water_below_pct == 30
        assert settings.timezone.key == "Europe/Madrid" and settings.warnings == ()
    finally:
        for key in cfg.ALLOWED_KEYS:  # load_env_file wrote these straight into os.environ
            os.environ.pop(key, None)


def test_real_environment_wins_and_a_missing_file_is_fine(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("WATER_BELOW_PCT=30\n", encoding="utf-8")
    monkeypatch.setattr(cfg, "ENV_FILE", env_file)
    monkeypatch.setenv("WATER_BELOW_PCT", "42")
    cfg.load_env_file()
    assert cfg.load_settings().irrigation.water_below_pct == 42
    monkeypatch.setattr(cfg, "ENV_FILE", tmp_path / "missing.env")
    cfg.load_env_file()


def test_bad_values_fall_back_with_a_warning():
    settings = cfg.load_settings({"WATER_BELOW_PCT": "banana", "TIMEZONE": "Mars/Base"})
    assert settings.irrigation.water_below_pct == 35.0 and settings.timezone.key == "America/Los_Angeles"
    assert len(settings.warnings) == 2
