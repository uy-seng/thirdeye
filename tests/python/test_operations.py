from __future__ import annotations

import asyncio
import sqlite3
import time

from jobs.models import JobCreate


def append_transcript(runtime, job_id: str) -> None:
    runtime.transcript_store.append(
        job_id,
        {
            "type": "Results",
            "is_final": True,
            "start": 0.0,
            "duration": 1.0,
            "channel": {"alternatives": [{"transcript": "Operation transcript", "words": []}]},
        },
    )


def wait_for_metadata_value(client, job_id: str, key: str, target: str, timeout: float = 5.0) -> dict[str, object]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/api/jobs/{job_id}").json()
        if payload.get("metadata_json", {}).get(key) == target:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} metadata {key} never reached {target}")


def operation_rows(settings) -> list[tuple[str, str, str, str | None]]:
    with sqlite3.connect(settings.controller_db_path) as connection:
        return list(
            connection.execute(
                "SELECT job_id, kind, status, error_message FROM operations ORDER BY created_at, id"
            )
        )


def test_summary_rerun_persists_one_idempotent_operation_for_duplicate_requests(client, settings, monkeypatch) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Durable summary operation"))
    append_transcript(runtime, job.id)
    calls = {"count": 0}

    async def slow_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        calls["count"] += 1
        await asyncio.sleep(0.15)
        summary_path = runtime.artifacts.job_paths(job_id).summary
        summary_path.write_text("# Summary\n\nGenerated once\n", encoding="utf-8")
        return str(summary_path)

    monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", slow_rewrite_canonical_summary)

    first = client.post(f"/api/jobs/{job.id}/summary/rerun")
    second = client.post(f"/api/jobs/{job.id}/summary/rerun")

    assert first.status_code == 202
    assert second.status_code == 202
    wait_for_metadata_value(client, job.id, "summary_status", "completed")
    assert calls["count"] == 1
    assert operation_rows(settings) == [(job.id, "summary_rerun", "completed", None)]


def test_summary_rerun_operation_records_failures(client, settings, monkeypatch) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Failed durable summary operation"))
    append_transcript(runtime, job.id)

    async def fail_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        raise RuntimeError("summary unavailable")

    monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", fail_rewrite_canonical_summary)

    response = client.post(f"/api/jobs/{job.id}/summary/rerun")

    assert response.status_code == 202
    wait_for_metadata_value(client, job.id, "summary_status", "failed")
    assert operation_rows(settings) == [(job.id, "summary_rerun", "failed", "summary unavailable")]
