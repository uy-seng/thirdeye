from __future__ import annotations

import asyncio
from typing import Any

from transcripts.deepgram_client import DeepgramClient
from transcripts.deepgram_relay import RelayManager


def test_relay_manager_tags_fake_events_with_source(settings) -> None:
    events: list[dict[str, Any]] = []

    async def on_event(job_id: str, event: dict[str, Any]) -> None:
        events.append(event)

    async def on_degraded(job_id: str, message: str) -> None:
        raise AssertionError(message)

    async def run() -> None:
        relay = RelayManager(
            settings=settings,
            deepgram_client=DeepgramClient(settings),
            on_event=on_event,
            on_degraded=on_degraded,
        )
        await relay.start(
            "job-123",
            lambda: None,
            {
                "model": "nova-3",
                "language": None,
                "diarize": True,
                "smart_format": True,
                "interim_results": True,
            },
            source="microphone",
        )
        await asyncio.sleep(0.2)
        await relay.stop("job-123", source="microphone")

    asyncio.run(run())

    assert events
    assert {event["source"] for event in events} == {"microphone"}


def test_relay_manager_stop_cancels_stalled_source_stream(settings) -> None:
    async def on_event(job_id: str, event: dict[str, Any]) -> None:
        return None

    async def on_degraded(job_id: str, message: str) -> None:
        raise AssertionError(message)

    class StalledWebSocket:
        async def send(self, message: object) -> None:
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Event().wait()
            raise StopAsyncIteration

    class StalledDeepgramClient:
        async def connect(self, **kwargs):
            return StalledWebSocket()

    async def stalled_stream():
        await asyncio.Event().wait()
        yield b""

    async def run() -> bool:
        relay = RelayManager(
            settings=settings.model_copy(update={"fake_mode": False, "deepgram_api_key": "test-token"}),
            deepgram_client=StalledDeepgramClient(),  # type: ignore[arg-type]
            on_event=on_event,
            on_degraded=on_degraded,
        )
        await relay.start(
            "job-123",
            stalled_stream,
            {
                "model": "nova-3",
                "language": None,
                "diarize": True,
                "smart_format": True,
                "interim_results": True,
            },
            source="system",
        )
        await relay.stop("job-123", source="system")
        return relay.is_running("job-123", source="system")

    assert asyncio.run(run()) is False
