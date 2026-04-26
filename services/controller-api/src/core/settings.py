from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field


OPENCLAW_SUMMARY_MODEL_DEFAULT = "openai-codex/gpt-5.4"
OPENCLAW_CONFIG_PATH_DEFAULT = Path.home() / ".openclaw" / "openclaw.json"
APP_NAME_DEFAULT = "thirdeye"
THIRDEYE_APPLICATION_SUPPORT_ROOT = Path.home() / "Library" / "Application Support" / "thirdeye"


def _read_openclaw_gateway_token(config_path: Path) -> str:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""

    gateway = payload.get("gateway")
    if not isinstance(gateway, dict):
        return ""
    auth = gateway.get("auth")
    if not isinstance(auth, dict):
        return ""
    token = auth.get("token")
    return token if isinstance(token, str) else ""


class Settings(BaseModel):
    app_name: str = APP_NAME_DEFAULT
    controller_username: str
    controller_password: str
    session_secret: str
    controller_base_url: str = "http://127.0.0.1:8788"
    controller_db_path: Path = THIRDEYE_APPLICATION_SUPPORT_ROOT / "controller" / "controller.db"
    artifacts_root: Path = THIRDEYE_APPLICATION_SUPPORT_ROOT / "artifacts"
    recordings_root: Path = THIRDEYE_APPLICATION_SUPPORT_ROOT / "recordings"
    controller_events_root: Path = THIRDEYE_APPLICATION_SUPPORT_ROOT / "controller-events"
    desktop_base_url: str = "http://127.0.0.1:8790"
    macos_capture_base_url: str = "http://127.0.0.1:8791"
    openclaw_base_url: str = "http://127.0.0.1:18789"
    openclaw_config_path: Path = OPENCLAW_CONFIG_PATH_DEFAULT
    openclaw_gateway_token: str = ""
    openclaw_summary_model: str = OPENCLAW_SUMMARY_MODEL_DEFAULT
    openclaw_summary_timeout_seconds: int = 60
    deepgram_api_key: str = ""
    deepgram_model: str = "nova-3"
    deepgram_language: str | None = None
    deepgram_diarize: bool = True
    deepgram_smart_format: bool = True
    deepgram_interim_results: bool = True
    deepgram_vad_events: bool = True
    deepgram_endpointing_ms: int = 300
    deepgram_utterance_end_ms: int = 1000
    max_duration_minutes: int = 60
    silence_timeout_minutes: int = 5
    enable_auto_stop: bool = False
    controller_cors_origins: list[str] = Field(default_factory=list)
    fake_mode: bool = False
    log_level: str = "INFO"
    tz: str = "UTC"
    recording_size_threshold_mb: int = Field(default=25)

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        openclaw_config_path = Path(env.get("OPENCLAW_CONFIG_PATH", str(OPENCLAW_CONFIG_PATH_DEFAULT))).expanduser()
        return cls(
            controller_username=env.get("CONTROLLER_USERNAME", "admin"),
            controller_password=env.get("CONTROLLER_PASSWORD", "change-me"),
            session_secret=env.get("SESSION_SECRET", env.get("CONTROLLER_PASSWORD", "change-me")),
            controller_base_url=env.get("CONTROLLER_BASE_URL", "http://127.0.0.1:8788"),
            controller_db_path=Path(env.get("CONTROLLER_DB_PATH", str(THIRDEYE_APPLICATION_SUPPORT_ROOT / "controller" / "controller.db"))),
            artifacts_root=Path(env.get("ARTIFACTS_ROOT", str(THIRDEYE_APPLICATION_SUPPORT_ROOT / "artifacts"))),
            recordings_root=Path(env.get("RECORDINGS_ROOT", str(THIRDEYE_APPLICATION_SUPPORT_ROOT / "recordings"))),
            controller_events_root=Path(env.get("CONTROLLER_EVENTS_ROOT", str(THIRDEYE_APPLICATION_SUPPORT_ROOT / "controller-events"))),
            desktop_base_url=env.get("DESKTOP_BASE_URL", "http://127.0.0.1:8790"),
            macos_capture_base_url=env.get("MACOS_CAPTURE_BASE_URL", "http://127.0.0.1:8791"),
            openclaw_base_url=env.get("OPENCLAW_BASE_URL", "http://127.0.0.1:18789"),
            openclaw_config_path=openclaw_config_path,
            openclaw_gateway_token=_read_openclaw_gateway_token(openclaw_config_path) or env.get("OPENCLAW_GATEWAY_TOKEN", ""),
            openclaw_summary_model=env.get("OPENCLAW_SUMMARY_MODEL", OPENCLAW_SUMMARY_MODEL_DEFAULT),
            openclaw_summary_timeout_seconds=int(env.get("OPENCLAW_SUMMARY_TIMEOUT_SECONDS", "60")),
            deepgram_api_key=env.get("DEEPGRAM_API_KEY", ""),
            deepgram_model=env.get("DEEPGRAM_MODEL", "nova-3"),
            deepgram_language=env.get("DEEPGRAM_LANGUAGE") or None,
            deepgram_diarize=env.get("DEEPGRAM_DIARIZE", "true").lower() in {"1", "true", "yes", "on"},
            deepgram_smart_format=env.get("DEEPGRAM_SMART_FORMAT", "true").lower() in {"1", "true", "yes", "on"},
            deepgram_interim_results=env.get("DEEPGRAM_INTERIM_RESULTS", "true").lower() in {"1", "true", "yes", "on"},
            deepgram_vad_events=env.get("DEEPGRAM_VAD_EVENTS", "true").lower() in {"1", "true", "yes", "on"},
            deepgram_endpointing_ms=int(env.get("DEEPGRAM_ENDPOINTING_MS", "300")),
            deepgram_utterance_end_ms=int(env.get("DEEPGRAM_UTTERANCE_END_MS", "1000")),
            max_duration_minutes=int(env.get("MAX_DURATION_MINUTES", "60")),
            silence_timeout_minutes=int(env.get("SILENCE_TIMEOUT_MINUTES", "5")),
            enable_auto_stop=env.get("ENABLE_AUTO_STOP", "false").lower() in {"1", "true", "yes", "on"},
            controller_cors_origins=[
                origin.strip()
                for origin in env.get("CONTROLLER_CORS_ORIGINS", "").split(",")
                if origin.strip()
            ],
            fake_mode=env.get("FAKE_MODE", "false").lower() in {"1", "true", "yes", "on"},
            log_level=env.get("LOG_LEVEL", "INFO"),
            tz=env.get("TZ", "UTC"),
            recording_size_threshold_mb=int(env.get("RECORDING_SIZE_THRESHOLD_MB", "25")),
        )
