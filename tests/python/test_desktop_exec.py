from __future__ import annotations

import asyncio

from capture.desktop_exec import DesktopHttpClient


def test_start_recording_forwards_controller_local_output_path(settings, monkeypatch) -> None:
    client = DesktopHttpClient(settings)
    captured: dict[str, object] = {}

    async def fake_post(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        captured["path"] = path
        captured["payload"] = payload or {}
        return {"pid": 1234}

    monkeypatch.setattr(client, "_post", fake_post)

    asyncio.run(
        client.start_recording(
            "job-123",
            "/data/recordings/jobs/job-123/recording.mp4",
            {"id": "desktop", "kind": "desktop", "label": "Isolated desktop"},
        )
    )

    assert captured == {
        "path": "/recording/start",
        "payload": {
            "job_id": "job-123",
            "output_file": "/data/recordings/jobs/job-123/recording.mp4",
            "target": {"id": "desktop", "kind": "desktop", "label": "Isolated desktop"},
            "mute_target_audio": False,
            "record_microphone": False,
            "echo_cancellation_enabled": False,
        },
    }


def test_start_recording_forwards_muted_target_audio_request(settings, monkeypatch) -> None:
    client = DesktopHttpClient(settings)
    captured: dict[str, object] = {}

    async def fake_post(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        captured["path"] = path
        captured["payload"] = payload or {}
        return {"pid": 1234}

    monkeypatch.setattr(client, "_post", fake_post)

    asyncio.run(
        client.start_recording(
            "job-123",
            "/data/recordings/jobs/job-123/recording.mp4",
            {"id": "application:chrome", "kind": "application", "label": "Google Chrome", "app_pid": 4242},
            mute_target_audio=True,
        )
    )

    assert captured["payload"] == {
        "job_id": "job-123",
        "output_file": "/data/recordings/jobs/job-123/recording.mp4",
        "target": {"id": "application:chrome", "kind": "application", "label": "Google Chrome", "app_pid": 4242},
        "mute_target_audio": True,
        "record_microphone": False,
        "echo_cancellation_enabled": False,
    }


def test_start_recording_forwards_microphone_request(settings, monkeypatch) -> None:
    from capture.desktop_exec import MacOSCaptureHttpClient

    client = MacOSCaptureHttpClient(settings)
    captured: dict[str, object] = {}

    async def fake_post(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        captured["path"] = path
        captured["payload"] = payload or {}
        return {"pid": 1234}

    monkeypatch.setattr(client, "_post", fake_post)

    asyncio.run(
        client.start_recording(
            "job-123",
            "/data/recordings/jobs/job-123/recording.mp4",
            {"id": "display:main", "kind": "display", "label": "Built-in Display", "display_id": "main"},
            record_microphone=True,
        )
    )

    assert captured["payload"] == {
        "job_id": "job-123",
        "output_file": "/data/recordings/jobs/job-123/recording.mp4",
        "target": {"id": "display:main", "kind": "display", "label": "Built-in Display", "display_id": "main"},
        "mute_target_audio": False,
        "record_microphone": True,
        "echo_cancellation_enabled": False,
    }


def test_start_live_audio_forwards_microphone_request(settings, monkeypatch) -> None:
    from capture.desktop_exec import MacOSCaptureHttpClient

    client = MacOSCaptureHttpClient(settings)
    captured: dict[str, object] = {}

    async def fake_post(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        captured["path"] = path
        captured["payload"] = payload or {}
        return {"pid": 5678}

    monkeypatch.setattr(client, "_post", fake_post)

    asyncio.run(
        client.start_live_audio(
            "job-123",
            {"id": "display:main", "kind": "display", "label": "Built-in Display", "display_id": "main"},
            record_microphone=True,
        )
    )

    assert captured["payload"] == {
        "job_id": "job-123",
        "target": {"id": "display:main", "kind": "display", "label": "Built-in Display", "display_id": "main"},
        "mute_target_audio": False,
        "record_microphone": True,
        "echo_cancellation_enabled": False,
    }


def test_set_target_audio_muted_posts_runtime_mute_request(settings, monkeypatch) -> None:
    from capture.desktop_exec import MacOSCaptureHttpClient

    client = MacOSCaptureHttpClient(settings)
    captured: dict[str, object] = {}

    async def fake_post(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        captured["path"] = path
        captured["payload"] = payload or {}
        return {"pid": 4321, "mute_target_audio": True}

    monkeypatch.setattr(client, "_post", fake_post)

    payload = asyncio.run(
        client.set_target_audio_muted(
            "job-123",
            {"id": "application:chrome", "kind": "application", "label": "Google Chrome", "app_pid": 4242},
            True,
        )
    )

    assert payload == {"pid": 4321, "mute_target_audio": True}
    assert captured == {
        "path": "/target-audio/mute",
        "payload": {
            "job_id": "job-123",
            "target": {"id": "application:chrome", "kind": "application", "label": "Google Chrome", "app_pid": 4242},
            "mute_target_audio": True,
        },
    }


def test_set_record_microphone_enabled_posts_runtime_microphone_request(settings, monkeypatch) -> None:
    from capture.desktop_exec import MacOSCaptureHttpClient

    client = MacOSCaptureHttpClient(settings)
    captured: dict[str, object] = {}

    async def fake_post(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        captured["path"] = path
        captured["payload"] = payload or {}
        return {"pid": 4321, "record_microphone": True}

    monkeypatch.setattr(client, "_post", fake_post)

    payload = asyncio.run(
        client.set_record_microphone_enabled(
            "job-123",
            {"id": "display:main", "kind": "display", "label": "Built-in Display", "display_id": "main"},
            True,
        )
    )

    assert payload == {"pid": 4321, "record_microphone": True}
    assert captured == {
        "path": "/microphone/record",
        "payload": {
            "job_id": "job-123",
            "target": {"id": "display:main", "kind": "display", "label": "Built-in Display", "display_id": "main"},
            "record_microphone": True,
        },
    }


def test_set_echo_cancellation_enabled_posts_runtime_echo_request(settings, monkeypatch) -> None:
    from capture.desktop_exec import MacOSCaptureHttpClient

    client = MacOSCaptureHttpClient(settings)
    captured: dict[str, object] = {}

    async def fake_post(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        captured["path"] = path
        captured["payload"] = payload or {}
        return {"pid": 4321, "echo_cancellation_enabled": True}

    monkeypatch.setattr(client, "_post", fake_post)

    payload = asyncio.run(
        client.set_echo_cancellation_enabled(
            "job-123",
            {"id": "display:main", "kind": "display", "label": "Built-in Display", "display_id": "main"},
            True,
        )
    )

    assert payload == {"pid": 4321, "echo_cancellation_enabled": True}
    assert captured == {
        "path": "/echo-cancellation",
        "payload": {
            "job_id": "job-123",
            "target": {"id": "display:main", "kind": "display", "label": "Built-in Display", "display_id": "main"},
            "echo_cancellation_enabled": True,
        },
    }


def test_stream_live_audio_can_request_microphone_source(settings, monkeypatch) -> None:
    from capture.desktop_exec import MacOSCaptureHttpClient

    client = MacOSCaptureHttpClient(settings)
    requested: dict[str, str] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self):
            yield b"mic"

    class FakeStream:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def stream(self, method: str, path: str):
            requested["method"] = method
            requested["path"] = path
            return FakeStream()

    monkeypatch.setattr("capture.desktop_exec.httpx.AsyncClient", FakeClient)

    chunks = asyncio.run(_collect_async(client.stream_live_audio("job-123", source="microphone")))

    assert chunks == [b"mic"]
    assert requested == {"method": "GET", "path": "/live-audio/stream?job_id=job-123&source=microphone"}


async def _collect_async(iterator):
    return [chunk async for chunk in iterator]


def test_stop_recording_forwards_controller_local_output_path(settings, monkeypatch) -> None:
    client = DesktopHttpClient(settings)
    captured: dict[str, object] = {}

    async def fake_post(path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        captured["path"] = path
        captured["payload"] = payload or {}
        return {"pid": 1234}

    monkeypatch.setattr(client, "_post", fake_post)

    asyncio.run(
        client.stop_recording(
            "job-123",
            "/data/recordings/jobs/job-123/recording.mp4",
            {"id": "desktop", "kind": "desktop", "label": "Isolated desktop"},
        )
    )

    assert captured == {
        "path": "/recording/stop",
        "payload": {
            "job_id": "job-123",
            "output_file": "/data/recordings/jobs/job-123/recording.mp4",
            "target": {"id": "desktop", "kind": "desktop", "label": "Isolated desktop"},
        },
    }


def test_targets_endpoint_reads_available_targets(settings, monkeypatch) -> None:
    client = DesktopHttpClient(settings)
    captured: dict[str, object] = {}

    async def fake_get(path: str) -> dict[str, object]:
        captured["path"] = path
        return {
            "targets": [
                {
                    "id": "desktop",
                    "kind": "desktop",
                    "label": "Isolated desktop",
                }
            ]
        }

    monkeypatch.setattr(client, "_get", fake_get)

    payload = asyncio.run(client.list_targets())

    assert captured == {"path": "/targets"}
    assert payload == [
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


def test_macos_targets_include_applications_for_muted_audio_selection(settings, monkeypatch) -> None:
    from capture.desktop_exec import MacOSCaptureHttpClient

    client = MacOSCaptureHttpClient(settings)

    async def fake_get(path: str) -> dict[str, object]:
        return {
            "targets": [
                {"id": "display:main", "kind": "display", "label": "Built-in Display", "display_id": "main"},
                {
                    "id": "application:chrome",
                    "kind": "application",
                    "label": "Google Chrome",
                    "app_bundle_id": "com.google.Chrome",
                    "app_name": "Google Chrome",
                    "app_pid": 4242,
                },
            ]
        }

    monkeypatch.setattr(client, "_get", fake_get)

    payload = asyncio.run(client.list_targets())

    assert [target["kind"] for target in payload] == ["display", "application"]
    assert payload[1]["app_pid"] == 4242
