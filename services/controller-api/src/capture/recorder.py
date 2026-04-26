from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecorderStatus:
    running: bool
    pid: int | None
