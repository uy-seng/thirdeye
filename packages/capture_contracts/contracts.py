from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


CaptureBackendName = Literal["docker_desktop", "macos_local"]
CaptureTargetKind = Literal["desktop", "display", "application", "window"]


class CaptureTarget(BaseModel):
    id: str
    kind: CaptureTargetKind
    label: str
    app_bundle_id: str | None = None
    app_name: str | None = None
    app_pid: int | None = None
    window_id: str | None = None
    display_id: str | None = None


class CaptureTargetsResponse(BaseModel):
    backend: CaptureBackendName
    targets: list[CaptureTarget]


def default_docker_capture_target() -> CaptureTarget:
    return CaptureTarget(
        id="desktop",
        kind="desktop",
        label="Isolated desktop",
    )


def resolve_capture_selection(
    backend: CaptureBackendName | str | None,
    target: CaptureTarget | dict[str, Any] | None,
) -> tuple[CaptureBackendName, CaptureTarget]:
    selected_backend = backend or "docker_desktop"
    if selected_backend not in {"docker_desktop", "macos_local"}:
        raise ValueError("unsupported capture backend")

    if selected_backend == "docker_desktop":
        selected_target = default_docker_capture_target() if target is None else CaptureTarget.model_validate(target)
        expected = default_docker_capture_target()
        if selected_target.id != expected.id or selected_target.kind != expected.kind:
            raise ValueError("docker_desktop only supports the isolated desktop target")
        return "docker_desktop", selected_target

    if target is None:
        raise ValueError("capture_target is required for macos_local")
    return "macos_local", CaptureTarget.model_validate(target)


def capture_selection_from_metadata(metadata: dict[str, Any]) -> tuple[CaptureBackendName, dict[str, Any]]:
    raw_capture = metadata.get("capture")
    if not isinstance(raw_capture, dict):
        default_target = default_docker_capture_target().model_dump()
        return "docker_desktop", default_target

    backend, target = resolve_capture_selection(
        raw_capture.get("backend"),
        raw_capture.get("target"),
    )
    return backend, target.model_dump()


__all__ = [
    "CaptureBackendName",
    "CaptureTarget",
    "CaptureTargetKind",
    "CaptureTargetsResponse",
    "capture_selection_from_metadata",
    "default_docker_capture_target",
    "resolve_capture_selection",
]
