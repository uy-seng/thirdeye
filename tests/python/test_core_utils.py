from __future__ import annotations

from datetime import datetime

from core.utils import isoformat


def test_isoformat_treats_naive_datetimes_as_utc() -> None:
    assert isoformat(datetime(2026, 4, 29, 19, 26, 19, 447583)) == "2026-04-29T19:26:19.447583Z"
