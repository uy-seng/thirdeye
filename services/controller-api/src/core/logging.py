from __future__ import annotations

import json
import logging
from typing import Any


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))


def log_json(logger: logging.Logger, event: str, **payload: Any) -> None:
    logger.info(json.dumps({"event": event, **payload}, sort_keys=True))
