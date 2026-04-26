from __future__ import annotations

from fastapi.testclient import TestClient

from thirdeye_desktop_agent import main as agent_main


class StubFanout:
    def __init__(self, calls: list[object]) -> None:
        self.calls = calls

    def reset(self) -> None:
        self.calls.append("reset")

    def ensure_running(self) -> None:
        self.calls.append("ensure")


def test_recording_start_prepares_pulse_runtime_before_launch(monkeypatch) -> None:
    calls: list[object] = []

    async def fake_run_script_async(name: str, *, env: dict[str, str]) -> dict[str, object]:
        calls.append(("script", name, env["JOB_ID"]))
        return {"ok": True}

    monkeypatch.setattr(agent_main, "run_script_async", fake_run_script_async)

    with TestClient(agent_main.app) as client:
        response = client.post("/recording/start", json={"job_id": "job-123"})

    assert response.status_code == 200
    assert calls == [
        ("script", "prepare_pulse_runtime.sh", "job-123"),
        ("script", "start_recording.sh", "job-123"),
    ]


def test_recording_start_accepts_target_payload(monkeypatch) -> None:
    calls: list[object] = []

    async def fake_run_script_async(name: str, *, env: dict[str, str]) -> dict[str, object]:
        calls.append(("script", name, env["JOB_ID"]))
        return {"ok": True}

    monkeypatch.setattr(agent_main, "run_script_async", fake_run_script_async)

    with TestClient(agent_main.app) as client:
        response = client.post(
            "/recording/start",
            json={
                "job_id": "job-123",
                "target": {"id": "desktop", "kind": "desktop", "label": "Isolated desktop"},
            },
        )

    assert response.status_code == 200
    assert calls == [
        ("script", "prepare_pulse_runtime.sh", "job-123"),
        ("script", "start_recording.sh", "job-123"),
    ]


def test_targets_endpoint_returns_isolated_desktop_target() -> None:
    with TestClient(agent_main.app) as client:
        response = client.get("/targets")

    assert response.status_code == 200
    assert response.json() == {
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
        ]
    }


def test_live_audio_start_resets_fanout_before_launch(monkeypatch) -> None:
    calls: list[object] = []

    async def fake_run_script_async(name: str, *, env: dict[str, str]) -> dict[str, object]:
        calls.append(("script", name, env["JOB_ID"]))
        return {"pid": 1234}

    monkeypatch.setattr(agent_main, "fanout", StubFanout(calls))
    monkeypatch.setattr(agent_main, "run_script_async", fake_run_script_async)

    with TestClient(agent_main.app) as client:
        response = client.post("/live-audio/start", json={"job_id": "job-123"})

    assert response.status_code == 200
    assert calls == [
        ("script", "prepare_pulse_runtime.sh", "job-123"),
        "reset",
        "ensure",
        ("script", "start_live_audio.sh", "job-123"),
    ]


def test_live_audio_stop_resets_fanout_after_stop(monkeypatch) -> None:
    calls: list[object] = []

    async def fake_run_script_async(name: str, *, env: dict[str, str]) -> dict[str, object]:
        calls.append(("script", name, env["JOB_ID"]))
        return {"pid": 1234}

    monkeypatch.setattr(agent_main, "fanout", StubFanout(calls))
    monkeypatch.setattr(agent_main, "run_script_async", fake_run_script_async)

    with TestClient(agent_main.app) as client:
        response = client.post("/live-audio/stop", json={"job_id": "job-123"})

    assert response.status_code == 200
    assert calls == [
        ("script", "stop_live_audio.sh", "job-123"),
        "reset",
    ]


def test_build_env_uses_container_recordings_mount_for_host_output_file(monkeypatch) -> None:
    monkeypatch.delenv("OUTPUT_DIR", raising=False)

    env = agent_main.build_env(
        "job-123",
        "/workspace/runtime/recordings/jobs/job-123/recording.mp4",
    )

    assert env["OUTPUT_DIR"] == "/recordings"
