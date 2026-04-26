from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TranscriptChannel:
    subscribers: list[asyncio.Queue[dict[str, Any]]] = field(default_factory=list)


class TranscriptHub:
    def __init__(self) -> None:
        self._channels: dict[str, TranscriptChannel] = defaultdict(TranscriptChannel)

    async def publish(self, job_id: str, event: dict[str, Any]) -> None:
        channel = self._channels[job_id]
        for queue in list(channel.subscribers):
            await queue.put(event)

    def subscribe(self, job_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._channels[job_id].subscribers.append(queue)
        return queue

    def unsubscribe(self, job_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        channel = self._channels[job_id]
        if queue in channel.subscribers:
            channel.subscribers.remove(queue)
