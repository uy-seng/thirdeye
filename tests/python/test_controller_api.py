from __future__ import annotations

import asyncio
import json
import time

from fastapi.testclient import TestClient

from api.main import create_app
from api.main import iter_live_stream_events, sse_payload
from jobs.models import JobCreate
from jobs.state_machine import JobState


def wait_for_stream_line(lines, *, timeout: float = 5.0) -> str:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            line = next(lines)
        except StopIteration as exc:  # pragma: no cover - defensive
            raise AssertionError("stream closed before expected event") from exc
        if line:
            return line
    raise AssertionError("timed out waiting for stream event")


def test_session_json_endpoints_are_removed(client) -> None:
    assert client.get("/api/session").status_code == 404
    assert client.post("/api/session/login", json={"username": "operator", "password": "secret-pass"}).status_code == 404
    assert client.post("/api/session/logout").status_code == 404


def test_controller_routes_do_not_require_login_or_tokens(client) -> None:
    plain = client.get("/api/settings/health")
    header = client.get("/api/settings/health", headers={"authorization": "Bearer ignored"})
    query = client.get("/api/settings/health?auth_token=ignored")

    assert plain.status_code == 200
    assert header.status_code == 200
    assert query.status_code == 200


def test_jobs_api_allows_tauri_dev_origin_for_credentialed_cors(client) -> None:
    response = client.options(
        "/api/jobs/start",
        headers={
            "origin": "http://127.0.0.1:1420",
            "access-control-request-method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_health_endpoint_aggregates_runtime_checks(client) -> None:
    response = client.get("/api/settings/health")

    assert response.status_code == 200
    assert response.json() == {
        "desktop": {"ok": True, "status": "ok", "details": {"status": "ok", "fake_mode": True}},
        "deepgram": {"ok": True, "status": "configured", "details": {"ok": True, "provider": "fake"}},
        "openclaw": {"ok": True, "status": "ok", "details": {"status": "ok", "provider": "test-double"}},
    }


def test_openclaw_test_endpoint_returns_runtime_probe_details(client) -> None:
    response = client.get("/api/settings/test/openclaw")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "test-double"}


def test_artifacts_overview_lists_jobs_with_artifacts(client) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Artifact Overview"))
    paths = runtime.artifacts.job_paths(job.id)
    paths.summary.write_text("# Summary\n", encoding="utf-8")

    response = client.get("/api/artifacts")

    assert response.status_code == 200
    payload = response.json()

    assert payload["jobs"][0]["job"] == runtime.jobs.get_job(job.id).model_dump()
    assert payload["jobs"][0]["artifacts"]["job_id"] == job.id
    assert {
        "name": "summary.md",
        "path": str(paths.summary),
        "size_bytes": paths.summary.stat().st_size,
        "download_url": f"http://127.0.0.1:8788/artifacts/{job.id}/summary.md",
    } in payload["jobs"][0]["artifacts"]["files"]


def test_recover_endpoint_accepts_recoverable_failed_job(client) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Recover endpoint"))
    paths = runtime.artifacts.job_paths(job.id)
    paths.transcript_markdown.write_text("# Transcript\n\nRecovered\n", encoding="utf-8")
    paths.transcript_text.write_text("Recovered\n", encoding="utf-8")
    runtime.jobs.update_runtime_fields(job.id, state=JobState.FAILED.value)
    runtime.jobs.update_metadata(job.id, finalization_checkpoint="transcript_compiled")

    response = client.post(f"/api/jobs/{job.id}/recover")

    assert response.status_code == 202
    assert response.json()["state"] == "recovering"


def test_recover_endpoint_rejects_failed_job_without_post_stop_artifacts(client) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Recover endpoint missing artifacts"))
    runtime.jobs.update_runtime_fields(job.id, state=JobState.FAILED.value)
    runtime.jobs.update_metadata(job.id, finalization_checkpoint="transcript_compiled")

    response = client.post(f"/api/jobs/{job.id}/recover")

    assert response.status_code == 409
    assert response.json() == {"detail": "job is not recoverable"}


def test_live_stream_sse_bootstraps_snapshot_and_emits_new_events(client) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="SSE Reader"))

    runtime.transcript_store.append(
        job.id,
        {
            "type": "Results",
            "is_final": True,
            "start": 12.0,
            "duration": 2.5,
            "channel": {
                "alternatives": [
                    {
                        "transcript": "Committed snapshot row.",
                        "words": [{"speaker": 2, "start": 12.0, "end": 14.5}],
                    }
                ]
            },
        },
    )
    runtime.transcript_store.append(
        job.id,
        {
            "type": "Results",
            "is_final": False,
            "start": 15.0,
            "duration": 1.0,
            "channel": {
                "alternatives": [
                    {
                        "transcript": "Draft snapshot row",
                        "words": [{"speaker": 2, "start": 15.0, "end": 16.0}],
                    }
                ]
            },
        },
    )

    async def exercise_stream() -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
        stream = iter_live_stream_events(runtime, job.id)

        first_payload = await anext(stream)
        second_payload = await anext(stream)
        third_payload = await anext(stream)

        runtime.transcript_store.append(
            job.id,
            {
                "type": "Results",
                "is_final": True,
                "start": 17.0,
                "duration": 1.0,
                "channel": {
                    "alternatives": [
                        {
                            "transcript": "Fresh streamed row.",
                            "words": [{"speaker": 3, "start": 17.0, "end": 18.0}],
                        }
                    ]
                },
            },
        )
        publish_task = asyncio.create_task(
            runtime.transcript_hub.publish(
                job.id,
                {"type": "final", "text": "Fresh streamed row.", "speaker": 3, "start": 17.0, "end": 18.0},
            )
        )
        fourth_payload = await asyncio.wait_for(anext(stream), timeout=1.0)
        await publish_task
        await stream.aclose()
        return first_payload, second_payload, third_payload, fourth_payload

    first_payload, second_payload, third_payload, fourth_payload = asyncio.run(exercise_stream())

    assert json.loads(sse_payload(first_payload).removeprefix("data: ")) == first_payload
    assert first_payload == {"type": "status", "state": "idle"}
    assert second_payload["type"] == "final"
    assert second_payload["text"] == "Committed snapshot row."
    assert third_payload == {"type": "interim", "text": "Draft snapshot row"}
    assert fourth_payload["type"] == "final"
    assert fourth_payload["text"] == "Fresh streamed row."


def test_voice_note_websocket_transcribes_streamed_microphone_audio(client) -> None:
    with client.websocket_connect("/ws/voice-notes/live") as websocket:
        websocket.send_bytes(b"\x00\x01" * 256)
        interim = websocket.receive_json()
        websocket.send_json({"type": "Finalize"})
        final = websocket.receive_json()
        complete = websocket.receive_json()

    assert interim["type"] == "interim"
    assert interim["text"]
    assert final["type"] == "final"
    assert final["text"]
    assert complete == {"type": "complete"}


def test_voice_note_websocket_uses_live_deepgram_path(settings, monkeypatch) -> None:
    class FakeDeepgramSocket:
        def __init__(self) -> None:
            self.messages: asyncio.Queue[str | None] = asyncio.Queue()

        async def send(self, message) -> None:
            if not isinstance(message, str):
                return
            payload = json.loads(message)
            if payload.get("type") == "Finalize":
                await self.messages.put(
                    json.dumps(
                        {
                            "type": "Results",
                            "is_final": True,
                            "start": 0.0,
                            "duration": 1.0,
                            "channel": {"alternatives": [{"transcript": "live voice note", "words": []}]},
                        }
                    )
                )
            if payload.get("type") == "CloseStream":
                await self.messages.put(None)

        def __aiter__(self):
            return self

        async def __anext__(self):
            message = await self.messages.get()
            if message is None:
                raise StopAsyncIteration
            return message

        async def close(self) -> None:
            return None

    async def fake_connect(self, **kwargs):
        return FakeDeepgramSocket()

    monkeypatch.setattr("api.main.DeepgramClient.connect", fake_connect)
    app = create_app(settings.model_copy(update={"fake_mode": False}))

    with TestClient(app) as test_client:
        with test_client.websocket_connect("/ws/voice-notes/live") as websocket:
            websocket.send_bytes(b"\x00\x01" * 256)
            websocket.send_json({"type": "Finalize"})
            final = websocket.receive_json()
            complete = websocket.receive_json()

    assert final == {"type": "final", "text": "live voice note", "speaker": None, "start": 0.0, "end": 1.0}
    assert complete == {"type": "complete"}


def test_voice_note_summary_endpoint_uses_openclaw(client) -> None:
    response = client.post(
        "/api/voice-notes/summary/generate",
        json={
            "title": "Customer call",
            "transcript": "The customer asked for pricing follow-up tomorrow.",
            "prompt": "Summarize this voice note.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["markdown"] == "# Summary\n\n- Captured transcript details"
    assert payload["provider"] == "openclaw/openai-codex/gpt-5.4"


def test_voice_note_summary_endpoint_requires_transcript(client) -> None:
    response = client.post(
        "/api/voice-notes/summary/generate",
        json={"title": "Empty note", "transcript": " ", "prompt": "Summarize this voice note."},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "transcript is required"}
