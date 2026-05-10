from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from transcripts.deepgram_client import DeepgramClient
from core.settings import Settings


EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]
DegradedCallback = Callable[[str, str], Awaitable[None]]
RelaySource = str
RelayKey = tuple[str, RelaySource]


def deepgram_error_message(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    if "HTTP 401" in message:
        return "Deepgram rejected the API key. Check DEEPGRAM_API_KEY in .env."
    if "HTTP 403" in message:
        return "Deepgram refused access for this API key. Check the key permissions in Deepgram."
    return message


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
        self._tasks: dict[RelayKey, asyncio.Task[None]] = {}
        self._stop_events: dict[RelayKey, asyncio.Event] = {}

    def is_running(self, job_id: str, source: RelaySource | None = None) -> bool:
        if source is not None:
            task = self._tasks.get((job_id, source))
            return task is not None and not task.done()
        return any(key_job_id == job_id and not task.done() for (key_job_id, _), task in self._tasks.items())

    async def start(
        self,
        job_id: str,
        stream_factory: Callable[[], Any],
        job_options: dict[str, Any],
        source: RelaySource = "system",
    ) -> None:
        key = (job_id, source)
        if self.is_running(job_id, source):
            return
        stop_event = asyncio.Event()
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
            message = deepgram_error_message(exc)
            await self.on_degraded(job_id, message)
            raise RuntimeError(message) from exc

        self._stop_events[key] = stop_event
        task = asyncio.create_task(self._run(job_id, stream_factory, websocket, stop_event, source))
        task.add_done_callback(lambda _: self._cleanup_key(key))
        self._tasks[key] = task

    async def stop(self, job_id: str, source: RelaySource | None = None) -> None:
        keys = [(job_id, source)] if source is not None else [key for key in self._tasks if key[0] == job_id]
        tasks: list[asyncio.Task[None]] = []
        for key in keys:
            stop_event = self._stop_events.get(key)
            if stop_event is not None:
                stop_event.set()
            task = self._tasks.get(key)
            if task is not None:
                tasks.append(task)
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=2.0)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)

    def _cleanup_key(self, key: RelayKey) -> None:
        self._tasks.pop(key, None)
        self._stop_events.pop(key, None)

    @staticmethod
    def _tag_event(source: RelaySource, event: dict[str, Any]) -> dict[str, Any]:
        tagged = dict(event)
        tagged["source"] = source
        return tagged

    async def _run(
        self,
        job_id: str,
        stream_factory: Callable[[], Any],
        websocket: Any,
        stop_event: asyncio.Event,
        source: RelaySource,
    ) -> None:
        async def sender() -> None:
            try:
                async for chunk in stream_factory():
                    if stop_event.is_set():
                        break
                    await websocket.send(chunk)
                await websocket.send(json.dumps({"type": "Finalize"}))
                await websocket.send(json.dumps({"type": "CloseStream"}))
            except Exception as exc:  # pragma: no cover - network
                await self.on_degraded(job_id, deepgram_error_message(exc))

        async def receiver() -> None:
            try:
                async for message in websocket:
                    if isinstance(message, bytes):
                        continue
                    await self.on_event(job_id, self._tag_event(source, json.loads(message)))
            except Exception as exc:  # pragma: no cover - network
                await self.on_degraded(job_id, deepgram_error_message(exc))

        try:
            await asyncio.gather(sender(), receiver())
        finally:
            close = getattr(websocket, "close", None)
            if close is not None:
                await close()
