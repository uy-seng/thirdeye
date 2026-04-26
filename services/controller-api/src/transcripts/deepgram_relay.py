from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from transcripts.deepgram_client import DeepgramClient
from core.settings import Settings


EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
DegradedCallback = Callable[[str, str], Awaitable[None]]


class RelayManager:
    def __init__(
        self,
        settings: Settings,
        deepgram_client: DeepgramClient,
        on_event: EventCallback,
        on_degraded: DegradedCallback,
    ) -> None:
        self.settings = settings
        self.deepgram_client = deepgram_client
        self.on_event = on_event
        self.on_degraded = on_degraded
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._stop_events: dict[str, asyncio.Event] = {}

    def is_running(self, job_id: str) -> bool:
        task = self._tasks.get(job_id)
        return task is not None and not task.done()

    async def start(self, job_id: str, stream_factory: Callable[[], Any], job_options: dict[str, Any]) -> None:
        stop_event = asyncio.Event()
        self._stop_events[job_id] = stop_event
        task = asyncio.create_task(self._run(job_id, stream_factory, stop_event, job_options))
        self._tasks[job_id] = task

    async def stop(self, job_id: str) -> None:
        stop_event = self._stop_events.get(job_id)
        if stop_event is not None:
            stop_event.set()
        task = self._tasks.get(job_id)
        if task is not None:
            await asyncio.wait([task], timeout=2.0)

    async def _run(self, job_id: str, stream_factory: Callable[[], Any], stop_event: asyncio.Event, job_options: dict[str, Any]) -> None:
        if self.settings.fake_mode:
            await self.on_event(job_id, {"type": "Metadata", "request_id": f"fake-{job_id}", "model_info": {"name": job_options["model"]}})
            await asyncio.sleep(0.05)
            await self.on_event(
                job_id,
                {
                    "type": "Results",
                    "is_final": False,
                    "start": 0.0,
                    "duration": 0.7,
                    "channel": {"alternatives": [{"transcript": "connecting to livestream", "words": [{"speaker": 1, "start": 0.0, "end": 0.7}]}]},
                },
            )
            await asyncio.sleep(0.05)
            await self.on_event(
                job_id,
                {
                    "type": "Results",
                    "is_final": True,
                    "start": 0.0,
                    "duration": 1.3,
                    "channel": {"alternatives": [{"transcript": "public session started", "words": [{"speaker": 1, "start": 0.0, "end": 1.3}]}]},
                },
            )
            await self.on_event(job_id, {"type": "SpeechStarted", "timestamp": 0.0})
            await self.on_event(job_id, {"type": "UtteranceEnd", "last_word_end": 1.3})
            await stop_event.wait()
            return

        try:
            websocket = await self.deepgram_client.connect(
                model=job_options["model"],
                language=job_options.get("language"),
                diarize=job_options["diarize"],
                smart_format=job_options["smart_format"],
                interim_results=job_options["interim_results"],
                vad_events=self.settings.deepgram_vad_events,
            )
        except Exception as exc:  # pragma: no cover - network
            await self.on_degraded(job_id, str(exc))
            return

        async def sender() -> None:
            try:
                async for chunk in stream_factory():
                    if stop_event.is_set():
                        break
                    await websocket.send(chunk)
                await websocket.send(json.dumps({"type": "Finalize"}))
                await websocket.send(json.dumps({"type": "CloseStream"}))
            except Exception as exc:  # pragma: no cover - network
                await self.on_degraded(job_id, str(exc))

        async def receiver() -> None:
            try:
                async for message in websocket:
                    if isinstance(message, bytes):
                        continue
                    await self.on_event(job_id, json.loads(message))
            except Exception as exc:  # pragma: no cover - network
                await self.on_degraded(job_id, str(exc))

        await asyncio.gather(sender(), receiver())
