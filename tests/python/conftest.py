from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from core.settings import OPENCLAW_SUMMARY_MODEL_DEFAULT, Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_name="Local Capture Controller",
        controller_base_url="http://127.0.0.1:8788",
        controller_db_path=tmp_path / "controller.db",
        artifacts_root=tmp_path / "artifacts",
        recordings_root=tmp_path / "recordings",
        controller_events_root=tmp_path / "events",
        desktop_base_url="http://desktop:8790",
        macos_capture_base_url="http://macos-capture:8791",
        openclaw_base_url="http://openclaw:18789",
        openclaw_gateway_token="gateway-token",
        deepgram_api_key="deepgram-token",
        deepgram_model="nova-3",
        deepgram_language=None,
        deepgram_diarize=True,
        deepgram_smart_format=True,
        deepgram_interim_results=True,
        deepgram_vad_events=True,
        deepgram_endpointing_ms=300,
        deepgram_utterance_end_ms=1000,
        openclaw_summary_model=OPENCLAW_SUMMARY_MODEL_DEFAULT,
        openclaw_summary_timeout_seconds=60,
        max_duration_minutes=30,
        silence_timeout_minutes=5,
        enable_auto_stop=False,
        fake_mode=True,
        log_level="DEBUG",
        tz="America/Chicago",
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    app = create_app(settings)
    runtime = app.state.runtime

    async def fake_generate_transcript_summary(
        *, prompt: str, transcript_text: str, title: str, model: str | None = None
    ) -> dict[str, object]:
        return {
            "markdown": "# Summary\n\n- Captured transcript details",
            "provider": f"openclaw/{OPENCLAW_SUMMARY_MODEL_DEFAULT}",
        }

    async def fake_openclaw_health() -> dict[str, object]:
        return {"status": "ok", "provider": "test-double"}

    runtime.openclaw.generate_transcript_summary = fake_generate_transcript_summary
    runtime.openclaw.health = fake_openclaw_health

    with TestClient(app) as test_client:
        yield test_client
