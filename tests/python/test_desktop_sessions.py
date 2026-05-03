from __future__ import annotations

from subprocess import CompletedProcess

from core.settings import Settings


def create_desktop(client, label: str = "Meeting desktop") -> dict[str, object]:
    response = client.post("/api/desktops", json={"label": label})
    assert response.status_code == 200
    return response.json()


def test_desktops_start_empty_and_create_on_demand(client) -> None:
    empty = client.get("/api/desktops")

    assert empty.status_code == 200
    assert empty.json() == {"desktops": []}

    created = create_desktop(client, "Career fair")

    assert created["label"] == "Career fair"
    assert created["status"] == "ready"
    assert created["browser_url"].startswith("http://127.0.0.1:")
    assert created["agent_url"].startswith("http://127.0.0.1:")
    assert created["active_job_id"] is None
    assert created["active_job_state"] is None

    listed = client.get("/api/desktops")

    assert listed.status_code == 200
    assert listed.json()["desktops"] == [created]


def test_docker_capture_targets_are_created_desktop_sessions(client) -> None:
    empty = client.get("/api/capture/targets?backend=docker_desktop")

    assert empty.status_code == 200
    assert empty.json() == {"backend": "docker_desktop", "targets": []}

    desktop = create_desktop(client, "Demo room")
    targets = client.get("/api/capture/targets?backend=docker_desktop").json()["targets"]

    assert targets == [
        {
            "id": desktop["target_id"],
            "kind": "desktop",
            "label": "Demo room",
            "app_bundle_id": None,
            "app_name": None,
            "app_pid": None,
            "window_id": None,
            "display_id": None,
            "browser_url": desktop["browser_url"],
            "available": True,
            "active_job_id": None,
            "active_job_state": None,
        }
    ]


def test_parallel_docker_jobs_use_different_desktop_sessions(client) -> None:
    first_desktop = create_desktop(client, "Session one")
    second_desktop = create_desktop(client, "Session two")

    first = client.post(
        "/api/jobs/start",
        json={
            "title": "First livestream",
            "capture_backend": "docker_desktop",
            "capture_target": {
                "id": first_desktop["target_id"],
                "kind": "desktop",
                "label": "Session one",
            },
        },
    )
    second = client.post(
        "/api/jobs/start",
        json={
            "title": "Second livestream",
            "capture_backend": "docker_desktop",
            "capture_target": {
                "id": second_desktop["target_id"],
                "kind": "desktop",
                "label": "Session two",
            },
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["capture_target"]["id"] == first_desktop["target_id"]
    assert second.json()["capture_target"]["id"] == second_desktop["target_id"]


def test_docker_job_rejects_already_recording_desktop_session(client) -> None:
    desktop = create_desktop(client, "Busy room")
    target = {"id": desktop["target_id"], "kind": "desktop", "label": "Busy room"}

    first = client.post(
        "/api/jobs/start",
        json={"title": "First livestream", "capture_backend": "docker_desktop", "capture_target": target},
    )
    second = client.post(
        "/api/jobs/start",
        json={"title": "Second livestream", "capture_backend": "docker_desktop", "capture_target": target},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json() == {"detail": "that isolated desktop is already recording"}


def test_destroy_desktop_session_rejects_active_recording(client) -> None:
    desktop = create_desktop(client, "Protected room")
    start = client.post(
        "/api/jobs/start",
        json={
            "title": "Protected livestream",
            "capture_backend": "docker_desktop",
            "capture_target": {
                "id": desktop["target_id"],
                "kind": "desktop",
                "label": "Protected room",
            },
        },
    )
    assert start.status_code == 200

    destroy = client.post(f"/api/desktops/{desktop['id']}/destroy")

    assert destroy.status_code == 409
    assert destroy.json() == {"detail": "stop the recording before destroying this desktop"}


def test_desktop_session_reports_post_stop_job_state(client) -> None:
    from jobs.state_machine import JobState

    desktop = create_desktop(client, "Wrapping room")
    start = client.post(
        "/api/jobs/start",
        json={
            "title": "Wrapping livestream",
            "capture_backend": "docker_desktop",
            "capture_target": {
                "id": desktop["target_id"],
                "kind": "desktop",
                "label": "Wrapping room",
            },
        },
    )
    assert start.status_code == 200
    job_id = start.json()["id"]

    runtime = client.app.state.runtime
    runtime.jobs.transition_job(job_id, JobState.STOPPING, "test")
    runtime.jobs.transition_job(job_id, JobState.FINALIZING_DEEPGRAM, "test")
    runtime.jobs.transition_job(job_id, JobState.COMPILING_TRANSCRIPT, "test")
    runtime.jobs.transition_job(job_id, JobState.SUMMARIZING, "test")

    listed = client.get("/api/desktops").json()["desktops"]

    assert listed[0]["active_job_id"] == job_id
    assert listed[0]["active_job_state"] == "summarizing"


def test_destroy_desktop_session_removes_inactive_desktop(client) -> None:
    desktop = create_desktop(client, "Disposable room")

    destroy = client.post(f"/api/desktops/{desktop['id']}/destroy")

    assert destroy.status_code == 200
    assert destroy.json()["status"] == "destroyed"
    assert client.get("/api/desktops").json() == {"desktops": []}


def test_desktop_container_is_grouped_under_thirdeye_in_docker_desktop(settings: Settings, monkeypatch) -> None:
    from capture import desktop_sessions as desktop_sessions_module
    from capture.desktop_sessions import DesktopSessionManager

    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> CompletedProcess[str]:
        commands.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return CompletedProcess(command, 0, stdout="[]", stderr="")
        if command[:2] == ["docker", "build"]:
            return CompletedProcess(command, 0, stdout="", stderr="")
        if command[:2] == ["docker", "run"]:
            return CompletedProcess(command, 0, stdout="container-id\n", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(desktop_sessions_module, "_port_is_open", lambda port: False)
    monkeypatch.setattr(desktop_sessions_module.subprocess, "run", fake_run)

    manager = DesktopSessionManager(settings)

    session = manager.create_session("Meeting room")

    docker_run = next(command for command in commands if command[:2] == ["docker", "run"])
    labels = [docker_run[index + 1] for index, value in enumerate(docker_run) if value == "--label"]

    assert session.container_id == "container-id"
    assert "thirdeye.managed=true" in labels
    assert "com.docker.compose.project=thirdeye" in labels
    assert "com.docker.compose.service=desktop" in labels


def test_local_desktop_image_is_rebuilt_before_starting_session(settings: Settings, monkeypatch) -> None:
    from capture import desktop_sessions as desktop_sessions_module
    from capture.desktop_sessions import DesktopSessionManager

    commands: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> CompletedProcess[str]:
        commands.append(command)
        if command[:3] == ["docker", "image", "inspect"]:
            return CompletedProcess(command, 0, stdout="[]", stderr="")
        if command[:2] == ["docker", "build"]:
            return CompletedProcess(command, 0, stdout="", stderr="")
        if command[:2] == ["docker", "run"]:
            return CompletedProcess(command, 0, stdout="container-id\n", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(desktop_sessions_module, "_port_is_open", lambda port: False)
    monkeypatch.setattr(desktop_sessions_module.subprocess, "run", fake_run)

    manager = DesktopSessionManager(settings)

    manager.create_session("Fresh image")

    build_index = next(index for index, command in enumerate(commands) if command[:2] == ["docker", "build"])
    run_index = next(index for index, command in enumerate(commands) if command[:2] == ["docker", "run"])

    assert build_index < run_index
