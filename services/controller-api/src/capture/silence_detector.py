from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass
class SilenceMonitor:
    timeout_minutes: int
    last_activity_at: datetime | None = None

    def touch(self) -> None:
        self.last_activity_at = datetime.now(tz=UTC)

    def expired(self) -> bool:
        if self.last_activity_at is None:
            return False
        return datetime.now(tz=UTC) - self.last_activity_at >= timedelta(minutes=self.timeout_minutes)
