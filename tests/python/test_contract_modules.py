from __future__ import annotations


def test_backend_contracts_have_dedicated_import_modules() -> None:
    from api.api_schemas import JobCreate, JobResponse
    from capture_contracts.contracts import CaptureTarget, default_docker_capture_target
    from db.models import Job, JobTransition

    assert Job.__tablename__ == "jobs"
    assert JobTransition.__tablename__ == "job_transitions"
    assert JobCreate.model_fields["title"].is_required()
    assert "state" in JobResponse.model_fields
    assert isinstance(default_docker_capture_target(), CaptureTarget)


def test_capture_target_carries_app_process_id_for_app_audio_routing() -> None:
    from capture_contracts.contracts import CaptureTarget

    target = CaptureTarget(
        id="window:chrome-1",
        kind="window",
        label="Google Meet",
        app_bundle_id="com.google.Chrome",
        app_name="Google Chrome",
        app_pid=4242,
        window_id="chrome-1",
    )

    assert target.app_pid == 4242
    assert target.model_dump()["app_pid"] == 4242
