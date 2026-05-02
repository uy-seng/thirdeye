from __future__ import annotations

from dataclasses import dataclass

from capture.desktop_exec import (
    CaptureClientProtocol,
    DesktopHttpClient,
    DesktopPoolHttpClient,
    FakeDesktopClient,
    FakeDesktopPoolClient,
    FakeMacOSCaptureClient,
    MacOSCaptureHttpClient,
)
from capture.desktop_sessions import DesktopSessionManager
from core.settings import Settings


@dataclass
class CaptureBackendRegistry:
    backends: dict[str, CaptureClientProtocol]

    def require(self, backend: str) -> CaptureClientProtocol:
        try:
            return self.backends[backend]
        except KeyError as exc:
            raise KeyError("capture backend not found") from exc


def build_capture_backends(settings: Settings, desktop_sessions: DesktopSessionManager) -> CaptureBackendRegistry:
    if settings.fake_mode:
        return CaptureBackendRegistry(
            {
                "docker_desktop": FakeDesktopPoolClient(settings, desktop_sessions),
                "macos_local": FakeMacOSCaptureClient(settings),
            }
        )

    return CaptureBackendRegistry(
        {
            "docker_desktop": DesktopPoolHttpClient(settings, desktop_sessions),
            "macos_local": MacOSCaptureHttpClient(settings),
        }
    )
