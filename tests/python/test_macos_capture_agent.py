from __future__ import annotations

import asyncio
import os

from fastapi.testclient import TestClient

from thirdeye_macos_capture.agent import main as agent_main
from thirdeye_macos_capture.agent.main import AudioFanout


class StubRuntime:
    def __init__(self, call_sink: list[object] | None = None) -> None:
        self.calls: list[object] = []
        self.call_sink = call_sink

    async def list_targets(self) -> list[dict[str, object]]:
        self.calls.append("targets")
        return [
            {
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
                "app_bundle_id": None,
                "app_name": None,
                "window_id": None,
            }
        ]

    async def start_recording(
        self,
        job_id: str,
        output_file: str | None,
        target: dict[str, object],
        mute_target_audio: bool = False,
    ) -> dict[str, object]:
        self.calls.append(("recording:start", job_id, output_file, target, mute_target_audio))
        return {"pid": 4321, "output_file": output_file}

    async def start_live_audio(
        self,
        job_id: str,
        target: dict[str, object],
        mute_target_audio: bool = False,
    ) -> dict[str, object]:
        self.calls.append(("live-audio:start", job_id, target, mute_target_audio))
        if self.call_sink is not None:
            self.call_sink.append("runtime:start_live_audio")
        return {"pid": 6789, "fifo_path": "/tmp/live_audio.pcm"}

    async def set_target_audio_muted(
        self,
        job_id: str,
        target: dict[str, object],
        mute_target_audio: bool,
    ) -> dict[str, object]:
        self.calls.append(("target-audio:mute", job_id, target, mute_target_audio))
        return {"pid": 6789, "mute_target_audio": mute_target_audio}


class StubFanout:
    def __init__(self, calls: list[object]) -> None:
        self.calls = calls

    def reset(self) -> None:
        self.calls.append("reset")

    def ensure_running(self) -> None:
        self.calls.append("ensure")


def test_targets_endpoint_returns_runtime_targets(monkeypatch) -> None:
    runtime = StubRuntime()
    monkeypatch.setattr(agent_main, "runtime", runtime)

    with TestClient(agent_main.app) as client:
        response = client.get("/targets")

    assert response.status_code == 200
    assert response.json() == {
        "targets": [
            {
                "id": "display:main",
                "kind": "display",
                "label": "Built-in Display",
                "display_id": "main",
                "app_bundle_id": None,
                "app_name": None,
                "window_id": None,
            }
        ]
    }


def test_recording_start_forwards_target_to_runtime(monkeypatch) -> None:
    runtime = StubRuntime()
    monkeypatch.setattr(agent_main, "runtime", runtime)

    with TestClient(agent_main.app) as client:
        response = client.post(
            "/recording/start",
            json={
                "job_id": "job-123",
                "output_file": "/tmp/recording.mp4",
                "target": {
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
    assert runtime.calls == [
        (
            "recording:start",
            "job-123",
            "/tmp/recording.mp4",
            {
                "id": "window:notes-1",
                "kind": "window",
                "label": "Notes",
                "app_bundle_id": "com.apple.Notes",
                "app_name": "Notes",
                "app_pid": None,
                "window_id": "notes-1",
                "display_id": None,
            },
            False,
        )
    ]


def test_live_audio_start_starts_runtime_before_fanout_reader(monkeypatch) -> None:
    calls: list[object] = []
    runtime = StubRuntime(calls)
    monkeypatch.setattr(agent_main, "runtime", runtime)
    monkeypatch.setattr(agent_main, "fanout", StubFanout(calls))

    with TestClient(agent_main.app) as client:
        response = client.post(
            "/live-audio/start",
            json={
                "job_id": "job-123",
                "target": {
                    "id": "application:notes",
                    "kind": "application",
                    "label": "Notes",
                    "app_bundle_id": "com.apple.Notes",
                    "app_name": "Notes",
                },
            },
        )

    assert response.status_code == 200
    assert calls == ["runtime:start_live_audio", "reset", "ensure"]
    assert runtime.calls == [
        (
            "live-audio:start",
            "job-123",
            {
                "id": "application:notes",
                "kind": "application",
                "label": "Notes",
                "app_bundle_id": "com.apple.Notes",
                "app_name": "Notes",
                "app_pid": None,
                "window_id": None,
                "display_id": None,
            },
            False,
        )
    ]


def test_recording_start_forwards_muted_app_audio_request(monkeypatch) -> None:
    runtime = StubRuntime()
    monkeypatch.setattr(agent_main, "runtime", runtime)

    with TestClient(agent_main.app) as client:
        response = client.post(
            "/recording/start",
            json={
                "job_id": "job-123",
                "output_file": "/tmp/recording.mp4",
                "mute_target_audio": True,
                "target": {
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
    assert runtime.calls == [
        (
            "recording:start",
            "job-123",
            "/tmp/recording.mp4",
            {
                "id": "application:chrome",
                "kind": "application",
                "label": "Google Chrome",
                "app_bundle_id": "com.google.Chrome",
                "app_name": "Google Chrome",
                "app_pid": 4242,
                "window_id": None,
                "display_id": None,
            },
            True,
        )
    ]


def test_target_audio_mute_endpoint_forwards_runtime_request(monkeypatch) -> None:
    runtime = StubRuntime()
    monkeypatch.setattr(agent_main, "runtime", runtime)

    with TestClient(agent_main.app) as client:
        response = client.post(
            "/target-audio/mute",
            json={
                "job_id": "job-123",
                "mute_target_audio": True,
                "target": {
                    "id": "window:chrome-1",
                    "kind": "window",
                    "label": "Google Chrome",
                    "app_bundle_id": "com.google.Chrome",
                    "app_name": "Google Chrome",
                    "app_pid": 4242,
                    "window_id": "chrome-1",
                },
            },
        )

    assert response.status_code == 200
    assert response.json() == {"pid": 6789, "mute_target_audio": True}
    assert runtime.calls == [
        (
            "target-audio:mute",
            "job-123",
            {
                "id": "window:chrome-1",
                "kind": "window",
                "label": "Google Chrome",
                "app_bundle_id": "com.google.Chrome",
                "app_name": "Google Chrome",
                "app_pid": 4242,
                "window_id": "chrome-1",
                "display_id": None,
            },
            True,
        )
    ]


def test_audio_fanout_emits_silence_when_fifo_is_idle(tmp_path) -> None:
    fifo_path = tmp_path / "live_audio.pcm"
    os.mkfifo(fifo_path)
    fanout = AudioFanout(fifo_path)
    fanout.SILENCE_INTERVAL_SECONDS = 0.05

    async def read_chunk() -> bytes:
        fanout.ensure_running()
        stream = fanout.stream()
        try:
            return await asyncio.wait_for(anext(stream), timeout=1.0)
        finally:
            await stream.aclose()
            fanout.reset()

    chunk = asyncio.run(read_chunk())

    assert chunk == b"\x00" * AudioFanout.SILENCE_CHUNK_BYTES


def test_audio_fanout_reopens_replaced_fifo(tmp_path) -> None:
    fifo_path = tmp_path / "live_audio.pcm"
    os.mkfifo(fifo_path)
    fanout = AudioFanout(fifo_path)

    async def read_from_replaced_fifo() -> bytes:
        fanout.ensure_running()
        await asyncio.sleep(0.05)
        fanout.reset()
        fifo_path.unlink()
        os.mkfifo(fifo_path)
        fanout.ensure_running()
        stream = fanout.stream()
        try:
            writer_fd = os.open(fifo_path, os.O_RDWR | os.O_NONBLOCK)
            try:
                os.write(writer_fd, b"live-bytes")
                return await asyncio.wait_for(anext(stream), timeout=1.0)
            finally:
                os.close(writer_fd)
        finally:
            await stream.aclose()
            fanout.reset()

    chunk = asyncio.run(read_from_replaced_fifo())

    assert chunk == b"live-bytes"
