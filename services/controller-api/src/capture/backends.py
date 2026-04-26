from __future__ import annotations

from dataclasses import dataclass

from capture.desktop_exec import (
    CaptureClientProtocol,
    DesktopHttpClient,
    FakeDesktopClient,
    FakeMacOSCaptureClient,
    MacOSCaptureHttpClient,
)
from core.settings import Settings


@dataclass
class CaptureBackendRegistry:
    backends: dict[str, CaptureClientProtocol]

    def require(self, backend: str) -> CaptureClientProtocol:
        try:
            return self.backends[backend]
        except KeyError as exc:
            raise KeyError("capture backend not found") from exc


def build_capture_backends(settings: Settings) -> CaptureBackendRegistry:
    if settings.fake_mode:
        return CaptureBackendRegistry(
            {
                "docker_desktop": FakeDesktopClient(settings),
                "macos_local": FakeMacOSCaptureClient(settings),
            }
        )

    return CaptureBackendRegistry(
        {
            "docker_desktop": DesktopHttpClient(settings),
            "macos_local": MacOSCaptureHttpClient(settings),
        }
    )
