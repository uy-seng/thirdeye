from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

from core.settings import Settings

OPENCLAW_SUMMARY_TIMEOUT_MAX_ATTEMPTS = 3
OPENCLAW_SUMMARY_TIMEOUT_RETRY_BASE_DELAY_SECONDS = 0.5


@dataclass
class OpenClawClient:
    settings: Settings

    def _auth_headers(self) -> dict[str, str]:
        if not self.settings.openclaw_gateway_token:
            return {}
        return {"Authorization": f"Bearer {self.settings.openclaw_gateway_token}"}

    async def health(self) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.settings.openclaw_base_url, timeout=10.0) as client:
            response = await client.get("/healthz")
            response.raise_for_status()
            return response.json() if response.headers.get("content-type", "").startswith("application/json") else {"status": response.text.strip() or "ok"}

    async def generate_transcript_summary(
        self,
        *,
        prompt: str,
        transcript_text: str,
        title: str,
        model: str | None = None,
    ) -> dict[str, str]:
        effective_model = self._effective_summary_model(model)
        prompt_text = (
            f"Session title: {title}\n\n"
            f"Operator request:\n{prompt}\n\n"
            f"Transcript snapshot:\n{transcript_text}"
        )
        payload = {
            "model": "openclaw",
            "instructions": "Summarize transcript excerpts in concise factual markdown. Do not invent facts.",
            "input": prompt_text,
        }
        async with httpx.AsyncClient(
            base_url=self.settings.openclaw_base_url,
            timeout=self.settings.openclaw_summary_timeout_seconds,
        ) as client:
            response = await self._post_with_timeout_retries(
                client=client,
                effective_model=effective_model,
                payload=payload,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = self._error_detail(response)
            raise RuntimeError(detail) from exc
        data = response.json()
        markdown = self._response_text(data).strip()
        if not markdown:
            raise RuntimeError("OpenClaw LLM returned no text")
        return {
            "markdown": markdown,
            "provider": f"openclaw/{effective_model}",
        }

    async def _post_with_timeout_retries(
        self,
        *,
        client: httpx.AsyncClient,
        effective_model: str,
        payload: dict[str, str],
    ) -> httpx.Response:
        for attempt in range(OPENCLAW_SUMMARY_TIMEOUT_MAX_ATTEMPTS):
            try:
                return await client.post(
                    "/v1/responses",
                    headers={
                        **self._auth_headers(),
                        "x-openclaw-model": effective_model,
                    },
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                if attempt == OPENCLAW_SUMMARY_TIMEOUT_MAX_ATTEMPTS - 1:
                    raise RuntimeError(
                        f"OpenClaw LLM request timed out after {self.settings.openclaw_summary_timeout_seconds}s"
                    ) from exc
                await asyncio.sleep(OPENCLAW_SUMMARY_TIMEOUT_RETRY_BASE_DELAY_SECONDS * (attempt + 1))
            except httpx.RequestError as exc:
                raise RuntimeError(f"OpenClaw LLM request failed: {exc}") from exc
        raise AssertionError("unreachable")

    def _effective_summary_model(self, model: str | None) -> str:
        candidate = (model or "").strip()
        if not candidate or candidate == "fake-summary":
            return self.settings.openclaw_summary_model
        return candidate

    @staticmethod
    def _response_text(payload: dict[str, Any]) -> str:
        if isinstance(payload.get("output_text"), str):
            return str(payload["output_text"])
        output = payload.get("output") or []
        chunks: list[str] = []
        if isinstance(output, list):
            for item in output:
                content = item.get("content") if isinstance(item, dict) else None
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if isinstance(block.get("text"), str):
                        chunks.append(str(block["text"]))
                    elif isinstance(block.get("content"), str):
                        chunks.append(str(block["content"]))
        return "\n".join(part for part in chunks if part).strip()

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        content_type = response.headers.get("content-type", "")
        if response.status_code == 404:
            return (
                f"OpenClaw responses endpoint not available at {response.url.path} "
                f"({response.status_code}). Ensure gateway.http.endpoints.responses.enabled=true "
                "in ~/.openclaw/openclaw.json and restart the OpenClaw gateway."
            )
        if "application/json" in content_type:
            payload = response.json()
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                return str(error["message"])
            if isinstance(payload, dict) and isinstance(payload.get("detail"), str):
                return str(payload["detail"])
        text = response.text.strip()
        return text or "OpenClaw LLM unavailable"
