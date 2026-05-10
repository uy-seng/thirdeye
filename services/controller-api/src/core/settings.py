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
    controller_base_url: str = "http://127.0.0.1:8788"
    controller_db_path: Path = THIRDEYE_APPLICATION_SUPPORT_ROOT / "controller" / "controller.db"
    artifacts_root: Path = THIRDEYE_APPLICATION_SUPPORT_ROOT / "artifacts"
    debug_logs_root: Path = THIRDEYE_APPLICATION_SUPPORT_ROOT / "logs"
    recordings_root: Path = THIRDEYE_APPLICATION_SUPPORT_ROOT / "recordings"
    desktop_sessions_root: Path = THIRDEYE_APPLICATION_SUPPORT_ROOT / "desktop-sessions"
    desktop_sessions_registry_path: Path = THIRDEYE_APPLICATION_SUPPORT_ROOT / "desktop-sessions" / "sessions.json"
    desktop_image: str = "thirdeye-desktop:local"
    desktop_browser_port_start: int = 3000
    desktop_agent_port_start: int = 8790
    max_desktop_sessions: int = 4
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
    silence_timeout_minutes: int = 2
    controller_cors_origins: list[str] = Field(default_factory=list)
    log_level: str = "INFO"
    tz: str = "UTC"

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        openclaw_config_path = Path(env.get("OPENCLAW_CONFIG_PATH", str(OPENCLAW_CONFIG_PATH_DEFAULT))).expanduser()
        return cls(
            controller_base_url=env.get("CONTROLLER_BASE_URL", "http://127.0.0.1:8788"),
            controller_db_path=Path(env.get("CONTROLLER_DB_PATH", str(THIRDEYE_APPLICATION_SUPPORT_ROOT / "controller" / "controller.db"))),
            artifacts_root=Path(env.get("ARTIFACTS_ROOT", str(THIRDEYE_APPLICATION_SUPPORT_ROOT / "artifacts"))),
            debug_logs_root=Path(env.get("DEBUG_LOGS_ROOT", str(THIRDEYE_APPLICATION_SUPPORT_ROOT / "logs"))),
            recordings_root=Path(env.get("RECORDINGS_ROOT", str(THIRDEYE_APPLICATION_SUPPORT_ROOT / "recordings"))),
            desktop_sessions_root=Path(env.get("DESKTOP_SESSIONS_ROOT", str(THIRDEYE_APPLICATION_SUPPORT_ROOT / "desktop-sessions"))),
            desktop_sessions_registry_path=Path(
                env.get("DESKTOP_SESSIONS_REGISTRY_PATH", str(THIRDEYE_APPLICATION_SUPPORT_ROOT / "desktop-sessions" / "sessions.json"))
            ),
            desktop_image=env.get("DESKTOP_IMAGE", "thirdeye-desktop:local"),
            desktop_browser_port_start=int(env.get("DESKTOP_BROWSER_PORT_START", "3000")),
            desktop_agent_port_start=int(env.get("DESKTOP_AGENT_PORT_START", "8790")),
            max_desktop_sessions=int(env.get("MAX_DESKTOP_SESSIONS", "4")),
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
            silence_timeout_minutes=int(env.get("SILENCE_TIMEOUT_MINUTES", "2")),
            controller_cors_origins=[
                origin.strip()
                for origin in env.get("CONTROLLER_CORS_ORIGINS", "").split(",")
                if origin.strip()
            ],
            log_level=env.get("LOG_LEVEL", "INFO"),
            tz=env.get("TZ", "UTC"),
        )
