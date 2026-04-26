from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from typing import Any, AsyncIterator, Protocol

import httpx

from jobs.models import CaptureTarget, default_docker_capture_target
from core.settings import Settings


class CaptureClientProtocol(Protocol):
    backend_name: str

    async def health(self) -> dict[str, Any]: ...
    async def status(self) -> dict[str, Any]: ...
    async def list_targets(self) -> list[dict[str, Any]]: ...
    async def start_recording(
        self,
        job_id: str,
        output_file: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
    ) -> dict[str, Any]: ...
    async def stop_recording(self, job_id: str, output_file: str, target: dict[str, Any]) -> dict[str, Any]: ...
    async def start_live_audio(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
    ) -> dict[str, Any]: ...
    async def set_target_audio_muted(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool,
    ) -> dict[str, Any]: ...
    async def stop_live_audio(self, job_id: str, target: dict[str, Any]) -> dict[str, Any]: ...
    async def stream_live_audio(self, job_id: str) -> AsyncIterator[bytes]: ...


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

    async def status(self) -> dict[str, Any]:
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
    ) -> dict[str, Any]:
        return await self._post(
            "/recording/start",
            {
                "job_id": job_id,
                "output_file": output_file,
                "target": target,
                "mute_target_audio": mute_target_audio,
            },
        )

    async def stop_recording(self, job_id: str, output_file: str, target: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/recording/stop", {"job_id": job_id, "output_file": output_file, "target": target})

    async def start_live_audio(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
    ) -> dict[str, Any]:
        return await self._post(
            "/live-audio/start",
            {"job_id": job_id, "target": target, "mute_target_audio": mute_target_audio},
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

    async def stop_live_audio(self, job_id: str, target: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/live-audio/stop", {"job_id": job_id, "target": target})

    async def stream_live_audio(self, job_id: str) -> AsyncIterator[bytes]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=None) as client:
            async with client.stream("GET", f"/live-audio/stream?job_id={job_id}") as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk


class DesktopHttpClient(HttpCaptureClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        super().__init__(base_url=settings.desktop_base_url, backend_name="docker_desktop")


class MacOSCaptureHttpClient(HttpCaptureClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        super().__init__(base_url=settings.macos_capture_base_url, backend_name="macos_local")


class FakeCaptureClient:
    def __init__(self, settings: Settings, *, backend_name: str, targets: list[dict[str, Any]]) -> None:
        self.settings = settings
        self.backend_name = backend_name
        self._targets = [CaptureTarget.model_validate(target).model_dump() for target in targets]
        self._recording_pid = 1111
        self._live_audio_pid = 2222
        self._running_recording = False
        self._running_live_audio = False
        self._output_file: Path | None = None
        self._target_audio_muted = False

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "fake_mode": True}

    async def status(self) -> dict[str, Any]:
        return {
            "recording": {"running": self._running_recording, "pid": self._recording_pid if self._running_recording else None},
            "live_audio": {"running": self._running_live_audio, "pid": self._live_audio_pid if self._running_live_audio else None},
        }

    async def list_targets(self) -> list[dict[str, Any]]:
        if self.backend_name == "macos_local":
            return [target for target in self._targets if target["kind"] in MACOS_LISTED_TARGET_KINDS]
        return self._targets

    async def start_recording(
        self,
        job_id: str,
        output_file: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
    ) -> dict[str, Any]:
        self._running_recording = True
        self._target_audio_muted = mute_target_audio
        self._output_file = Path(output_file)
        self._output_file.parent.mkdir(parents=True, exist_ok=True)
        suffix = ":muted" if mute_target_audio else ""
        self._output_file.write_bytes(f"fake-mp4:{self.backend_name}:{target['id']}{suffix}".encode("utf-8"))
        return {"pid": self._recording_pid, "output_file": output_file}

    async def stop_recording(self, job_id: str, output_file: str, target: dict[str, Any]) -> dict[str, Any]:
        self._running_recording = False
        assert self._output_file is not None
        self._output_file.write_bytes(self._output_file.read_bytes() + b"-finalized")
        return {"pid": self._recording_pid, "output_file": str(self._output_file)}

    async def start_live_audio(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
    ) -> dict[str, Any]:
        self._running_live_audio = True
        self._target_audio_muted = mute_target_audio
        return {"pid": self._live_audio_pid, "fifo_path": str(self.settings.recordings_root / "jobs" / job_id / "live_audio.pcm")}

    async def set_target_audio_muted(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool,
    ) -> dict[str, Any]:
        self._target_audio_muted = mute_target_audio
        return {"pid": self._recording_pid if self._running_recording else self._live_audio_pid, "mute_target_audio": mute_target_audio}

    async def stop_live_audio(self, job_id: str, target: dict[str, Any]) -> dict[str, Any]:
        self._running_live_audio = False
        return {"pid": self._live_audio_pid}

    async def stream_live_audio(self, job_id: str) -> AsyncIterator[bytes]:
        for _ in range(3):
            await asyncio.sleep(0.05)
            yield b"\x00\x01" * 64


class FakeDesktopClient(FakeCaptureClient):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            backend_name="docker_desktop",
            targets=[default_docker_capture_target().model_dump()],
        )


class FakeMacOSCaptureClient(FakeCaptureClient):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            settings,
            backend_name="macos_local",
            targets=[
                {
                    "id": "display:main",
                    "kind": "display",
                    "label": "Built-in Display",
                    "display_id": "main",
                },
                {
                    "id": "application:notes",
                    "kind": "application",
                    "label": "Notes",
                    "app_bundle_id": "com.apple.Notes",
                    "app_name": "Notes",
                    "app_pid": 4242,
                },
                {
                    "id": "window:notes-1",
                    "kind": "window",
                    "label": "Notes",
                    "app_bundle_id": "com.apple.Notes",
                    "app_name": "Notes",
                    "app_pid": 4242,
                    "window_id": "notes-1",
                    "display_id": "main",
                },
            ],
        )
