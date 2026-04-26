from __future__ import annotations

from capture.backends import CaptureBackendRegistry
from jobs.models import JobCreate
from jobs.recovery import RecoveryService
from jobs.state_machine import JobState


class FakeCaptureClient:
    def __init__(self, status_payload: dict[str, object] | None = None) -> None:
        self.status_payload = {
            "recording": {"running": True, "pid": 111},
            "live_audio": {"running": True, "pid": 222},
        }
        if status_payload is not None:
            self.status_payload = status_payload

    async def status(self) -> dict[str, object]:
        return self.status_payload


class FakeRuntime:
    def __init__(self) -> None:
        self.restarted_jobs: list[str] = []
        self.resumed_jobs: list[str] = []

    async def restore_live_relay(self, job_id: str) -> None:
        self.restarted_jobs.append(job_id)

    async def dispatch_recover_capture(self, job_id: str) -> None:
        self.resumed_jobs.append(job_id)


def test_recovery_restarts_relay_for_active_job(settings) -> None:
    from api.main import create_runtime

    runtime = create_runtime(settings)
    job = runtime.jobs.create_job(
        JobCreate(
            title="Authorized public livestream",
        )
    )
    runtime.jobs.transition_job(job.id, JobState.PENDING_START, "created")
    runtime.jobs.transition_job(job.id, JobState.RECORDING, "recording started")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAM_CONNECTING, "live audio connecting")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAMING, "live audio streaming")

    capture_backends = CaptureBackendRegistry({"docker_desktop": FakeCaptureClient()})
    fake_runtime = FakeRuntime()
    recovery = RecoveryService(runtime.jobs, capture_backends, fake_runtime)

    summary = recovery.reconcile()

    assert summary["restarted_relays"] == [job.id]


def test_recovery_resumes_jobs_in_recoverable_post_stop_states(settings) -> None:
    from api.main import create_runtime

    runtime = create_runtime(settings)
    recovering_job = runtime.jobs.create_job(JobCreate(title="Recovering job"))
    failed_job = runtime.jobs.create_job(JobCreate(title="Failed job"))
    skipped_failed_job = runtime.jobs.create_job(JobCreate(title="Skipped failed job"))
    completed_job = runtime.jobs.create_job(JobCreate(title="Completed job"))
    failed_paths = runtime.artifacts.job_paths(failed_job.id)
    failed_paths.transcript_markdown.write_text("# Transcript\n\nRecovered\n", encoding="utf-8")
    failed_paths.transcript_text.write_text("Recovered\n", encoding="utf-8")

    runtime.jobs.update_runtime_fields(recovering_job.id, state=JobState.RECOVERING.value)
    runtime.jobs.update_runtime_fields(failed_job.id, state=JobState.FAILED.value)
    runtime.jobs.update_metadata(failed_job.id, finalization_checkpoint="transcript_compiled")
    runtime.jobs.update_runtime_fields(skipped_failed_job.id, state=JobState.FAILED.value)
    runtime.jobs.update_metadata(skipped_failed_job.id, finalization_checkpoint="transcript_compiled")
    runtime.jobs.update_runtime_fields(completed_job.id, state=JobState.COMPLETED.value)

    capture_backends = CaptureBackendRegistry({"docker_desktop": FakeCaptureClient()})
    fake_runtime = FakeRuntime()
    recovery = RecoveryService(runtime.jobs, capture_backends, fake_runtime)

    summary = recovery.reconcile()

    assert set(summary["resumed_jobs"]) == {recovering_job.id, failed_job.id}
    assert fake_runtime.resumed_jobs == summary["resumed_jobs"]


def test_recovery_uses_job_backend_status_for_active_capture(settings) -> None:
    from api.main import create_runtime

    runtime = create_runtime(settings)
    job = runtime.jobs.create_job(
        JobCreate(
            title="This Mac stream",
            capture_backend="macos_local",
            capture_target={
                "id": "window:notes-1",
                "kind": "window",
                "label": "Notes",
                "app_bundle_id": "com.apple.Notes",
                "app_name": "Notes",
                "window_id": "notes-1",
            },
        )
    )
    runtime.jobs.transition_job(job.id, JobState.PENDING_START, "created")
    runtime.jobs.transition_job(job.id, JobState.RECORDING, "recording started")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAM_CONNECTING, "live audio connecting")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAMING, "live audio streaming")

    capture_backends = CaptureBackendRegistry(
        {
            "docker_desktop": FakeCaptureClient(
                {
                    "recording": {"running": False, "pid": None},
                    "live_audio": {"running": False, "pid": None},
                }
            ),
            "macos_local": FakeCaptureClient(),
        }
    )
    fake_runtime = FakeRuntime()
    recovery = RecoveryService(runtime.jobs, capture_backends, fake_runtime)

    summary = recovery.reconcile()

    assert summary["restarted_relays"] == [job.id]


def test_recovery_fails_live_job_when_capture_processes_are_gone(settings) -> None:
    from api.main import create_runtime

    runtime = create_runtime(settings)
    job = runtime.jobs.create_job(JobCreate(title="Dead stream"))
    runtime.jobs.transition_job(job.id, JobState.PENDING_START, "created")
    runtime.jobs.transition_job(job.id, JobState.RECORDING, "recording started")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAM_CONNECTING, "live audio connecting")
    runtime.jobs.transition_job(job.id, JobState.LIVE_STREAMING, "live audio streaming")

    capture_backends = CaptureBackendRegistry(
        {
            "docker_desktop": FakeCaptureClient(
                {
                    "recording": {"running": False, "pid": None},
                    "live_audio": {"running": False, "pid": None},
                }
            )
        }
    )
    fake_runtime = FakeRuntime()
    recovery = RecoveryService(runtime.jobs, capture_backends, fake_runtime)

    summary = recovery.reconcile()

    recovered = runtime.jobs.get_job(job.id)
    assert summary["failed_jobs"] == [job.id]
    assert recovered.state == JobState.FAILED.value
    assert recovered.error_message == "capture processes are no longer running"
    assert fake_runtime.restarted_jobs == []
