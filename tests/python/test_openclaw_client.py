from __future__ import annotations

import asyncio
import pytest

import httpx

from integrations.openclaw_client import OpenClawClient
from core.settings import OPENCLAW_SUMMARY_MODEL_DEFAULT, Settings


class FakeAsyncClient:
    last_json: dict[str, object] | None = None
    last_headers: dict[str, str] | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> httpx.Response:
        self.__class__.last_json = json
        self.__class__.last_headers = headers
        request = httpx.Request("POST", f"http://openclaw.test{url}")
        if json.get("model") != "openclaw":
            return httpx.Response(
                400,
                json={"error": {"message": "Invalid `model`. Use `openclaw` or `openclaw/<agentId>`.", "type": "invalid_request_error"}},
                request=request,
            )
        input_value = json.get("input")
        if not isinstance(input_value, str):
            return httpx.Response(
                400,
                json={"error": {"message": "input: Invalid input", "type": "invalid_request_error"}},
                request=request,
            )
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": "# Summary\n\n- Captured transcript details",
                            }
                        ]
                    }
                ]
            },
            request=request,
        )


class NotFoundAsyncClient:
    @staticmethod
    def _req(path: str) -> httpx.Request:
        return httpx.Request("POST", f"http://openclaw.test{path}")

    last_json: dict[str, object] | None = None

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "NotFoundAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> httpx.Response:
        self.__class__.last_json = json
        return httpx.Response(404, text="Not Found", request=self._req(url))


class TimeoutAsyncClient:
    attempts = 0

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "TimeoutAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> httpx.Response:
        self.__class__.attempts += 1
        request = httpx.Request("POST", f"http://openclaw.test{url}")
        raise httpx.ReadTimeout("timed out", request=request)


class FlakyTimeoutAsyncClient:
    attempts = 0

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self) -> "FlakyTimeoutAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> httpx.Response:
        self.__class__.attempts += 1
        request = httpx.Request("POST", f"http://openclaw.test{url}")
        if self.__class__.attempts < 3:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(
            200,
            json={
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": "# Summary\n\n- Captured transcript details",
                            }
                        ]
                    }
                ]
            },
            request=request,
        )


def test_generate_transcript_summary_uses_openclaw_model_and_string_input(monkeypatch) -> None:
    settings = Settings(
        controller_username="operator",
        controller_password="secret-pass",
        session_secret="test-session-secret",
        openclaw_gateway_token="gateway-token",
        fake_mode=True,
    )
    client = OpenClawClient(settings)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        client.generate_transcript_summary(
            prompt="Summarize decisions and next steps",
            transcript_text="hello world",
            title="Demo session",
        )
    )

    assert result == {
        "markdown": "# Summary\n\n- Captured transcript details",
        "provider": f"openclaw/{OPENCLAW_SUMMARY_MODEL_DEFAULT}",
    }
    assert FakeAsyncClient.last_json is not None
    assert FakeAsyncClient.last_json == {
        "model": "openclaw",
        "instructions": "Summarize transcript excerpts in concise factual markdown. Do not invent facts.",
        "input": (
            "Session title: Demo session\n\n"
            "Operator request:\nSummarize decisions and next steps\n\n"
            "Transcript snapshot:\nhello world"
        ),
    }
    assert FakeAsyncClient.last_headers is not None
    assert FakeAsyncClient.last_headers["x-openclaw-model"] == OPENCLAW_SUMMARY_MODEL_DEFAULT


def test_generate_transcript_summary_honors_explicit_model_override(monkeypatch) -> None:
    settings = Settings(
        controller_username="operator",
        controller_password="secret-pass",
        session_secret="test-session-secret",
        openclaw_gateway_token="gateway-token",
        fake_mode=True,
    )
    client = OpenClawClient(settings)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        client.generate_transcript_summary(
            prompt="Summarize decisions and next steps",
            transcript_text="hello world",
            title="Demo session",
            model="custom-summary-model",
        )
    )

    assert result == {
        "markdown": "# Summary\n\n- Captured transcript details",
        "provider": "openclaw/custom-summary-model",
    }
    assert FakeAsyncClient.last_json is not None
    assert FakeAsyncClient.last_json == {
        "model": "openclaw",
        "instructions": "Summarize transcript excerpts in concise factual markdown. Do not invent facts.",
        "input": (
            "Session title: Demo session\n\n"
            "Operator request:\nSummarize decisions and next steps\n\n"
            "Transcript snapshot:\nhello world"
        ),
    }
    assert FakeAsyncClient.last_headers is not None
    assert FakeAsyncClient.last_headers["x-openclaw-model"] == "custom-summary-model"


def test_generate_transcript_summary_falls_back_from_legacy_fake_summary_model(monkeypatch) -> None:
    settings = Settings(
        controller_username="operator",
        controller_password="secret-pass",
        session_secret="test-session-secret",
        openclaw_gateway_token="gateway-token",
        fake_mode=True,
    )
    client = OpenClawClient(settings)

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    result = asyncio.run(
        client.generate_transcript_summary(
            prompt="Summarize decisions and next steps",
            transcript_text="hello world",
            title="Demo session",
            model="fake-summary",
        )
    )

    assert result == {
        "markdown": "# Summary\n\n- Captured transcript details",
        "provider": f"openclaw/{OPENCLAW_SUMMARY_MODEL_DEFAULT}",
    }
    assert FakeAsyncClient.last_json is not None
    assert FakeAsyncClient.last_json["model"] == "openclaw"
    assert FakeAsyncClient.last_headers is not None
    assert FakeAsyncClient.last_headers["x-openclaw-model"] == OPENCLAW_SUMMARY_MODEL_DEFAULT


def test_generate_transcript_summary_not_found_explains_config(monkeypatch) -> None:
    settings = Settings(
        controller_username="operator",
        controller_password="secret-pass",
        session_secret="test-session-secret",
        openclaw_gateway_token="gateway-token",
        fake_mode=True,
    )
    client = OpenClawClient(settings)

    monkeypatch.setattr(httpx, "AsyncClient", NotFoundAsyncClient)

    with pytest.raises(RuntimeError, match="OpenClaw responses endpoint not available"):
        asyncio.run(
            client.generate_transcript_summary(
                prompt="Summarize decisions and next steps",
                transcript_text="hello world",
                title="Demo session",
            )
        )


def test_generate_transcript_summary_timeout_surfaces_runtime_error(monkeypatch) -> None:
    settings = Settings(
        controller_username="operator",
        controller_password="secret-pass",
        session_secret="test-session-secret",
        fake_mode=True,
        openclaw_summary_timeout_seconds=60,
    )
    client = OpenClawClient(settings)

    TimeoutAsyncClient.attempts = 0
    monkeypatch.setattr(httpx, "AsyncClient", TimeoutAsyncClient)

    with pytest.raises(RuntimeError, match="OpenClaw LLM request timed out after 60s"):
        asyncio.run(
            client.generate_transcript_summary(
                prompt="Summarize decisions and next steps",
                transcript_text="hello world",
                title="Demo session",
            )
        )
    assert TimeoutAsyncClient.attempts == 3


def test_generate_transcript_summary_retries_timeout_and_recovers(monkeypatch) -> None:
    settings = Settings(
        controller_username="operator",
        controller_password="secret-pass",
        session_secret="test-session-secret",
        openclaw_gateway_token="gateway-token",
        fake_mode=True,
        openclaw_summary_timeout_seconds=60,
    )
    client = OpenClawClient(settings)

    FlakyTimeoutAsyncClient.attempts = 0
    monkeypatch.setattr(httpx, "AsyncClient", FlakyTimeoutAsyncClient)

    async def fake_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        client.generate_transcript_summary(
            prompt="Summarize decisions and next steps",
            transcript_text="hello world",
            title="Demo session",
        )
    )

    assert result == {
        "markdown": "# Summary\n\n- Captured transcript details",
        "provider": f"openclaw/{OPENCLAW_SUMMARY_MODEL_DEFAULT}",
    }
    assert FlakyTimeoutAsyncClient.attempts == 3
