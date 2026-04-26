from __future__ import annotations

import asyncio

from capture.backends import CaptureBackendRegistry
from jobs.jobs import JobRepository
from jobs.state_machine import JobState, RECOVERABLE_POST_STOP_STATES


class RecoveryService:
    def __init__(self, jobs: JobRepository, capture_backends: CaptureBackendRegistry, runtime) -> None:
        self.jobs = jobs
        self.capture_backends = capture_backends
        self.runtime = runtime

    async def areconcile(self) -> dict[str, list[str]]:
        restarted_relays: list[str] = []
        resumed_jobs: list[str] = []
        failed_jobs: list[str] = []
        backend_statuses: dict[str, dict[str, object]] = {}
        for job in self.jobs.list_jobs():
            state = JobState(job.state)
            if state == JobState.LIVE_STREAMING:
                status = backend_statuses.get(job.capture_backend)
                if status is None:
                    status = await self.capture_backends.require(job.capture_backend).status()
                    backend_statuses[job.capture_backend] = status
                recording_running = bool((status.get("recording") or {}).get("running"))
                live_audio_running = bool((status.get("live_audio") or {}).get("running"))
                if recording_running and live_audio_running:
                    await self.runtime.restore_live_relay(job.id)
                    restarted_relays.append(job.id)
                else:
                    self.jobs.fail_job(job.id, "capture process exited", "capture processes are no longer running")
                    failed_jobs.append(job.id)
                continue
            if state in RECOVERABLE_POST_STOP_STATES or self._is_terminal_post_stop_recovery_candidate(job):
                await self.runtime.dispatch_recover_capture(job.id)
                resumed_jobs.append(job.id)
        return {"restarted_relays": restarted_relays, "resumed_jobs": resumed_jobs, "failed_jobs": failed_jobs}

    def _is_terminal_post_stop_recovery_candidate(self, job) -> bool:
        if job.state != JobState.FAILED.value:
            return False
        metadata = job.metadata_json
        checkpoint = metadata.get("finalization_checkpoint")
        if checkpoint not in {"transcript_compiled", "summary_completed"}:
            return False
        paths = self.jobs.artifacts.job_paths(job.id)
        transcript_ready = paths.transcript_markdown.exists() and paths.transcript_text.exists()
        return transcript_ready or paths.deepgram_events.exists()

    def reconcile(self) -> dict[str, list[str]]:
        return asyncio.run(self.areconcile())
