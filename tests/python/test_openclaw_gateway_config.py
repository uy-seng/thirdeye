from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_openclaw_gateway_uses_lan_bind_for_docker_bridge() -> None:
    config = (ROOT / "config" / "openclaw.jsonc").read_text(encoding="utf-8")

    assert 'bind: "lan"' in config


def test_openclaw_gateway_healthcheck_has_startup_grace_period() -> None:
    compose = (ROOT / "infra" / "compose.yaml").read_text(encoding="utf-8")

    assert "start_period: 90s" in compose


def test_openclaw_gateway_enables_responses_endpoint_for_llm_requests() -> None:
    config = (ROOT / "config" / "openclaw.jsonc").read_text(encoding="utf-8")

    assert "responses" in config
    assert "enabled: true" in config
