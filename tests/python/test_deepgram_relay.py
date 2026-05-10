from __future__ import annotations

import asyncio
from typing import Any

from transcripts.deepgram_relay import RelayManager


def test_relay_manager_tags_deepgram_events_with_source(settings) -> None:
    events: list[dict[str, Any]] = []

    async def on_event(job_id: str, event: dict[str, Any]) -> None:
        events.append(event)

    async def on_degraded(job_id: str, message: str) -> None:
        raise AssertionError(message)

    class ScriptedWebSocket:
        def __init__(self) -> None:
            self.messages: asyncio.Queue[str | None] = asyncio.Queue()
            self.messages.put_nowait(
                '{"type":"Results","is_final":true,"start":0.0,"duration":1.0,"channel":{"alternatives":[{"transcript":"hello","words":[]}]}}'
            )
            self.messages.put_nowait(None)

        async def send(self, message: object) -> None:
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            message = await self.messages.get()
            if message is None:
                raise StopAsyncIteration
            return message

    class ScriptedDeepgramClient:
        async def connect(self, **kwargs):
            return ScriptedWebSocket()

    async def audio_stream():
        yield b"\x00\x01"

    async def run() -> None:
        relay = RelayManager(
            settings=settings,
            deepgram_client=ScriptedDeepgramClient(),  # type: ignore[arg-type]
            on_event=on_event,
            on_degraded=on_degraded,
        )
        await relay.start(
            "job-123",
            audio_stream,
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
            settings=settings.model_copy(update={"deepgram_api_key": "test-token"}),
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


def test_relay_manager_raises_when_deepgram_connection_is_rejected(settings) -> None:
    degraded: list[tuple[str, str]] = []

    async def on_event(job_id: str, event: dict[str, Any]) -> None:
        raise AssertionError(event)

    async def on_degraded(job_id: str, message: str) -> None:
        degraded.append((job_id, message))

    class RejectedDeepgramClient:
        async def connect(self, **kwargs):
            raise RuntimeError("server rejected WebSocket connection: HTTP 401")

    async def audio_stream():
        yield b"\x00\x01"

    async def run() -> None:
        relay = RelayManager(
            settings=settings,
            deepgram_client=RejectedDeepgramClient(),  # type: ignore[arg-type]
            on_event=on_event,
            on_degraded=on_degraded,
        )
        try:
            await relay.start(
                "job-123",
                audio_stream,
                {
                    "model": "nova-3",
                    "language": None,
                    "diarize": True,
                    "smart_format": True,
                    "interim_results": True,
                },
                source="system",
            )
        except RuntimeError as exc:
            assert "Deepgram rejected the API key" in str(exc)
            return
        raise AssertionError("expected Deepgram startup failure")

    asyncio.run(run())

    assert degraded == [("job-123", "Deepgram rejected the API key. Check DEEPGRAM_API_KEY in .env.")]
