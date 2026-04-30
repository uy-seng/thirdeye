from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from jobs.artifacts import ArtifactManager
from capture.backends import CaptureBackendRegistry
from jobs.models import (
    Job,
    JobCreate,
    JobResponse,
    JobTransition,
    JobTransitionResponse,
    merge_metadata,
    resolve_capture_selection,
)
from core.settings import Settings
from jobs.state_machine import ACTIVE_JOB_STATES, JobState, JobStateMachine
from transcripts.prompt_service import TranscriptPromptService
from transcripts.compiler import TranscriptCompiler
from transcripts.store import TranscriptStore
from core.utils import dump_json, isoformat, load_json, utcnow


class CaptureConflictError(RuntimeError):
    pass


class CaptureStartupError(RuntimeError):
    pass


class CaptureStopError(RuntimeError):
    pass


class CaptureMuteError(RuntimeError):
    pass


class CaptureMuteUnsupportedError(CaptureMuteError):
    pass


class CaptureMuteStateError(CaptureMuteError):
    pass


@dataclass
class JobRepository:
    session_factory: sessionmaker
    settings: Settings
    artifacts: ArtifactManager
    state_machine: JobStateMachine

    def create_job(self, payload: JobCreate) -> JobResponse:
        job_id = uuid.uuid4().hex
        paths = self.artifacts.job_paths(job_id)
        stage_recording = self.artifacts.recording_stage_path(job_id)
        stage_audio = self.artifacts.live_audio_stage_path(job_id)
        capture_backend, capture_target = resolve_capture_selection(payload.capture_backend, payload.capture_target)
        with self.session_factory() as session:
            job = Job(
                id=job_id,
                title=payload.title,
                source_url=payload.source_url,
                created_at=utcnow(),
                started_at=None,
                stopped_at=None,
                state=JobState.IDLE.value,
                max_duration_minutes=payload.max_duration_minutes or self.settings.max_duration_minutes,
                auto_stop_enabled=self.settings.enable_auto_stop if payload.auto_stop_enabled is None else payload.auto_stop_enabled,
                silence_timeout_minutes=payload.silence_timeout_minutes or self.settings.silence_timeout_minutes,
                deepgram_model=payload.deepgram_model or self.settings.deepgram_model,
                deepgram_language=payload.deepgram_language if payload.deepgram_language is not None else self.settings.deepgram_language,
                diarize=self.settings.deepgram_diarize if payload.diarize is None else payload.diarize,
                smart_format=self.settings.deepgram_smart_format if payload.smart_format is None else payload.smart_format,
                interim_results=self.settings.deepgram_interim_results if payload.interim_results is None else payload.interim_results,
                notify_email="",
                summary_model=payload.summary_model or self.settings.openclaw_summary_model,
                recording_path=str(paths.recording) if payload.record_screen else None,
                audio_path=str(stage_audio),
                transcript_text_path=str(paths.transcript_text),
                transcript_events_path=str(paths.deepgram_events),
                summary_path=str(paths.summary),
                ffmpeg_pid=None,
                live_audio_pid=None,
                deepgram_request_id=None,
                error_message=None,
                metadata_json=dump_json(
                    {
                        "capture": {
                            "backend": capture_backend,
                            "target": capture_target.model_dump(),
                        },
                        "session_preferences": {
                            "record_screen": payload.record_screen,
                            "generate_summary": payload.generate_summary,
                            "mute_target_audio": payload.mute_target_audio,
                            "notify_on_inactivity": payload.notify_on_inactivity,
                        },
                        "recording_stage_path": str(stage_recording),
                        "audio_stage_path": str(stage_audio),
                    }
                ),
            )
            session.add(job)
            session.commit()
            response = JobResponse.from_orm_job(job)
        self.artifacts.write_metadata(response)
        self.artifacts.append_controller_event(job_id, {"type": "created", "timestamp": response.created_at})
        return response

    def get_job(self, job_id: str) -> JobResponse:
        with self.session_factory() as session:
            job = session.get(Job, job_id)
            if job is None:
                raise KeyError(job_id)
            return JobResponse.from_orm_job(job)

    def get_job_orm(self, session: Session, job_id: str) -> Job:
        job = session.get(Job, job_id)
        if job is None:
            raise KeyError(job_id)
        return job

    def list_jobs(self) -> list[JobResponse]:
        with self.session_factory() as session:
            rows = session.execute(select(Job).order_by(Job.created_at.desc())).scalars().all()
            return [JobResponse.from_orm_job(row) for row in rows]

    def list_transitions(self, job_id: str) -> list[JobTransitionResponse]:
        with self.session_factory() as session:
            rows = session.execute(select(JobTransition).where(JobTransition.job_id == job_id).order_by(JobTransition.id)).scalars().all()
            return [
                JobTransitionResponse(
                    from_state=row.from_state,
                    to_state=row.to_state,
                    occurred_at=isoformat(row.occurred_at) or "",
                    reason=row.reason,
                    payload=load_json(row.payload_json),
                )
                for row in rows
            ]

    def active_job(self) -> JobResponse | None:
        with self.session_factory() as session:
            rows = session.execute(select(Job).order_by(Job.created_at.desc())).scalars().all()
            for row in rows:
                if JobState(row.state) in ACTIVE_JOB_STATES:
                    return JobResponse.from_orm_job(row)
        return None

    def update_runtime_fields(self, job_id: str, **fields: Any) -> JobResponse:
        with self.session_factory() as session:
            job = self.get_job_orm(session, job_id)
            for key, value in fields.items():
                setattr(job, key, value)
            session.add(job)
            session.commit()
            response = JobResponse.from_orm_job(job)
        self.artifacts.write_metadata(response)
        return response

    def update_metadata(self, job_id: str, **updates: Any) -> JobResponse:
        with self.session_factory() as session:
            job = self.get_job_orm(session, job_id)
            merge_metadata(job, updates)
            session.add(job)
            session.commit()
            response = JobResponse.from_orm_job(job)
        self.artifacts.write_metadata(response)
        return response

    def transition_job(self, job_id: str, target: JobState, reason: str, payload: dict[str, Any] | None = None) -> JobResponse:
        with self.session_factory() as session:
            job = self.get_job_orm(session, job_id)
            current = JobState(job.state)
            self.state_machine.assert_transition(current, target)
            if target == JobState.RECORDING and job.started_at is None:
                job.started_at = utcnow()
            if target == JobState.STOPPING and job.stopped_at is None:
                job.stopped_at = utcnow()
            job.state = target.value
            transition = JobTransition(
                job_id=job_id,
                from_state=current.value,
                to_state=target.value,
                occurred_at=utcnow(),
                reason=reason,
                payload_json=dump_json(payload or {}),
            )
            session.add(job)
            session.add(transition)
            session.commit()
            response = JobResponse.from_orm_job(job)
        self.artifacts.append_controller_event(
            job_id,
            {
                "type": "transition",
                "from_state": current.value,
                "to_state": target.value,
                "reason": reason,
                "payload": payload or {},
                "timestamp": response.stopped_at or response.started_at or response.created_at,
            },
        )
        self.artifacts.write_metadata(response)
        return response

    def fail_job(self, job_id: str, reason: str, message: str) -> JobResponse:
        with self.session_factory() as session:
            job = self.get_job_orm(session, job_id)
            current = JobState(job.state)
            self.state_machine.assert_transition(current, JobState.FAILED)
            job.state = JobState.FAILED.value
            job.error_message = message
            transition = JobTransition(
                job_id=job_id,
                from_state=current.value,
                to_state=JobState.FAILED.value,
                occurred_at=utcnow(),
                reason=reason,
                payload_json=dump_json({"error": message}),
            )
            session.add(job)
            session.add(transition)
            session.commit()
            response = JobResponse.from_orm_job(job)
        self.artifacts.append_controller_event(job_id, {"type": "failed", "reason": reason, "error": message, "timestamp": response.created_at})
        self.artifacts.write_metadata(response)
        return response

    def cleanup_job(self, job_id: str) -> JobResponse:
        with self.session_factory() as session:
            job = self.get_job_orm(session, job_id)
            if JobState(job.state) in ACTIVE_JOB_STATES:
                raise RuntimeError("cannot clean up an active job")
            response = JobResponse.from_orm_job(job)
        self.artifacts.cleanup_job(job_id)
        return response

    def delete_job(self, job_id: str) -> JobResponse:
        with self.session_factory() as session:
            job = self.get_job_orm(session, job_id)
            if JobState(job.state) in ACTIVE_JOB_STATES:
                raise RuntimeError("cannot delete an active job")
            response = JobResponse.from_orm_job(job)
            session.execute(delete(JobTransition).where(JobTransition.job_id == job_id))
            session.delete(job)
            session.commit()
        self.artifacts.cleanup_job(job_id)
        return response


class CaptureRuntime:
    SUMMARY_STATUS_KEY = "summary_status"
    SUMMARY_ERROR_KEY = "summary_error"
    SUMMARY_COMPLETED_AT_KEY = "summary_completed_at"
    SUMMARY_RERUN_STATUS_KEY = "summary_rerun_status"
    SUMMARY_RERUN_ERROR_KEY = "summary_rerun_error"
    SUMMARY_RERUN_COMPLETED_AT_KEY = "summary_rerun_completed_at"
    FINALIZATION_CHECKPOINT_KEY = "finalization_checkpoint"

    def __init__(
        self,
        settings: Settings,
        jobs: JobRepository,
        artifacts: ArtifactManager,
        transcript_store: TranscriptStore,
        transcript_compiler: TranscriptCompiler,
        transcript_prompts: TranscriptPromptService,
        relay_manager,
        capture_backends: CaptureBackendRegistry,
        transcript_hub,
    ) -> None:
        self.settings = settings
        self.jobs = jobs
        self.artifacts = artifacts
        self.transcript_store = transcript_store
        self.transcript_compiler = transcript_compiler
        self.transcript_prompts = transcript_prompts
        self.relay_manager = relay_manager
        self.capture_backends = capture_backends
        self.desktop_client = capture_backends.require("docker_desktop")
        self.transcript_hub = transcript_hub
        self._supervisor_tasks: dict[str, asyncio.Task[None]] = {}
        self._background_tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._background_tasks_lock = asyncio.Lock()

    @staticmethod
    def _failure_message(exc: Exception) -> str:
        message = str(exc).strip()
        return message or exc.__class__.__name__

    async def handle_deepgram_event(self, job_id: str, raw_event: dict[str, Any]) -> None:
        result = self.transcript_store.append(job_id, raw_event)
        normalized = result.event
        if normalized["type"] == "metadata" and normalized.get("request_id"):
            self.jobs.update_runtime_fields(job_id, deepgram_request_id=normalized["request_id"])
        if normalized["type"] in {"speech_started", "utterance_end"}:
            self.jobs.update_metadata(job_id, last_speech_event=normalized)
        if result.promoted is not None:
            await self.transcript_hub.publish(job_id, result.promoted)
        await self.transcript_hub.publish(job_id, normalized)

    async def mark_degraded(self, job_id: str, message: str) -> None:
        self.jobs.update_metadata(job_id, deepgram_degraded=True, deepgram_error=message)
        await self.transcript_hub.publish(job_id, {"type": "warning", "message": message})

    def _backend_for_job(self, job: JobResponse):
        return self.capture_backends.require(job.capture_backend)

    @staticmethod
    def _session_preference(job: JobResponse, key: str, default: bool) -> bool:
        preferences = job.metadata_json.get("session_preferences")
        if not isinstance(preferences, dict):
            return default
        value = preferences.get(key)
        return value if isinstance(value, bool) else default

    def _record_screen_enabled(self, job: JobResponse) -> bool:
        return self._session_preference(job, "record_screen", True)

    def _summary_enabled(self, job: JobResponse) -> bool:
        return self._session_preference(job, "generate_summary", True)

    def _mute_target_audio_enabled(self, job: JobResponse) -> bool:
        return self._session_preference(job, "mute_target_audio", False)

    def _update_session_preference(self, job: JobResponse, key: str, value: bool) -> JobResponse:
        preferences = job.metadata_json.get("session_preferences")
        next_preferences = dict(preferences) if isinstance(preferences, dict) else {}
        next_preferences[key] = value
        return self.jobs.update_metadata(job.id, session_preferences=next_preferences)

    async def start_capture(self, payload: JobCreate) -> JobResponse:
        if self.jobs.active_job() is not None:
            raise CaptureConflictError("only one active capture is allowed")

        job = self.jobs.create_job(payload)
        backend = self._backend_for_job(job)
        recording_stage_path = self.artifacts.recording_stage_path(job.id).as_posix()
        record_screen = self._record_screen_enabled(job)
        mute_target_audio = self._mute_target_audio_enabled(job)
        self.jobs.transition_job(job.id, JobState.PENDING_START, "capture requested")
        recording_started = False
        live_audio_started = False
        try:
            if record_screen:
                recording_response = await backend.start_recording(
                    job.id,
                    recording_stage_path,
                    job.capture_target,
                    mute_target_audio,
                )
                recording_started = True
                job = self.jobs.update_runtime_fields(
                    job.id,
                    ffmpeg_pid=recording_response.get("pid"),
                    audio_path=self.artifacts.live_audio_stage_path(job.id).as_posix(),
                )
                self.jobs.transition_job(job.id, JobState.RECORDING, "recording started")

            live_audio_response = await backend.start_live_audio(job.id, job.capture_target, mute_target_audio)
            live_audio_started = True
            job = self.jobs.update_runtime_fields(job.id, live_audio_pid=live_audio_response.get("pid"))
            self.jobs.transition_job(job.id, JobState.LIVE_STREAM_CONNECTING, "live audio started")
            await self.relay_manager.start(
                job.id,
                lambda: backend.stream_live_audio(job.id),
                {
                    "model": job.deepgram_model,
                    "language": job.deepgram_language,
                    "diarize": job.diarize,
                    "smart_format": job.smart_format,
                    "interim_results": job.interim_results,
                },
            )
            job = self.jobs.transition_job(job.id, JobState.LIVE_STREAMING, "deepgram relay started")
            await self.transcript_hub.publish(job.id, {"type": "status", "state": job.state})
            self._supervisor_tasks[job.id] = asyncio.create_task(self._supervise(job.id))
            return job
        except Exception as exc:
            message = self._start_failure_message(exc)
            if live_audio_started:
                with contextlib.suppress(Exception):
                    await backend.stop_live_audio(job.id, job.capture_target)
            if recording_started:
                with contextlib.suppress(Exception):
                    await backend.stop_recording(job.id, recording_stage_path, job.capture_target)
            failed_job = self.jobs.fail_job(job.id, "capture start failed", message)
            await self.transcript_hub.publish(job.id, {"type": "status", "state": failed_job.state, "error": message})
            raise CaptureStartupError(message) from exc

    async def stop_capture(self, job_id: str, *, skip_summary: bool = False) -> JobResponse:
        job = self.jobs.get_job(job_id)
        backend = self._backend_for_job(job)
        recording_stage_path = self.artifacts.recording_stage_path(job.id).as_posix()
        record_screen = self._record_screen_enabled(job)
        if job.state in {
            JobState.STOPPING.value,
            JobState.FINALIZING_DEEPGRAM.value,
            JobState.COMPILING_TRANSCRIPT.value,
            JobState.SUMMARIZING.value,
            JobState.RECOVERING.value,
            JobState.COMPLETED.value,
            JobState.FAILED.value,
            JobState.CANCELED.value,
        }:
            return job
        if job.state == JobState.RECORDING.value:
            self.jobs.transition_job(job.id, JobState.LIVE_STREAM_CONNECTING, "normalizing stop path")
            self.jobs.transition_job(job.id, JobState.LIVE_STREAMING, "normalizing stop path")
        recording_stopped = False
        recording_copied = False
        try:
            job = self.jobs.transition_job(job.id, JobState.STOPPING, "stop requested")
            await self.transcript_hub.publish(job.id, {"type": "status", "state": job.state})
            await backend.stop_live_audio(job.id, job.capture_target)
            await self.relay_manager.stop(job.id)
            job = self.jobs.transition_job(job.id, JobState.FINALIZING_DEEPGRAM, "deepgram finalized")
            if record_screen:
                await backend.stop_recording(job.id, recording_stage_path, job.capture_target)
                recording_stopped = True
                recording_path = self.artifacts.copy_recording(job.id)
                recording_copied = True
                self.jobs.update_runtime_fields(job.id, recording_path=recording_path)
            else:
                self.jobs.update_runtime_fields(job.id, recording_path=None)
            job = self._compile_transcript(job.id)
        except Exception as exc:
            message = self._failure_message(exc)
            with contextlib.suppress(Exception):
                await backend.stop_live_audio(job.id, job.capture_target)
            with contextlib.suppress(Exception):
                await self.relay_manager.stop(job.id)
            if record_screen and not recording_stopped:
                with contextlib.suppress(Exception):
                    await backend.stop_recording(job.id, recording_stage_path, job.capture_target)
                    recording_stopped = True
            if record_screen and not recording_copied:
                with contextlib.suppress(Exception):
                    recording_path = self.artifacts.copy_recording(job.id)
                    recording_copied = True
                    self.jobs.update_runtime_fields(job.id, recording_path=recording_path)
            failed_job = self.jobs.fail_job(job.id, "capture stop failed", message)
            with contextlib.suppress(Exception):
                await self.transcript_hub.publish(job.id, {"type": "status", "state": failed_job.state, "error": message})
            raise CaptureStopError(message) from exc

        job = await self._finalize_post_stop(
            job.id,
            completion_reason="capture completed",
            skip_summary=skip_summary or not self._summary_enabled(job),
        )
        self.artifacts.write_metadata(job)
        with contextlib.suppress(Exception):
            if job.state == JobState.COMPLETED.value:
                await self.transcript_hub.publish(job.id, {"type": "complete", "state": job.state})
            else:
                await self.transcript_hub.publish(job.id, {"type": "status", "state": job.state})
        return job

    async def set_target_audio_muted(self, job_id: str, mute_target_audio: bool) -> JobResponse:
        job = self.jobs.get_job(job_id)
        if job.capture_backend != "macos_local":
            raise CaptureMuteUnsupportedError("runtime mute is only available for This Mac capture")
        if job.capture_target.get("kind") not in {"application", "window"}:
            raise CaptureMuteUnsupportedError("runtime mute requires an app or window target")
        if job.state not in {JobState.RECORDING.value, JobState.LIVE_STREAMING.value}:
            raise CaptureMuteStateError("capture must be recording before changing mute")
        if self._mute_target_audio_enabled(job) == mute_target_audio:
            return job

        backend = self._backend_for_job(job)
        try:
            await backend.set_target_audio_muted(job.id, job.capture_target, mute_target_audio)
        except Exception as exc:
            raise CaptureMuteError(self._failure_message(exc)) from exc

        updated = self._update_session_preference(job, "mute_target_audio", mute_target_audio)
        with contextlib.suppress(Exception):
            await self.transcript_hub.publish(
                job.id,
                {"type": "status", "state": updated.state, "mute_target_audio": mute_target_audio},
            )
        return updated

    async def restore_live_relay(self, job_id: str) -> None:
        if not self.relay_manager.is_running(job_id):
            job = self.jobs.get_job(job_id)
            backend = self._backend_for_job(job)
            await self.relay_manager.start(
                job_id,
                lambda: backend.stream_live_audio(job_id),
                {
                    "model": job.deepgram_model,
                    "language": job.deepgram_language,
                    "diarize": job.diarize,
                    "smart_format": job.smart_format,
                    "interim_results": job.interim_results,
                },
            )

    async def dispatch_stop_capture(self, job_id: str, *, skip_summary: bool = False) -> JobResponse:
        self.jobs.get_job(job_id)
        await self._ensure_background_task(job_id, "stop", self._run_stop_capture(job_id, skip_summary=skip_summary))
        return self.jobs.get_job(job_id)

    async def dispatch_summary_rerun(self, job_id: str) -> JobResponse:
        self.jobs.get_job(job_id)
        self._mark_summary_running(job_id, include_legacy_keys=True)
        await self._ensure_background_task(job_id, "summary_rerun", self._run_summary_rerun(job_id))
        return self.jobs.get_job(job_id)

    async def dispatch_recover_capture(self, job_id: str) -> JobResponse:
        job = self.jobs.get_job(job_id)
        if not self._can_recover_post_stop(job):
            raise RuntimeError("job is not recoverable")
        if JobState(job.state) != JobState.COMPILING_TRANSCRIPT and JobState(job.state) != JobState.RECOVERING:
            job = self.jobs.transition_job(job.id, JobState.RECOVERING, "recovery requested")
        await self._ensure_background_task(job_id, "recover", self._run_recover_capture(job_id))
        return job

    async def _supervise(self, job_id: str) -> None:
        while True:
            await asyncio.sleep(0.25)
            job = self.jobs.get_job(job_id)
            if JobState(job.state) not in ACTIVE_JOB_STATES:
                return
            await self.transcript_hub.publish(job_id, {"type": "status", "state": job.state})

    def _start_failure_message(self, exc: Exception) -> str:
        message = str(exc).strip()
        if message:
            return message
        return "capture failed to start"

    async def _ensure_background_task(self, job_id: str, action: str, coroutine) -> None:
        key = (job_id, action)
        async with self._background_tasks_lock:
            existing = self._background_tasks.get(key)
            if existing is not None and not existing.done():
                coroutine.close()
                return
            task = asyncio.create_task(coroutine)
            self._background_tasks[key] = task

            def _cleanup(completed: asyncio.Task[None]) -> None:
                self._background_tasks.pop(key, None)
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    completed.result()

            task.add_done_callback(_cleanup)

    async def _run_stop_capture(self, job_id: str, *, skip_summary: bool = False) -> None:
        with contextlib.suppress(Exception):
            await self.stop_capture(job_id, skip_summary=skip_summary)

    async def _run_summary_rerun(self, job_id: str) -> None:
        try:
            summary_path = await self.transcript_prompts.rewrite_canonical_summary(job_id=job_id)
            self.jobs.update_runtime_fields(job_id, summary_path=summary_path)
            self._mark_summary_completed(job_id, include_legacy_keys=True)
        except Exception as exc:
            self._mark_summary_failed(job_id, exc, include_legacy_keys=True)

    async def _run_recover_capture(self, job_id: str) -> None:
        with contextlib.suppress(Exception):
            await self.recover_capture(job_id)

    async def recover_capture(self, job_id: str) -> JobResponse:
        job = self.jobs.get_job(job_id)
        if not self._can_recover_post_stop(job):
            raise RuntimeError("job is not recoverable")
        state = JobState(job.state)
        if state != JobState.COMPILING_TRANSCRIPT and state != JobState.RECOVERING:
            job = self.jobs.transition_job(job.id, JobState.RECOVERING, "recovery requested")
        if self._needs_transcript_compile(job):
            try:
                job = self._compile_transcript(job.id)
            except Exception as exc:
                failed_job = self.jobs.fail_job(job.id, "capture recovery failed", self._failure_message(exc))
                with contextlib.suppress(Exception):
                    await self.transcript_hub.publish(job.id, {"type": "status", "state": failed_job.state, "error": failed_job.error_message})
                return failed_job
        job = await self._finalize_post_stop(job.id, completion_reason="capture recovered")
        self.artifacts.write_metadata(job)
        with contextlib.suppress(Exception):
            if job.state == JobState.COMPLETED.value:
                await self.transcript_hub.publish(job.id, {"type": "complete", "state": job.state})
            else:
                await self.transcript_hub.publish(job.id, {"type": "status", "state": job.state})
        return job

    def _compile_transcript(self, job_id: str) -> JobResponse:
        job = self.jobs.get_job(job_id)
        if job.state != JobState.COMPILING_TRANSCRIPT.value:
            job = self.jobs.transition_job(job.id, JobState.COMPILING_TRANSCRIPT, "compiling transcript")
        paths = self.artifacts.job_paths(job.id)
        compiled = self.transcript_compiler.compile(
            job_id=job.id,
            title=job.title,
            started_at=job.started_at,
            stopped_at=job.stopped_at,
            model=job.deepgram_model,
            language=job.deepgram_language,
            events_path=paths.deepgram_events,
            output_dir=paths.root,
        )
        self.jobs.update_runtime_fields(
            job.id,
            transcript_text_path=str(compiled.text_path),
        )
        self.jobs.update_metadata(
            job.id,
            finalization_checkpoint="transcript_compiled",
            summary_status="pending",
            summary_error=None,
            summary_completed_at=None,
        )
        return self.jobs.get_job(job.id)

    async def _finalize_post_stop(self, job_id: str, *, completion_reason: str, skip_summary: bool = False) -> JobResponse:
        job = self.jobs.get_job(job_id)
        if skip_summary:
            self._mark_summary_skipped(job.id)
            self.jobs.update_metadata(job.id, finalization_checkpoint="summary_skipped")
            return self._complete_post_stop(job.id, completion_reason)
        if self._should_generate_summary(job):
            summary_succeeded, job = await self._run_summary_step(job.id)
            if not summary_succeeded:
                return self._complete_post_stop(job.id, completion_reason)
        return self._complete_post_stop(job.id, completion_reason)

    def _should_generate_summary(self, job: JobResponse) -> bool:
        return job.metadata_json.get(self.SUMMARY_STATUS_KEY) != "completed" or not self.artifacts.job_paths(job.id).summary.exists()

    async def _run_summary_step(self, job_id: str) -> tuple[bool, JobResponse]:
        job = self.jobs.get_job(job_id)
        if job.state != JobState.SUMMARIZING.value:
            job = self.jobs.transition_job(job.id, JobState.SUMMARIZING, "writing summary")
        self._mark_summary_running(job.id)
        try:
            summary_path = await self.transcript_prompts.rewrite_canonical_summary(job_id=job.id)
            self.jobs.update_runtime_fields(job.id, summary_path=summary_path)
        except Exception as exc:
            self._mark_summary_failed(job.id, exc)
            return False, self.jobs.get_job(job.id)
        self._mark_summary_completed(job.id)
        self.jobs.update_metadata(job.id, finalization_checkpoint="summary_completed")
        return True, self.jobs.get_job(job.id)

    def _complete_post_stop(self, job_id: str, reason: str) -> JobResponse:
        job = self.jobs.get_job(job_id)
        if job.state == JobState.COMPLETED.value:
            return job
        completed = self.jobs.transition_job(job.id, JobState.COMPLETED, reason)
        return self.jobs.update_runtime_fields(job.id, error_message=None, state=completed.state)

    def _can_recover_post_stop(self, job: JobResponse) -> bool:
        state = JobState(job.state)
        if state in {
            JobState.COMPILING_TRANSCRIPT,
            JobState.SUMMARIZING,
            JobState.RECOVERING,
        }:
            return True
        if state != JobState.FAILED:
            return False
        metadata = job.metadata_json
        checkpoint = metadata.get(self.FINALIZATION_CHECKPOINT_KEY)
        if checkpoint not in {"transcript_compiled", "summary_completed"}:
            return False
        return self._has_recovery_artifacts(job)

    def _needs_transcript_compile(self, job: JobResponse) -> bool:
        if JobState(job.state) == JobState.COMPILING_TRANSCRIPT:
            return True
        return not self._has_transcript_artifacts(job)

    def _has_recovery_artifacts(self, job: JobResponse) -> bool:
        if self._has_transcript_artifacts(job):
            return True
        return self.artifacts.job_paths(job.id).deepgram_events.exists()

    def _has_transcript_artifacts(self, job: JobResponse) -> bool:
        paths = self.artifacts.job_paths(job.id)
        return paths.transcript_markdown.exists() and paths.transcript_text.exists()

    def _mark_summary_running(self, job_id: str, *, include_legacy_keys: bool = False) -> None:
        updates: dict[str, Any] = {
            self.SUMMARY_STATUS_KEY: "running",
            self.SUMMARY_ERROR_KEY: None,
            self.SUMMARY_COMPLETED_AT_KEY: None,
        }
        if include_legacy_keys:
            updates.update(
                {
                    self.SUMMARY_RERUN_STATUS_KEY: "running",
                    self.SUMMARY_RERUN_ERROR_KEY: None,
                    self.SUMMARY_RERUN_COMPLETED_AT_KEY: None,
                }
            )
        self.jobs.update_metadata(job_id, **updates)

    def _mark_summary_completed(self, job_id: str, *, include_legacy_keys: bool = False) -> None:
        completed_at = isoformat(utcnow())
        updates: dict[str, Any] = {
            self.SUMMARY_STATUS_KEY: "completed",
            self.SUMMARY_ERROR_KEY: None,
            self.SUMMARY_COMPLETED_AT_KEY: completed_at,
        }
        if include_legacy_keys:
            updates.update(
                {
                    self.SUMMARY_RERUN_STATUS_KEY: "completed",
                    self.SUMMARY_RERUN_ERROR_KEY: None,
                    self.SUMMARY_RERUN_COMPLETED_AT_KEY: completed_at,
                }
            )
        self.jobs.update_metadata(job_id, **updates)

    def _mark_summary_failed(self, job_id: str, exc: Exception, *, include_legacy_keys: bool = False) -> None:
        completed_at = isoformat(utcnow())
        error = self._failure_message(exc)
        updates: dict[str, Any] = {
            self.SUMMARY_STATUS_KEY: "failed",
            self.SUMMARY_ERROR_KEY: error,
            self.SUMMARY_COMPLETED_AT_KEY: completed_at,
        }
        if include_legacy_keys:
            updates.update(
                {
                    self.SUMMARY_RERUN_STATUS_KEY: "failed",
                    self.SUMMARY_RERUN_ERROR_KEY: error,
                    self.SUMMARY_RERUN_COMPLETED_AT_KEY: completed_at,
                }
            )
        self.jobs.update_metadata(job_id, **updates)

    def _mark_summary_skipped(self, job_id: str) -> None:
        self.jobs.update_metadata(
            job_id,
            summary_status="skipped",
            summary_error=None,
            summary_completed_at=isoformat(utcnow()),
        )
