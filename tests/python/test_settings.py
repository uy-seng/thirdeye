from __future__ import annotations

from pathlib import Path

from core.settings import Settings


def test_settings_from_env_prefers_host_openclaw_config(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "openclaw.json"
    config_path.write_text(
        '{"gateway":{"auth":{"token":"host-config-token"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "env-token")

    settings = Settings.from_env()

    assert settings.openclaw_gateway_token == "host-config-token"
    assert settings.openclaw_config_path == config_path


def test_settings_from_env_falls_back_to_env_token_when_host_config_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENCLAW_CONFIG_PATH", str(tmp_path / "missing-openclaw.json"))
    monkeypatch.setenv("OPENCLAW_GATEWAY_TOKEN", "env-token")

    settings = Settings.from_env()

    assert settings.openclaw_gateway_token == "env-token"


def test_settings_from_env_reads_macos_capture_base_url(monkeypatch) -> None:
    monkeypatch.setenv("MACOS_CAPTURE_BASE_URL", "http://127.0.0.1:8791")

    settings = Settings.from_env()

    assert settings.macos_capture_base_url == "http://127.0.0.1:8791"


def test_settings_from_env_defaults_to_thirdeye_application_support(monkeypatch) -> None:
    monkeypatch.delenv("CONTROLLER_DB_PATH", raising=False)
    monkeypatch.delenv("ARTIFACTS_ROOT", raising=False)
    monkeypatch.delenv("RECORDINGS_ROOT", raising=False)
    monkeypatch.delenv("CONTROLLER_EVENTS_ROOT", raising=False)

    settings = Settings.from_env()

    assert settings.app_name == "thirdeye"
    assert settings.controller_db_path.parts[-4:] == ("Application Support", "thirdeye", "controller", "controller.db")
    assert settings.artifacts_root.parts[-3:] == ("Application Support", "thirdeye", "artifacts")
    assert settings.recordings_root.parts[-3:] == ("Application Support", "thirdeye", "recordings")
    assert settings.controller_events_root.parts[-3:] == ("Application Support", "thirdeye", "controller-events")
