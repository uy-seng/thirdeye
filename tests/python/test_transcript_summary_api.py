from __future__ import annotations

import asyncio
import json
import time

from jobs.models import JobCreate
from transcripts.prompt_service import DEFAULT_CANONICAL_SUMMARY_PROMPT
from conftest import login


def login_json(client) -> None:
    response = client.post(
        "/api/session/login",
        json={"username": "operator", "password": "secret-pass"},
    )
    assert response.status_code == 200
    assert response.json()["authenticated"] is True


def append_transcript(runtime, job_id: str, *, final_text: str = "Committed line", interim_text: str | None = None) -> None:
    runtime.transcript_store.append(
        job_id,
        {
            "type": "Results",
            "is_final": True,
            "start": 5.0,
            "duration": 2.0,
            "channel": {
                "alternatives": [
                    {
                        "transcript": final_text,
                        "words": [{"speaker": 1, "start": 5.0, "end": 7.0}],
                    }
                ]
            },
        },
    )
    if interim_text is not None:
        runtime.transcript_store.append(
            job_id,
            {
                "type": "Results",
                "is_final": False,
                "start": 8.0,
                "duration": 1.0,
                "channel": {
                    "alternatives": [
                        {
                            "transcript": interim_text,
                            "words": [{"speaker": 1, "start": 8.0, "end": 9.0}],
                        }
                    ]
                },
            },
        )


def test_transcript_summary_routes_require_login(client) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Protected Summary"))

    generate = client.post(
        f"/api/jobs/{job.id}/transcript-summary/generate",
        json={"prompt": "Summarize this"},
    )
    save = client.post(
        f"/api/jobs/{job.id}/transcript-summary/save",
        json={"request_id": "missing"},
    )

    assert generate.status_code == 401
    assert generate.json() == {"detail": "authentication required"}
    assert save.status_code == 401
    assert save.json() == {"detail": "authentication required"}


def test_generate_transcript_summary_uses_live_snapshot_for_active_jobs(client, monkeypatch) -> None:
    login_json(client)
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Active Transcript Summary"))
    runtime.jobs.update_runtime_fields(job.id, state="live_streaming")
    append_transcript(runtime, job.id, final_text="Committed line", interim_text="Interim line")

    captured: dict[str, str] = {}

    async def fake_generate_transcript_summary(
        *, prompt: str, transcript_text: str, title: str, model: str | None = None
    ) -> dict[str, str]:
        captured["prompt"] = prompt
        captured["transcript_text"] = transcript_text
        captured["title"] = title
        return {
            "markdown": "# Summary\n\n- Interim summary",
            "provider": "openclaw/openai-codex",
        }

    monkeypatch.setattr(
        runtime.openclaw,
        "generate_transcript_summary",
        fake_generate_transcript_summary,
        raising=False,
    )

    response = client.post(
        f"/api/jobs/{job.id}/transcript-summary/generate",
        json={"prompt": "Summarize decisions and risks"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openclaw/openai-codex"
    assert payload["markdown"] == "# Summary\n\n- Interim summary"
    assert payload["request_id"]
    assert payload["source"] == {"final_block_count": 1, "interim_included": True}
    assert captured["prompt"] == "Summarize decisions and risks"
    assert captured["title"] == "Active Transcript Summary"
    assert "Committed line" in captured["transcript_text"]
    assert "Interim line" in captured["transcript_text"]


def test_generate_transcript_summary_rebuilds_completed_job_snapshot_from_events(client, monkeypatch) -> None:
    login_json(client)
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Completed Transcript Summary"))
    runtime.jobs.update_runtime_fields(job.id, state="completed")
    append_transcript(runtime, job.id, final_text="Recovered final block")
    runtime.transcript_store._snapshots.pop(job.id, None)

    captured: dict[str, str] = {}

    async def fake_generate_transcript_summary(
        *, prompt: str, transcript_text: str, title: str, model: str | None = None
    ) -> dict[str, str]:
        captured["transcript_text"] = transcript_text
        return {
            "markdown": "# Summary\n\nRecovered",
            "provider": "openclaw/openai-codex",
        }

    monkeypatch.setattr(
        runtime.openclaw,
        "generate_transcript_summary",
        fake_generate_transcript_summary,
        raising=False,
    )

    response = client.post(
        f"/api/jobs/{job.id}/transcript-summary/generate",
        json={"prompt": "Summarize the recap"},
    )

    assert response.status_code == 200
    assert response.json()["source"] == {"final_block_count": 1, "interim_included": False}
    assert "Recovered final block" in captured["transcript_text"]


def test_generate_transcript_summary_rejects_blank_prompt(client) -> None:
    login_json(client)
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Blank Prompt"))
    append_transcript(runtime, job.id)

    response = client.post(
        f"/api/jobs/{job.id}/transcript-summary/generate",
        json={"prompt": "   "},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "prompt is required"}


def test_generate_transcript_summary_rejects_empty_snapshot(client) -> None:
    login_json(client)
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Empty Transcript"))

    response = client.post(
        f"/api/jobs/{job.id}/transcript-summary/generate",
        json={"prompt": "Summarize this"},
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "transcript snapshot is empty"}


def test_generate_transcript_summary_surfaces_openclaw_failures(client, monkeypatch) -> None:
    login_json(client)
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="OpenClaw Failure"))
    append_transcript(runtime, job.id)

    async def fail_generate_transcript_summary(
        *, prompt: str, transcript_text: str, title: str, model: str | None = None
    ) -> dict[str, str]:
        raise RuntimeError("OpenClaw LLM unavailable")

    monkeypatch.setattr(
        runtime.openclaw,
        "generate_transcript_summary",
        fail_generate_transcript_summary,
        raising=False,
    )

    response = client.post(
        f"/api/jobs/{job.id}/transcript-summary/generate",
        json={"prompt": "Summarize this"},
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "OpenClaw LLM unavailable"}


def test_save_transcript_summary_persists_cached_result_without_reinvoking_openclaw(client, monkeypatch) -> None:
    login_json(client)
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Save Transcript Summary"))
    append_transcript(runtime, job.id)

    calls = {"count": 0}

    async def fake_generate_transcript_summary(
        *, prompt: str, transcript_text: str, title: str, model: str | None = None
    ) -> dict[str, str]:
        calls["count"] += 1
        return {
            "markdown": "# Prompt Summary\n\nSaved content",
            "provider": "openclaw/openai-codex",
        }

    monkeypatch.setattr(
        runtime.openclaw,
        "generate_transcript_summary",
        fake_generate_transcript_summary,
        raising=False,
    )

    generated = client.post(
        f"/api/jobs/{job.id}/transcript-summary/generate",
        json={"prompt": "Summarize the key points"},
    )

    assert generated.status_code == 200
    request_id = generated.json()["request_id"]

    saved = client.post(
        f"/api/jobs/{job.id}/transcript-summary/save",
        json={"request_id": request_id},
    )

    assert saved.status_code == 200
    payload = saved.json()
    assert payload["name"].startswith("transcript-summary-")
    assert payload["name"].endswith(".md")
    assert payload["download_url"].endswith(f"/artifacts/{job.id}/{payload['name']}")
    assert calls["count"] == 1

    artifacts = client.get(f"/api/jobs/{job.id}/artifacts")
    assert artifacts.status_code == 200
    artifact_names = {item["name"] for item in artifacts.json()["files"]}
    assert payload["name"] in artifact_names

    saved_path = runtime.artifacts.job_root(job.id) / payload["name"]
    assert saved_path.exists()
    assert saved_path.read_text(encoding="utf-8") == "# Prompt Summary\n\nSaved content\n"

    duplicate = client.post(
        f"/api/jobs/{job.id}/transcript-summary/save",
        json={"request_id": request_id},
    )

    assert duplicate.status_code == 404
    assert duplicate.json() == {"detail": "transcript summary request not found"}


def test_saved_transcript_summary_events_do_not_store_prompt_or_inline_content(client, monkeypatch) -> None:
    login_json(client)
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Transcript Summary Events"))
    append_transcript(runtime, job.id)

    async def fake_generate_transcript_summary(
        *, prompt: str, transcript_text: str, title: str, model: str | None = None
    ) -> dict[str, str]:
        return {
            "markdown": "# Summary\n\nPrivate result",
            "provider": "openclaw/openai-codex",
        }

    monkeypatch.setattr(
        runtime.openclaw,
        "generate_transcript_summary",
        fake_generate_transcript_summary,
        raising=False,
    )

    generated = client.post(
        f"/api/jobs/{job.id}/transcript-summary/generate",
        json={"prompt": "Do not persist this raw prompt"},
    )
    assert generated.status_code == 200
    request_id = generated.json()["request_id"]

    saved = client.post(
        f"/api/jobs/{job.id}/transcript-summary/save",
        json={"request_id": request_id},
    )
    assert saved.status_code == 200

    events = [
        json.loads(line)
        for line in runtime.artifacts.job_paths(job.id).controller_events.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    generated_event = next(event for event in events if event["type"] == "transcript_summary_generated")
    saved_event = next(event for event in events if event["type"] == "transcript_summary_saved")

    assert generated_event["job_id"] == job.id
    assert generated_event["request_id"] == request_id
    assert "prompt" not in generated_event
    assert "markdown" not in generated_event

    assert saved_event["job_id"] == job.id
    assert saved_event["request_id"] == request_id
    assert saved_event["artifact_name"] == saved.json()["name"]
    assert "prompt" not in saved_event
    assert "markdown" not in saved_event


def test_rerun_summary_route_uses_openclaw_and_rewrites_canonical_summary(client, monkeypatch) -> None:
    login(client)
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Canonical Summary", summary_model="custom-summary-model"))
    paths = runtime.artifacts.job_paths(job.id)
    append_transcript(runtime, job.id, final_text="Canonical transcript line")

    captured: dict[str, str] = {}

    async def fake_generate_transcript_summary(
        *, prompt: str, transcript_text: str, title: str, model: str | None = None
    ) -> dict[str, str]:
        captured["prompt"] = prompt
        captured["transcript_text"] = transcript_text
        captured["title"] = title
        captured["model"] = model or ""
        return {
            "markdown": "# Summary\n\nCanonical recap\n",
            "provider": "openclaw/openai-codex",
        }

    monkeypatch.setattr(
        runtime.openclaw,
        "generate_transcript_summary",
        fake_generate_transcript_summary,
        raising=False,
    )

    response = client.post(f"/api/jobs/{job.id}/summary/rerun")

    assert response.status_code == 202
    assert response.json()["metadata_json"]["summary_status"] == "running"
    for _ in range(100):
        payload = client.get(f"/api/jobs/{job.id}").json()
        if payload["metadata_json"].get("summary_status") == "completed":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("summary rerun did not complete")

    assert paths.summary.read_text(encoding="utf-8") == "# Summary\n\nCanonical recap\n"
    assert captured["prompt"] == DEFAULT_CANONICAL_SUMMARY_PROMPT
    assert captured["title"] == "Canonical Summary"
    assert captured["model"] == "custom-summary-model"
    assert "Canonical transcript line" in captured["transcript_text"]


def test_rerun_summary_route_falls_back_from_legacy_fake_summary_model(client, monkeypatch) -> None:
    login(client)
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Legacy Canonical Summary", summary_model="fake-summary"))
    append_transcript(runtime, job.id, final_text="Legacy transcript line")

    captured: dict[str, str] = {}

    async def fake_generate_transcript_summary(
        *, prompt: str, transcript_text: str, title: str, model: str | None = None
    ) -> dict[str, str]:
        captured["model"] = model or ""
        return {
            "markdown": "# Summary\n\nCanonical recap\n",
            "provider": "openclaw/openai-codex",
        }

    monkeypatch.setattr(
        runtime.openclaw,
        "generate_transcript_summary",
        fake_generate_transcript_summary,
        raising=False,
    )

    response = client.post(f"/api/jobs/{job.id}/summary/rerun")

    assert response.status_code == 202
    for _ in range(100):
        payload = client.get(f"/api/jobs/{job.id}").json()
        if payload["metadata_json"].get("summary_status") == "completed":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("summary rerun did not complete")

    assert captured["model"] == runtime.settings.openclaw_summary_model


def test_duplicate_summary_rerun_requests_reuse_existing_background_run(client, monkeypatch) -> None:
    login(client)
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Canonical Summary Reuse"))
    append_transcript(runtime, job.id, final_text="Canonical transcript line")

    calls = {"count": 0}

    async def slow_generate_transcript_summary(
        *, prompt: str, transcript_text: str, title: str, model: str | None = None
    ) -> dict[str, str]:
        calls["count"] += 1
        await asyncio.sleep(0.15)
        return {
            "markdown": "# Summary\n\nCanonical recap\n",
            "provider": "openclaw/openai-codex",
        }

    monkeypatch.setattr(
        runtime.openclaw,
        "generate_transcript_summary",
        slow_generate_transcript_summary,
        raising=False,
    )

    first = client.post(f"/api/jobs/{job.id}/summary/rerun")
    second = client.post(f"/api/jobs/{job.id}/summary/rerun")

    assert first.status_code == 202
    assert second.status_code == 202
    for _ in range(100):
        payload = client.get(f"/api/jobs/{job.id}").json()
        if payload["metadata_json"].get("summary_status") == "completed":
            break
        time.sleep(0.02)
    else:
        raise AssertionError("summary rerun did not complete")

    assert calls["count"] == 1
