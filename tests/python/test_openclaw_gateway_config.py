from __future__ import annotations

from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[2]


def test_openclaw_seed_is_valid_json_and_uses_lan_bind() -> None:
    config = json.loads((ROOT / "config" / "openclaw.json").read_text(encoding="utf-8"))

    assert config["gateway"]["bind"] == "lan"


def test_openclaw_gateway_healthcheck_has_startup_grace_period() -> None:
    compose = (ROOT / "infra" / "compose.yaml").read_text(encoding="utf-8")

    assert "start_period: 90s" in compose


def test_openclaw_gateway_enables_responses_endpoint_for_llm_requests() -> None:
    config = json.loads((ROOT / "config" / "openclaw.json").read_text(encoding="utf-8"))

    assert config["gateway"]["http"]["endpoints"]["responses"]["enabled"] is True
