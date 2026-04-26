from __future__ import annotations

from jobs.models import JobCreate
from jobs.state_machine import JobState
from conftest import login


def test_create_job_defaults_to_docker_desktop_capture_selection(settings) -> None:
    from api.main import create_runtime

    runtime = create_runtime(settings)

    job = runtime.jobs.create_job(JobCreate(title="Default capture backend"))

    assert job.capture_backend == "docker_desktop"
    assert job.capture_target == {
        "id": "desktop",
        "kind": "desktop",
        "label": "Isolated desktop",
        "app_bundle_id": None,
        "app_name": None,
        "app_pid": None,
        "window_id": None,
        "display_id": None,
    }
    assert job.metadata_json["capture"] == {
        "backend": "docker_desktop",
        "target": {
            "id": "desktop",
            "kind": "desktop",
                "label": "Isolated desktop",
                "app_bundle_id": None,
                "app_name": None,
                "app_pid": None,
                "window_id": None,
                "display_id": None,
            },
    }


def test_start_job_persists_requested_macos_capture_selection(client) -> None:
    login(client)

    response = client.post(
        "/api/jobs/start",
        json={
            "title": "This Mac capture",
            "capture_backend": "macos_local",
            "capture_target": {
                "id": "window:notes-1",
                "kind": "window",
                "label": "Notes",
                "app_bundle_id": "com.apple.Notes",
                "app_name": "Notes",
                "window_id": "notes-1",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["capture_backend"] == "macos_local"
    assert payload["capture_target"] == {
        "id": "window:notes-1",
        "kind": "window",
        "label": "Notes",
        "app_bundle_id": "com.apple.Notes",
        "app_name": "Notes",
        "app_pid": None,
        "window_id": "notes-1",
        "display_id": None,
    }
    assert payload["metadata_json"]["capture"] == {
        "backend": "macos_local",
        "target": {
            "id": "window:notes-1",
            "kind": "window",
            "label": "Notes",
                "app_bundle_id": "com.apple.Notes",
                "app_name": "Notes",
                "app_pid": None,
                "window_id": "notes-1",
                "display_id": None,
        },
    }


def test_start_job_persists_muted_target_audio_preference(client) -> None:
    login(client)

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
    payload = response.json()
    assert payload["metadata_json"]["session_preferences"]["mute_target_audio"] is True
    assert payload["capture_target"]["app_pid"] == 4242


def test_capture_targets_endpoint_lists_targets_for_requested_backend(client) -> None:
    login(client)

    docker_response = client.get("/api/capture/targets?backend=docker_desktop")

    assert docker_response.status_code == 200
    assert docker_response.json() == {
        "backend": "docker_desktop",
        "targets": [
            {
                "id": "desktop",
                "kind": "desktop",
                "label": "Isolated desktop",
                "app_bundle_id": None,
                "app_name": None,
                "app_pid": None,
                "window_id": None,
                "display_id": None,
            }
        ],
    }

    macos_response = client.get("/api/capture/targets?backend=macos_local")

    assert macos_response.status_code == 200
    assert macos_response.json() == {
        "backend": "macos_local",
        "targets": [
            {
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "app_bundle_id": None,
                "app_name": None,
                "app_pid": None,
                "window_id": None,
                "display_id": "main",
            },
            {
                "id": "application:notes",
                "kind": "application",
                "label": "Notes",
                "app_bundle_id": "com.apple.Notes",
                "app_name": "Notes",
                "app_pid": 4242,
                "window_id": None,
                "display_id": None,
            },
            {
                "id": "window:notes-1",
                "kind": "window",
                "label": "Notes",
                "app_bundle_id": "com.apple.Notes",
                "app_name": "Notes",
                "app_pid": 4242,
                "window_id": "notes-1",
                "display_id": "main",
            },
        ],
    }
    assert {target["kind"] for target in macos_response.json()["targets"]} == {"display", "application", "window"}


def test_capture_targets_endpoint_rejects_unknown_backend(client) -> None:
    login(client)

    response = client.get("/api/capture/targets?backend=unknown-backend")

    assert response.status_code == 404
    assert response.json() == {"detail": "capture backend not found"}


def test_capture_targets_reuses_active_local_target_without_refreshing_screen_capture(client, monkeypatch) -> None:
    login(client)
    runtime = client.app.state.runtime
    job = runtime.jobs.create_job(
        JobCreate(
            title="Active local capture",
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
    macos_backend = runtime.capture_backends.require("macos_local")

    async def fail_list_targets() -> list[dict[str, object]]:
        raise AssertionError("active local capture should not refresh ScreenCaptureKit targets")

    monkeypatch.setattr(macos_backend, "list_targets", fail_list_targets)

    response = client.get("/api/capture/targets?backend=macos_local")

    assert response.status_code == 200
    assert response.json() == {
        "backend": "macos_local",
        "targets": [
            {
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "app_bundle_id": None,
                "app_name": None,
                "app_pid": None,
                "window_id": None,
                "display_id": "main",
            }
        ],
    }
