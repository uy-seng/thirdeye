from __future__ import annotations


def test_runtime_wiring_lives_outside_fastapi_routes(settings) -> None:
    from api.runtime import AppRuntime, create_runtime

    runtime = create_runtime(settings)

    assert isinstance(runtime, AppRuntime)
    assert runtime.settings is settings
    assert runtime.capture_backends.require("macos_local").backend_name == "macos_local"
