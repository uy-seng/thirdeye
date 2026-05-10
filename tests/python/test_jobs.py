from __future__ import annotations

import asyncio
import time

import httpx

from jobs.models import JobCreate
from jobs.state_machine import JobState


def wait_for_state(client, job_id: str, target: str, timeout: float = 5.0) -> dict[str, object]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        payload = response.json()
        if payload["state"] == target:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} never reached state {target}")


def wait_for_metadata_value(client, job_id: str, key: str, target: str, timeout: float = 5.0) -> dict[str, object]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        payload = response.json()
        metadata = payload.get("metadata_json", {})
        if metadata.get(key) == target:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} metadata {key} never reached {target}")


def create_desktop_session(client, label: str = "Test desktop") -> dict[str, object]:
    response = client.post("/api/desktops", json={"label": label})
    assert response.status_code == 200
    return response.json()


def test_cleanup_job_removes_artifacts_and_recordings_but_keeps_job(client) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Cleanup Candidate"))
    runtime.jobs.update_runtime_fields(job.id, state=JobState.FAILED.value)

    paths = runtime.artifacts.job_paths(job.id)
    paths.summary.write_text("# Summary\n", encoding="utf-8")
    recording_root = runtime.settings.recordings_root / "jobs" / job.id
    recording_root.mkdir(parents=True, exist_ok=True)
    (recording_root / "recording.mp4").write_text("binary", encoding="utf-8")

    response = client.post(f"/api/jobs/{job.id}/cleanup")

    assert response.status_code == 200
    assert response.json()["id"] == job.id
    assert runtime.jobs.get_job(job.id).id == job.id
    assert not paths.root.exists()
    assert not recording_root.exists()


def test_delete_job_removes_job_record_transitions_and_files(client) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Delete Candidate"))
    runtime.jobs.transition_job(job.id, JobState.PENDING_START, "test")
    runtime.jobs.fail_job(job.id, "test", "failed on purpose")

    paths = runtime.artifacts.job_paths(job.id)
    paths.summary.write_text("# Summary\n", encoding="utf-8")
    recording_root = runtime.settings.recordings_root / "jobs" / job.id
    recording_root.mkdir(parents=True, exist_ok=True)
    (recording_root / "recording.mp4").write_text("binary", encoding="utf-8")

    response = client.post(f"/api/jobs/{job.id}/delete")

    assert response.status_code == 200
    assert response.json()["id"] == job.id
    assert job.id not in {item.id for item in runtime.jobs.list_jobs()}
    assert runtime.jobs.list_transitions(job.id) == []
    assert not paths.root.exists()
    assert not recording_root.exists()


def test_start_job_rejects_second_active_capture(client) -> None:
    create_desktop_session(client)

    first = client.post(
        "/api/jobs/start",
        json={"title": "Authorized public livestream"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/jobs/start",
        json={"title": "Another public livestream"},
    )
    assert second.status_code == 409


def test_start_job_allows_this_mac_while_isolated_desktop_is_active(client) -> None:
    create_desktop_session(client)
    isolated = client.post(
        "/api/jobs/start",
        json={"title": "Isolated desktop livestream"},
    )
    assert isolated.status_code == 200

    local = client.post(
        "/api/jobs/start",
        json={
            "title": "This Mac livestream",
            "capture_backend": "macos_local",
            "capture_target": {
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
        },
    )

    assert local.status_code == 200
    assert local.json()["capture_backend"] == "macos_local"


def test_start_job_allows_isolated_desktop_while_this_mac_is_active(client) -> None:
    desktop = create_desktop_session(client, "Isolated desktop")
    local = client.post(
        "/api/jobs/start",
        json={
            "title": "This Mac livestream",
            "capture_backend": "macos_local",
            "capture_target": {
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
        },
    )
    assert local.status_code == 200

    isolated = client.post(
        "/api/jobs/start",
        json={
            "title": "Isolated desktop livestream",
            "capture_backend": "docker_desktop",
            "capture_target": {"id": desktop["target_id"], "kind": "desktop", "label": "Isolated desktop"},
        },
    )

    assert isolated.status_code == 200
    assert isolated.json()["capture_backend"] == "docker_desktop"


def test_start_job_rejects_second_this_mac_capture(client) -> None:
    first = client.post(
        "/api/jobs/start",
        json={
            "title": "First This Mac livestream",
            "capture_backend": "macos_local",
            "capture_target": {
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/api/jobs/start",
        json={
            "title": "Second This Mac livestream",
            "capture_backend": "macos_local",
            "capture_target": {
                "id": "window:notes",
                "kind": "window",
                "label": "Notes",
                "app_bundle_id": "com.apple.Notes",
                "app_name": "Notes",
                "window_id": "notes",
            },
        },
    )

    assert second.status_code == 409
    assert second.json() == {"detail": "only one active This Mac capture is allowed"}


def test_start_job_rejects_unknown_payload_fields(client) -> None:

    start = client.post(
        "/api/jobs/start",
        json={"title": "Authorized public livestream", "legacy_contact": "person"},
    )

    assert start.status_code == 422


def test_start_job_failure_marks_job_failed_and_allows_retry(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    create_desktop_session(client)
    original_start_live_audio = runtime.capture.desktop_client.start_live_audio

    async def fail_start_live_audio(
        job_id: str,
        target: dict[str, object],
        mute_target_audio: bool = False,
    ) -> dict[str, object]:
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(runtime.capture.desktop_client, "start_live_audio", fail_start_live_audio)

    failed = client.post(
        "/api/jobs/start",
        json={"title": "Authorized public livestream"},
    )
    assert failed.status_code == 502
    assert "timed out" in failed.json()["detail"]

    jobs = client.get("/api/jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["state"] == "failed"
    assert "timed out" in jobs[0]["error_message"]

    monkeypatch.setattr(runtime.capture.desktop_client, "start_live_audio", original_start_live_audio)

    retry = client.post(
        "/api/jobs/start",
        json={"title": "Retry public livestream"},
    )
    assert retry.status_code == 200


def test_start_job_deepgram_auth_failure_fails_job_and_stops_capture(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    backend = runtime.capture.capture_backends.require("macos_local")

    async def fail_start(job_id: str, stream_factory, job_options: dict[str, object], source: str = "system") -> None:
        raise RuntimeError("Deepgram rejected the API key. Check DEEPGRAM_API_KEY in .env.")

    monkeypatch.setattr(runtime.capture.relay_manager, "start", fail_start)

    failed = client.post(
        "/api/jobs/start",
        json={
            "title": "Deepgram auth failure",
            "capture_backend": "macos_local",
            "capture_target": {
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
        },
    )

    assert failed.status_code == 502
    assert failed.json()["detail"] == "Deepgram rejected the API key. Check DEEPGRAM_API_KEY in .env."
    assert runtime.jobs.active_jobs() == []
    status = asyncio.run(backend.status({"id": "display:main"}))
    assert status["recording"]["running"] is False
    assert status["live_audio"]["running"] is False


def test_live_websocket_rebroadcasts_and_stop_finalizes_artifacts(client) -> None:
    create_desktop_session(client)
    start = client.post("/api/jobs/start", json={"title": "Authorized public livestream"})
    assert start.status_code == 200
    job_id = start.json()["id"]

    with client.websocket_connect(f"/ws/jobs/{job_id}/live") as websocket:
        first = websocket.receive_json()
        second = websocket.receive_json()
        assert first["type"] == "status"
        assert second["type"] in {"interim", "final"}

    stop = client.post(f"/api/jobs/{job_id}/stop")
    assert stop.status_code == 202

    payload = wait_for_metadata_value(client, job_id, "summary_status", "completed")
    assert payload["state"] == "completed"
    assert payload["summary_path"].endswith("summary.md")
    paths = client.app.state.runtime.artifacts.job_paths(job_id)

    artifacts = client.get(f"/api/jobs/{job_id}/artifacts").json()
    artifact_names = {item["name"] for item in artifacts["files"]}
    assert {
        "recording.mp4",
        "transcript.md",
        "transcript.json",
        "summary.md",
        "deepgram-events.jsonl",
        "controller-events.jsonl",
    } <= artifact_names
    assert "metadata.json" not in artifact_names
    assert "transcript.txt" not in artifact_names
    assert paths.transcript_json == paths.logs_root / "transcript.json"
    assert paths.deepgram_events == paths.logs_root / "deepgram-events.jsonl"
    assert paths.controller_events == paths.logs_root / "controller-events.jsonl"
    assert paths.metadata == paths.logs_root / "metadata.json"
    assert not (paths.root / "metadata.json").exists()
    assert not (paths.root / "transcript.txt").exists()
    assert not (paths.root / "transcript.json").exists()
    assert not (paths.root / "deepgram-events.jsonl").exists()
    assert not (paths.root / "controller-events.jsonl").exists()
    assert paths.transcript_json.exists()
    assert paths.deepgram_events.exists()
    assert paths.controller_events.exists()
    assert paths.metadata.exists()
    assert client.get(f"/artifacts/{job_id}/metadata.json").status_code == 404
    for debug_name in {"transcript.json", "deepgram-events.jsonl", "controller-events.jsonl"}:
        artifact = next(item for item in artifacts["files"] if item["name"] == debug_name)
        assert "/logs/jobs/" in artifact["path"]
        download = client.get(f"/artifacts/{job_id}/{debug_name}")
        assert download.status_code == 200


def test_start_job_can_skip_screen_recording_while_keeping_transcript_and_summary(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    create_desktop_session(client)
    backend = runtime.capture.capture_backends.require("docker_desktop")

    async def unexpected_start_recording(job_id: str, output_file: str, target: dict[str, object]) -> dict[str, object]:
        raise AssertionError("screen recording should not start")

    async def unexpected_stop_recording(job_id: str, output_file: str, target: dict[str, object]) -> dict[str, object]:
        raise AssertionError("screen recording should not stop")

    monkeypatch.setattr(backend, "start_recording", unexpected_start_recording)
    monkeypatch.setattr(backend, "stop_recording", unexpected_stop_recording)

    start = client.post(
        "/api/jobs/start",
        json={"title": "Transcript and summary only", "record_screen": False},
    )

    assert start.status_code == 200
    job_id = start.json()["id"]

    stop = client.post(f"/api/jobs/{job_id}/stop")

    assert stop.status_code == 202
    payload = wait_for_metadata_value(client, job_id, "summary_status", "completed")
    paths = runtime.artifacts.job_paths(job_id)
    artifacts = client.get(f"/api/jobs/{job_id}/artifacts").json()
    artifact_names = {item["name"] for item in artifacts["files"]}
    assert payload["state"] == "completed"
    assert payload["recording_path"] is None
    assert payload["metadata_json"]["session_preferences"]["record_screen"] is False
    assert payload["metadata_json"]["session_preferences"]["generate_summary"] is True
    assert payload["metadata_json"]["session_preferences"]["notify_on_inactivity"] is True
    assert not paths.recording.exists()
    assert "recording.mp4" not in artifact_names
    assert "transcript.md" in artifact_names
    assert "transcript.txt" not in artifact_names
    assert "summary.md" in artifact_names


def test_start_job_forwards_muted_target_audio_to_capture_backend(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    backend = runtime.capture.capture_backends.require("macos_local")
    calls: list[tuple[str, bool]] = []

    async def start_recording(
        job_id: str,
        output_file: str,
        target: dict[str, object],
        mute_target_audio: bool = False,
    ) -> dict[str, object]:
        calls.append(("recording", mute_target_audio))
        return {"pid": 1111, "output_file": output_file}

    async def start_live_audio(
        job_id: str,
        target: dict[str, object],
        mute_target_audio: bool = False,
    ) -> dict[str, object]:
        calls.append(("live_audio", mute_target_audio))
        return {"pid": 2222}

    monkeypatch.setattr(backend, "start_recording", start_recording)
    monkeypatch.setattr(backend, "start_live_audio", start_live_audio)

    response = client.post(
        "/api/jobs/start",
        json={
            "title": "Muted Chrome capture",
            "capture_backend": "macos_local",
            "mute_target_audio": True,
            "capture_target": {
                "id": "application:chrome",
                "kind": "application",
                "label": "Google Chrome",
                "app_bundle_id": "com.google.Chrome",
                "app_name": "Google Chrome",
                "app_pid": 4242,
            },
        },
    )

    assert response.status_code == 200
    assert calls == [("recording", True), ("live_audio", True)]


def test_start_job_keeps_processed_microphone_out_of_capture_helper(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    backend = runtime.capture.capture_backends.require("macos_local")
    calls: list[tuple[str, bool]] = []

    async def start_recording(
        job_id: str,
        output_file: str,
        target: dict[str, object],
        mute_target_audio: bool = False,
    ) -> dict[str, object]:
        calls.append(("recording", mute_target_audio))
        return {"pid": 1111, "output_file": output_file}

    async def start_live_audio(
        job_id: str,
        target: dict[str, object],
        mute_target_audio: bool = False,
    ) -> dict[str, object]:
        calls.append(("live_audio", mute_target_audio))
        return {"pid": 2222}

    monkeypatch.setattr(backend, "start_recording", start_recording)
    monkeypatch.setattr(backend, "start_live_audio", start_live_audio)

    response = client.post(
        "/api/jobs/start",
        json={
            "title": "Microphone capture",
            "capture_backend": "macos_local",
            "record_microphone": True,
            "capture_target": {
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
        },
    )

    assert response.status_code == 200
    assert calls == [("recording", False), ("live_audio", False)]
    assert response.json()["metadata_json"]["session_preferences"]["record_microphone"] is True


def test_start_job_with_processed_microphone_starts_only_system_relay(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    started_sources: list[str] = []

    async def fake_start(job_id: str, stream_factory, job_options: dict[str, object], source: str = "system") -> None:
        started_sources.append(source)

    monkeypatch.setattr(runtime.capture.relay_manager, "start", fake_start)

    response = client.post(
        "/api/jobs/start",
        json={
            "title": "Two source capture",
            "capture_backend": "macos_local",
            "capture_target": {
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
            "record_screen": False,
            "record_microphone": True,
            "generate_summary": False,
        },
    )

    assert response.status_code == 200
    assert started_sources == ["system"]


def test_start_job_accepts_processed_microphone_with_app_audio_mute(client) -> None:
    response = client.post(
        "/api/jobs/start",
        json={
            "title": "Processed microphone and muted app",
            "capture_backend": "macos_local",
            "record_microphone": True,
            "mute_target_audio": True,
            "capture_target": {
                "id": "application:chrome",
                "kind": "application",
                "label": "Google Chrome",
                "app_bundle_id": "com.google.Chrome",
                "app_name": "Google Chrome",
                "app_pid": 4242,
            },
        },
    )

    assert response.status_code == 200
    preferences = response.json()["metadata_json"]["session_preferences"]
    assert preferences["record_microphone"] is True
    assert preferences["mute_target_audio"] is True


def test_mute_target_audio_endpoint_updates_active_local_app_capture_after_backend_ack(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(
        JobCreate(
            title="Runtime mute",
            capture_backend="macos_local",
            mute_target_audio=True,
            capture_target={
                "id": "application:chrome",
                "kind": "application",
                "label": "Google Chrome",
                "app_bundle_id": "com.google.Chrome",
                "app_name": "Google Chrome",
                "app_pid": 4242,
            },
        )
    )
    runtime.jobs.transition_job(job.id, JobState.PENDING_START, "test")
    runtime.jobs.transition_job(job.id, JobState.RECORDING, "test")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAM_CONNECTING, "test")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAMING, "test")
    backend = runtime.capture_backends.require("macos_local")
    calls: list[tuple[str, bool]] = []

    async def set_target_audio_muted(job_id: str, target: dict[str, object], mute_target_audio: bool) -> dict[str, object]:
        calls.append((job_id, mute_target_audio))
        return {"pid": 4321, "mute_target_audio": mute_target_audio}

    monkeypatch.setattr(backend, "set_target_audio_muted", set_target_audio_muted)

    response = client.post(f"/api/jobs/{job.id}/mute-target-audio", json={"mute_target_audio": False})

    assert response.status_code == 200
    assert calls == [(job.id, False)]
    assert response.json()["metadata_json"]["session_preferences"]["mute_target_audio"] is False
    assert runtime.jobs.get_job(job.id).metadata_json["session_preferences"]["mute_target_audio"] is False


def test_mute_target_audio_endpoint_is_idempotent_when_state_already_matches(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(
        JobCreate(
            title="Runtime mute no-op",
            capture_backend="macos_local",
            mute_target_audio=True,
            capture_target={
                "id": "window:chrome-1",
                "kind": "window",
                "label": "Google Chrome",
                "app_bundle_id": "com.google.Chrome",
                "app_name": "Google Chrome",
                "app_pid": 4242,
                "window_id": "chrome-1",
            },
        )
    )
    runtime.jobs.transition_job(job.id, JobState.PENDING_START, "test")
    runtime.jobs.transition_job(job.id, JobState.RECORDING, "test")
    backend = runtime.capture_backends.require("macos_local")

    async def unexpected_set_target_audio_muted(job_id: str, target: dict[str, object], mute_target_audio: bool) -> dict[str, object]:
        raise AssertionError("matching mute state should not call the capture helper")

    monkeypatch.setattr(backend, "set_target_audio_muted", unexpected_set_target_audio_muted)

    response = client.post(f"/api/jobs/{job.id}/mute-target-audio", json={"mute_target_audio": True})

    assert response.status_code == 200
    assert response.json()["metadata_json"]["session_preferences"]["mute_target_audio"] is True


def test_mute_target_audio_endpoint_rejects_inactive_job(client) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(
        JobCreate(
            title="Inactive mute",
            capture_backend="macos_local",
            capture_target={
                "id": "application:chrome",
                "kind": "application",
                "label": "Google Chrome",
                "app_pid": 4242,
            },
        )
    )

    response = client.post(f"/api/jobs/{job.id}/mute-target-audio", json={"mute_target_audio": True})

    assert response.status_code == 409
    assert response.json() == {"detail": "capture must be recording before changing mute"}


def test_mute_target_audio_endpoint_rejects_unsupported_backend_and_target(client) -> None:
    runtime = client.app.state.runtime
    docker_job = runtime.jobs.create_job(JobCreate(title="Docker mute"))
    runtime.jobs.transition_job(docker_job.id, JobState.PENDING_START, "test")
    runtime.jobs.transition_job(docker_job.id, JobState.RECORDING, "test")

    docker_response = client.post(f"/api/jobs/{docker_job.id}/mute-target-audio", json={"mute_target_audio": True})

    assert docker_response.status_code == 400
    assert docker_response.json() == {"detail": "runtime mute is only available for This Mac capture"}

    runtime.jobs.fail_job(docker_job.id, "test", "end active capture")
    display_job = runtime.jobs.create_job(
        JobCreate(
            title="Display mute",
            capture_backend="macos_local",
            capture_target={
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
        )
    )
    runtime.jobs.transition_job(display_job.id, JobState.PENDING_START, "test")
    runtime.jobs.transition_job(display_job.id, JobState.RECORDING, "test")

    display_response = client.post(f"/api/jobs/{display_job.id}/mute-target-audio", json={"mute_target_audio": True})

    assert display_response.status_code == 400
    assert display_response.json() == {"detail": "runtime mute requires an app or window target"}


def test_record_microphone_endpoint_updates_processed_microphone_preference_without_backend_call(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(
        JobCreate(
            title="Runtime microphone",
            capture_backend="macos_local",
            capture_target={
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
        )
    )
    runtime.jobs.transition_job(job.id, JobState.PENDING_START, "test")
    runtime.jobs.transition_job(job.id, JobState.RECORDING, "test")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAM_CONNECTING, "test")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAMING, "test")
    started_sources: list[str] = []

    async def fake_start(job_id: str, stream_factory, job_options: dict[str, object], source: str = "system") -> None:
        started_sources.append(source)

    monkeypatch.setattr(runtime.capture.relay_manager, "start", fake_start)

    response = client.post(
        f"/api/jobs/{job.id}/record-microphone",
        json={"record_microphone": True},
    )

    assert response.status_code == 200
    assert started_sources == []
    assert response.json()["metadata_json"]["session_preferences"]["record_microphone"] is True
    assert "echo_cancellation_enabled" not in response.json()["metadata_json"]["session_preferences"]
    assert runtime.jobs.get_job(job.id).metadata_json["session_preferences"]["record_microphone"] is True


def test_record_microphone_endpoint_disables_processed_microphone_without_backend_call(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(
        JobCreate(
            title="Runtime microphone stop",
            capture_backend="macos_local",
            record_microphone=True,
            capture_target={
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
        )
    )
    runtime.jobs.transition_job(job.id, JobState.PENDING_START, "test")
    runtime.jobs.transition_job(job.id, JobState.RECORDING, "test")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAM_CONNECTING, "test")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAMING, "test")
    stopped_sources: list[str | None] = []

    async def fake_stop(job_id: str, source: str | None = None) -> None:
        stopped_sources.append(source)

    monkeypatch.setattr(runtime.capture.relay_manager, "stop", fake_stop)

    response = client.post(f"/api/jobs/{job.id}/record-microphone", json={"record_microphone": False})

    assert response.status_code == 200
    assert stopped_sources == []
    assert response.json()["metadata_json"]["session_preferences"]["record_microphone"] is False


def test_record_microphone_endpoint_is_idempotent_when_state_already_matches(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(
        JobCreate(
            title="Runtime microphone no-op",
            capture_backend="macos_local",
            record_microphone=True,
            capture_target={
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
        )
    )
    runtime.jobs.transition_job(job.id, JobState.PENDING_START, "test")
    runtime.jobs.transition_job(job.id, JobState.RECORDING, "test")

    response = client.post(
        f"/api/jobs/{job.id}/record-microphone",
        json={"record_microphone": True},
    )

    assert response.status_code == 200
    assert response.json()["metadata_json"]["session_preferences"]["record_microphone"] is True


def test_record_microphone_endpoint_rejects_inactive_job(client) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(
        JobCreate(
            title="Inactive microphone",
            capture_backend="macos_local",
            capture_target={
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
        )
    )

    response = client.post(f"/api/jobs/{job.id}/record-microphone", json={"record_microphone": True})

    assert response.status_code == 409
    assert response.json() == {"detail": "capture must be recording before changing microphone"}


def test_record_microphone_endpoint_rejects_unsupported_backend_but_allows_muted_app_audio(client) -> None:
    runtime = client.app.state.runtime
    docker_job = runtime.jobs.create_job(JobCreate(title="Docker microphone"))
    runtime.jobs.transition_job(docker_job.id, JobState.PENDING_START, "test")
    runtime.jobs.transition_job(docker_job.id, JobState.RECORDING, "test")

    docker_response = client.post(f"/api/jobs/{docker_job.id}/record-microphone", json={"record_microphone": True})

    assert docker_response.status_code == 400
    assert docker_response.json() == {"detail": "runtime microphone recording is only available for This Mac capture"}

    runtime.jobs.fail_job(docker_job.id, "test", "end active capture")
    app_job = runtime.jobs.create_job(
        JobCreate(
            title="Muted app microphone",
            capture_backend="macos_local",
            mute_target_audio=True,
            capture_target={
                "id": "application:chrome",
                "kind": "application",
                "label": "Google Chrome",
                "app_bundle_id": "com.google.Chrome",
                "app_name": "Google Chrome",
                "app_pid": 4242,
            },
        )
    )
    runtime.jobs.transition_job(app_job.id, JobState.PENDING_START, "test")
    runtime.jobs.transition_job(app_job.id, JobState.RECORDING, "test")

    runtime.jobs.transition_job(app_job.id, JobState.LIVE_STREAM_CONNECTING, "test")
    runtime.jobs.transition_job(app_job.id, JobState.LIVE_STREAMING, "test")

    muted_response = client.post(f"/api/jobs/{app_job.id}/record-microphone", json={"record_microphone": True})

    assert muted_response.status_code == 200
    assert muted_response.json()["metadata_json"]["session_preferences"]["record_microphone"] is True


def test_stop_endpoint_accepts_active_job(client) -> None:
    create_desktop_session(client)
    start = client.post("/api/jobs/start", json={"title": "Authorized public livestream"})
    assert start.status_code == 200
    job_id = start.json()["id"]

    response = client.post(f"/api/jobs/{job_id}/stop")

    assert response.status_code == 202
    wait_for_state(client, job_id, "completed")


def test_stop_capture_runs_processed_microphone_mix_off_event_loop(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    start = client.post(
        "/api/jobs/start",
        json={
            "title": "Nonblocking microphone mix",
            "capture_backend": "macos_local",
            "record_microphone": True,
            "generate_summary": False,
            "capture_target": {
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
        },
    )
    assert start.status_code == 200
    job_id = start.json()["id"]
    runtime.artifacts.microphone_stage_path(job_id).write_bytes(b"\x00\x00" * 160)
    marker_delays: list[float] = []
    mix_started_at = {"value": 0.0}

    async def fake_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        raise AssertionError("summary generation should be skipped")

    async def run_stop() -> None:
        loop = asyncio.get_running_loop()

        def slow_mix(selected_job_id: str) -> None:
            assert selected_job_id == job_id
            mix_started_at["value"] = time.perf_counter()
            loop.call_soon_threadsafe(lambda: marker_delays.append(time.perf_counter() - mix_started_at["value"]))
            time.sleep(0.2)

        monkeypatch.setattr(runtime.artifacts, "mix_recording_with_microphone", slow_mix)
        monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", fake_rewrite_canonical_summary)
        stop_task = asyncio.create_task(runtime.capture.stop_capture(job_id, skip_summary=True))
        await asyncio.sleep(0.05)
        assert marker_delays and marker_delays[0] < 0.1
        await stop_task

    asyncio.run(run_stop())


def test_stop_endpoint_resumes_job_stuck_after_recording_stop(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(
        JobCreate(
            title="Resume finalizing",
            capture_backend="macos_local",
            generate_summary=False,
            capture_target={
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
            },
        )
    )
    runtime.jobs.transition_job(job.id, JobState.PENDING_START, "test")
    runtime.jobs.transition_job(job.id, JobState.RECORDING, "test")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAM_CONNECTING, "test")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAMING, "test")
    runtime.jobs.transition_job(job.id, JobState.STOPPING, "test")
    runtime.jobs.transition_job(job.id, JobState.FINALIZING_DEEPGRAM, "test")
    runtime.artifacts.recording_stage_path(job.id).write_bytes(b"finalized-recording")

    async def fake_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        raise AssertionError("summary generation should be skipped")

    monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", fake_rewrite_canonical_summary)

    response = client.post(f"/api/jobs/{job.id}/stop", json={"skip_summary": True})

    assert response.status_code == 202
    payload = wait_for_state(client, job.id, "completed")
    paths = runtime.artifacts.job_paths(job.id)
    assert payload["recording_path"] == str(paths.recording)
    assert paths.recording.read_bytes() == b"finalized-recording"
    assert paths.transcript_markdown.exists()


def test_artifacts_endpoint_only_lists_registered_summary(client) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Markdown Summary"))
    before = client.get(f"/api/jobs/{job.id}/artifacts")

    assert before.status_code == 200
    assert "summary.md" not in {item["name"] for item in before.json()["files"]}

    summary_path = runtime.artifacts.job_paths(job.id).summary
    summary_path.write_text("# Summary\n", encoding="utf-8")
    runtime.artifacts.register_file(job.id, summary_path, content_type="text/markdown")

    after = client.get(f"/api/jobs/{job.id}/artifacts")

    assert after.status_code == 200
    assert "summary.md" in {item["name"] for item in after.json()["files"]}


def test_create_job_defaults_summary_model_to_openclaw_model(client) -> None:
    runtime = client.app.state.runtime

    job = runtime.jobs.create_job(JobCreate(title="Summary Model Default"))

    assert job.summary_model == runtime.settings.openclaw_summary_model


def test_summary_rerun_endpoint_dispatches_refresh(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Summary Refresh"))

    async def fake_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        assert job_id == job.id
        summary_path = runtime.artifacts.job_paths(job_id).summary
        summary_path.write_text("# Summary\n\nRefreshed\n", encoding="utf-8")
        return str(summary_path)

    monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", fake_rewrite_canonical_summary)

    response = client.post(f"/api/jobs/{job.id}/summary/rerun")

    assert response.status_code == 202
    payload = wait_for_metadata_value(client, job.id, "summary_status", "completed")
    assert payload["summary_path"] == str(runtime.artifacts.job_paths(job.id).summary)


def test_summary_rerun_endpoint_tracks_controlled_error(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Summary Refresh Failure"))

    async def fail_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        raise RuntimeError("summary unavailable")

    monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", fail_rewrite_canonical_summary)

    response = client.post(f"/api/jobs/{job.id}/summary/rerun")

    assert response.status_code == 202
    payload = wait_for_metadata_value(client, job.id, "summary_error", "summary unavailable")
    assert payload["metadata_json"]["summary_status"] == "failed"


def test_stop_summary_failure_keeps_job_completed_and_tracks_recap_error(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    create_desktop_session(client)
    start = client.post("/api/jobs/start", json={"title": "Authorized public livestream"})
    assert start.status_code == 200
    job_id = start.json()["id"]

    async def fail_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        raise RuntimeError("summary unavailable")

    monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", fail_rewrite_canonical_summary)

    response = client.post(f"/api/jobs/{job_id}/stop")

    assert response.status_code == 202

    payload = wait_for_metadata_value(client, job_id, "summary_status", "failed")
    assert payload["state"] == "completed"
    assert payload["error_message"] is None
    assert payload["metadata_json"]["summary_status"] == "failed"
    assert payload["metadata_json"]["summary_error"] == "summary unavailable"
    assert payload["metadata_json"]["summary_completed_at"]
    assert "notify_status" not in payload["metadata_json"]
    assert "notify_error" not in payload["metadata_json"]
    assert "notify_completed_at" not in payload["metadata_json"]

    artifacts = client.get(f"/api/jobs/{job_id}/artifacts").json()
    assert "recording.mp4" in {item["name"] for item in artifacts["files"]}
    assert "transcript.md" in {item["name"] for item in artifacts["files"]}
    assert "transcript.txt" not in {item["name"] for item in artifacts["files"]}

def test_recover_route_resumes_recovering_job_and_completes(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(JobCreate(title="Recoverable failure"))
    paths = runtime.artifacts.job_paths(job.id)
    paths.transcript_markdown.write_text("# Transcript\n\nRecovered\n", encoding="utf-8")
    paths.transcript_json.write_text('{"segments":[]}\n', encoding="utf-8")
    paths.recording.write_bytes(b"recording")
    runtime.jobs.update_runtime_fields(
        job.id,
        state=JobState.FAILED.value,
        recording_path=str(paths.recording),
    )
    runtime.jobs.update_metadata(
        job.id,
        finalization_checkpoint="transcript_compiled",
        summary_status="failed",
        summary_error="summary unavailable",
        summary_completed_at="2026-04-23T12:00:00Z",
    )

    async def successful_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        summary_path = runtime.artifacts.job_paths(job_id).summary
        summary_path.write_text("# Summary\n\nRecovered\n", encoding="utf-8")
        return str(summary_path)

    monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", successful_rewrite_canonical_summary)

    recover = client.post(f"/api/jobs/{job.id}/recover")

    assert recover.status_code == 202

    payload = wait_for_metadata_value(client, job.id, "summary_status", "completed")
    assert payload["state"] == "completed"
    assert payload["metadata_json"]["summary_status"] == "completed"
    assert payload["metadata_json"]["summary_error"] is None
    assert payload["metadata_json"]["summary_completed_at"]
    assert "notify_status" not in payload["metadata_json"]
    assert "notify_error" not in payload["metadata_json"]
    assert "notify_completed_at" not in payload["metadata_json"]
    assert runtime.artifacts.job_paths(job.id).summary.read_text(encoding="utf-8") == "# Summary\n\nRecovered\n"


def test_stop_uses_transcript_prompts_for_canonical_summary(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    create_desktop_session(client)
    start = client.post("/api/jobs/start", json={"title": "Authorized public livestream"})
    assert start.status_code == 200
    job_id = start.json()["id"]

    called: dict[str, str] = {}

    async def fake_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        called["job_id"] = job_id
        summary_path = runtime.artifacts.job_paths(job_id).summary
        summary_path.write_text("# Summary\n\nGenerated by OpenClaw\n", encoding="utf-8")
        return str(summary_path)

    monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", fake_rewrite_canonical_summary)

    stop = client.post(f"/api/jobs/{job_id}/stop")

    assert stop.status_code == 202
    payload = wait_for_metadata_value(client, job_id, "summary_status", "completed")
    assert payload["state"] == "completed"
    assert called["job_id"] == job_id
    assert runtime.artifacts.job_paths(job_id).summary.read_text(encoding="utf-8") == "# Summary\n\nGenerated by OpenClaw\n"


def test_stop_can_skip_canonical_summary_generation(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    create_desktop_session(client)
    start = client.post("/api/jobs/start", json={"title": "Authorized public livestream"})
    assert start.status_code == 200
    job_id = start.json()["id"]

    called = {"summary": False}

    async def unexpected_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        called["summary"] = True
        raise AssertionError("summary generation should be skipped")

    monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", unexpected_rewrite_canonical_summary)

    stop = client.post(f"/api/jobs/{job_id}/stop", json={"skip_summary": True})

    assert stop.status_code == 202
    payload = wait_for_metadata_value(client, job_id, "summary_status", "skipped")
    paths = runtime.artifacts.job_paths(job_id)
    assert payload["state"] == "completed"
    assert called["summary"] is False
    assert payload["metadata_json"]["summary_status"] == "skipped"
    assert payload["metadata_json"]["summary_error"] is None
    assert payload["metadata_json"]["summary_completed_at"]
    assert "notify_status" not in payload["metadata_json"]
    assert "notify_error" not in payload["metadata_json"]
    assert "notify_completed_at" not in payload["metadata_json"]
    assert not paths.summary.exists()
    assert paths.transcript_markdown.exists()
    assert paths.transcript_json.exists()
    assert not (paths.root / "transcript.txt").exists()


def test_start_job_can_disable_final_summary_generation(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    create_desktop_session(client)
    start = client.post(
        "/api/jobs/start",
        json={"title": "Transcript only", "generate_summary": False},
    )
    assert start.status_code == 200
    job_id = start.json()["id"]

    called = {"summary": False}

    async def unexpected_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        called["summary"] = True
        raise AssertionError("summary generation should be skipped")

    monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", unexpected_rewrite_canonical_summary)

    stop = client.post(f"/api/jobs/{job_id}/stop")

    assert stop.status_code == 202
    payload = wait_for_metadata_value(client, job_id, "summary_status", "skipped")
    paths = runtime.artifacts.job_paths(job_id)
    assert payload["state"] == "completed"
    assert called["summary"] is False
    assert payload["metadata_json"]["session_preferences"]["record_screen"] is True
    assert payload["metadata_json"]["session_preferences"]["generate_summary"] is False
    assert payload["metadata_json"]["session_preferences"]["notify_on_inactivity"] is True
    assert payload["metadata_json"]["summary_status"] == "skipped"
    assert not paths.summary.exists()
    assert paths.transcript_markdown.exists()
    assert paths.transcript_json.exists()
    assert not (paths.root / "transcript.txt").exists()


def test_duplicate_stop_requests_reuse_existing_background_run(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    create_desktop_session(client)
    start = client.post("/api/jobs/start", json={"title": "Authorized public livestream"})
    assert start.status_code == 200
    job_id = start.json()["id"]

    calls = {"count": 0}

    async def slow_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        calls["count"] += 1
        await asyncio.sleep(0.15)
        summary_path = runtime.artifacts.job_paths(job_id).summary
        summary_path.write_text("# Summary\n\nGenerated once\n", encoding="utf-8")
        return str(summary_path)

    monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", slow_rewrite_canonical_summary)

    first = client.post(f"/api/jobs/{job_id}/stop")
    second = client.post(f"/api/jobs/{job_id}/stop")

    assert first.status_code == 202
    assert second.status_code == 202
    wait_for_metadata_value(client, job_id, "summary_status", "completed")
    assert calls["count"] == 1


def test_stop_keeps_job_active_until_summary_finishes(client, monkeypatch) -> None:
    runtime = client.app.state.runtime
    create_desktop_session(client)
    start = client.post("/api/jobs/start", json={"title": "Authorized public livestream"})
    assert start.status_code == 200
    job_id = start.json()["id"]

    async def slow_rewrite_canonical_summary(*, job_id: str, prompt: str = "") -> str:
        await asyncio.sleep(0.15)
        summary_path = runtime.artifacts.job_paths(job_id).summary
        summary_path.write_text("# Summary\n\nGenerated while stopping\n", encoding="utf-8")
        return str(summary_path)

    monkeypatch.setattr(runtime.transcript_prompts, "rewrite_canonical_summary", slow_rewrite_canonical_summary)

    response = client.post(f"/api/jobs/{job_id}/stop")

    assert response.status_code == 202
    running_payload = wait_for_metadata_value(client, job_id, "summary_status", "running")
    assert running_payload["state"] == "summarizing"

    completed_payload = wait_for_metadata_value(client, job_id, "summary_status", "completed")
    assert completed_payload["state"] == "completed"
