from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from core.utils import utcnow


class TranscriptSummaryRequestNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class CachedTranscriptSummary:
    job_id: str
    request_id: str
    prompt: str
    markdown: str
    created_at_seconds: float


class TranscriptSummaryCache:
    def __init__(self, *, ttl_seconds: int = 900) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[tuple[str, str], CachedTranscriptSummary] = {}

    def store(self, *, job_id: str, prompt: str, markdown: str) -> CachedTranscriptSummary:
        self._purge_expired()
        request_id = uuid.uuid4().hex
        entry = CachedTranscriptSummary(
            job_id=job_id,
            request_id=request_id,
            prompt=prompt,
            markdown=markdown,
            created_at_seconds=utcnow().timestamp(),
        )
        self._entries[(job_id, request_id)] = entry
        return entry

    def pop(self, *, job_id: str, request_id: str) -> CachedTranscriptSummary:
        self._purge_expired()
        key = (job_id, request_id)
        if key not in self._entries:
            raise TranscriptSummaryRequestNotFoundError("transcript summary request not found")
        return self._entries.pop(key)

    def _purge_expired(self) -> None:
        cutoff = utcnow() - timedelta(seconds=self.ttl_seconds)
        cutoff_seconds = cutoff.timestamp()
        expired = [key for key, entry in self._entries.items() if entry.created_at_seconds < cutoff_seconds]
        for key in expired:
            self._entries.pop(key, None)
