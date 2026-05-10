from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

from capture.desktop_sessions import DesktopSession, DesktopSessionLimitError, DesktopSessionManager, DesktopSessionNotFoundError
from core.utils import isoformat, utcnow
from jobs.models import CaptureTarget, default_docker_capture_target


EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class FakeDesktopSessionManager:
    def __init__(self, settings) -> None:
        self.settings = settings
        self.root = settings.desktop_sessions_root
        self.registry_path = settings.desktop_sessions_registry_path
        self.sessions: list[DesktopSession] = []

    def list_sessions(self) -> list[DesktopSession]:
        return [session for session in self.sessions if session.status != "destroyed"]

    def create_session(self, label: str | None = None) -> DesktopSession:
        sessions = self.list_sessions()
        active_sessions = [session for session in sessions if session.status in {"starting", "ready"}]
        if len(active_sessions) >= self.settings.max_desktop_sessions:
            raise DesktopSessionLimitError("maximum isolated desktops are already running")

        desktop_id = uuid.uuid4().hex[:10]
        offset = len(sessions)
        session = DesktopSession(
            id=desktop_id,
            target_id=f"desktop:{desktop_id}",
            label=label or f"Isolated desktop {len(sessions) + 1}",
            container_id=f"test-container-{desktop_id}",
            container_name=f"thirdeye-desktop-{desktop_id}",
            browser_url=f"http://127.0.0.1:{self.settings.desktop_browser_port_start + offset}",
            agent_url=f"http://127.0.0.1:{self.settings.desktop_agent_port_start + offset}",
            status="ready",
            created_at=isoformat(utcnow()) or "",
            active_job_id=None,
            active_job_state=None,
            error_message=None,
        )
        self.sessions.append(session)
        return session

    def destroy_session(self, desktop_id: str) -> DesktopSession:
        selected = next((session for session in self.list_sessions() if session.id == desktop_id), None)
        if selected is None:
            raise DesktopSessionNotFoundError("isolated desktop not found")
        destroyed = selected.model_copy(update={"status": "destroyed", "active_job_id": None, "active_job_state": None})
        self.sessions = [session for session in self.sessions if session.id != desktop_id]
        return destroyed

    def session_for_target(self, target_id: str | None) -> DesktopSession:
        sessions = self.list_sessions()
        if target_id == "desktop" and len(sessions) == 1:
            return sessions[0]
        selected = next((session for session in sessions if session.target_id == target_id), None)
        if selected is None:
            raise DesktopSessionNotFoundError("isolated desktop not found")
        return selected

    def capture_targets(self, active_job_by_target: dict[str, str] | None = None) -> list[dict[str, Any]]:
        active_job_by_target = active_job_by_target or {}
        targets: list[dict[str, Any]] = []
        for session in self.list_sessions():
            if session.status != "ready":
                continue
            active_job_id = active_job_by_target.get(session.target_id)
            targets.append(
                {
                    "id": session.target_id,
                    "kind": "desktop",
                    "label": session.label,
                    "app_bundle_id": None,
                    "app_name": None,
                    "app_pid": None,
                    "window_id": None,
                    "display_id": None,
                    "browser_url": session.browser_url,
                    "available": active_job_id is None,
                    "active_job_id": active_job_id,
                }
            )
        return targets

    @staticmethod
    def target_for_session(session: DesktopSession) -> dict[str, Any]:
        return {
            "id": session.target_id,
            "kind": "desktop",
            "label": session.label,
        }


class FakeCaptureClient:
    def __init__(self, settings, *, backend_name: str, targets: list[dict[str, Any]]) -> None:
        self.settings = settings
        self.backend_name = backend_name
        self._targets = [CaptureTarget.model_validate(target).model_dump() for target in targets]
        self._recording_pid = 1111
        self._live_audio_pid = 2222
        self._running_recording = False
        self._running_live_audio = False
        self._output_file: Path | None = None
        self._target_audio_muted = False
        self._record_microphone = False

    async def health(self) -> dict[str, Any]:
        return {"status": "ok", "provider": "test-double"}

    async def status(self, target: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "recording": {"running": self._running_recording, "pid": self._recording_pid if self._running_recording else None},
            "live_audio": {"running": self._running_live_audio, "pid": self._live_audio_pid if self._running_live_audio else None},
        }

    async def list_targets(self) -> list[dict[str, Any]]:
        if self.backend_name == "macos_local":
            return [target for target in self._targets if target["kind"] in {"display", "application", "window"}]
        return self._targets

    async def start_recording(
        self,
        job_id: str,
        output_file: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
        record_microphone: bool = False,
    ) -> dict[str, Any]:
        self._running_recording = True
        self._target_audio_muted = mute_target_audio
        self._record_microphone = record_microphone
        self._output_file = Path(output_file)
        self._output_file.parent.mkdir(parents=True, exist_ok=True)
        suffix = ":muted" if mute_target_audio else ""
        suffix += ":microphone" if record_microphone else ""
        self._output_file.write_bytes(f"test-mp4:{self.backend_name}:{target['id']}{suffix}".encode("utf-8"))
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
        record_microphone: bool = False,
    ) -> dict[str, Any]:
        self._running_live_audio = True
        self._target_audio_muted = mute_target_audio
        self._record_microphone = record_microphone
        return {"pid": self._live_audio_pid, "fifo_path": str(self.settings.recordings_root / "jobs" / job_id / "live_audio.pcm")}

    async def set_target_audio_muted(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool,
    ) -> dict[str, Any]:
        self._target_audio_muted = mute_target_audio
        return {"pid": self._recording_pid if self._running_recording else self._live_audio_pid, "mute_target_audio": mute_target_audio}

    async def set_record_microphone_enabled(
        self,
        job_id: str,
        target: dict[str, Any],
        record_microphone: bool,
    ) -> dict[str, Any]:
        self._record_microphone = record_microphone
        return {"pid": self._recording_pid if self._running_recording else self._live_audio_pid, "record_microphone": record_microphone}

    async def stop_live_audio(self, job_id: str, target: dict[str, Any]) -> dict[str, Any]:
        self._running_live_audio = False
        return {"pid": self._live_audio_pid}

    async def stream_live_audio(self, job_id: str, source: str = "system") -> AsyncIterator[bytes]:
        chunk = b"\x00\x02" * 64 if source == "microphone" else b"\x00\x01" * 64
        for _ in range(3):
            await asyncio.sleep(0.01)
            yield chunk


class FakeDesktopPoolClient:
    backend_name = "docker_desktop"

    def __init__(self, settings, desktop_sessions: DesktopSessionManager) -> None:
        self.settings = settings
        self.desktop_sessions = desktop_sessions
        self._clients: dict[str, FakeCaptureClient] = {}

    def _client_for_target(self, target: dict[str, Any] | None) -> FakeCaptureClient:
        target_id = target.get("id") if isinstance(target, dict) else None
        session = self.desktop_sessions.session_for_target(target_id)
        client = self._clients.get(session.target_id)
        if client is None:
            client = FakeCaptureClient(
                self.settings,
                backend_name="docker_desktop",
                targets=[self.desktop_sessions.target_for_session(session)],
            )
            self._clients[session.target_id] = client
        return client

    async def health(self) -> dict[str, Any]:
        sessions = self.desktop_sessions.list_sessions()
        return {
            "status": "ok",
            "provider": "test-double",
            "desktops": len(sessions),
            "ready_desktops": sum(1 for session in sessions if session.status == "ready"),
        }

    async def status(self, target: dict[str, Any] | None = None) -> dict[str, Any]:
        if target is not None:
            return await self._client_for_target(target).status()
        statuses = [await client.status() for client in self._clients.values()]
        return {
            "recording": {"running": any(bool(status["recording"]["running"]) for status in statuses)},
            "live_audio": {"running": any(bool(status["live_audio"]["running"]) for status in statuses)},
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
    ) -> dict[str, Any]:
        return await self._client_for_target(target).start_recording(
            job_id,
            output_file,
            target,
            mute_target_audio,
            record_microphone,
        )

    async def stop_recording(self, job_id: str, output_file: str, target: dict[str, Any]) -> dict[str, Any]:
        return await self._client_for_target(target).stop_recording(job_id, output_file, target)

    async def start_live_audio(
        self,
        job_id: str,
        target: dict[str, Any],
        mute_target_audio: bool = False,
        record_microphone: bool = False,
    ) -> dict[str, Any]:
        return await self._client_for_target(target).start_live_audio(
            job_id,
            target,
            mute_target_audio,
            record_microphone,
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

    async def stop_live_audio(self, job_id: str, target: dict[str, Any]) -> dict[str, Any]:
        return await self._client_for_target(target).stop_live_audio(job_id, target)

    async def stream_live_audio(self, job_id: str, source: str = "system") -> AsyncIterator[bytes]:
        raise RuntimeError("stream_live_audio requires an isolated desktop target")

    async def stream_live_audio_for_target(self, job_id: str, target: dict[str, Any], source: str = "system") -> AsyncIterator[bytes]:
        async for chunk in self._client_for_target(target).stream_live_audio(job_id, source):
            yield chunk


class FakeMacOSCaptureClient(FakeCaptureClient):
    def __init__(self, settings) -> None:
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


class FakeDesktopClient(FakeCaptureClient):
    def __init__(self, settings) -> None:
        super().__init__(
            settings,
            backend_name="docker_desktop",
            targets=[default_docker_capture_target().model_dump()],
        )


class FakeRelayManager:
    def __init__(self, on_event: EventCallback) -> None:
        self.on_event = on_event
        self._running: set[tuple[str, str]] = set()

    def is_running(self, job_id: str, source: str | None = None) -> bool:
        if source is not None:
            return (job_id, source) in self._running
        return any(active_job_id == job_id for active_job_id, _ in self._running)

    async def start(
        self,
        job_id: str,
        stream_factory,
        job_options: dict[str, Any],
        source: str = "system",
    ) -> None:
        key = (job_id, source)
        if key in self._running:
            return
        self._running.add(key)
        await self.on_event(
            job_id,
            self._tag(source, {"type": "Metadata", "request_id": f"test-{job_id}-{source}", "model_info": {"name": job_options["model"]}}),
        )
        await self.on_event(
            job_id,
            self._tag(
                source,
                {
                    "type": "Results",
                    "is_final": False,
                    "start": 0.0,
                    "duration": 0.7,
                    "channel": {"alternatives": [{"transcript": "connecting to livestream", "words": [{"speaker": 1, "start": 0.0, "end": 0.7}]}]},
                },
            ),
        )
        await self.on_event(
            job_id,
            self._tag(
                source,
                {
                    "type": "Results",
                    "is_final": True,
                    "start": 0.0,
                    "duration": 1.3,
                    "channel": {"alternatives": [{"transcript": "public session started", "words": [{"speaker": 1, "start": 0.0, "end": 1.3}]}]},
                },
            ),
        )
        await self.on_event(job_id, self._tag(source, {"type": "SpeechStarted", "timestamp": 0.0}))
        await self.on_event(job_id, self._tag(source, {"type": "UtteranceEnd", "last_word_end": 1.3}))

    async def stop(self, job_id: str, source: str | None = None) -> None:
        if source is not None:
            self._running.discard((job_id, source))
            return
        self._running = {key for key in self._running if key[0] != job_id}

    @staticmethod
    def _tag(source: str, event: dict[str, Any]) -> dict[str, Any]:
        tagged = dict(event)
        tagged["source"] = source
        return tagged
