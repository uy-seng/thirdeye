from __future__ import annotations

import json
import os
import socket
import subprocess
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.settings import Settings
from core.utils import ensure_directory, isoformat, utcnow


DesktopSessionStatus = Literal["starting", "ready", "stopped", "destroyed", "error"]


class DesktopSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = None


class DesktopSession(BaseModel):
    id: str
    target_id: str
    label: str
    container_id: str | None = None
    container_name: str
    browser_url: str
    agent_url: str
    status: DesktopSessionStatus
    created_at: str
    active_job_id: str | None = None
    active_job_state: str | None = None
    error_message: str | None = None


class DesktopSessionsResponse(BaseModel):
    desktops: list[DesktopSession]


class DesktopSessionError(RuntimeError):
    pass


class DesktopSessionLimitError(DesktopSessionError):
    pass


class DesktopSessionNotFoundError(DesktopSessionError):
    pass


def _port_is_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


class DesktopSessionManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = ensure_directory(settings.desktop_sessions_root)
        self.registry_path = settings.desktop_sessions_registry_path
        self.config_root = ensure_directory(self.root / "config")
        ensure_directory(self.registry_path.parent)

    def list_sessions(self) -> list[DesktopSession]:
        sessions = [session for session in self._read_registry() if session.status != "destroyed"]
        return [self._refresh_session(session) for session in sessions]

    def create_session(self, label: str | None = None) -> DesktopSession:
        sessions = self.list_sessions()
        active_sessions = [session for session in sessions if session.status in {"starting", "ready"}]
        if len(active_sessions) >= self.settings.max_desktop_sessions:
            raise DesktopSessionLimitError("maximum isolated desktops are already running")

        desktop_id = uuid.uuid4().hex[:10]
        browser_port = self._allocate_port(self.settings.desktop_browser_port_start, sessions)
        agent_port = self._allocate_port(self.settings.desktop_agent_port_start, sessions)
        session = DesktopSession(
            id=desktop_id,
            target_id=f"desktop:{desktop_id}",
            label=label or f"Isolated desktop {len(sessions) + 1}",
            container_id=None,
            container_name=f"thirdeye-desktop-{desktop_id}",
            browser_url=f"http://127.0.0.1:{browser_port}",
            agent_url=f"http://127.0.0.1:{agent_port}",
            status="ready" if self.settings.fake_mode else "starting",
            created_at=isoformat(utcnow()) or "",
            active_job_id=None,
            active_job_state=None,
            error_message=None,
        )

        if self.settings.fake_mode:
            self._write_registry([*sessions, session])
            return session

        try:
            started = self._start_container(session, browser_port=browser_port, agent_port=agent_port)
        except Exception as exc:
            failed = session.model_copy(update={"status": "error", "error_message": str(exc)})
            self._write_registry([*sessions, failed])
            raise DesktopSessionError(str(exc)) from exc

        ready = started.model_copy(update={"status": "ready", "error_message": None})
        self._write_registry([*sessions, ready])
        return ready

    def destroy_session(self, desktop_id: str) -> DesktopSession:
        sessions = self.list_sessions()
        selected = next((session for session in sessions if session.id == desktop_id), None)
        if selected is None:
            raise DesktopSessionNotFoundError("isolated desktop not found")

        if not self.settings.fake_mode and selected.container_id:
            subprocess.run(["docker", "rm", "-f", selected.container_id], capture_output=True, text=True, check=False)

        destroyed = selected.model_copy(update={"status": "destroyed", "active_job_id": None, "active_job_state": None})
        self._write_registry([session for session in sessions if session.id != desktop_id])
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

    def target_for_session(self, session: DesktopSession) -> dict[str, Any]:
        return {
            "id": session.target_id,
            "kind": "desktop",
            "label": session.label,
        }

    def _read_registry(self) -> list[DesktopSession]:
        if not self.registry_path.exists():
            return []
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        raw_sessions = payload.get("desktops", []) if isinstance(payload, dict) else []
        if not isinstance(raw_sessions, list):
            return []
        sessions: list[DesktopSession] = []
        for raw_session in raw_sessions:
            try:
                sessions.append(DesktopSession.model_validate(raw_session))
            except Exception:
                continue
        return sessions

    def _write_registry(self, sessions: list[DesktopSession]) -> None:
        ensure_directory(self.registry_path.parent)
        payload = {"desktops": [session.model_dump() for session in sessions if session.status != "destroyed"]}
        self.registry_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _refresh_session(self, session: DesktopSession) -> DesktopSession:
        if self.settings.fake_mode or session.status in {"destroyed", "error"} or not session.container_id:
            return session

        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", session.container_id],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return session.model_copy(update={"status": "stopped"})
        return session.model_copy(update={"status": "ready" if result.stdout.strip() == "true" else "stopped"})

    def _allocate_port(self, start: int, sessions: list[DesktopSession]) -> int:
        used = {self._port_from_url(session.browser_url) for session in sessions}
        used |= {self._port_from_url(session.agent_url) for session in sessions}
        for port in range(start, start + 100):
            if port not in used and not _port_is_open(port):
                return port
        raise DesktopSessionError("no local ports are available for an isolated desktop")

    @staticmethod
    def _port_from_url(url: str) -> int:
        return int(url.rsplit(":", 1)[1])

    def _start_container(self, session: DesktopSession, *, browser_port: int, agent_port: int) -> DesktopSession:
        image = self.settings.desktop_image
        self._ensure_image(image)
        config_dir = ensure_directory(self.config_root / session.id)
        command = [
            "docker",
            "run",
            "-d",
            "--name",
            session.container_name,
            "--label",
            "thirdeye.managed=true",
            "--label",
            f"thirdeye.desktop_session={session.id}",
            "--label",
            "com.docker.compose.project=thirdeye",
            "--label",
            "com.docker.compose.service=desktop",
            "--shm-size",
            "2g",
            "--tmpfs",
            "/tmp",
            "--security-opt",
            "seccomp=unconfined",
            "-e",
            f"PUID={os.environ.get('PUID', '1000')}",
            "-e",
            f"PGID={os.environ.get('PGID', '1000')}",
            "-e",
            f"TZ={self.settings.tz}",
            "-e",
            "PIXELFLUX_WAYLAND=false",
            "-e",
            "CHROME_CLI=--remote-debugging-port=9222 --remote-debugging-address=0.0.0.0 --autoplay-policy=no-user-gesture-required",
            "-e",
            f"RECORDING_FPS={os.environ.get('RECORDING_FPS', '15')}",
            "-e",
            f"RECORDING_WIDTH={os.environ.get('RECORDING_WIDTH', '1280')}",
            "-e",
            f"RECORDING_HEIGHT={os.environ.get('RECORDING_HEIGHT', '720')}",
            "-e",
            f"SELKIES_MANUAL_WIDTH={os.environ.get('RECORDING_WIDTH', '1280')}",
            "-e",
            f"SELKIES_MANUAL_HEIGHT={os.environ.get('RECORDING_HEIGHT', '720')}",
            "-e",
            f"FAKE_CAPTURE={'1' if self.settings.fake_mode else '0'}",
            "-p",
            f"127.0.0.1:{browser_port}:3000",
            "-p",
            f"127.0.0.1:{agent_port}:8790",
            "-v",
            f"{config_dir}:/config",
            "-v",
            f"{self.settings.recordings_root}:/recordings",
            image,
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise DesktopSessionError(result.stderr.strip() or result.stdout.strip() or "failed to start isolated desktop")
        container_id = result.stdout.strip()
        return session.model_copy(update={"container_id": container_id})

    def _ensure_image(self, image: str) -> None:
        inspect = subprocess.run(["docker", "image", "inspect", image], capture_output=True, text=True, check=False)
        if inspect.returncode == 0 and image != "thirdeye-desktop:local":
            return
        build = subprocess.run(
            [
                "docker",
                "build",
                "-f",
                "infra/docker/desktop/Dockerfile",
                "-t",
                image,
                ".",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if build.returncode != 0:
            raise DesktopSessionError(build.stderr.strip() or build.stdout.strip() or "failed to build isolated desktop image")
