from __future__ import annotations

import asyncio
import json
import time

from api.main import iter_live_stream_events, sse_payload
from jobs.models import JobCreate
from jobs.state_machine import JobState


def login_json(client) -> None:
    response = client.post(
        "/api/session/login",
        json={"username": "operator", "password": "secret-pass"},
    )
    assert response.status_code == 200
    assert response.json()["authenticated"] is True


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


def test_session_json_endpoints_report_and_clear_auth_state(client) -> None:
    initial = client.get("/api/session")

    assert initial.status_code == 200
    assert initial.json() == {"authenticated": False, "username": None}

    invalid = client.post(
        "/api/session/login",
        json={"username": "operator", "password": "wrong"},
    )

    assert invalid.status_code == 401
    assert invalid.json() == {"detail": "invalid credentials"}

    login = client.post(
        "/api/session/login",
        json={"username": "operator", "password": "secret-pass"},
    )

    assert login.status_code == 200
    assert login.json() == {"authenticated": True, "username": "operator"}

    current = client.get("/api/session")

    assert current.status_code == 200
    assert current.json() == {"authenticated": True, "username": "operator"}

    logout = client.post("/api/session/logout")

    assert logout.status_code == 200
    assert logout.json() == {"authenticated": False, "username": None}

    after = client.get("/api/session")

    assert after.status_code == 200
    assert after.json() == {"authenticated": False, "username": None}


def test_native_client_token_authenticates_without_session_cookie(client) -> None:
    login = client.post(
        "/api/session/login",
        json={"username": "operator", "password": "secret-pass"},
        headers={"x-thirdeye-client": "macos"},
    )

    assert login.status_code == 200
    token = login.json()["api_token"]
    assert token

    client.cookies.clear()

    header_auth = client.get("/api/settings/health", headers={"authorization": f"Bearer {token}"})
    query_auth = client.get(f"/api/settings/health?auth_token={token}")

    assert header_auth.status_code == 200
    assert query_auth.status_code == 200


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
    login_json(client)

    response = client.get("/api/settings/health")

    assert response.status_code == 200
    assert response.json() == {
        "desktop": {"ok": True, "status": "ok", "details": {"status": "ok", "fake_mode": True}},
        "deepgram": {"ok": True, "status": "configured", "details": {"ok": True, "provider": "fake"}},
        "openclaw": {"ok": True, "status": "ok", "details": {"status": "ok", "provider": "test-double"}},
    }


def test_openclaw_test_endpoint_returns_runtime_probe_details(client) -> None:
    login_json(client)

    response = client.get("/api/settings/test/openclaw")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "provider": "test-double"}


def test_smtp_test_endpoint_is_removed(client) -> None:
    login_json(client)

    response = client.get("/api/settings/test/smtp")

    assert response.status_code == 404


def test_artifacts_overview_lists_jobs_with_artifacts(client) -> None:
    login_json(client)
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
    login_json(client)
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
    login_json(client)
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Recover endpoint missing artifacts"))
    runtime.jobs.update_runtime_fields(job.id, state=JobState.FAILED.value)
    runtime.jobs.update_metadata(job.id, finalization_checkpoint="transcript_compiled")

    response = client.post(f"/api/jobs/{job.id}/recover")

    assert response.status_code == 409
    assert response.json() == {"detail": "job is not recoverable"}


def test_live_stream_sse_bootstraps_snapshot_and_emits_new_events(client) -> None:
    login_json(client)
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
