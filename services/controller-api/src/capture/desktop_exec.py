from __future__ import annotations

import contextlib
from typing import Any, AsyncIterator, Protocol
from urllib.parse import urlencode

import httpx

from capture.desktop_sessions import DesktopSessionManager
from jobs.models import CaptureTarget
from core.settings import Settings


class CaptureClientProtocol(Protocol):
    backend_name: str

    async def health(self) -> dict[str, Any]: ...
    async def status(self, target: dict[str, Any] | None = None) -> dict[str, Any]: ...
    async def list_targets(self) -> list[dict[str, Any]]: ...
    async def start_recording(
        self,
        job_id: str,
        output_file: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
        record_microphone: bool = False,
        echo_cancellation_enabled: bool = False,
    ) -> dict[str, Any]: ...
    async def stop_recording(self, job_id: str, output_file: str, target: dict[str, Any]) -> dict[str, Any]: ...
    async def start_live_audio(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
        record_microphone: bool = False,
        echo_cancellation_enabled: bool = False,
    ) -> dict[str, Any]: ...
    async def set_target_audio_muted(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool,
    ) -> dict[str, Any]: ...
    async def set_record_microphone_enabled(
        self,
        job_id: str,
        target: dict[str, Any],
        record_microphone: bool,
    ) -> dict[str, Any]: ...
    async def set_echo_cancellation_enabled(
        self,
        job_id: str,
        target: dict[str, Any],
        echo_cancellation_enabled: bool,
    ) -> dict[str, Any]: ...
    async def stop_live_audio(self, job_id: str, target: dict[str, Any]) -> dict[str, Any]: ...
    async def stream_live_audio(self, job_id: str, source: str = "system") -> AsyncIterator[bytes]: ...


DesktopClientProtocol = CaptureClientProtocol


class CaptureClientError(RuntimeError):
    pass


DesktopClientError = CaptureClientError

MACOS_LISTED_TARGET_KINDS = {"display", "application", "window"}


def _response_detail(response: httpx.Response) -> str:
    with contextlib.suppress(ValueError):
        payload = response.json()
        if isinstance(payload, dict) and payload.get("detail"):
            return str(payload["detail"])
    text = response.text.strip()
    if text:
        return text
    return f"capture request failed with status {response.status_code}"


class HttpCaptureClient:
    backend_name: str
    base_url: str

    def __init__(self, *, base_url: str, backend_name: str) -> None:
        self.base_url = base_url
        self.backend_name = backend_name

    async def _post(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=30.0) as client:
                response = await client.post(path, json=payload or {})
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise CaptureClientError(f"{self.backend_name} request timed out: {path}") from exc
        except httpx.HTTPStatusError as exc:
            raise CaptureClientError(_response_detail(exc.response)) from exc
        except httpx.RequestError as exc:
            raise CaptureClientError(f"{self.backend_name} request failed: {exc}") from exc

    async def _get(self, path: str) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=10.0) as client:
                response = await client.get(path)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as exc:
            raise CaptureClientError(f"{self.backend_name} request timed out: {path}") from exc
        except httpx.HTTPStatusError as exc:
            raise CaptureClientError(_response_detail(exc.response)) from exc
        except httpx.RequestError as exc:
            raise CaptureClientError(f"{self.backend_name} request failed: {exc}") from exc

    async def health(self) -> dict[str, Any]:
        return await self._get("/health")

    async def status(self, target: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._get("/status")

    async def list_targets(self) -> list[dict[str, Any]]:
        payload = await self._get("/targets")
        targets = payload.get("targets", [])
        if not isinstance(targets, list):
            raise CaptureClientError(f"{self.backend_name} returned an invalid targets payload")
        normalized = [CaptureTarget.model_validate(target).model_dump() for target in targets]
        if self.backend_name == "macos_local":
            return [target for target in normalized if target["kind"] in MACOS_LISTED_TARGET_KINDS]
        return normalized

    async def start_recording(
        self,
        job_id: str,
        output_file: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
        record_microphone: bool = False,
        echo_cancellation_enabled: bool = False,
    ) -> dict[str, Any]:
        return await self._post(
            "/recording/start",
            {
                "job_id": job_id,
                "output_file": output_file,
                "target": target,
                "mute_target_audio": mute_target_audio,
                "record_microphone": record_microphone,
                "echo_cancellation_enabled": echo_cancellation_enabled,
            },
        )

    async def stop_recording(self, job_id: str, output_file: str, target: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/recording/stop", {"job_id": job_id, "output_file": output_file, "target": target})

    async def start_live_audio(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
        record_microphone: bool = False,
        echo_cancellation_enabled: bool = False,
    ) -> dict[str, Any]:
        return await self._post(
            "/live-audio/start",
            {
                "job_id": job_id,
                "target": target,
                "mute_target_audio": mute_target_audio,
                "record_microphone": record_microphone,
                "echo_cancellation_enabled": echo_cancellation_enabled,
            },
        )

    async def set_target_audio_muted(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool,
    ) -> dict[str, Any]:
        return await self._post(
            "/target-audio/mute",
            {"job_id": job_id, "target": target, "mute_target_audio": mute_target_audio},
        )

    async def set_record_microphone_enabled(
        self,
        job_id: str,
        target: dict[str, Any],
        record_microphone: bool,
    ) -> dict[str, Any]:
        return await self._post(
            "/microphone/record",
            {"job_id": job_id, "target": target, "record_microphone": record_microphone},
        )

    async def set_echo_cancellation_enabled(
        self,
        job_id: str,
        target: dict[str, Any],
        echo_cancellation_enabled: bool,
    ) -> dict[str, Any]:
        return await self._post(
            "/echo-cancellation",
            {"job_id": job_id, "target": target, "echo_cancellation_enabled": echo_cancellation_enabled},
        )

    async def stop_live_audio(self, job_id: str, target: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/live-audio/stop", {"job_id": job_id, "target": target})

    async def stream_live_audio(self, job_id: str, source: str = "system") -> AsyncIterator[bytes]:
        query = urlencode({"job_id": job_id, "source": source})
        async with httpx.AsyncClient(base_url=self.base_url, timeout=None) as client:
            async with client.stream("GET", f"/live-audio/stream?{query}") as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk


class DesktopHttpClient(HttpCaptureClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        super().__init__(base_url=settings.desktop_base_url, backend_name="docker_desktop")


class DesktopPoolHttpClient:
    backend_name = "docker_desktop"

    def __init__(self, settings: Settings, desktop_sessions: DesktopSessionManager) -> None:
        self.settings = settings
        self.desktop_sessions = desktop_sessions

    def _client_for_target(self, target: dict[str, Any] | None) -> HttpCaptureClient:
        target_id = target.get("id") if isinstance(target, dict) else None
        session = self.desktop_sessions.session_for_target(target_id)
        return HttpCaptureClient(base_url=session.agent_url, backend_name=f"docker_desktop:{session.id}")

    async def health(self) -> dict[str, Any]:
        sessions = self.desktop_sessions.list_sessions()
        ready_count = sum(1 for session in sessions if session.status == "ready")
        return {"status": "ok", "desktops": len(sessions), "ready_desktops": ready_count}

    async def status(self, target: dict[str, Any] | None = None) -> dict[str, Any]:
        if target is not None:
            return await self._client_for_target(target).status()
        statuses: list[dict[str, Any]] = []
        for session in self.desktop_sessions.list_sessions():
            if session.status != "ready":
                continue
            try:
                statuses.append(await HttpCaptureClient(base_url=session.agent_url, backend_name=f"docker_desktop:{session.id}").status())
            except CaptureClientError:
                statuses.append({"recording": {"running": False}, "live_audio": {"running": False}})
        return {
            "recording": {"running": any(bool((status.get("recording") or {}).get("running")) for status in statuses)},
            "live_audio": {"running": any(bool((status.get("live_audio") or {}).get("running")) for status in statuses)},
        }

    async def list_targets(self) -> list[dict[str, Any]]:
        return self.desktop_sessions.capture_targets()

    async def start_recording(
        self,
        job_id: str,
        output_file: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
        record_microphone: bool = False,
        echo_cancellation_enabled: bool = False,
    ) -> dict[str, Any]:
        return await self._client_for_target(target).start_recording(
            job_id,
            output_file,
            target,
            mute_target_audio,
            record_microphone,
            echo_cancellation_enabled,
        )

    async def stop_recording(self, job_id: str, output_file: str, target: dict[str, Any]) -> dict[str, Any]:
        return await self._client_for_target(target).stop_recording(job_id, output_file, target)

    async def start_live_audio(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
        record_microphone: bool = False,
        echo_cancellation_enabled: bool = False,
    ) -> dict[str, Any]:
        return await self._client_for_target(target).start_live_audio(
            job_id,
            target,
            mute_target_audio,
            record_microphone,
            echo_cancellation_enabled,
        )

    async def set_target_audio_muted(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool,
    ) -> dict[str, Any]:
        return await self._client_for_target(target).set_target_audio_muted(job_id, target, mute_target_audio)

    async def set_record_microphone_enabled(
        self,
        job_id: str,
        target: dict[str, Any],
        record_microphone: bool,
    ) -> dict[str, Any]:
        return await self._client_for_target(target).set_record_microphone_enabled(job_id, target, record_microphone)

    async def set_echo_cancellation_enabled(
        self,
        job_id: str,
        target: dict[str, Any],
        echo_cancellation_enabled: bool,
    ) -> dict[str, Any]:
        return await self._client_for_target(target).set_echo_cancellation_enabled(job_id, target, echo_cancellation_enabled)

    async def stop_live_audio(self, job_id: str, target: dict[str, Any]) -> dict[str, Any]:
        return await self._client_for_target(target).stop_live_audio(job_id, target)

    async def stream_live_audio(self, job_id: str, source: str = "system") -> AsyncIterator[bytes]:
        raise CaptureClientError("stream_live_audio requires an isolated desktop target")

    async def stream_live_audio_for_target(self, job_id: str, target: dict[str, Any], source: str = "system") -> AsyncIterator[bytes]:
        async for chunk in self._client_for_target(target).stream_live_audio(job_id, source):
            yield chunk


class MacOSCaptureHttpClient(HttpCaptureClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        super().__init__(base_url=settings.macos_capture_base_url, backend_name="macos_local")
